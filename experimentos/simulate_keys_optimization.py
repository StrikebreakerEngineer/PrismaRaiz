import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================

if len(sys.argv) < 2:
    print("Usage: python -m experimentos.simulate_keys_optimization <letter>")
    print("Example: python -m experimentos.simulate_keys_optimization a")
    sys.exit(1)

TARGET_LETTER = sys.argv[1].lower().strip()

if len(TARGET_LETTER) != 1:
    print("ERROR: Please provide a single letter.")
    sys.exit(1)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "datos" / "baseDeDatos" / "crawler.db"

TABLE_NAME = f"rae_keys_{TARGET_LETTER}"

# These are the characters the crawler currently uses for children.
QUERY_ALPHABET = (
    "abcdefghijklmn"
    "ñ"
    "opqrstuvwxyz"
    "ü"
)

MAX_PREFIX_LENGTH = 30


# ============================================================
# NORMALIZATION
# ============================================================

ACUTE_TRANSLATION = str.maketrans(
    "áéíóúÁÉÍÓÚ",
    "aeiouAEIOU",
)


def normalize(text):
    """
    Match the normalization used by the crawler.

    Important:
    - acute accents are folded
    - ñ is preserved
    - ü is preserved
    """
    return text.translate(ACUTE_TRANSLATION).lower()


# ============================================================
# LOAD KEYS
# ============================================================

def load_keys():
    conn = sqlite3.connect(DB_PATH)

    try:
        rows = conn.execute(
            f"SELECT key FROM {TABLE_NAME}"
        ).fetchall()
    finally:
        conn.close()

    return [row[0] for row in rows]


# ============================================================
# BUILD PREFIX INDEX
# ============================================================

def build_prefix_index(keys):
    """
    Build:

        prefix -> sorted list of matching keys

    This is the expensive part, but we do it ONLY ONCE.

    The API appears to return the first 10 matching keys
    in lexical order, so this lets us simulate that behavior
    without making thousands of repeated scans.
    """

    prefix_index = defaultdict(list)

    for key in keys:
        normalized = normalize(key)

        # Include every prefix of the normalized key.
        for length in range(1, min(len(normalized), MAX_PREFIX_LENGTH) + 1):
            prefix = normalized[:length]
            prefix_index[prefix].append(key)

    # Sort each prefix's results exactly once.
    for values in prefix_index.values():
        values.sort(key=normalize)

    return prefix_index


# ============================================================
# FIND SATURATED PREFIXES
# ============================================================

def find_saturated_prefixes(prefix_index):
    """
    A saturated prefix is one where /keys would return
    exactly 10 results.

    These are the prefixes where our current crawler
    has to branch.
    """

    return {
        prefix
        for prefix, values in prefix_index.items()
        if len(values) >= 10
    }


# ============================================================
# BRANCH HELPERS
# ============================================================

def child_branch(prefix, key):
    """
    Return the character immediately after prefix.

    Example:

        prefix = "agua"
        key    = "aguacatón"

        -> "c"
    """

    normalized_prefix = normalize(prefix)
    normalized_key = normalize(key)

    if not normalized_key.startswith(normalized_prefix):
        return None

    if len(normalized_key) <= len(normalized_prefix):
        return None

    return normalized_key[len(normalized_prefix)]


def available_branches(prefix, matches):
    """
    Find every actual child branch represented by the
    ground-truth database.
    """

    branches = set()

    for key in matches:
        branch = child_branch(prefix, key)

        if branch is not None:
            branches.add(branch)

    return branches


def returned_branches(prefix, matches):
    """
    Find the child branches represented in the first
    10 results returned by /keys.
    """

    first_ten = matches[:10]

    branches = set()

    for key in first_ten:
        branch = child_branch(prefix, key)

        if branch is not None:
            branches.add(branch)

    return branches


def tenth_branch(prefix, matches):
    """
    Return the branch containing the 10th API result.
    """

    if len(matches) < 10:
        return None

    return child_branch(prefix, matches[9])


# ============================================================
# RULE SIMULATION
# ============================================================

def simulate_rules(prefix_index, saturated_prefixes):
    """
    Compare several possible optimization rules.

    RULE A:
        Query only the branch containing the 10th result.

    RULE B:
        Query the 10th-result branch plus every branch
        lexically AFTER it.

    RULE C:
        Query every branch represented by the first 10 results.

    The current crawler queries EVERY possible child.
    """

    alphabet_order = {
        char: index
        for index, char in enumerate(QUERY_ALPHABET)
    }

    stats = {
        "A": {
            "safe": 0,
            "unsafe": 0,
            "missing_branches": 0,
            "child_requests": 0,
        },
        "B": {
            "safe": 0,
            "unsafe": 0,
            "missing_branches": 0,
            "child_requests": 0,
        },
        "C": {
            "safe": 0,
            "unsafe": 0,
            "missing_branches": 0,
            "child_requests": 0,
        },
    }

    failures = {
        "A": [],
        "B": [],
        "C": [],
    }

    current_child_count = len(QUERY_ALPHABET)

    for prefix in saturated_prefixes:

        matches = prefix_index[prefix]

        # Simulate the API's first 10.
        first_ten = matches[:10]

        actual = available_branches(prefix, matches)

        boundary = tenth_branch(prefix, matches)

        returned = returned_branches(prefix, matches)

        # ----------------------------------------------------
        # RULE A
        # ----------------------------------------------------

        rule_a = set()

        if boundary is not None:
            rule_a.add(boundary)

        missing_a = actual - rule_a

        stats["A"]["child_requests"] += len(rule_a)

        if missing_a:
            stats["A"]["unsafe"] += 1
            stats["A"]["missing_branches"] += len(missing_a)

            if len(failures["A"]) < 10:
                failures["A"].append(
                    (prefix, first_ten, actual, rule_a, missing_a)
                )
        else:
            stats["A"]["safe"] += 1

        # ----------------------------------------------------
        # RULE B
        # ----------------------------------------------------

        rule_b = set()

        if boundary is not None:
            boundary_index = alphabet_order.get(boundary)

            if boundary_index is not None:
                for branch in actual:
                    branch_index = alphabet_order.get(branch)

                    if (
                        branch_index is not None
                        and branch_index >= boundary_index
                    ):
                        rule_b.add(branch)

        missing_b = actual - rule_b

        stats["B"]["child_requests"] += len(rule_b)

        if missing_b:
            stats["B"]["unsafe"] += 1
            stats["B"]["missing_branches"] += len(missing_b)

            if len(failures["B"]) < 10:
                failures["B"].append(
                    (prefix, first_ten, actual, rule_b, missing_b)
                )
        else:
            stats["B"]["safe"] += 1

        # ----------------------------------------------------
        # RULE C
        # ----------------------------------------------------

        rule_c = returned

        missing_c = actual - rule_c

        stats["C"]["child_requests"] += len(rule_c)

        if missing_c:
            stats["C"]["unsafe"] += 1
            stats["C"]["missing_branches"] += len(missing_c)

            if len(failures["C"]) < 10:
                failures["C"].append(
                    (prefix, first_ten, actual, rule_c, missing_c)
                )
        else:
            stats["C"]["safe"] += 1

    return stats, failures, current_child_count


# ============================================================
# PRINT FAILURES
# ============================================================

def print_failures(name, failures):
    if not failures:
        return

    print()
    print(f"FIRST {len(failures)} FAILURES — RULE {name}")
    print("-" * 70)

    for prefix, first_ten, actual, attempted, missing in failures:

        print(f"Prefix:       {prefix!r}")
        print(f"10th result:  {first_ten[-1]!r}")
        print(f"Actual:       {sorted(actual)}")
        print(f"Attempted:    {sorted(attempted)}")
        print(f"MISSING:      {sorted(missing)}")
        print()


# ============================================================
# MAIN
# ============================================================

def main():

    started = time.monotonic()

    print()
    print("=" * 70)
    print("FAST /KEYS OPTIMIZATION SIMULATION")
    print("=" * 70)
    print(f"Letter:       {TARGET_LETTER}")
    print(f"Database:     {DB_PATH}")
    print(f"Table:        {TABLE_NAME}")
    print("=" * 70)
    print()

    # --------------------------------------------------------
    # Load
    # --------------------------------------------------------

    print("Loading keys...", flush=True)

    keys = load_keys()

    print(f"Ground-truth keys: {len(keys):,}")

    # --------------------------------------------------------
    # Prefix index
    # --------------------------------------------------------

    print("Building prefix index...", flush=True)

    prefix_index = build_prefix_index(keys)

    print(f"Unique prefixes:   {len(prefix_index):,}")

    # --------------------------------------------------------
    # Saturated prefixes
    # --------------------------------------------------------

    print("Finding saturated prefixes...", flush=True)

    saturated = find_saturated_prefixes(prefix_index)

    print(f"Saturated prefixes: {len(saturated):,}")

    # --------------------------------------------------------
    # Simulate
    # --------------------------------------------------------

    print()
    print("Simulating rules...", flush=True)

    stats, failures, current_child_count = simulate_rules(
        prefix_index,
        saturated,
    )

    # --------------------------------------------------------
    # Results
    # --------------------------------------------------------

    elapsed = time.monotonic() - started

    print()
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)

    print()
    print(f"Ground-truth keys:      {len(keys):,}")
    print(f"Unique prefixes:        {len(prefix_index):,}")
    print(f"Saturated prefixes:     {len(saturated):,}")
    print(f"Current child requests: {len(saturated) * current_child_count:,}")
    print()

    for name, label in [
        ("A", "10th branch only"),
        ("B", "10th branch + branches after it"),
        ("C", "branches represented in first 10"),
    ]:

        s = stats[name]

        total = s["safe"] + s["unsafe"]

        if total:
            safety = (s["safe"] / total) * 100
        else:
            safety = 0

        reduction = (
            1
            - (s["child_requests"] /
               (len(saturated) * current_child_count))
        ) * 100

        print(f"RULE {name} — {label}")
        print("-" * 70)
        print(f"Safe:                 {s['safe']:,}/{total:,} ({safety:.2f}%)")
        print(f"Unsafe:               {s['unsafe']:,}")
        print(f"Missing branches:     {s['missing_branches']:,}")
        print(f"Estimated child reqs: {s['child_requests']:,}")
        print(f"Theoretical reduction:{reduction:8.2f}%")
        print()

    # --------------------------------------------------------
    # Failures
    # --------------------------------------------------------

    print("=" * 70)
    print("FAILURE EXAMPLES")
    print("=" * 70)

    print_failures("A", failures["A"])
    print_failures("B", failures["B"])
    print_failures("C", failures["C"])

    print()
    print("=" * 70)
    print(f"Finished in {elapsed:.2f} seconds")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()