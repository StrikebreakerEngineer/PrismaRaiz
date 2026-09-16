import sqlite3
from collections import Counter
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "datos" / "baseDeDatos" / "crawler.db"

# Roots that our normal crawler intentionally covered.
EXPECTED_ROOTS = set(
    "abcdefghijklmnñopqrstuvwxyzü"
)

# Special roots we already know about from manual testing.
KNOWN_SPECIAL_ROOTS = {"-", "‒"}


# ============================================================
# DATABASE
# ============================================================

def get_tables(conn):
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name LIKE 'rae_keys_%'
        ORDER BY name
        """
    ).fetchall()

    return [row[0] for row in rows]


def load_all_keys(conn, tables):
    all_keys = []

    for table in tables:
        rows = conn.execute(
            f"SELECT key FROM {table}"
        ).fetchall()

        all_keys.extend(row[0] for row in rows)

    return all_keys


# ============================================================
# ANALYSIS
# ============================================================

def first_character(key):
    if not key:
        return "<EMPTY>"

    return key[0]


def show_character(char):
    """
    Make invisible/special characters easier to identify.
    """

    if char == " ":
        return "[SPACE]"

    if char == "\t":
        return "[TAB]"

    if char == "\n":
        return "[NEWLINE]"

    if char == "\r":
        return "[CR]"

    return char


def unicode_info(char):
    return f"U+{ord(char):04X}"


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("RAE /KEYS ROOT COVERAGE ANALYZER")
    print("=" * 70)
    print(f"Database: {DB_PATH}")
    print("=" * 70)
    print()

    if not DB_PATH.exists():
        print("ERROR: crawler.db was not found.")
        return

    conn = sqlite3.connect(DB_PATH)

    try:
        tables = get_tables(conn)

        if not tables:
            print("No rae_keys_* tables found.")
            return

        print(f"Tables found: {len(tables)}")
        print()

        print("Tables:")
        for table in tables:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

            print(f"  {table:<20} {count:>10,} keys")

        print()

        keys = load_all_keys(conn, tables)

    finally:
        conn.close()

    # --------------------------------------------------------
    # Basic totals
    # --------------------------------------------------------

    unique_keys = set(keys)

    print("=" * 70)
    print("TOTALS")
    print("=" * 70)

    print(f"Rows loaded:       {len(keys):,}")
    print(f"Unique keys:       {len(unique_keys):,}")
    print(f"Duplicate rows:    {len(keys) - len(unique_keys):,}")
    print()

    # --------------------------------------------------------
    # First-character inventory
    # --------------------------------------------------------

    counts = Counter(
        first_character(key)
        for key in unique_keys
    )

    print("=" * 70)
    print("FIRST-CHARACTER INVENTORY")
    print("=" * 70)

    print()
    print(f"{'CHAR':<12} {'UNICODE':<10} {'COUNT':>12}  STATUS")
    print("-" * 55)

    for char, count in sorted(
        counts.items(),
        key=lambda item: (-item[1], item[0])
    ):
        display = show_character(char)
        code = unicode_info(char) if len(char) == 1 else "?"

        if char in EXPECTED_ROOTS:
            status = "NORMAL ROOT"
        elif char in KNOWN_SPECIAL_ROOTS:
            status = "KNOWN SPECIAL"
        else:
            status = "*** UNEXPECTED ***"

        print(
            f"{display:<12} "
            f"{code:<10} "
            f"{count:>12,}  "
            f"{status}"
        )

    # --------------------------------------------------------
    # Unexpected roots
    # --------------------------------------------------------

    unexpected = sorted(
        char
        for char in counts
        if char not in EXPECTED_ROOTS
    )

    print()
    print("=" * 70)
    print("UNEXPECTED ROOTS")
    print("=" * 70)

    if not unexpected:
        print("None.")
    else:
        for char in unexpected:
            print(
                f"{show_character(char)!r} "
                f"({unicode_info(char)}) "
                f"→ {counts[char]:,} keys"
            )

    # --------------------------------------------------------
    # Known special roots
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("KNOWN SPECIAL ROOTS")
    print("=" * 70)

    for char in sorted(KNOWN_SPECIAL_ROOTS):

        count = counts.get(char, 0)

        print(
            f"{show_character(char)!r} "
            f"({unicode_info(char)}) "
            f"→ {count:,} keys currently stored"
        )

    # --------------------------------------------------------
    # Sample keys from every unexpected root
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("SAMPLES FROM UNEXPECTED ROOTS")
    print("=" * 70)

    for char in unexpected:

        matching = sorted(
            key for key in unique_keys
            if key.startswith(char)
        )

        print()
        print(
            f"ROOT {show_character(char)!r} "
            f"({unicode_info(char)}) "
            f"— {len(matching):,} keys"
        )

        for key in matching[:20]:
            print(f"  {key}")

        if len(matching) > 20:
            print("  ...")

    # --------------------------------------------------------
    # Missing normal roots
    # --------------------------------------------------------

    missing_normal = sorted(
        root
        for root in EXPECTED_ROOTS
        if root not in counts
    )

    print()
    print("=" * 70)
    print("EXPECTED ROOTS WITH ZERO KEYS")
    print("=" * 70)

    if not missing_normal:
        print("None.")
    else:
        print(", ".join(sorted(missing_normal)))

    # --------------------------------------------------------
    # Final summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    print(f"Total unique keys:       {len(unique_keys):,}")
    print(f"Distinct first chars:    {len(counts):,}")
    print(f"Normal roots present:    {len(EXPECTED_ROOTS & set(counts)):,}")
    print(f"Special/unexpected roots:{len(set(unexpected)):,}")
    print()

    if unexpected:
        print("ACTION NEEDED:")
        print("Investigate the unexpected roots above before declaring")
        print("the /keys crawl complete.")
    else:
        print("No unexpected roots found in the crawled data.")

    print()
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()