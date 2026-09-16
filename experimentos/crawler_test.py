import html
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from dotenv import dotenv_values

# ============================================================
# CONFIGURATION
# ============================================================

if len(sys.argv) < 2:
    print("Usage: python -m path.to.script <letter>", file=sys.stderr)
    sys.exit(1)

TARGET_LETTER = sys.argv[1].lower().strip()

if len(TARGET_LETTER) != 1:
    print("ERROR: Provide a single letter", file=sys.stderr)
    sys.exit(1)

config = dotenv_values(".env")
RAE_USER = config.get("RAE_USER")
RAE_PASSWORD = config.get("RAE_PASSWORD")

RAE_SEARCH_URL = "https://dle.rae.es/data/search"

ALPHABET = "aábcdeéfghiíjklmnñoópqrstuúüvwxyz-"
MAX_PREFIX_LENGTH = 30
DEFAULT_WORKERS = 200
REQUEST_TIMEOUT = 15
MAX_RETRIES = 5

TAG_RE = re.compile(r"<[^>]+>")


def clean_header(header):
    if not header:
        return ""
    return TAG_RE.sub("", html.unescape(header)).strip()


_thread_local = None


def get_session():
    global _thread_local
    if _thread_local is None:
        import threading
        _thread_local = threading.local()

    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Connection": "keep-alive",
        })
        adapter = requests.adapters.HTTPAdapter(pool_connections=50, pool_maxsize=50, max_retries=0)
        session.mount("https://", adapter)
        _thread_local.session = session
    return session


def search_prefix(prefix):
    session = get_session()

    params = {
        "w": prefix,
        "m": 31
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                RAE_SEARCH_URL,
                params=params,
                auth=(RAE_USER, RAE_PASSWORD),
                timeout=REQUEST_TIMEOUT,
            )

            response.raise_for_status()

            return response.json().get("res", [])

        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise RuntimeError(
                    f"Failed {prefix!r}: {exc}"
                )

            time.sleep(0.3 * (2 ** (attempt - 1)))


def process_prefix(prefix):
    results = search_prefix(prefix)

    children = []

    if results and len(prefix) < MAX_PREFIX_LENGTH:
        children = [
            prefix + char
            for char in ALPHABET
        ]

    return prefix, results, children


def main():

    if not RAE_USER or not RAE_PASSWORD:
        print("ERROR: Missing RAE credentials", file=sys.stderr)
        sys.exit(1)

    current_batch = [TARGET_LETTER]
    seen_prefixes = {TARGET_LETTER}

    total_requests = 0
    empty_responses = 0
    non_empty_responses = 0
    total_results = 0

    started = time.monotonic()

    with ThreadPoolExecutor(max_workers=DEFAULT_WORKERS) as executor:

        batch_num = 0

        while current_batch:
            batch_num += 1

            print(f"\n========== BATCH {batch_num} ==========")
            print(f"Prefixes: {len(current_batch):,}")

            futures = {
                executor.submit(process_prefix, p): p
                for p in current_batch
            }

            next_batch = []

            completed = 0

            for future in as_completed(futures):

                prefix = futures[future]

                try:
                    returned_prefix, results, children = future.result()

                except Exception as exc:
                    print(
                        f"\nERROR {prefix}: {exc}",
                        file=sys.stderr
                    )
                    continue


                total_requests += 1
                completed += 1

                count = len(results)

                total_results += count


                if count == 0:
                    empty_responses += 1
                else:
                    non_empty_responses += 1

                    for child in children:
                        if child not in seen_prefixes:
                            seen_prefixes.add(child)
                            next_batch.append(child)


                print(
                    f"\r[{completed}/{len(futures)}] "
                    f"{returned_prefix:<20} "
                    f"results={count:<4} "
                    f"next={len(next_batch):<8}",
                    end="",
                    flush=True
                )


            elapsed = time.monotonic() - started
            rps = total_requests / elapsed if elapsed else 0

            print("\n")
            print(f"Requests:          {total_requests:,}")
            print(f"Empty responses:   {empty_responses:,}")
            print(f"Non-empty:         {non_empty_responses:,}")
            print(f"Total results:     {total_results:,}")
            print(f"Prefixes seen:     {len(seen_prefixes):,}")
            print(f"Requests/sec:      {rps:.2f}")
            print(f"Next batch size:   {len(next_batch):,}")

            current_batch = next_batch


def test_pagination(prefix):

    base = {
        "w": prefix,
        "m": 31
    }

    tests = [
        {"page": 2},
        {"p": 2},
        {"offset": 20},
        {"start": 20},
        {"from": 20},
        {"skip": 20},
        {"limit": 200},
        {"n": 200},
        {"size": 200},
    ]

    for extra in tests:
        params = base | extra

        r = requests.get(
            RAE_SEARCH_URL,
            params=params,
            auth=(RAE_USER, RAE_PASSWORD)
        )

        try:
            data = r.json()
            results = data.get("res", [])

            print(extra, len(results))

        except Exception:
            print(extra, r.text[:100])


def inspect_response(prefix):
    session = requests.Session()

    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Connection": "keep-alive",
    })

    response = session.get(
        RAE_SEARCH_URL,
        params={
            "w": prefix,
            "m": 31
        },
        auth=(RAE_USER, RAE_PASSWORD),
        timeout=15
    )

    print(response.url)
    print("STATUS:", response.status_code)
    print("HEADERS:")
    print(response.headers)

    print("\nFIRST 500 CHARACTERS:")
    print(response.text[:500])

    if response.status_code == 200:
        data = response.json()

        print("\nJSON KEYS:")
        print(data.keys())

        for key, value in data.items():
            print(
                key,
                type(value),
                len(value) if hasattr(value, "__len__") else ""
            )



if __name__ == "__main__":
    inspect_response("l")