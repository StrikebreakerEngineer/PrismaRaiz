import argparse
import html
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from dotenv import dotenv_values

'aábcdeéfghiíjklmnñoópqrstuúüvwxyz-'
# ============================================================
# CONFIGURATION
# ============================================================

# Put your RAE credentials here.
config = dotenv_values(".env")
RAE_USER = config.get("RAE_USER")
RAE_PASSWORD = config.get("RAE_PASSWORD")

RAE_SEARCH_URL = "https://dle.rae.es/data/search"

# Put the path to your existing SQLite database here.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DB_PATH = (
    PROJECT_ROOT
    / "datos"
    / "baseDeDatos"
    / "test.db"
)

# SQLite table created by this scraper.
TABLE_NAME = "rae_discovered_2"

# Identifies where each record came from.
METHOD = "lowercase_tree_search"

# Lowercase Spanish alphabet.
ALPHABET = "aábcdeéfghiíjklmnñoópqrstuúüvwxyz"

# Safety valve only.
#
# This is NOT used to determine whether a prefix is complete.
# It simply prevents an accidental infinite tree.
MAX_PREFIX_LENGTH = 40

# HTTP settings.
DEFAULT_WORKERS = 8
DEFAULT_BATCH_SIZE = 100
REQUEST_TIMEOUT = 20
MAX_RETRIES = 8


# ============================================================
# SQLITE
# ============================================================

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL,
    rae_id TEXT NOT NULL UNIQUE,
    method TEXT NOT NULL,
    time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_INDEX_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_rae_id
ON {TABLE_NAME}(rae_id);
"""

CREATE_METHOD_INDEX_SQL = f"""
CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_method
ON {TABLE_NAME}(method);
"""


def create_database():
    """Create the discovery table and indexes."""

    conn = sqlite3.connect(DB_PATH)

    try:
        # WAL allows readers to continue while we write.
        conn.execute("PRAGMA journal_mode=WAL")

        # Good performance while retaining reasonable durability.
        conn.execute("PRAGMA synchronous=NORMAL")

        conn.execute(CREATE_TABLE_SQL)
        conn.execute(CREATE_INDEX_SQL)
        conn.execute(CREATE_METHOD_INDEX_SQL)

        conn.commit()

    finally:
        conn.close()


def get_existing_count():
    """Return the number of IDs already in the table."""

    conn = sqlite3.connect(DB_PATH)

    try:
        row = conn.execute(
            f"SELECT COUNT(*) FROM {TABLE_NAME}"
        ).fetchone()

        return row[0]

    finally:
        conn.close()


def insert_entries(conn, entries):
    """
    Insert a batch of entries.

    The RAE ID is UNIQUE, so duplicate discoveries are ignored.

    SQLite supplies the timestamp through DEFAULT CURRENT_TIMESTAMP.
    """

    if not entries:
        return 0

    sql = f"""
        INSERT OR IGNORE INTO {TABLE_NAME}
        (word, rae_id, method)
        VALUES (?, ?, ?)
    """

    before = conn.total_changes

    conn.executemany(
        sql,
        entries,
    )

    conn.commit()

    return conn.total_changes - before


# ============================================================
# HTML / WORD CLEANING
# ============================================================

TAG_RE = re.compile(r"<[^>]+>")


def clean_header(header):
    """
    Turn the RAE header into plain text.

    Examples:

        <i>eagle</i>  -> eagle
        ebriedad      -> ebriedad
        e<sup>1</sup> -> e1
    """

    if not header:
        return ""

    header = html.unescape(header)

    header = TAG_RE.sub("", header)

    return header.strip()


# ============================================================
# HTTP
# ============================================================

_thread_local = None


def get_session():
    """
    Give every worker thread its own requests.Session.

    Sessions reuse TCP connections, which makes a substantial
    difference when making many requests to the same host.
    """

    global _thread_local

    if _thread_local is None:
        import threading
        _thread_local = threading.local()

    session = getattr(
        _thread_local,
        "session",
        None,
    )

    if session is None:

        session = requests.Session()

        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/140.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Connection": "keep-alive",
        })

        # Give urllib3 a larger connection pool.
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=100,
            pool_maxsize=100,
            max_retries=0,
        )

        session.mount(
            "https://",
            adapter,
        )

        session.mount(
            "http://",
            adapter,
        )

        _thread_local.session = session

    return session


def search_prefix(prefix):
    """
    Query the RAE prefix-search endpoint.

        /data/search?w=<prefix>&m=31&f=1&t=200

    IMPORTANT:

    We do NOT interpret the number of returned results as
    indicating completeness.

    Any non-empty response causes the caller to investigate
    every possible child prefix.
    """

    session = get_session()

    params = {
        "w": prefix,
        "m": 31,
        "f": 1,
        "t": 200,
    }

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            response = session.get(
                RAE_SEARCH_URL,
                params=params,
                auth=(RAE_USER, RAE_PASSWORD),
                timeout=REQUEST_TIMEOUT,
            )

            response.raise_for_status()

            data = response.json()

            return data.get("res", [])

        except Exception as exc:

            last_error = exc

            if attempt == MAX_RETRIES:
                break

            delay = min(
                20,
                0.5 * (2 ** (attempt - 1)),
            )

            print(
                f"\n[RETRY] prefix={prefix!r} "
                f"attempt={attempt}/{MAX_RETRIES} "
                f"error={exc} "
                f"sleep={delay:.1f}s",
                file=sys.stderr,
                flush=True,
            )

            time.sleep(delay)

    raise RuntimeError(
        f"Search permanently failed for "
        f"{prefix!r}: {last_error}"
    )


# ============================================================
# TREE
# ============================================================

def get_children(prefix):
    """
    Return every possible child of a prefix.

    Example:

        eb

    becomes:

        eba
        ebá
        ebb
        ebc
        ...
        eb-
    """

    if len(prefix) >= MAX_PREFIX_LENGTH:
        return []

    return [
        prefix + character
        for character in ALPHABET
    ]


# ============================================================
# WORKER FUNCTION
# ============================================================

def process_prefix(prefix):
    """
    Execute one RAE search.

    Returns:

        prefix
        results
        children

    Children are created whenever results are non-empty.
    """

    results = search_prefix(prefix)

    if not results:
        return (
            prefix,
            results,
            [],
        )

    children = get_children(prefix)

    return (
        prefix,
        results,
        children,
    )


# ============================================================
# CRAWLER
# ============================================================

class LowercaseCrawler:

    def __init__(
        self,
        workers,
        batch_size,
    ):
        self.workers = workers
        self.batch_size = batch_size

        # Prefixes we have already scheduled.
        self.seen_prefixes = set()

        # Statistics.
        self.total_requests = 0
        self.total_results = 0
        self.total_new_ids = 0

        self.started = time.monotonic()

    def initial_prefixes(self):
        """
        Start with every character in the alphabet.

        This means the first batch includes:

            a
            á
            b
            c
            ...
            z
            -
        """

        prefixes = []

        for character in ALPHABET:

            if character not in self.seen_prefixes:

                self.seen_prefixes.add(
                    character
                )

                prefixes.append(
                    character
                )

        return prefixes

    def crawl(self, conn):

        current_batch = self.initial_prefixes()

        batch_number = 0

        with ThreadPoolExecutor(
            max_workers=self.workers
        ) as executor:

            while current_batch:

                batch_number += 1

                print(
                    "\n"
                    "================================================",
                    flush=True,
                )

                print(
                    f"BATCH {batch_number}",
                    flush=True,
                )

                print(
                    "================================================",
                    flush=True,
                )

                print(
                    f"Prefixes submitted: "
                    f"{len(current_batch):,}",
                    flush=True,
                )

                print(
                    f"Workers: {self.workers}",
                    flush=True,
                )

                # ------------------------------------------------
                # Submit this batch.
                # ------------------------------------------------

                futures = {
                    executor.submit(
                        process_prefix,
                        prefix,
                    ): prefix
                    for prefix in current_batch
                }

                next_batch = []

                db_entries = []

                batch_requests = 0
                batch_results = 0
                batch_new_prefixes = 0
                batch_errors = 0

                # ------------------------------------------------
                # Process results as soon as workers finish.
                # ------------------------------------------------

                for future in as_completed(futures):

                    prefix = futures[future]

                    try:

                        (
                            returned_prefix,
                            results,
                            children,
                        ) = future.result()

                    except Exception as exc:

                        batch_errors += 1

                        print(
                            f"\n[ERROR] "
                            f"prefix={prefix!r}: {exc}",
                            file=sys.stderr,
                            flush=True,
                        )

                        # Do NOT silently lose a failed branch.
                        #
                        # Put it into the next batch for retry.
                        if prefix not in next_batch:
                            next_batch.append(prefix)

                        continue

                    batch_requests += 1
                    self.total_requests += 1

                    result_count = len(results)

                    batch_results += result_count
                    self.total_results += result_count

                    # ------------------------------------------------
                    # Prepare SQLite rows.
                    # ------------------------------------------------

                    for result in results:

                        rae_id = result.get("id")

                        if not rae_id:
                            continue

                        word = clean_header(
                            result.get(
                                "header",
                                "",
                            )
                        )

                        db_entries.append(
                            (
                                word,
                                rae_id,
                                METHOD,
                            )
                        )

                    # ------------------------------------------------
                    # COMPLETENESS RULE
                    # ------------------------------------------------
                    #
                    # This is the key behavior.
                    #
                    # We don't care if RAE returned:
                    #
                    #     1 result
                    #     15 results
                    #     40 results
                    #     200 results
                    #
                    # If it returned ANYTHING, we investigate every
                    # possible child.
                    # ------------------------------------------------

                    if results:

                        for child in children:

                            if child not in self.seen_prefixes:

                                self.seen_prefixes.add(
                                    child
                                )

                                next_batch.append(
                                    child
                                )

                                batch_new_prefixes += 1

                    # ------------------------------------------------
                    # Live progress.
                    # ------------------------------------------------

                    print(
                        f"\r"
                        f"{returned_prefix:<20} "
                        f"results={result_count:<4} "
                        f"next={len(next_batch):<7}",
                        end="",
                        flush=True,
                    )

                print()

                # ------------------------------------------------
                # One SQLite write for the whole batch.
                # ------------------------------------------------

                new_ids = insert_entries(
                    conn,
                    db_entries,
                )

                self.total_new_ids += new_ids

                # ------------------------------------------------
                # Statistics.
                # ------------------------------------------------

                elapsed = (
                    time.monotonic()
                    - self.started
                )

                requests_per_second = (
                    self.total_requests / elapsed
                    if elapsed > 0
                    else 0
                )

                print(
                    f"Requests this batch: "
                    f"{batch_requests:,}",
                    flush=True,
                )

                print(
                    f"Results this batch:  "
                    f"{batch_results:,}",
                    flush=True,
                )

                print(
                    f"New SQLite IDs:      "
                    f"{new_ids:,}",
                    flush=True,
                )

                print(
                    f"New prefixes:        "
                    f"{batch_new_prefixes:,}",
                    flush=True,
                )

                print(
                    f"Errors/retries:      "
                    f"{batch_errors:,}",
                    flush=True,
                )

                print(
                    f"Total prefixes seen: "
                    f"{len(self.seen_prefixes):,}",
                    flush=True,
                )

                print(
                    f"Total requests:      "
                    f"{self.total_requests:,}",
                    flush=True,
                )

                print(
                    f"Total unique IDs:    "
                    f"{self.total_new_ids:,}",
                    flush=True,
                )

                print(
                    f"Requests/sec:        "
                    f"{requests_per_second:.2f}",
                    flush=True,
                )

                print(
                    f"Next batch size:     "
                    f"{len(next_batch):,}",
                    flush=True,
                )

                # ------------------------------------------------
                # Move to next generation.
                # ------------------------------------------------

                current_batch = next_batch

        # --------------------------------------------------------
        # COMPLETE
        # --------------------------------------------------------

        elapsed = (
            time.monotonic()
            - self.started
        )

        print(
            "\n"
            "================================================",
            flush=True,
        )

        print(
            "LOWERCASE TREE COMPLETE",
            flush=True,
        )

        print(
            "================================================",
            flush=True,
        )

        print(
            f"Total requests:  "
            f"{self.total_requests:,}",
            flush=True,
        )

        print(
            f"Total API results:"
            f" {self.total_results:,}",
            flush=True,
        )

        print(
            f"New SQLite IDs:  "
            f"{self.total_new_ids:,}",
            flush=True,
        )

        print(
            f"Prefixes visited: "
            f"{len(self.seen_prefixes):,}",
            flush=True,
        )

        print(
            f"Elapsed:          "
            f"{elapsed:.1f}s",
            flush=True,
        )

        if elapsed > 0:

            print(
                f"Requests/sec:     "
                f"{self.total_requests / elapsed:.2f}",
                flush=True,
            )

        print(
            "================================================",
            flush=True,
        )


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "High-throughput exhaustive "
            "lowercase RAE prefix crawler"
        )
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=(
            "Number of concurrent HTTP workers "
            f"(default: {DEFAULT_WORKERS})"
        ),
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=(
            "Maximum prefixes per batch "
            f"(default: {DEFAULT_BATCH_SIZE})"
        ),
    )

    args = parser.parse_args()

    if args.workers < 1:
        parser.error(
            "--workers must be >= 1"
        )

    if args.batch_size < 1:
        parser.error(
            "--batch-size must be >= 1"
        )

    # --------------------------------------------------------
    # Validate configuration.
    # --------------------------------------------------------

    if (
        not RAE_USER
        or RAE_USER == "YOUR_USERNAME"
    ):
        print(
            "ERROR: Set RAE_USER at the top of the script.",
            file=sys.stderr,
        )

        sys.exit(1)

    if (
        not RAE_PASSWORD
        or RAE_PASSWORD == "YOUR_PASSWORD"
    ):
        print(
            "ERROR: Set RAE_PASSWORD at the top of the script.",
            file=sys.stderr,
        )

        sys.exit(1)

    if not DB_PATH:
        print(
            "ERROR: Set DB_PATH at the top of the script.",
            file=sys.stderr,
        )

        sys.exit(1)

    print(
        "\n"
        "================================================",
        flush=True,
    )

    print(
        "RAE LOWERCASE EXHAUSTIVE TREE",
        flush=True,
    )

    print(
        "================================================",
        flush=True,
    )

    print(
        f"Database:          {DB_PATH}",
        flush=True,
    )

    print(
        f"Table:             {TABLE_NAME}",
        flush=True,
    )

    print(
        f"Workers:           {args.workers}",
        flush=True,
    )

    print(
        f"Batch size:        {args.batch_size}",
        flush=True,
    )

    print(
        f"Alphabet length:   {len(ALPHABET)}",
        flush=True,
    )

    print(
        f"Max prefix length: {MAX_PREFIX_LENGTH}",
        flush=True,
    )

    print(
        "Result cap logic:  DISABLED",
        flush=True,
    )

    print(
        "================================================\n",
        flush=True,
    )

    # --------------------------------------------------------
    # Database setup.
    # --------------------------------------------------------

    create_database()

    existing = get_existing_count()

    print(
        f"Existing IDs: {existing:,}",
        flush=True,
    )

    # --------------------------------------------------------
    # Keep ONE SQLite writer.
    # HTTP requests happen concurrently, but SQLite writes
    # happen from this main thread only.
    # --------------------------------------------------------

    conn = sqlite3.connect(
        DB_PATH,
        timeout=60,
    )

    try:

        conn.execute(
            "PRAGMA journal_mode=WAL"
        )

        conn.execute(
            "PRAGMA synchronous=NORMAL"
        )

        crawler = LowercaseCrawler(
            workers=args.workers,
            batch_size=args.batch_size,
        )

        crawler.crawl(conn)

    finally:

        conn.close()


if __name__ == "__main__":
    main()