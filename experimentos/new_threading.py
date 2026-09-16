import argparse
import html
import re
import sqlite3
import sys
import time
import threading
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

DB_PATH = (
    PROJECT_ROOT
    / "datos"
    / "baseDeDatos"
    / "new.db"
)

TABLE_NAME = "rae_discovered_frontier"

METHOD = "lexical_frontier_search"

# IMPORTANT:
# This must represent the actual characters that we are willing
# to append to a prefix.
#
# The API is lexicographically ordered, so this alphabet is used
# to enumerate the children of a prefix in lexical order.
ALPHABET = "aábcdeéfghiíjklmnñoópqrstuúüvwxyz-"

MAX_PREFIX_LENGTH = 40

DEFAULT_WORKERS = 50
DEFAULT_BATCH_SIZE = 1000

REQUEST_TIMEOUT = 20
MAX_RETRIES = 8

API_REQUEST_LIMIT = 200


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
    conn = sqlite3.connect(DB_PATH)

    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        conn.execute(CREATE_TABLE_SQL)
        conn.execute(CREATE_INDEX_SQL)
        conn.execute(CREATE_METHOD_INDEX_SQL)

        conn.commit()

    finally:
        conn.close()


def get_existing_count():
    conn = sqlite3.connect(DB_PATH)

    try:
        row = conn.execute(
            f"SELECT COUNT(*) FROM {TABLE_NAME}"
        ).fetchone()

        return row[0]

    finally:
        conn.close()


def insert_entries(conn, entries):
    if not entries:
        return 0

    sql = f"""
        INSERT OR IGNORE INTO {TABLE_NAME}
        (word, rae_id, method)
        VALUES (?, ?, ?)
    """

    before = conn.total_changes

    conn.executemany(sql, entries)
    conn.commit()

    return conn.total_changes - before


# ============================================================
# TEXT HANDLING
# ============================================================

TAG_RE = re.compile(r"<[^>]+>")


def clean_header(header):
    """
    Convert the RAE HTML header into display text.

    Example:

        cabalgar<sup>1</sup>

    becomes:

        cabalgar1
    """

    if not header:
        return ""

    header = html.unescape(header)
    header = TAG_RE.sub("", header)

    return header.strip()


def traversal_word(header):
    """
    Return the lexical portion of an RAE header for traversal.

    Examples:

        cabalero, ra
            -> cabalero

        cabalgar1
            -> cabalgar

        cabalgar2
            -> cabalgar

    IMPORTANT:

    This function is ONLY used to identify the lexical headword.

    It must NOT change the actual character sequence in arbitrary
    ways.

    In particular, we do NOT normalize accents and we do NOT
    remove characters from the middle of the word.
    """

    value = clean_header(header)

    if not value:
        return ""

    # Remove the comma qualification.
    value = value.split(",", 1)[0].strip()

    # Remove trailing numeric markers resulting from <sup>.
    value = re.sub(r"\d+$", "", value)

    return value


def lexical_startswith(word, prefix):
    """
    Exact prefix test.

    We deliberately do NOT use accent stripping, Unicode
    normalization, punctuation removal, or other transformations.

    The API's lexical ordering is the ordering we are traversing.
    """

    if not word or not prefix:
        return False

    return word.startswith(prefix)


# ============================================================
# HTTP
# ============================================================

_thread_local = threading.local()


def get_session():
    session = getattr(
        _thread_local,
        "session",
        None,
    )

    if session is not None:
        return session

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

    adapter = requests.adapters.HTTPAdapter(
        pool_connections=100,
        pool_maxsize=100,
        max_retries=0,
    )

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    _thread_local.session = session

    return session


def search_prefix(prefix):
    """
    Query RAE.

    The API response is assumed to be lexicographically ordered.

    We DO NOT interpret len(results) as completeness.
    """

    session = get_session()

    params = {
        "w": prefix,
        "m": 31,
        "f": 1,
        "t": API_REQUEST_LIMIT,
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
                f"\n[RETRY] "
                f"{prefix!r} "
                f"{attempt}/{MAX_RETRIES} "
                f"{exc} "
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
# LEXICAL FRONTIER
# ============================================================

def get_children(prefix):
    """
    Return every immediate lexical child.

    Example:

        cab

    produces:

        caba
        cabá
        cabb
        cabc
        ...
    """

    if len(prefix) >= MAX_PREFIX_LENGTH:
        return []

    return [
        prefix + character
        for character in ALPHABET
    ]


def frontier_index(prefix, last_header):
    """
    Determine the character position at which the final returned
    headword leaves `prefix`.

    Example:

        prefix:
            cab

        final result:
            cabalístico

        next character:
            a

        therefore:

            frontier_index = index("a")
            = 0
    """

    word = traversal_word(last_header)

    if not word:
        return None

    if not word.startswith(prefix):
        return None

    if len(word) <= len(prefix):
        return None

    next_character = word[len(prefix)]

    try:
        return ALPHABET.index(next_character)

    except ValueError:
        return None


def calculate_next_prefixes(prefix, results):
    """
    Calculate the unresolved lexical branches.

    This relies directly on the fact that RAE returns the results
    in lexical order.

    Suppose:

        search("cab")

    returns through:

        cabalístico

    Then the final result is inside the `caba` branch.

    Therefore:

        caba
        cabá
        cabb
        ...

    are the branches that can still contain results after the
    returned lexical window.

    Branches before `caba` have already been passed by the
    parent's ordered result stream.

    IMPORTANT:

    We never construct a child from a normalized/modified version
    of the prefix. The child is ALWAYS:

        prefix + one actual character
    """

    if not results:
        return []

    if len(prefix) >= MAX_PREFIX_LENGTH:
        return []

    last_header = results[-1].get("header", "")

    index = frontier_index(
        prefix,
        last_header,
    )

    # Defensive fallback.
    #
    # If the API returns something that does not begin with the
    # queried prefix, we cannot safely infer a lexical frontier.
    #
    # In that case we search every legitimate immediate child.
    if index is None:
        return get_children(prefix)

    return [
        prefix + character
        for character in ALPHABET[index:]
    ]


# ============================================================
# WORKER
# ============================================================

def process_prefix(prefix):
    results = search_prefix(prefix)

    next_prefixes = calculate_next_prefixes(
        prefix,
        results,
    )

    return (
        prefix,
        results,
        next_prefixes,
    )


# ============================================================
# CRAWLER
# ============================================================

class LexicalFrontierCrawler:

    def __init__(
        self,
        workers,
        batch_size,
    ):
        self.workers = workers
        self.batch_size = batch_size

        self.seen_prefixes = set()

        self.total_requests = 0
        self.total_results = 0
        self.total_new_ids = 0

        self.started = time.monotonic()

    # --------------------------------------------------------
    # Initial prefixes
    # --------------------------------------------------------

    def initial_prefixes(self):
        prefixes = []

        for character in ALPHABET:

            if character in self.seen_prefixes:
                continue

            self.seen_prefixes.add(character)

            prefixes.append(character)

        return prefixes

    # --------------------------------------------------------
    # Process batch
    # --------------------------------------------------------

    def process_batch(
        self,
        executor,
        current_batch,
        conn,
        batch_number,
    ):

        print()
        print("=" * 56)
        print(f"BATCH {batch_number}")
        print("=" * 56)

        print(
            f"Prefixes submitted: {len(current_batch):,}",
            flush=True,
        )

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

        for future in as_completed(futures):

            prefix = futures[future]

            try:

                (
                    returned_prefix,
                    results,
                    next_prefixes,
                ) = future.result()

            except Exception as exc:

                batch_errors += 1

                print(
                    f"\n[ERROR] "
                    f"prefix={prefix!r}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )

                # Put failed prefixes back into the queue.
                if prefix not in next_batch:
                    next_batch.append(prefix)

                continue

            batch_requests += 1
            self.total_requests += 1

            result_count = len(results)

            batch_results += result_count
            self.total_results += result_count

            # ------------------------------------------------
            # Store all returned entries.
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
            # Queue unresolved lexical branches.
            # ------------------------------------------------

            for child in next_prefixes:

                if child in self.seen_prefixes:
                    continue

                self.seen_prefixes.add(child)

                next_batch.append(child)

                batch_new_prefixes += 1

            # ------------------------------------------------
            # Progress display.
            # ------------------------------------------------

            last_word = ""

            if results:

                last_word = clean_header(
                    results[-1].get(
                        "header",
                        "",
                    )
                )

            print(
                f"\r"
                f"{returned_prefix:<20} "
                f"results={result_count:<4} "
                f"frontier={last_word[:25]:<25} "
                f"next={len(next_batch):<7}",
                end="",
                flush=True,
            )

        print()

        # ----------------------------------------------------
        # One SQLite writer.
        # ----------------------------------------------------

        new_ids = insert_entries(
            conn,
            db_entries,
        )

        self.total_new_ids += new_ids

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
            f"Requests this batch: {batch_requests:,}",
            flush=True,
        )

        print(
            f"Results this batch:  {batch_results:,}",
            flush=True,
        )

        print(
            f"New SQLite IDs:      {new_ids:,}",
            flush=True,
        )

        print(
            f"New prefixes:        {batch_new_prefixes:,}",
            flush=True,
        )

        print(
            f"Errors:              {batch_errors:,}",
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

        return next_batch

    # --------------------------------------------------------
    # Main crawl
    # --------------------------------------------------------

    def crawl(self, conn):

        current_batch = self.initial_prefixes()

        batch_number = 0

        with ThreadPoolExecutor(
            max_workers=self.workers
        ) as executor:

            while current_batch:

                batch_number += 1

                # ------------------------------------------------
                # Batch size controls ONLY how many prefixes are
                # submitted to the executor in one batch.
                #
                # It does NOT control:
                #
                #   - number of API results
                #   - number of children generated
                #   - lexical depth
                #   - database size
                #
                # A batch of 50 therefore means:
                #
                #     query 50 prefixes
                #
                # and then generate whatever lexical frontier
                # those 50 searches require.
                # ------------------------------------------------

                batch = current_batch[
                    :self.batch_size
                ]

                current_batch = current_batch[
                    self.batch_size:
                ]

                generated_next = self.process_batch(
                    executor,
                    batch,
                    conn,
                    batch_number,
                )

                # New lexical frontier gets priority.
                current_batch = (
                    generated_next
                    + current_batch
                )

        self.print_complete()

    # --------------------------------------------------------
    # Final statistics
    # --------------------------------------------------------

    def print_complete(self):

        elapsed = (
            time.monotonic()
            - self.started
        )

        print()
        print("=" * 56)
        print("LEXICAL FRONTIER CRAWLER COMPLETE")
        print("=" * 56)

        print(
            f"Total requests:   "
            f"{self.total_requests:,}",
            flush=True,
        )

        print(
            f"Total API results:"
            f"{self.total_results:,}",
            flush=True,
        )

        print(
            f"New SQLite IDs:   "
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

        print("=" * 56)


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "RAE lexical-frontier prefix crawler"
        )
    )

    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=(
            "Concurrent HTTP workers "
            f"(default: {DEFAULT_WORKERS})"
        ),
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=(
            "Maximum prefixes processed per batch "
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
    # Credentials.
    # --------------------------------------------------------

    if not RAE_USER:

        print(
            "ERROR: RAE_USER is missing from .env",
            file=sys.stderr,
        )

        sys.exit(1)

    if not RAE_PASSWORD:

        print(
            "ERROR: RAE_PASSWORD is missing from .env",
            file=sys.stderr,
        )

        sys.exit(1)

    # --------------------------------------------------------
    # Header.
    # --------------------------------------------------------

    print()
    print("=" * 56)
    print("RAE LEXICAL FRONTIER CRAWLER")
    print("=" * 56)

    print(f"Database:          {DB_PATH}")
    print(f"Table:             {TABLE_NAME}")
    print(f"Workers:           {args.workers}")
    print(f"Batch size:        {args.batch_size}")
    print(f"Alphabet length:   {len(ALPHABET)}")
    print(f"Max prefix length: {MAX_PREFIX_LENGTH}")
    print("Traversal:         LEXICAL FRONTIER")
    print("Ordering:          API LEXICOGRAPHIC ORDER")
    print("Result cap logic:  NOT USED")

    print("=" * 56)
    print()

    # --------------------------------------------------------
    # Database.
    # --------------------------------------------------------

    create_database()

    existing = get_existing_count()

    print(
        f"Existing IDs: {existing:,}",
        flush=True,
    )

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

        crawler = LexicalFrontierCrawler(
            workers=args.workers,
            batch_size=args.batch_size,
        )

        crawler.crawl(conn)

    finally:

        conn.close()


if __name__ == "__main__":
    main()