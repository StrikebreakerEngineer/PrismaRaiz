import html
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from dotenv import dotenv_values

# ============================================================
# CONFIGURATION
# ============================================================

config = dotenv_values(".env")
RAE_USER = config.get("RAE_USER")
RAE_PASSWORD = config.get("RAE_PASSWORD")

RAE_SEARCH_URL = "https://dle.rae.es/data/search"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "datos" / "baseDeDatos" / "test_a.db"
TABLE_NAME = "rae_test_a"
METHOD = "prefix_tree_a_test"

# Lowercase Spanish alphabet
ALPHABET = "aábcdeéfghiíjklmnñoópqrstuúüvwxyz-"
MAX_PREFIX_LENGTH = 30
DEFAULT_WORKERS = 100
REQUEST_TIMEOUT = 15
MAX_RETRIES = 5

TAG_RE = re.compile(r"<[^>]+>")


def clean_header(header):
    if not header:
        return ""
    return TAG_RE.sub("", html.unescape(header)).strip()


def create_database():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL,
                rae_id TEXT NOT NULL UNIQUE,
                method TEXT NOT NULL,
                time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_rae_id ON {TABLE_NAME}(rae_id);")
        conn.commit()
    finally:
        conn.close()


def insert_entries(conn, entries):
    if not entries:
        return 0
    sql = f"INSERT OR IGNORE INTO {TABLE_NAME} (word, rae_id, method) VALUES (?, ?, ?)"
    before = conn.total_changes
    conn.executemany(sql, entries)
    conn.commit()
    return conn.total_changes - before


_thread_local = None

def get_session():
    global _thread_local
    if _thread_local is None:
        import threading
        _thread_local = threading.local()

    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Connection": "keep-alive",
        })
        adapter = requests.adapters.HTTPAdapter(pool_connections=50, pool_maxsize=50, max_retries=0)
        session.mount("https://", adapter)
        _thread_local.session = session
    return session


def search_prefix(prefix):
    session = get_session()
    params = {"w": prefix, "m": 31, "f": 1, "t": 200}
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                RAE_SEARCH_URL,
                params=params,
                auth=(RAE_USER, RAE_PASSWORD),
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response.json().get("res", [])
        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise RuntimeError(f"Failed {prefix!r}: {exc}")
            time.sleep(0.3 * (2 ** (attempt - 1)))


def process_prefix(prefix):
    results = search_prefix(prefix)
    if not results:
        return prefix, [], []
    
    children = []
    if len(prefix) < MAX_PREFIX_LENGTH:
        children = [prefix + char for char in ALPHABET]
        
    return prefix, results, children


def main():
    if not RAE_USER or not RAE_PASSWORD:
        print("ERROR: Missing RAE credentials in .env", file=sys.stderr)
        sys.exit(1)

    create_database()
    conn = sqlite3.connect(DB_PATH)

    current_batch = ["a"]
    seen_prefixes = {"a"}
    total_requests = 0
    total_results = 0
    total_new_ids = 0
    started = time.monotonic()

    print(f"\n================================================", flush=True)
    print(f"RAE PREFIX CRAWLER TEST ('a' root)", flush=True)
    print(f"================================================", flush=True)
    print(f"Workers: {DEFAULT_WORKERS}", flush=True)
    print(f"Database: {DB_PATH}", flush=True)
    print(f"================================================\n", flush=True)

    try:
        with ThreadPoolExecutor(max_workers=DEFAULT_WORKERS) as executor:
            batch_num = 0
            while current_batch:
                batch_num += 1

                print(f"\n================================================", flush=True)
                print(f"BATCH {batch_num}", flush=True)
                print(f"================================================", flush=True)
                print(f"Prefixes submitted: {len(current_batch):,}", flush=True)
                print(f"Workers: {DEFAULT_WORKERS}", flush=True)

                futures = {executor.submit(process_prefix, p): p for p in current_batch}
                next_batch = []
                db_entries = []

                batch_requests = 0
                batch_results = 0
                batch_new_prefixes = 0
                batch_errors = 0
                completed_count = 0
                total_in_batch = len(futures)

                for future in as_completed(futures):
                    prefix = futures[future]
                    completed_count += 1
                    try:
                        returned_prefix, results, children = future.result()
                    except Exception as exc:
                        batch_errors += 1
                        print(f"\n[ERROR] prefix={prefix!r}: {exc}", file=sys.stderr, flush=True)
                        if prefix not in next_batch:
                            next_batch.append(prefix)
                        continue

                    batch_requests += 1
                    total_requests += 1
                    result_count = len(results)
                    batch_results += result_count
                    total_results += result_count

                    for r in results:
                        rae_id = r.get("id")
                        if rae_id:
                            word = clean_header(r.get("header", ""))
                            db_entries.append((word, rae_id, METHOD))

                    if results:
                        for child in children:
                            if child not in seen_prefixes:
                                seen_prefixes.add(child)
                                next_batch.append(child)
                                batch_new_prefixes += 1

                    print(
                        f"\r[{completed_count}/{total_in_batch}] "
                        f"{returned_prefix:<18} "
                        f"results={result_count:<4} "
                        f"next={len(next_batch):<7}",
                        end="",
                        flush=True,
                    )

                print()

                new_ids = insert_entries(conn, db_entries)
                total_new_ids += new_ids

                elapsed = time.monotonic() - started
                req_per_sec = total_requests / elapsed if elapsed > 0 else 0

                print(f"Requests this batch: {batch_requests:,}", flush=True)
                print(f"Results this batch:  {batch_results:,}", flush=True)
                print(f"New SQLite IDs:      {new_ids:,}", flush=True)
                print(f"New prefixes:        {batch_new_prefixes:,}", flush=True)
                print(f"Errors/retries:      {batch_errors:,}", flush=True)
                print(f"Total prefixes seen: {len(seen_prefixes):,}", flush=True)
                print(f"Total requests:      {total_requests:,}", flush=True)
                print(f"Total unique IDs:    {total_new_ids:,}", flush=True)
                print(f"Requests/sec:        {req_per_sec:.2f}", flush=True)
                print(f"Next batch size:     {len(next_batch):,}", flush=True)

                current_batch = next_batch

    except KeyboardInterrupt:
        print("\n\n[INTERRUPT] Caught Ctrl+C. Safely shutting down...", flush=True)
    finally:
        conn.close()
        print(f"\nCompleted. Total requests: {total_requests:,}, Unique IDs saved: {total_new_ids:,}\n", flush=True)


if __name__ == "__main__":
    main()