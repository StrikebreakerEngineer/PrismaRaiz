import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from dotenv import load_dotenv

DB_PATH = "datos/basededatos/crawler.db"

RAE_SEARCH_URL = "https://dle.rae.es/data/search"

DEFAULT_WORKERS = 200
BATCH_SIZE = 100

REQUEST_TIMEOUT = 15
MAX_RETRIES = 5

METHOD = "rae_search_exact"

load_dotenv()

RAE_USER = os.getenv("RAE_USER")
RAE_PASSWORD = os.getenv("RAE_PASSWORD")

if not RAE_USER or not RAE_PASSWORD:
    raise RuntimeError(
        "No se encontraron RAE_USER y RAE_PASSWORD en .env"
    )


# ---------------------------------------------------------
# Thread-local HTTP sessions
# ---------------------------------------------------------

thread_local = threading.local()


def get_session():
    if not hasattr(thread_local, "session"):
        session = requests.Session()

        session.auth = (RAE_USER, RAE_PASSWORD)

        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36"
            ),
            "Accept": "application/json",
            "Connection": "keep-alive",
        })

        thread_local.session = session

    return thread_local.session


# ---------------------------------------------------------
# Get all keys
# ---------------------------------------------------------

def get_all_keys(connection):
    cursor = connection.cursor()

    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name LIKE 'rae_keys_%'
        ORDER BY name
    """)

    tables = [row[0] for row in cursor.fetchall()]

    keys = set()

    for table in tables:
        cursor.execute(f'''
            SELECT key
            FROM "{table}"
        ''')

        for (key,) in cursor.fetchall():
            keys.add(key)

    return sorted(keys)


# ---------------------------------------------------------
# Search one key
# ---------------------------------------------------------

def search_key(key):
    session = get_session()

    params = {
        "w": key,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                RAE_SEARCH_URL,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )

            response.raise_for_status()

            data = response.json()

            results = data.get("res", [])

            entries = []

            for result in results:
                rae_id = result.get("id")

                if not rae_id:
                    continue

                entries.append({
                    "key": key,
                    "header": result.get("header"),
                    "rae_id": rae_id,
                    "grp": result.get("grp"),
                    "method": METHOD,
                })

            return entries

        except Exception as error:
            if attempt == MAX_RETRIES:
                print(
                    f"ERROR: {key!r} "
                    f"after {MAX_RETRIES} attempts: {error}"
                )
                return []

            time.sleep(0.5 * attempt)

    return []


# ---------------------------------------------------------
# Save batch
# ---------------------------------------------------------

def save_batch(connection, entries):
    if not entries:
        return 0

    cursor = connection.cursor()

    cursor.executemany("""
        INSERT OR IGNORE INTO rae_ids
            (key, header, rae_id, grp, method)
        VALUES
            (?, ?, ?, ?, ?)
    """, [
        (
            entry["key"],
            entry["header"],
            entry["rae_id"],
            entry["grp"],
            entry["method"],
        )
        for entry in entries
    ])

    connection.commit()

    return cursor.rowcount


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():
    start_time = time.time()

    connection = sqlite3.connect(DB_PATH)

    # Make sure the table has the expected structure.
    connection.execute("""
        CREATE TABLE IF NOT EXISTS rae_ids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            header TEXT,
            rae_id TEXT NOT NULL,
            grp INTEGER,
            method TEXT NOT NULL,
            time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(key, rae_id)
        )
    """)

    connection.commit()

    print("Leyendo keys...")

    keys = get_all_keys(connection)

    print(f"Keys encontradas: {len(keys):,}")

    if not keys:
        print("No hay keys para procesar.")
        connection.close()
        return

    print(f"Workers: {DEFAULT_WORKERS}")
    print(f"Batch:   {BATCH_SIZE}")
    print()
    print("Comenzando búsquedas...")
    print()

    total_processed = 0
    total_entries = 0
    total_inserted = 0

    batch = []

    with ThreadPoolExecutor(max_workers=DEFAULT_WORKERS) as executor:

        futures = {
            executor.submit(search_key, key): key
            for key in keys
        }

        for future in as_completed(futures):
            key = futures[future]

            try:
                entries = future.result()

            except Exception as error:
                print(f"ERROR procesando {key!r}: {error}")
                entries = []

            total_processed += 1
            total_entries += len(entries)

            batch.extend(entries)

            if len(batch) >= BATCH_SIZE:
                inserted = save_batch(connection, batch)
                total_inserted += inserted
                batch.clear()

            if total_processed % 1000 == 0:
                elapsed = time.time() - start_time
                rate = total_processed / elapsed if elapsed else 0

                print(
                    f"{total_processed:,}/{len(keys):,} "
                    f"| entries: {total_entries:,} "
                    f"| nuevos: {total_inserted:,} "
                    f"| {rate:.1f} keys/s"
                )

    # Save remaining entries
    if batch:
        inserted = save_batch(connection, batch)
        total_inserted += inserted
        batch.clear()

    elapsed = time.time() - start_time

    print()
    print("========================================")
    print("COMPLETADO")
    print("========================================")
    print(f"Keys procesadas:  {total_processed:,}")
    print(f"Entries recibidas: {total_entries:,}")
    print(f"Entries nuevas:   {total_inserted:,}")
    print(f"Tiempo:           {elapsed:.1f} segundos")

    if elapsed:
        print(f"Velocidad:        {total_processed / elapsed:.2f} keys/s")

    connection.close()


if __name__ == "__main__":
    main()