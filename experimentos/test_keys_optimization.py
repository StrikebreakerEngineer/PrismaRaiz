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
        "Usage: python -m experimentos.test_keys_optimization <letter>",
        file=sys.stderr,
    )
    print(
        "Example: python -m experimentos.test_keys_optimization a",
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
    / f"keys_optimization_{TARGET_LETTER}.json"
)

DEFAULT_WORKERS = 200
REQUEST_TIMEOUT = 15
MAX_RETRIES = 5
MAX_EXAMPLES = 100


# ============================================================
# NORMALIZATION
# ============================================================

# IMPORTANT:
# Preserve ñ and ü.
# Only fold acute accents.

ACUTE_TRANSLATION = str.maketrans(
    "áéíóúÁÉÍÓÚ",
    "aeiouAEIOU",
)


def normalize(text):
    return text.translate(ACUTE_TRANSLATION).lower()


# ============================================================
# HTTP SESSION
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
            pool_connections=50,
            pool_maxsize=50,
            max_retries=0,
        )

        session.mount("https://", adapter)

        _thread_local.session = session

    return session


def query_keys(prefix):
    session = get_session()

    params = {"q": prefix}

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
# LOAD GROUND TRUTH
# ============================================================

def load_keys():
    print(f"Opening database: {DB_PATH}")
    print(f"Table: {TABLE_NAME}")

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

    keys = [row[0] for row in rows]

    return keys


# ============================================================
# TRIE
# ============================================================

class TrieNode:

    __slots__ = (
        "children",
        "terminal",
        "keys_below",
    )

    def __init__(self):
        self.children = {}
        self.terminal = False
        self.keys_below = 0


def build_trie(keys):
    root = TrieNode()

    for key in keys:
        node = root

        for char in normalize(key):
            if char not in node.children:
                node.children[char] = TrieNode()

            node = node.children[char]

        node.terminal = True

    calculate_counts(root)

    return root


def calculate_counts(node):
    count = 1 if node.terminal else 0

    for child in node.children.values():
        count += calculate_counts(child)

    node.keys_below = count

    return count


def get_node(root, prefix):
    node = root

    for char in normalize(prefix):
        node = node.children.get(char)

        if node is None:
            return None

    return node


# ============================================================
# FIND SATURATED PREFIXES
# ============================================================

def find_saturated_prefixes(root):
    """
    Find every prefix whose subtree contains >= 10 keys.

    These are the prefixes where /keys can potentially return
    only a subset of the available keys.
    """

    saturated = []

    stack = [
        ("", root)
    ]

    while stack:
        prefix, node = stack.pop()

        if node.keys_below >= 10:
            saturated.append(prefix)

        for char, child in node.children.items():
            stack.append(
                (prefix + char, child)
            )

    return saturated


# ============================================================
# ACTUAL BRANCHES
# ============================================================

def get_actual_branches(root, prefix):
    """
    Given a prefix, determine which immediate next-character
    branches actually contain keys.

    Also records whether the prefix itself is a key.
    """

    node = get_node(root, prefix)

    if node is None:
        return {
            "terminal": False,
            "branches": [],
            "count": 0,
        }

    branches = sorted(node.children.keys())

    return {
        "terminal": node.terminal,
        "branches": branches,
        "count": node.keys_below,
    }


# ============================================================
# ANALYZE ONE PREFIX
# ============================================================

def analyze_prefix(root, prefix):
    actual = get_actual_branches(root, prefix)

    api_results = query_keys(prefix)

    api_normalized = [
        normalize(x)
        for x in api_results
    ]

    actual_branches = set(actual["branches"])

    returned_branches = set()

    for result in api_normalized:
        if len(result) > len(normalize(prefix)):
            child_char = result[len(normalize(prefix))]
            returned_branches.add(child_char)

    hidden_branches = actual_branches - returned_branches
    represented_branches = actual_branches & returned_branches

    # The branch containing the prefix itself isn't represented
    # by a child character, so record it separately.

    exact_returned = (
        normalize(prefix) in api_normalized
    )

    return {
        "prefix": prefix,
        "ground_truth_count": actual["count"],
        "ground_truth_terminal": actual["terminal"],
        "ground_truth_branches": actual["branches"],
        "api_count": len(api_results),
        "api_results": api_results,
        "api_returned_branches": sorted(returned_branches),
        "represented_branches": sorted(represented_branches),
        "hidden_branches": sorted(hidden_branches),
        "exact_prefix_returned": exact_returned,
        "api_first": api_results[0] if api_results else None,
        "api_last": api_results[-1] if api_results else None,
    }


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
    print("RAE /KEYS OPTIMIZATION DIAGNOSTIC")
    print("=" * 60)
    print(f"Letter:       {TARGET_LETTER}")
    print(f"Database:     {DB_PATH}")
    print(f"Table:        {TABLE_NAME}")
    print(f"Workers:      {DEFAULT_WORKERS}")
    print("=" * 60)
    print()

    # --------------------------------------------------------
    # Load keys
    # --------------------------------------------------------

    keys = load_keys()

    print(f"Ground-truth keys: {len(keys):,}")

    # --------------------------------------------------------
    # Build trie
    # --------------------------------------------------------

    print("Building trie...")

    trie_started = time.monotonic()

    root = build_trie(keys)

    trie_elapsed = time.monotonic() - trie_started

    print(
        f"Trie built in {trie_elapsed:.3f} seconds."
    )

    # --------------------------------------------------------
    # Find saturated prefixes
    # --------------------------------------------------------

    print("Finding saturated prefixes...")

    saturated = find_saturated_prefixes(root)

    # Don't query the root again if the letter itself is the
    # starting point. The crawler already established it.
    #
    # We DO want the letter prefix because this diagnostic is
    # about exactly how /keys behaves at that point.

    saturated = sorted(
        saturated,
        key=lambda x: (len(x), x)
    )

    print(
        f"Saturated prefixes to test: {len(saturated):,}"
    )

    print()

    # --------------------------------------------------------
    # Query API
    # --------------------------------------------------------

    results = []

    total = len(saturated)
    completed = 0
    errors = 0

    api_started = time.monotonic()

    with ThreadPoolExecutor(
        max_workers=DEFAULT_WORKERS
    ) as executor:

        futures = {
            executor.submit(
                analyze_prefix,
                root,
                prefix,
            ): prefix
            for prefix in saturated
        }

        for future in as_completed(futures):

            prefix = futures[future]

            try:
                result = future.result()
                results.append(result)

            except Exception as exc:
                errors += 1

                print(
                    f"\n[ERROR] {prefix!r}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )

            completed += 1

            print(
                f"\r[{completed:,}/{total:,}] "
                f"errors={errors:,}",
                end="",
                flush=True,
            )

    print()

    api_elapsed = time.monotonic() - api_started

    print()
    print(
        f"API diagnostic time: {api_elapsed:.1f} seconds"
    )

    # --------------------------------------------------------
    # Aggregate statistics
    # --------------------------------------------------------

    saturated_results = [
        r
        for r in results
        if r["api_count"] == 10
    ]

    non_saturated_results = [
        r
        for r in results
        if r["api_count"] < 10
    ]

    hidden_branch_results = [
        r
        for r in results
        if r["hidden_branches"]
    ]

    no_hidden_branch_results = [
        r
        for r in results
        if not r["hidden_branches"]
    ]

    # --------------------------------------------------------
    # Branch statistics
    # --------------------------------------------------------

    branch_stats = {}

    for result in saturated_results:

        actual = set(
            result["ground_truth_branches"]
        )

        returned = set(
            result["api_returned_branches"]
        )

        for branch in actual:

            if branch not in branch_stats:
                branch_stats[branch] = {
                    "available": 0,
                    "returned": 0,
                    "hidden": 0,
                }

            branch_stats[branch]["available"] += 1

            if branch in returned:
                branch_stats[branch]["returned"] += 1
            else:
                branch_stats[branch]["hidden"] += 1

    # --------------------------------------------------------
    # First/last result patterns
    # --------------------------------------------------------

    first_chars = {}
    last_chars = {}

    for result in saturated_results:

        prefix_norm = normalize(
            result["prefix"]
        )

        for field, counter in (
            ("api_first", first_chars),
            ("api_last", last_chars),
        ):

            value = result[field]

            if not value:
                continue

            value_norm = normalize(value)

            if len(value_norm) <= len(prefix_norm):
                continue

            char = value_norm[len(prefix_norm)]

            counter[char] = (
                counter.get(char, 0) + 1
            )

    # --------------------------------------------------------
    # Find interesting examples
    # --------------------------------------------------------

    hidden_examples = sorted(
        hidden_branch_results,
        key=lambda r: (
            -len(r["hidden_branches"]),
            r["prefix"],
        ),
    )[:MAX_EXAMPLES]

    no_hidden_examples = sorted(
        no_hidden_branch_results,
        key=lambda r: r["prefix"],
    )[:MAX_EXAMPLES]

    # --------------------------------------------------------
    # Print summary
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)

    print(
        f"Ground-truth keys:          {len(keys):,}"
    )

    print(
        f"Saturated prefixes tested:  {len(saturated):,}"
    )

    print(
        f"API results obtained:       {len(results):,}"
    )

    print(
        f"API errors:                 {errors:,}"
    )

    print(
        f"Returned exactly 10:        {len(saturated_results):,}"
    )

    print(
        f"Returned <10:               {len(non_saturated_results):,}"
    )

    print(
        f"Prefixes with hidden branch:{len(hidden_branch_results):,}"
    )

    print(
        f"Prefixes with no hidden:    {len(no_hidden_branch_results):,}"
    )

    # --------------------------------------------------------
    # Branch table
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("BRANCH FREQUENCY")
    print("=" * 60)

    print(
        f"{'BRANCH':<8}"
        f"{'AVAILABLE':>12}"
        f"{'RETURNED':>12}"
        f"{'HIDDEN':>12}"
    )

    for branch in sorted(branch_stats):

        stats = branch_stats[branch]

        print(
            f"{branch!r:<8}"
            f"{stats['available']:>12,}"
            f"{stats['returned']:>12,}"
            f"{stats['hidden']:>12,}"
        )

    # --------------------------------------------------------
    # First / last branch statistics
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("FIRST RESULT BRANCHES")
    print("=" * 60)

    for branch, count in sorted(
        first_chars.items(),
        key=lambda x: (-x[1], x[0]),
    ):
        print(
            f"{branch!r}: {count:,}"
        )

    print()
    print("=" * 60)
    print("LAST RESULT BRANCHES")
    print("=" * 60)

    for branch, count in sorted(
        last_chars.items(),
        key=lambda x: (-x[1], x[0]),
    ):
        print(
            f"{branch!r}: {count:,}"
        )

    # --------------------------------------------------------
    # Examples where branches are hidden
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("EXAMPLES WITH HIDDEN BRANCHES")
    print("=" * 60)

    for result in hidden_examples[:20]:

        print()
        print(
            f"PREFIX: {result['prefix']!r}"
        )

        print(
            f"GROUND TRUTH COUNT: "
            f"{result['ground_truth_count']}"
        )

        print(
            f"ACTUAL BRANCHES: "
            f"{result['ground_truth_branches']}"
        )

        print(
            f"API BRANCHES: "
            f"{result['api_returned_branches']}"
        )

        print(
            f"HIDDEN: "
            f"{result['hidden_branches']}"
        )

        print(
            f"API RESULTS: "
            f"{result['api_results']}"
        )

    # --------------------------------------------------------
    # Save JSON
    # --------------------------------------------------------

    report = {
        "letter": TARGET_LETTER,
        "database": str(DB_PATH),
        "table": TABLE_NAME,

        "ground_truth_key_count": len(keys),

        "saturated_prefix_count": len(saturated),

        "results_count": len(results),

        "errors": errors,

        "statistics": {
            "returned_exactly_10": len(
                saturated_results
            ),
            "returned_less_than_10": len(
                non_saturated_results
            ),
            "with_hidden_branches": len(
                hidden_branch_results
            ),
            "without_hidden_branches": len(
                no_hidden_branch_results
            ),
        },

        "branch_stats": branch_stats,

        "first_result_branches": first_chars,

        "last_result_branches": last_chars,

        "examples_hidden_branches": hidden_examples,

        "examples_no_hidden_branches": no_hidden_examples,

        "all_results": sorted(
            results,
            key=lambda r: (
                len(r["prefix"]),
                r["prefix"],
            ),
        ),
    }

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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
        f"Total elapsed: {elapsed:.1f} seconds"
    )

    print(
        f"Report saved to:\n{REPORT_PATH}"
    )

    print()


if __name__ == "__main__":
    main()