import json
import sqlite3
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import threading

import requests
from dotenv import dotenv_values


# ============================================================
# CONFIG
# ============================================================

if len(sys.argv) < 2:
    print(
        "Usage: python -m experimentos.test_keys_ordering <letter>",
        file=sys.stderr,
    )
    print(
        "Example: python -m experimentos.test_keys_ordering a",
        file=sys.stderr,
    )
    sys.exit(1)

TARGET_LETTER = sys.argv[1].lower().strip()

if len(TARGET_LETTER) != 1:
    print("ERROR: Please provide one letter.", file=sys.stderr)
    sys.exit(1)


config = dotenv_values(".env")

RAE_USER = config.get("RAE_USER")
RAE_PASSWORD = config.get("RAE_PASSWORD")

RAE_KEYS_URL = "https://dle.rae.es/data/keys"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "datos" / "baseDeDatos" / "crawler.db"

TABLE_NAME = f"rae_keys_{TARGET_LETTER}"

REPORT_PATH = (
    PROJECT_ROOT
    / "experimentos"
    / f"keys_ordering_{TARGET_LETTER}.json"
)

DEFAULT_WORKERS = 50
REQUEST_TIMEOUT = 15
MAX_RETRIES = 5


# ============================================================
# NORMALIZATION
# ============================================================

# Fold acute accents only.
# Preserve ñ and ü.

ACUTE_TRANSLATION = str.maketrans(
    "áéíóúÁÉÍÓÚ",
    "aeiouAEIOU",
)


def normalize(text):
    return text.translate(ACUTE_TRANSLATION).lower()


# ============================================================
# HTTP
# ============================================================

_thread_local = threading.local()


def get_session():
    session = getattr(_thread_local, "session", None)

    if session is None:
        session = requests.Session()

        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36"
            ),
            "Accept": "application/json",
            "Connection": "keep-alive",
        })

        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=0,
        )

        session.mount("https://", adapter)

        _thread_local.session = session

    return session


def query_keys(prefix):
    session = get_session()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                RAE_KEYS_URL,
                params={"q": prefix},
                auth=(RAE_USER, RAE_PASSWORD),
                timeout=REQUEST_TIMEOUT,
            )

            response.raise_for_status()

            data = response.json()

            if not isinstance(data, list):
                raise ValueError(
                    f"Unexpected response type: {type(data).__name__}"
                )

            return data

        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"Failed {prefix!r}: {exc}"
                )

            time.sleep(0.3 * (2 ** (attempt - 1)))


# ============================================================
# DATABASE
# ============================================================

def load_keys():
    conn = sqlite3.connect(DB_PATH)

    try:
        rows = conn.execute(
            f"""
            SELECT key
            FROM {TABLE_NAME}
            ORDER BY key
            """
        ).fetchall()
    finally:
        conn.close()

    return [row[0] for row in rows]


# ============================================================
# GROUND-TRUTH HELPERS
# ============================================================

def sorted_matches(keys, prefix):
    """
    Return the ground-truth keys whose normalized form starts
    with the normalized prefix, in Python lexical order.
    """

    p = normalize(prefix)

    return sorted(
        (
            key
            for key in keys
            if normalize(key).startswith(p)
        ),
        key=normalize,
    )


def ground_truth_after(keys, value, limit=10):
    """
    Return the first `limit` ground-truth keys whose normalized
    value is >= the supplied value.
    """

    target = normalize(value)

    ordered = sorted(
        keys,
        key=normalize,
    )

    return [
        key
        for key in ordered
        if normalize(key) >= target
    ][:limit]


def next_prefix_candidates(value):
    """
    Generate useful candidate prefixes immediately around a
    returned key.

    We don't assume any one of these is correct; this is
    purely diagnostic.
    """

    candidates = []

    # Exact returned key.
    candidates.append(value)

    # Every prefix of the returned key.
    for i in range(1, len(value) + 1):
        candidates.append(value[:i])

    # Append likely next characters.
    alphabet = (
        "abcdefghijklmn"
        "ñ"
        "opqrstuvwxyz"
        "ü"
        "-"
        " "
    )

    for char in alphabet:
        candidates.append(value + char)

    # Remove duplicates while preserving order.
    seen = set()
    output = []

    for candidate in candidates:
        normalized = normalize(candidate)

        if normalized not in seen:
            seen.add(normalized)
            output.append(candidate)

    return output


# ============================================================
# TEST PREFIX
# ============================================================

def analyze_prefix(keys, prefix):

    api_results = query_keys(prefix)

    ground_matches = sorted_matches(
        keys,
        prefix,
    )

    result = {
        "prefix": prefix,
        "api_results": api_results,
        "ground_truth_first_20": ground_matches[:20],
        "api_count": len(api_results),
        "ground_truth_count": len(ground_matches),
    }

    if not api_results:
        return result

    # --------------------------------------------------------
    # Compare API result ordering with ground truth
    # --------------------------------------------------------

    normalized_api = [
        normalize(x)
        for x in api_results
    ]

    normalized_ground = [
        normalize(x)
        for x in ground_matches[:len(api_results)]
    ]

    result["api_matches_ground_truth"] = (
        normalized_api == normalized_ground
    )

    # --------------------------------------------------------
    # 10th result
    # --------------------------------------------------------

    tenth = api_results[-1]

    result["tenth_result"] = tenth

    # --------------------------------------------------------
    # What comes after the 10th result in ground truth?
    # --------------------------------------------------------

    target = normalize(tenth)

    after_tenth = [
        key
        for key in ground_matches
        if normalize(key) > target
    ]

    result["ground_truth_after_tenth"] = after_tenth[:20]

    # --------------------------------------------------------
    # Query exact 10th result
    # --------------------------------------------------------

    exact_results = query_keys(tenth)

    result["query_exact_tenth"] = {
        "query": tenth,
        "results": exact_results,
        "count": len(exact_results),
    }

    # --------------------------------------------------------
    # Compare exact tenth query to expected continuation
    # --------------------------------------------------------

    exact_normalized = [
        normalize(x)
        for x in exact_results
    ]

    expected_after = [
        normalize(x)
        for x in after_tenth[:len(exact_results)]
    ]

    result["exact_tenth_matches_ground_truth_after"] = (
        exact_normalized == expected_after
    )

    # --------------------------------------------------------
    # Test candidate next prefixes
    # --------------------------------------------------------

    candidates = next_prefix_candidates(tenth)

    candidate_results = []

    for candidate in candidates:

        # Don't generate enormous repeated queries.
        # We only care about candidates beginning with the
        # original prefix or the tenth result.
        if not (
            normalize(candidate).startswith(
                normalize(prefix)
            )
            or normalize(candidate).startswith(
                normalize(tenth)
            )
        ):
            continue

        try:
            api = query_keys(candidate)

            candidate_results.append({
                "query": candidate,
                "results": api,
                "count": len(api),
            })

        except Exception as exc:
            candidate_results.append({
                "query": candidate,
                "error": str(exc),
            })

    result["candidate_queries"] = candidate_results

    return result


# ============================================================
# TEST SET
# ============================================================

TEST_PREFIXES = [
    "a",
    "al",
    "anti",
    "agua",
    "ama",
    "ana",
    "apa",
    "aca",
    "acu",
    "ala",
    "alca",
    "ale",
    "an",
    "ad",
    "alo",
]


# ============================================================
# MAIN
# ============================================================

def main():

    if not RAE_USER or not RAE_PASSWORD:
        print(
            "ERROR: Missing RAE_USER or RAE_PASSWORD in .env",
            file=sys.stderr,
        )
        sys.exit(1)

    started = time.monotonic()

    print()
    print("=" * 60)
    print("RAE /KEYS ORDERING DIAGNOSTIC")
    print("=" * 60)
    print(f"Letter:       {TARGET_LETTER}")
    print(f"Database:     {DB_PATH}")
    print(f"Table:        {TABLE_NAME}")
    print("=" * 60)
    print()

    # --------------------------------------------------------
    # Load database
    # --------------------------------------------------------

    keys = load_keys()

    print(
        f"Ground-truth keys loaded: {len(keys):,}"
    )

    # --------------------------------------------------------
    # Select test prefixes that actually exist
    # --------------------------------------------------------

    available = []

    for prefix in TEST_PREFIXES:

        if any(
            normalize(key).startswith(
                normalize(prefix)
            )
            for key in keys
        ):
            available.append(prefix)

    print(
        f"Test prefixes: {len(available)}"
    )

    print()

    # --------------------------------------------------------
    # Run tests
    # --------------------------------------------------------

    results = []

    with ThreadPoolExecutor(
        max_workers=DEFAULT_WORKERS
    ) as executor:

        futures = {
            executor.submit(
                analyze_prefix,
                keys,
                prefix,
            ): prefix
            for prefix in available
        }

        completed = 0

        for future in as_completed(futures):

            prefix = futures[future]

            try:
                result = future.result()
                results.append(result)

            except Exception as exc:

                print(
                    f"\n[ERROR] {prefix!r}: {exc}",
                    file=sys.stderr,
                )

            completed += 1

            print(
                f"\r[{completed}/{len(available)}]",
                end="",
                flush=True,
            )

    print()

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    for result in sorted(
        results,
        key=lambda r: r["prefix"],
    ):

        prefix = result["prefix"]

        print()
        print(f"PREFIX: {prefix!r}")

        print(
            f"API count:           "
            f"{result['api_count']}"
        )

        print(
            f"Ground truth count:  "
            f"{result['ground_truth_count']}"
        )

        print(
            f"API = lexical first 10: "
            f"{result.get('api_matches_ground_truth')}"
        )

        if result.get("tenth_result"):

            print(
                f"10th result:         "
                f"{result['tenth_result']!r}"
            )

            print(
                f"After 10th in DB:    "
                f"{result['ground_truth_after_tenth'][:5]}"
            )

            print(
                f"Exact 10th query:    "
                f"{result['exact_tenth_matches_ground_truth_after']}"
            )

            print(
                f"Exact query results: "
                f"{result['query_exact_tenth']['results'][:10]}"
            )

    # --------------------------------------------------------
    # Save report
    # --------------------------------------------------------

    report = {
        "letter": TARGET_LETTER,
        "database": str(DB_PATH),
        "table": TABLE_NAME,
        "ground_truth_count": len(keys),
        "test_prefixes": available,
        "results": sorted(
            results,
            key=lambda r: r["prefix"],
        ),
    }

    with REPORT_PATH.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            report,
            f,
            ensure_ascii=False,
            indent=2,
        )

    elapsed = time.monotonic() - started

    print()
    print("=" * 60)
    print("DONE")
    print("=" * 60)
    print(
        f"Elapsed: {elapsed:.1f} seconds"
    )
    print(
        f"Report: {REPORT_PATH}"
    )
    print()


if __name__ == "__main__":
    main()