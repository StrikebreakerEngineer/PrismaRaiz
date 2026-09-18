import csv
import json
import re
import sqlite3
import threading
import time
from pathlib import Path

import requests
from dotenv import dotenv_values
from concurrent.futures import ThreadPoolExecutor, as_completed


# ============================================================
# CONFIGURATION
# ============================================================

DB_PATH = Path("datos/basededatos/crawler.db")
MISSING_IDS_PATH = Path(
    "datos/procesado/comparacion_lemario/05_ids_solo_csv.csv"
)
CSV_PATH = Path("datos/sinProcesar/lemario.csv")

OUTPUT_DIR = Path(
    "datos/procesado/comparacion_lemario/investigacion_missing"
)

RAE_SEARCH_URL = "https://dle.rae.es/data/search"

DEFAULT_WORKERS = 100
REQUEST_TIMEOUT = 15
MAX_RETRIES = 5


# ============================================================
# AUTH / HEADERS
# ============================================================

ENV = dotenv_values(".env")

RAE_USER = ENV.get("RAE_USER")
RAE_PASSWORD = ENV.get("RAE_PASSWORD")

if not RAE_USER or not RAE_PASSWORD:
    raise RuntimeError(
        "No se encontraron RAE_USER y/o RAE_PASSWORD en .env"
    )

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Connection": "keep-alive",
}


# ============================================================
# THREAD-LOCAL SESSION
# ============================================================

_thread_local = threading.local()


def get_session():
    if not hasattr(_thread_local, "session"):
        session = requests.Session()
        session.auth = (RAE_USER, RAE_PASSWORD)
        session.headers.update(HEADERS)
        _thread_local.session = session

    return _thread_local.session


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_header(text):
    """
    Make CSV entries and RAE headers comparable.

    Removes:
        <sup>1</sup>
        other HTML
        excess whitespace

    Does NOT remove accents.
    """

    if text is None:
        return ""

    text = str(text).strip()

    # Remove homonym markers such as <sup>1</sup>.
    text = re.sub(
        r"<sup>.*?</sup>",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Remove remaining HTML tags.
    text = re.sub(
        r"<[^>]+>",
        "",
        text,
    )

    # Normalize whitespace.
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip().lower()


# ============================================================
# LOAD OLD CSV
# ============================================================

def load_lemario():
    """
    Returns:

        dict[rae_id] = entry

    """

    result = {}

    with CSV_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.reader(f)

        for row in reader:

            if len(row) < 2:
                continue

            entry = row[0].strip().strip('"')
            rae_id = row[1].strip().strip('"')

            if not entry or not rae_id:
                continue

            if (
                entry.lower() in {"entry", "lemma", "word"}
                and rae_id.lower() in {"id", "rae_id"}
            ):
                continue

            result[rae_id] = entry

    return result


# ============================================================
# LOAD MISSING IDs
# ============================================================

def load_missing_ids():
    ids = []

    with MISSING_IDS_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            rae_id = row["rae_id"].strip()

            if rae_id:
                ids.append(rae_id)

    return ids


# ============================================================
# QUERY RAE
# ============================================================

def query_rae(entry):

    session = get_session()

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            response = session.get(
                RAE_SEARCH_URL,
                params={"w": entry},
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 200:

                return {
                    "status": "OK",
                    "http_status": 200,
                    "data": response.json(),
                    "error": "",
                }

            if response.status_code in {
                429,
                500,
                502,
                503,
                504,
                520,
            }:

                time.sleep(
                    min(2 ** (attempt - 1), 10)
                )

                continue

            return {
                "status": "HTTP_ERROR",
                "http_status": response.status_code,
                "data": None,
                "error": response.text[:500],
            }

        except Exception as e:

            if attempt == MAX_RETRIES:

                return {
                    "status": "ERROR",
                    "http_status": None,
                    "data": None,
                    "error": repr(e),
                }

            time.sleep(
                min(2 ** (attempt - 1), 10)
            )

    return {
        "status": "ERROR",
        "http_status": None,
        "data": None,
        "error": "Maximum retries exceeded",
    }


# ============================================================
# INVESTIGATE ONE ENTRY
# ============================================================

def investigate(entry, missing_ids):

    response = query_rae(entry)

    if response["status"] != "OK":

        return {
            "entry": entry,
            "normalized_entry": normalize_header(entry),
            "missing_ids": sorted(missing_ids),
            "status": response["status"],
            "http_status": response["http_status"],
            "returned": [],
            "same_ids": [],
            "matching_headers": [],
            "different_headers": [],
            "error": response["error"],
            "raw_json": "",
        }

    data = response["data"]

    results = []

    if isinstance(data, dict):
        results = data.get("res", [])

    old_normalized = normalize_header(entry)

    returned = []

    for item in results:

        current_id = item.get("id", "")
        current_header = item.get("header", "")

        normalized_current = normalize_header(
            current_header
        )

        returned.append(
            {
                "id": current_id,
                "header": current_header,
                "normalized_header": normalized_current,
            }
        )

    missing_id_set = set(missing_ids)

    same_ids = sorted(
        {
            item["id"]
            for item in returned
            if item["id"] in missing_id_set
        }
    )

    matching_headers = [
        item
        for item in returned
        if item["normalized_header"] == old_normalized
    ]

    different_headers = [
        item
        for item in returned
        if item["normalized_header"] != old_normalized
    ]

    current_matching_ids = sorted(
        {
            item["id"]
            for item in matching_headers
            if item["id"]
        }
    )

    if same_ids:

        status = "SAME_ID"

    elif current_matching_ids:

        if len(current_matching_ids) == 1:
            status = "ID_CHANGED"
        else:
            status = "MULTIPLE_CURRENT_IDS"

    elif returned:

        status = "RELATED_RESULT"

    else:

        status = "NOT_FOUND"

    return {
        "entry": entry,
        "normalized_entry": old_normalized,
        "missing_ids": sorted(missing_id_set),
        "status": status,
        "http_status": response["http_status"],
        "returned": returned,
        "same_ids": same_ids,
        "matching_headers": matching_headers,
        "different_headers": different_headers,
        "error": "",
        "raw_json": json.dumps(
            data,
            ensure_ascii=False,
        ),
    }


# ============================================================
# MAIN
# ============================================================

def main():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("Loading old lemario.csv...")
    lemario = load_lemario()

    print("Loading missing IDs...")
    missing_ids = load_missing_ids()

    print()
    print(
        f"Missing IDs to investigate: "
        f"{len(missing_ids):,}"
    )

    # Group missing IDs by their old CSV entry.
    entry_to_ids = {}

    for rae_id in missing_ids:

        entry = lemario.get(rae_id)

        if entry is None:
            continue

        entry_to_ids.setdefault(
            entry,
            set(),
        ).add(rae_id)

    entries = list(entry_to_ids.items())

    print(
        f"Unique entries to query:   "
        f"{len(entries):,}"
    )

    print()
    print("Querying RAE...")
    print()

    results = []

    completed = 0
    total = len(entries)

    start_time = time.perf_counter()

    with ThreadPoolExecutor(
        max_workers=DEFAULT_WORKERS
    ) as executor:

        futures = {
            executor.submit(
                investigate,
                entry,
                sorted(ids),
            ): entry
            for entry, ids in entries
        }

        for future in as_completed(futures):

            entry = futures[future]

            try:

                result = future.result()

            except Exception as e:

                result = {
                    "entry": entry,
                    "normalized_entry": normalize_header(
                        entry
                    ),
                    "missing_ids": sorted(
                        entry_to_ids[entry]
                    ),
                    "status": "ERROR",
                    "http_status": None,
                    "returned": [],
                    "same_ids": [],
                    "matching_headers": [],
                    "different_headers": [],
                    "error": repr(e),
                    "raw_json": "",
                }

            results.append(result)

            completed += 1

            if (
                completed % 100 == 0
                or completed == total
            ):

                elapsed = (
                    time.perf_counter()
                    - start_time
                )

                rate = (
                    completed / elapsed
                    if elapsed
                    else 0
                )

                print(
                    f"{completed:,}/{total:,} "
                    f"({completed / total * 100:.1f}%) "
                    f"{rate:.1f} queries/s"
                )

    elapsed = (
        time.perf_counter()
        - start_time
    )

    # ========================================================
    # BUILD ID-LEVEL RESULTS
    # ========================================================

    id_results = []

    for result in results:

        returned_ids = [
            item["id"]
            for item in result["returned"]
            if item["id"]
        ]

        returned_headers = [
            item["header"]
            for item in result["returned"]
            if item["header"]
        ]

        matching_ids = [
            item["id"]
            for item in result["matching_headers"]
            if item["id"]
        ]

        matching_header_text = [
            item["header"]
            for item in result["matching_headers"]
            if item["header"]
        ]

        for old_id in result["missing_ids"]:

            id_results.append(
                {
                    "old_rae_id": old_id,
                    "old_entry": result["entry"],
                    "status": result["status"],
                    "current_rae_ids": " | ".join(
                        returned_ids
                    ),
                    "current_headers": " | ".join(
                        returned_headers
                    ),
                    "matching_current_ids": " | ".join(
                        matching_ids
                    ),
                    "matching_current_headers": " | ".join(
                        matching_header_text
                    ),
                    "error": result["error"],
                }
            )

    # ========================================================
    # SAVE MASTER RESULT
    # ========================================================

    master_path = (
        OUTPUT_DIR
        / "01_investigacion_por_id.csv"
    )

    with master_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "old_rae_id",
                "old_entry",
                "status",
                "current_rae_ids",
                "current_headers",
                "matching_current_ids",
                "matching_current_headers",
                "error",
            ],
        )

        writer.writeheader()
        writer.writerows(
            sorted(
                id_results,
                key=lambda x: (
                    x["status"],
                    x["old_entry"].lower(),
                    x["old_rae_id"],
                ),
            )
        )

    # ========================================================
    # SAVE CATEGORY FILES
    # ========================================================

    statuses = sorted(
        {
            result["status"]
            for result in id_results
        }
    )

    for status in statuses:

        path = (
            OUTPUT_DIR
            / f"{status}.csv"
        )

        rows = [
            result
            for result in id_results
            if result["status"] == status
        ]

        with path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as f:

            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "old_rae_id",
                    "old_entry",
                    "status",
                    "current_rae_ids",
                    "current_headers",
                    "matching_current_ids",
                    "matching_current_headers",
                    "error",
                ],
            )

            writer.writeheader()
            writer.writerows(rows)

    # ========================================================
    # SAVE RAW RESULTS
    # ========================================================

    raw_path = (
        OUTPUT_DIR
        / "02_investigacion_raw.jsonl"
    )

    with raw_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        for result in sorted(
            results,
            key=lambda x: x["entry"].lower(),
        ):

            f.write(
                json.dumps(
                    result,
                    ensure_ascii=False,
                )
                + "\n"
            )

    # ========================================================
    # SUMMARY
    # ========================================================

    counts = {}

    for result in id_results:

        status = result["status"]

        counts[status] = (
            counts.get(status, 0) + 1
        )

    print()
    print("=" * 60)
    print("RESULT")
    print("=" * 60)

    print(
        f"IDs investigated:       "
        f"{len(id_results):,}"
    )

    print(
        f"Unique entries queried: "
        f"{len(results):,}"
    )

    print()

    for status in [
        "SAME_ID",
        "ID_CHANGED",
        "MULTIPLE_CURRENT_IDS",
        "RELATED_RESULT",
        "NOT_FOUND",
        "ERROR",
    ]:

        print(
            f"{status:24} "
            f"{counts.get(status, 0):,}"
        )

    print()
    print(
        f"Time: {elapsed:.1f} seconds"
    )

    print()
    print("Output:")
    print(master_path)
    print(raw_path)


if __name__ == "__main__":
    main()