import requests
import sys
import unicodedata
import json
from pathlib import Path
from dotenv import dotenv_values


# ============================================================
# CONFIGURATION
# ============================================================

RAE_KEYS_URL = "https://dle.rae.es/data/keys"

config = dotenv_values(".env")

RAE_USER = config.get("RAE_USER")
RAE_PASSWORD = config.get("RAE_PASSWORD")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36"
    ),
    "Accept": "application/json",
    "Connection": "keep-alive",
}

MAX_RESULTS = 10

QUERY_ALPHABET = "abcdefghijklmnopqrstuvwxyzñü"

OUTPUT_FILE = Path(
    "experimentos/keys_y_results.json"
)


# ============================================================
# SESSION
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# NORMALIZATION
# ============================================================

def normalize(text):
    """
    Remove acute accents for comparison.

    Returned RAE keys themselves are never modified.
    """

    text = unicodedata.normalize("NFD", text)

    return "".join(
        char
        for char in text
        if unicodedata.category(char) != "Mn"
    ).lower()


def query_char(char):
    """
    Convert an accented vowel into its base vowel for querying.

    Examples:

        á -> a
        é -> e
        í -> i
        ó -> o
        ú -> u
    """

    normalized = normalize(char)

    if len(normalized) == 1:
        return normalized

    return char


# ============================================================
# API
# ============================================================

request_count = 0
seen_prefixes = set()
all_keys = set()


def get_keys(prefix):

    global request_count

    response = session.get(
        RAE_KEYS_URL,
        params={"q": prefix},
        auth=(RAE_USER, RAE_PASSWORD),
        timeout=15,
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError(
            f"Unexpected response for {prefix!r}: {data!r}"
        )

    request_count += 1

    return data


# ============================================================
# DETERMINE RELEVANT BRANCHES
# ============================================================

def get_relevant_branches(prefix, results):

    if not results:
        return []

    prefix_norm = normalize(prefix)

    represented = set()

    # --------------------------------------------------------
    # Find branches represented in the returned results.
    # --------------------------------------------------------

    for result in results:

        result_norm = normalize(result)

        if not result_norm.startswith(prefix_norm):
            continue

        suffix = result_norm[len(prefix_norm):]

        if not suffix:
            continue

        child = query_char(suffix[0])

        if child in QUERY_ALPHABET:
            represented.add(child)

    # --------------------------------------------------------
    # Find the branch containing the final returned result.
    # --------------------------------------------------------

    last_norm = normalize(results[-1])

    if not last_norm.startswith(prefix_norm):
        return sorted(
            prefix + child
            for child in represented
        )

    suffix = last_norm[len(prefix_norm):]

    if not suffix:
        return sorted(
            prefix + child
            for child in represented
        )

    last_child = query_char(suffix[0])

    # --------------------------------------------------------
    # Every represented branch needs checking.
    #
    # A represented branch could itself contain >10 results.
    # --------------------------------------------------------

    branches = {
        prefix + child
        for child in represented
    }

    # --------------------------------------------------------
    # Any branch AFTER the last returned branch could contain
    # results that were not included in the first 10.
    # --------------------------------------------------------

    if last_child in QUERY_ALPHABET:

        position = QUERY_ALPHABET.index(last_child)

        for child in QUERY_ALPHABET[position + 1:]:
            branches.add(prefix + child)

    return sorted(branches)


# ============================================================
# CRAWLER
# ============================================================

def enumerate_prefix(prefix, depth=0):

    if prefix in seen_prefixes:
        return

    seen_prefixes.add(prefix)

    indent = "  " * depth

    results = get_keys(prefix)

    print(
        f"{indent}{prefix!r} → {len(results)}"
    )

    for key in results:
        all_keys.add(key)

    # --------------------------------------------------------
    # Fewer than 10 = complete for this prefix.
    # --------------------------------------------------------

    if len(results) < MAX_RESULTS:
        return

    # --------------------------------------------------------
    # Exactly 10 = possible hidden results.
    # --------------------------------------------------------

    branches = get_relevant_branches(
        prefix,
        results,
    )

    print(
        f"{indent}  FULL → "
        f"checking {len(branches)} branches"
    )

    for branch in branches:

        enumerate_prefix(
            branch,
            depth + 1,
        )


# ============================================================
# SAVE RESULTS
# ============================================================

def save_results():

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = {
        "prefix": "y",
        "key_count": len(all_keys),
        "request_count": request_count,
        "prefix_count": len(seen_prefixes),
        "keys": sorted(all_keys),
    }

    OUTPUT_FILE.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


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

    print("=" * 70)
    print("RAE /data/keys — Y TEST")
    print("=" * 70)
    print()

    enumerate_prefix("y")

    save_results()

    print()
    print("=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)

    print(f"Requests made:    {request_count:,}")
    print(f"Prefixes queried: {len(seen_prefixes):,}")
    print(f"Unique /keys:     {len(all_keys):,}")
    print(f"/search benchmark: 266")
    print(f"Difference:        {len(all_keys) - 266:+,}")

    print()
    print(f"Saved to:")
    print(f"  {OUTPUT_FILE}")

    print()
    print("First 50 keys:")
    print("-" * 70)

    for key in sorted(all_keys)[:50]:
        print(key)


if __name__ == "__main__":
    main()