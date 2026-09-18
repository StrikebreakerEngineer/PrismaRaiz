import csv
import re
import sqlite3
from pathlib import Path


DB_PATH = Path("datos/basededatos/crawler.db")
CSV_PATH = Path("datos/sinProcesar/lemario.csv")
OUTPUT_DIR = Path("datos/procesado/comparacion_lemario")


def normalize_header(text):
    """Normalize CSV entries and RAE HTML headers for comparison."""
    if text is None:
        return ""

    text = str(text).strip()

    # Remove homonym markers such as <sup>1</sup>.
    text = re.sub(r"<sup>.*?</sup>", "", text, flags=re.IGNORECASE)

    # Remove any remaining HTML tags.
    text = re.sub(r"<[^>]+>", "", text)

    # Normalize whitespace.
    text = re.sub(r"\s+", " ", text)

    return text.strip().lower()


def load_lemario():
    rows = []
    pairs = set()
    ids = set()

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)

        for row_number, row in enumerate(reader, start=1):
            if not row or len(row) < 2:
                continue

            entry = row[0].strip().strip('"')
            rae_id = row[1].strip().strip('"')

            if not entry or not rae_id:
                continue

            # Ignore a possible header row.
            if entry.lower() in {"entry", "lemma", "word"} and rae_id.lower() in {
                "id",
                "rae_id",
            }:
                continue

            normalized_entry = normalize_header(entry)

            rows.append((entry, rae_id))
            pairs.add((normalized_entry, rae_id))
            ids.add(rae_id)

    return rows, pairs, ids


def load_database(connection):
    rows = connection.execute(
        """
        SELECT feed_id, header, rae_id
        FROM rae_ids
        WHERE rae_id IS NOT NULL
        """
    ).fetchall()

    pairs = set()
    ids = set()

    for feed_id, header, rae_id in rows:
        pairs.add((normalize_header(header), rae_id))
        ids.add(rae_id)

    return rows, pairs, ids


def write_csv(filename, header, rows):
    path = OUTPUT_DIR / filename

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)

    return path


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading lemario.csv...")
    csv_rows, csv_pairs, csv_ids = load_lemario()

    print("Loading rae_ids...")
    connection = sqlite3.connect(DB_PATH)

    try:
        db_rows, db_pairs, db_ids = load_database(connection)
    finally:
        connection.close()

    # ------------------------------------------------------------
    # ROW COUNTS
    # ------------------------------------------------------------

    print()
    print("=" * 60)
    print("ROW COUNTS")
    print("=" * 60)

    print(f"CSV rows:                 {len(csv_rows):,}")
    print(f"DB rows:                  {len(db_rows):,}")

    # ------------------------------------------------------------
    # UNIQUE RAE IDs
    # ------------------------------------------------------------

    ids_both = csv_ids & db_ids
    ids_csv_only = csv_ids - db_ids
    ids_db_only = db_ids - csv_ids

    print()
    print("=" * 60)
    print("UNIQUE RAE IDs")
    print("=" * 60)

    print(f"CSV unique IDs:           {len(csv_ids):,}")
    print(f"DB unique IDs:            {len(db_ids):,}")
    print(f"IDs in both:              {len(ids_both):,}")
    print(f"IDs only in CSV:          {len(ids_csv_only):,}")
    print(f"IDs only in DB:           {len(ids_db_only):,}")

    # ------------------------------------------------------------
    # UNIQUE HEADER + ID PAIRS
    # ------------------------------------------------------------

    pairs_both = csv_pairs & db_pairs
    pairs_csv_only = csv_pairs - db_pairs
    pairs_db_only = db_pairs - csv_pairs

    print()
    print("=" * 60)
    print("UNIQUE HEADER + ID PAIRS")
    print("=" * 60)

    print(f"CSV unique pairs:         {len(csv_pairs):,}")
    print(f"DB unique pairs:          {len(db_pairs):,}")
    print(f"Pairs in both:            {len(pairs_both):,}")
    print(f"Pairs only in CSV:        {len(pairs_csv_only):,}")
    print(f"Pairs only in DB:         {len(pairs_db_only):,}")

    # ------------------------------------------------------------
    # SAME ID, DIFFERENT HEADER
    # ------------------------------------------------------------

    csv_by_id = {}

    for header, rae_id in csv_pairs:
        csv_by_id.setdefault(rae_id, set()).add(header)

    db_by_id = {}

    for header, rae_id in db_pairs:
        db_by_id.setdefault(rae_id, set()).add(header)

    changed = []

    for rae_id in ids_both:
        csv_headers = csv_by_id.get(rae_id, set())
        db_headers = db_by_id.get(rae_id, set())

        if csv_headers != db_headers:
            changed.append(
                (
                    rae_id,
                    " | ".join(sorted(csv_headers)),
                    " | ".join(sorted(db_headers)),
                )
            )

    print()
    print("=" * 60)
    print("SAME ID, DIFFERENT HEADER")
    print("=" * 60)

    print(f"IDs with different headers: {len(changed):,}")

    # ------------------------------------------------------------
    # SAVE RESULTS
    # ------------------------------------------------------------

    # IDs only in CSV.
    write_csv(
        "05_ids_solo_csv.csv",
        ["rae_id"],
        [(rae_id,) for rae_id in sorted(ids_csv_only)],
    )

    # IDs only in DB.
    write_csv(
        "06_ids_solo_db.csv",
        ["rae_id"],
        [(rae_id,) for rae_id in sorted(ids_db_only)],
    )

    # Same ID but different header.
    write_csv(
        "07_mismo_id_header_diferente.csv",
        ["rae_id", "csv_header", "db_header"],
        sorted(changed),
    )

    # Exact pair matches.
    write_csv(
        "01_coinciden.csv",
        ["entry", "rae_id"],
        sorted(pairs_both),
    )

    # Pair combinations only in CSV.
    write_csv(
        "02_solo_csv.csv",
        ["entry", "rae_id"],
        sorted(pairs_csv_only),
    )

    # Pair combinations only in DB.
    write_csv(
        "03_solo_db.csv",
        ["entry", "rae_id"],
        sorted(pairs_db_only),
    )

    print()
    print("=" * 60)
    print("FILES WRITTEN")
    print("=" * 60)

    print(f"01_coinciden.csv")
    print(f"02_solo_csv.csv")
    print(f"03_solo_db.csv")
    print(f"05_ids_solo_csv.csv")
    print(f"06_ids_solo_db.csv")
    print(f"07_mismo_id_header_diferente.csv")

    print()
    print(f"Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()