import csv
import sqlite3
from pathlib import Path


DB_PATH = Path("datos/basededatos/crawler.db")
LEMARIO_PATH = Path("datos/sinProcesar/lemario.csv")
OUTPUT_DIR = Path("datos/procesado/comparacion_cobertura")


def load_lemario():
    """Load unique headwords from the old lemario.csv."""
    words = set()

    with LEMARIO_PATH.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)

        for row in reader:
            if not row:
                continue

            word = row[0].strip().strip('"')

            if word:
                words.add(word)

    return words


def get_table_names(connection):
    """Get all rae_keys_* tables."""
    cursor = connection.cursor()

    cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name LIKE 'rae_keys_%'
        ORDER BY name
    """)

    return [row[0] for row in cursor.fetchall()]


def load_crawler_keys(connection):
    """Load all unique keys from all crawler tables."""
    keys = set()
    table_counts = {}

    for table_name in get_table_names(connection):
        cursor = connection.cursor()

        # Table names are quoted because some contain punctuation.
        cursor.execute(f'SELECT key FROM "{table_name}"')

        rows = cursor.fetchall()

        table_keys = {row[0] for row in rows if row[0]}

        keys.update(table_keys)
        table_counts[table_name] = len(table_keys)

    return keys, table_counts


def write_list(path, values):
    """Write one value per line."""
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["key"])

        for value in sorted(values):
            writer.writerow([value])


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading old lemario...")
    lemario = load_lemario()

    print(f"Old lemario unique keys: {len(lemario):,}")

    print("\nLoading crawler database...")

    connection = sqlite3.connect(DB_PATH)

    try:
        crawler_keys, table_counts = load_crawler_keys(connection)
    finally:
        connection.close()

    print(f"Crawler unique keys:      {len(crawler_keys):,}")

    # Set comparisons
    both = lemario & crawler_keys
    lemario_only = lemario - crawler_keys
    crawler_only = crawler_keys - lemario

    # Save results
    write_list(
        OUTPUT_DIR / "01_lemario_only.csv",
        lemario_only,
    )

    write_list(
        OUTPUT_DIR / "02_crawler_only.csv",
        crawler_only,
    )

    write_list(
        OUTPUT_DIR / "03_both.csv",
        both,
    )

    # Save table counts
    with (OUTPUT_DIR / "04_table_counts.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.writer(f)
        writer.writerow(["table", "unique_keys"])

        for table_name, count in table_counts.items():
            writer.writerow([table_name, count])

    print("\n" + "=" * 60)
    print("COVERAGE COMPARISON")
    print("=" * 60)

    print(f"Old lemario:             {len(lemario):,}")
    print(f"Our crawler:             {len(crawler_keys):,}")
    print(f"Present in both:         {len(both):,}")
    print(f"Only in old lemario:     {len(lemario_only):,}")
    print(f"Only in our crawler:     {len(crawler_only):,}")

    print("\nFiles written to:")
    print(OUTPUT_DIR)

    print("\nOld lemario entries NOT found by our crawler:")

    for word in sorted(lemario_only)[:100]:
        print(f"  {word}")

    print("\nOur crawler entries NOT found in old lemario:")

    for word in sorted(crawler_only)[:100]:
        print(f"  {word}")


if __name__ == "__main__":
    main()