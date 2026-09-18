from __future__ import annotations

import os
import sys
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from dotenv import dotenv_values


# ============================================================
# CONFIGURACIÓN
# ============================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "datos", "basededatos", "crawler.db")

RAE_KEYS_URL = "https://dle.rae.es/data/keys"

MAX_WORKERS = 200
BATCH_SIZE = 100
TIMEOUT = 15
RETRIES = 5

# Incluimos letras normales, letras acentuadas, ñ y ü.
# La API puede tratar algunas de ellas como equivalentes,
# pero conservarlas aquí hace la exploración más exhaustiva.
ALPHABET = "aábcdeéfghiíjklmnñoópqrstuúüvwxyz"

TARGET_PREFIX = "-"

TABLE_NAME = "rae_keys_-"
METHOD = "keys_prefix_tree_hyphen"


# ============================================================
# AUTENTICACIÓN
# ============================================================

env = dotenv_values(os.path.join(BASE_DIR, ".env"))

RAE_USER = env.get("RAE_USER")
RAE_PASSWORD = env.get("RAE_PASSWORD")

if not RAE_USER or not RAE_PASSWORD:
    raise RuntimeError(
        "No se encontraron RAE_USER y RAE_PASSWORD en .env"
    )


# ============================================================
# THREAD-LOCAL SESSION
# ============================================================

_thread_local = threading.local()


def get_session():
    if not hasattr(_thread_local, "session"):
        session = requests.Session()

        session.auth = (RAE_USER, RAE_PASSWORD)

        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Connection": "keep-alive",
        })

        _thread_local.session = session

    return _thread_local.session


# ============================================================
# CONSULTAR /data/keys
# ============================================================

def query_prefix(prefix: str):
    session = get_session()

    last_error = None

    for attempt in range(1, RETRIES + 1):
        try:
            response = session.get(
                RAE_KEYS_URL,
                params={"q": prefix},
                timeout=TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()

                if not isinstance(data, list):
                    raise RuntimeError(
                        f"Respuesta inesperada para {prefix!r}: {data!r}"
                    )

                return {
                    "prefix": prefix,
                    "keys": data,
                    "count": len(data),
                    "status": 200,
                    "error": None,
                }

            last_error = (
                f"HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )

        except Exception as exc:
            last_error = repr(exc)

        if attempt < RETRIES:
            time.sleep(min(2 ** (attempt - 1), 8))

    return {
        "prefix": prefix,
        "keys": [],
        "count": -1,
        "status": None,
        "error": last_error,
    }


# ============================================================
# BASE DE DATOS
# ============================================================

def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def setup_database(connection):
    table = quote_identifier(TABLE_NAME)

    connection.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            method TEXT NOT NULL,
            time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()


def insert_keys(connection, keys):
    if not keys:
        return 0

    table = quote_identifier(TABLE_NAME)

    rows = [
        (key, METHOD)
        for key in keys
    ]

    connection.executemany(
        f"""
        INSERT OR IGNORE INTO {table}
            (key, method)
        VALUES (?, ?)
        """,
        rows,
    )

    connection.commit()

    return connection.total_changes


# ============================================================
# EXPLORACIÓN DEL ÁRBOL
# ============================================================

def child_prefixes(prefix: str):
    """
    Genera TODOS los posibles hijos del prefijo.

    Ejemplo:
        -a
    produce:
        -aa
        -aá
        -ab
        ...
        -az
    """

    return [
        prefix + char
        for char in ALPHABET
    ]


def crawl():
    connection = sqlite3.connect(DB_PATH)

    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")

    setup_database(connection)

    # --------------------------------------------------------
    # Estado
    # --------------------------------------------------------

    pending = {TARGET_PREFIX}
    visited = set()

    all_keys = set()

    total_requests = 0
    total_errors = 0
    saturated = 0
    completed = 0

    start_time = time.time()

    print()
    print("=" * 70)
    print("RAE /data/keys — BÚSQUEDA EXHAUSTIVA DEL PREFIJO '-'")
    print("=" * 70)
    print()
    print(f"Base de datos: {DB_PATH}")
    print(f"Tabla:         {TABLE_NAME}")
    print(f"Workers:       {MAX_WORKERS}")
    print(f"Alfabeto:      {len(ALPHABET)} caracteres")
    print()

    # --------------------------------------------------------
    # BFS por niveles
    # --------------------------------------------------------

    while pending:

        # Nunca volvemos a consultar el mismo prefijo.
        current_batch = [
            prefix
            for prefix in pending
            if prefix not in visited
        ]

        pending.clear()

        if not current_batch:
            break

        print(
            f"Nivel actual: {len(current_batch):,} prefijos"
        )

        results = []

        with ThreadPoolExecutor(
            max_workers=MAX_WORKERS
        ) as executor:

            futures = {
                executor.submit(
                    query_prefix,
                    prefix
                ): prefix
                for prefix in current_batch
            }

            for future in as_completed(futures):

                prefix = futures[future]

                try:
                    result = future.result()

                except Exception as exc:
                    result = {
                        "prefix": prefix,
                        "keys": [],
                        "count": -1,
                        "status": None,
                        "error": repr(exc),
                    }

                results.append(result)

        # ----------------------------------------------------
        # Procesar resultados
        # ----------------------------------------------------

        next_pending = set()

        for result in results:

            prefix = result["prefix"]

            if prefix in visited:
                continue

            visited.add(prefix)

            total_requests += 1

            count = result["count"]

            if count == -1:
                total_errors += 1

                print(
                    f"  ERROR {prefix!r}: "
                    f"{result['error']}"
                )

                # Lo volvemos a intentar en una futura pasada.
                # No lo marcamos como completo conceptualmente,
                # pero sí queda registrado para no hacer loops.
                continue

            keys = result["keys"]

            completed += 1

            # Guardamos absolutamente todos los resultados.
            for key in keys:
                if isinstance(key, str):
                    all_keys.add(key)

            # ------------------------------------------------
            # LA REGLA IMPORTANTE
            # ------------------------------------------------
            #
            # Si hay 10 resultados, la respuesta está saturada.
            #
            # NO usamos solamente los prefijos observados.
            #
            # Exploramos TODOS los posibles hijos.
            #
            if count == 10:
                saturated += 1

                for child in child_prefixes(prefix):
                    if child not in visited:
                        next_pending.add(child)

        # ----------------------------------------------------
        # Guardar en DB
        # ----------------------------------------------------

        if all_keys:
            inserted = insert_keys(
                connection,
                all_keys,
            )
        else:
            inserted = 0

        # No necesitamos conservar todas las claves en memoria
        # después de insertarlas.
        all_keys.clear()

        pending.update(next_pending)

        elapsed = time.time() - start_time

        print(
            f"  consultados: {completed:,} | "
            f"saturados: {saturated:,} | "
            f"siguiente nivel: {len(pending):,} | "
            f"errores: {total_errors:,} | "
            f"tiempo: {elapsed:.1f}s"
        )

        print()

    # ========================================================
    # FINAL
    # ========================================================

    elapsed = time.time() - start_time

    table = quote_identifier(TABLE_NAME)

    row = connection.execute(
        f"SELECT COUNT(*) FROM {table}"
    ).fetchone()

    total_keys = row[0]

    connection.close()

    print("=" * 70)
    print("FINALIZADO")
    print("=" * 70)
    print()
    print(f"Prefijos consultados: {total_requests:,}")
    print(f"Prefijos saturados:   {saturated:,}")
    print(f"Errores:              {total_errors:,}")
    print(f"Claves en tabla:      {total_keys:,}")
    print(f"Tiempo:               {elapsed:.1f} segundos")
    print()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    crawl()