import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from dotenv import dotenv_values

# ============================================================
# CONFIGURATION
# ============================================================

if len(sys.argv) < 2:
    print(
        "Usage: python -m experimentos.crawler_keys <letter>",
        file=sys.stderr,
    )
    print(
        "Example: python -m experimentos.crawler_keys y",
        file=sys.stderr,
    )
    sys.exit(1)


TARGET_INPUT = sys.argv[1].lower().strip()

SPECIAL_ROOTS = {
    "hyphen": "-",
    "figure_dash": "‒",
}

TARGET_LETTER = SPECIAL_ROOTS.get(TARGET_INPUT, TARGET_INPUT)

if len(TARGET_LETTER) != 1:
    print(
        "ERROR: Please provide a single letter or special root.",
        file=sys.stderr,
    )
    print(
        "Examples: a, b, y, ñ, hyphen, figure_dash",
        file=sys.stderr,
    )
    sys.exit(1)


# ============================================================
# RAE CONFIGURATION
# ============================================================

config = dotenv_values(".env")

RAE_USER = config.get("RAE_USER")
RAE_PASSWORD = config.get("RAE_PASSWORD")

RAE_KEYS_URL = "https://dle.rae.es/data/keys"


# ============================================================
# PROJECT / DATABASE
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DB_DIR = PROJECT_ROOT / "datos" / "baseDeDatos"
DB_PATH = DB_DIR / "crawler.db"


# ============================================================
# TABLE NAME
# ============================================================
#
# The actual RAE root is used in the table name.
#
# Examples:
#
#   a           -> rae_keys_a
#   ñ           -> rae_keys_ñ
#   -           -> rae_keys_-
#   ‒           -> rae_keys_‒
#
# The table name is always quoted when used in SQL.
#
# ============================================================

TABLE_NAME = f"rae_keys_{TARGET_LETTER}"
METHOD = f"keys_prefix_tree_{TARGET_INPUT}"


# ============================================================
# CRAWLER SETTINGS
# ============================================================

MAX_PREFIX_LENGTH = 30

DEFAULT_WORKERS = 200

REQUEST_TIMEOUT = 15
MAX_RETRIES = 5

BATCH_SIZE = 100


# ============================================================
# IMPORTANT: /keys CHARACTER BRANCHES
# ============================================================
#
# Acute accents are NOT separate branches:
#
#   a / á
#   e / é
#   i / í
#   o / ó
#   u / ú
#
# But ñ and ü ARE kept distinct.
#
# This alphabet is used for deciding which child branches
# must be queried after a saturated /keys result.
#
# ============================================================

QUERY_ALPHABET = (
    "abcdefghijklmn"
    "ñ"
    "opqrstuvwxyz"
    "ü"
)


# ============================================================
# ACCENT NORMALIZATION
# ============================================================
#
# ONLY acute vowels are folded.
#
#   á -> a
#   é -> e
#   í -> i
#   ó -> o
#   ú -> u
#
# ñ remains ñ
# ü remains ü
#
# ============================================================

ACUTE_TRANSLATION = str.maketrans(
    "áéíóúÁÉÍÓÚ",
    "aeiouAEIOU",
)


def normalize(text):
    return text.translate(ACUTE_TRANSLATION).lower()


# ============================================================
# THREAD-LOCAL HTTP SESSION
# ============================================================

_thread_local = threading.local()


def get_session():
    session = getattr(_thread_local, "session", None)

    if session is None:

        session = requests.Session()

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

        adapter = requests.adapters.HTTPAdapter(
            pool_connections=50,
            pool_maxsize=50,
            max_retries=0,
        )

        session.mount("https://", adapter)

        _thread_local.session = session

    return session


# ============================================================
# DATABASE
# ============================================================

def create_database():

    DB_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    try:

        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        conn.execute(
            f'''
            CREATE TABLE IF NOT EXISTS "{TABLE_NAME}" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                rae_id TEXT,
                header TEXT,
                method TEXT NOT NULL,
                time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            '''
        )

        conn.execute(
            f'''
            CREATE INDEX IF NOT EXISTS
            "idx_{TABLE_NAME}_rae_id"
            ON "{TABLE_NAME}"(rae_id);
            '''
        )

        conn.commit()

    finally:
        conn.close()


def insert_keys(conn, keys):

    if not keys:
        return 0

    sql = f'''
        INSERT OR IGNORE INTO "{TABLE_NAME}"
        (key, method)
        VALUES (?, ?)
    '''

    entries = [
        (key, METHOD)
        for key in keys
    ]

    before = conn.total_changes

    conn.executemany(sql, entries)
    conn.commit()

    return conn.total_changes - before


# ============================================================
# API REQUEST
# ============================================================

def search_keys(prefix):

    session = get_session()

    params = {
        "q": prefix,
    }

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            response = session.get(
                RAE_KEYS_URL,
                params=params,
                auth=(RAE_USER, RAE_PASSWORD),
                timeout=REQUEST_TIMEOUT,
            )

            response.raise_for_status()

            data = response.json()

            if not isinstance(data, list):
                raise RuntimeError(
                    f"Unexpected response for {prefix!r}: "
                    f"{type(data).__name__}"
                )

            return data

        except Exception as exc:

            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"Failed {prefix!r}: {exc}"
                )

            time.sleep(
                0.3 * (2 ** (attempt - 1))
            )


# ============================================================
# SAFE CHILD-BRANCH CALCULATION
# ============================================================

def get_required_children(prefix, results):
    """
    Safe version.

    If /keys returns 10 results, the branch is saturated.
    We cannot safely infer the cutoff position from the order
    of the returned results, so query every possible child.

    If fewer than 10 results were returned, this function is
    never called.
    """

    if len(results) != 10:
        return []

    if len(prefix) >= MAX_PREFIX_LENGTH:
        return []

    return [
        prefix + char
        for char in QUERY_ALPHABET
    ]


# ============================================================
# PROCESS ONE PREFIX
# ============================================================

def process_prefix(prefix):

    results = search_keys(prefix)

    return prefix, results


# ============================================================
# MAIN CRAWLER
# ============================================================

def main():

    if not RAE_USER or not RAE_PASSWORD:

        print(
            "ERROR: Missing RAE_USER or RAE_PASSWORD in .env",
            file=sys.stderr,
        )

        sys.exit(1)

    create_database()

    conn = sqlite3.connect(DB_PATH)

    current_batch = [TARGET_LETTER]

    seen_prefixes = {
        TARGET_LETTER
    }

    total_requests = 0
    total_results = 0
    total_new_keys = 0
    total_errors = 0

    started = time.monotonic()

    print()
    print("=" * 60)
    print(
        f"RAE /KEYS PREFIX CRAWLER "
        f"('{TARGET_LETTER}' ROOT)"
    )
    print("=" * 60)
    print(f"Database:       {DB_PATH}")
    print(f"Table:          {TABLE_NAME}")
    print(f"Workers:        {DEFAULT_WORKERS}")
    print(f"Batch size:     {BATCH_SIZE}")
    print(f"Max prefix:     {MAX_PREFIX_LENGTH}")
    print("=" * 60)
    print()

    try:

        with ThreadPoolExecutor(
            max_workers=DEFAULT_WORKERS
        ) as executor:

            batch_num = 0

            while current_batch:

                batch_num += 1

                print()
                print("=" * 60)
                print(f"BATCH {batch_num}")
                print("=" * 60)
                print(
                    f"Prefixes submitted: "
                    f"{len(current_batch):,}"
                )

                batch_next = []

                batch_requests = 0
                batch_results = 0
                batch_new_prefixes = 0
                batch_errors = 0

                for chunk_start in range(
                    0,
                    len(current_batch),
                    BATCH_SIZE,
                ):

                    chunk = current_batch[
                        chunk_start:
                        chunk_start + BATCH_SIZE
                    ]

                    futures = {
                        executor.submit(
                            process_prefix,
                            prefix,
                        ): prefix
                        for prefix in chunk
                    }

                    completed = 0
                    total_in_chunk = len(futures)

                    db_keys = []

                    for future in as_completed(futures):

                        prefix = futures[future]

                        completed += 1

                        try:

                            returned_prefix, results = (
                                future.result()
                            )

                        except Exception as exc:

                            batch_errors += 1
                            total_errors += 1

                            print(
                                f"\n[ERROR] "
                                f"prefix={prefix!r}: "
                                f"{exc}",
                                file=sys.stderr,
                                flush=True,
                            )

                            if prefix not in batch_next:
                                batch_next.append(prefix)

                            continue

                        batch_requests += 1
                        total_requests += 1

                        result_count = len(results)

                        batch_results += result_count
                        total_results += result_count

                        for key in results:
                            db_keys.append(key)

                        if (
                            result_count == 10
                            and len(prefix) < MAX_PREFIX_LENGTH
                        ):

                            children = get_required_children(
                                prefix,
                                results,
                            )

                            for child in children:

                                if child not in seen_prefixes:

                                    seen_prefixes.add(child)

                                    batch_next.append(child)

                                    batch_new_prefixes += 1

                        print(
                            f"\r"
                            f"[{completed}/{total_in_chunk}] "
                            f"{returned_prefix:<20} "
                            f"results={result_count:<3} "
                            f"next={len(batch_next):<7}",
                            end="",
                            flush=True,
                        )

                    print()

                    new_keys = insert_keys(
                        conn,
                        db_keys,
                    )

                    total_new_keys += new_keys

                elapsed = (
                    time.monotonic() - started
                )

                req_per_sec = (
                    total_requests / elapsed
                    if elapsed > 0
                    else 0
                )

                print()
                print(
                    f"Requests this batch: "
                    f"{batch_requests:,}"
                )

                print(
                    f"Results this batch:  "
                    f"{batch_results:,}"
                )

                print(
                    f"New SQLite keys:     "
                    f"{total_new_keys:,}"
                )

                print(
                    f"New prefixes:        "
                    f"{batch_new_prefixes:,}"
                )

                print(
                    f"Errors:              "
                    f"{batch_errors:,}"
                )

                print(
                    f"Total prefixes seen: "
                    f"{len(seen_prefixes):,}"
                )

                print(
                    f"Total requests:      "
                    f"{total_requests:,}"
                )

                print(
                    f"Total results:       "
                    f"{total_results:,}"
                )

                print(
                    f"Requests/sec:        "
                    f"{req_per_sec:.2f}"
                )

                print(
                    f"Next batch size:     "
                    f"{len(batch_next):,}"
                )

                current_batch = batch_next

    except KeyboardInterrupt:

        print(
            "\n\n[INTERRUPT] "
            "Caught Ctrl+C. Safely shutting down..."
        )

    finally:

        conn.close()

        elapsed = time.monotonic() - started

        print()
        print("=" * 60)
        print("CRAWL FINISHED")
        print("=" * 60)
        print(
            f"Letter:       {TARGET_LETTER}"
        )
        print(
            f"Requests:     {total_requests:,}"
        )
        print(
            f"Results:      {total_results:,}"
        )
        print(
            f"Unique keys:  {total_new_keys:,}"
        )
        print(
            f"Prefixes:     {len(seen_prefixes):,}"
        )
        print(
            f"Errors:       {total_errors:,}"
        )
        print(
            f"Elapsed:      {elapsed:.1f} seconds"
        )
        print(
            f"Database:     {DB_PATH}"
        )
        print(
            f"Table:        {TABLE_NAME}"
        )
        print("=" * 60)
        print()


if __name__ == "__main__":
    main()