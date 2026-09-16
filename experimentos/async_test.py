import asyncio
import html
import re
import sqlite3
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

# ============================================================
# CONFIGURATION
# ============================================================

config = dotenv_values(".env")
RAE_USER = config.get("RAE_USER")
RAE_PASSWORD = config.get("RAE_PASSWORD")

RAE_SEARCH_URL = "https://dle.rae.es/data/search"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "datos" / "baseDeDatos" / "async.db"
TABLE_NAME = "rae_async_b"
METHOD = "async_prefix_tree"

ALPHABET = "aábcdeéfghiíjklmnñoópqrstuúüvwxyz-"
MAX_PREFIX_LENGTH = 30
CONCURRENCY_LIMIT = 100
REQUEST_TIMEOUT = 15.0

TAG_RE = re.compile(r"<[^>]+>")


def clean_header(header):
    if not header:
        return ""
    return TAG_RE.sub("", html.unescape(header)).strip()


def create_database():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL,
                rae_id TEXT NOT NULL UNIQUE,
                method TEXT NOT NULL,
                time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_rae_id ON {TABLE_NAME}(rae_id);")
        conn.commit()
    finally:
        conn.close()


async def fetch_prefix(client, semaphore, prefix):
    params = {"w": prefix, "m": 31, "f": 1, "t": 200}
    async with semaphore:
        for attempt in range(1, 6):
            try:
                response = await client.get(
                    RAE_SEARCH_URL,
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                return prefix, response.json().get("res", [])
            except Exception:
                if attempt == 5:
                    return prefix, []
                await asyncio.sleep(0.3 * (2 ** (attempt - 1)))
        return prefix, []


async def db_writer_worker(queue):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    
    sql = f"INSERT OR IGNORE INTO {TABLE_NAME} (word, rae_id, method) VALUES (?, ?, ?)"
    buffer = []
    inserted_count = 0

    try:
        while True:
            item = await queue.get()
            if item is None:
                if buffer:
                    before = conn.total_changes
                    conn.executemany(sql, buffer)
                    conn.commit()
                    inserted_count += (conn.total_changes - before)
                queue.task_done()
                break
            
            buffer.append(item)
            if len(buffer) >= 1000:
                before = conn.total_changes
                conn.executemany(sql, buffer)
                conn.commit()
                inserted_count += (conn.total_changes - before)
                buffer.clear()
            queue.task_done()
    finally:
        conn.close()
    return inserted_count


async def main():
    if not RAE_USER or not RAE_PASSWORD:
        print("ERROR: Missing RAE credentials in .env", file=sys.stderr)
        sys.exit(1)

    create_database()
    
    current_batch = ["a"]
    seen_prefixes = {"a"}
    total_requests = 0
    total_results = 0
    started = time.monotonic()

    print(f"\n================================================", flush=True)
    print(f"RAE ASYNC CRAWLER ('a' root -> async.db)", flush=True)
    print(f"================================================", flush=True)
    print(f"Concurrency Limit: {CONCURRENCY_LIMIT}", flush=True)
    print(f"Database: {DB_PATH}", flush=True)
    print(f"================================================\n", flush=True)

    queue = asyncio.Queue()
    writer_task = asyncio.create_task(db_writer_worker(queue))

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Connection": "keep-alive",
    }
    limits = httpx.Limits(max_keepalive_connections=CONCURRENCY_LIMIT, max_connections=CONCURRENCY_LIMIT * 2)
    
    try:
        auth = httpx.BasicAuth(RAE_USER, RAE_PASSWORD)
        async with httpx.AsyncClient(http2=False, limits=limits, headers=headers, auth=auth) as client:
            semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
            batch_num = 0

            while current_batch:
                batch_num += 1
                print(f"\n================================================", flush=True)
                print(f"BATCH {batch_num}", flush=True)
                print(f"================================================", flush=True)
                print(f"Prefixes submitted: {len(current_batch):,}", flush=True)

                tasks = [fetch_prefix(client, semaphore, p) for p in current_batch]
                
                next_batch = []
                batch_requests = 0
                batch_results = 0
                batch_new_prefixes = 0
                batch_errors = 0
                completed_count = 0
                total_in_batch = len(tasks)

                for coro in asyncio.as_completed(tasks):
                    completed_count += 1
                    try:
                        prefix, results = await coro
                    except Exception as exc:
                        batch_errors += 1
                        continue

                    batch_requests += 1
                    total_requests += 1
                    result_count = len(results)
                    batch_results += result_count
                    total_results += result_count

                    if results:
                        for r in results:
                            rae_id = r.get("id")
                            if rae_id:
                                word = clean_header(r.get("header", ""))
                                await queue.put((word, rae_id, METHOD))

                        if len(prefix) < MAX_PREFIX_LENGTH:
                            for char in ALPHABET:
                                child = prefix + char
                                if child not in seen_prefixes:
                                    seen_prefixes.add(child)
                                    next_batch.append(child)
                                    batch_new_prefixes += 1

                    print(
                        f"\r[{completed_count}/{total_in_batch}] "
                        f"{prefix:<18} "
                        f"results={result_count:<4} "
                        f"next={len(next_batch):<7}",
                        end="",
                        flush=True,
                    )

                print()
                elapsed = time.monotonic() - started
                req_per_sec = total_requests / elapsed if elapsed > 0 else 0

                print(f"Requests this batch: {batch_requests:,}", flush=True)
                print(f"Results this batch:  {batch_results:,}", flush=True)
                print(f"New prefixes:        {batch_new_prefixes:,}", flush=True)
                print(f"Errors/retries:      {batch_errors:,}", flush=True)
                print(f"Total prefixes seen: {len(seen_prefixes):,}", flush=True)
                print(f"Total requests:      {total_requests:,}", flush=True)
                print(f"Requests/sec:        {req_per_sec:.2f}", flush=True)
                print(f"Next batch size:     {len(next_batch):,}", flush=True)

                current_batch = next_batch

    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n\n[INTERRUPT] Caught shutdown signal. Cleaning up...", flush=True)
    finally:
        await queue.put(None)
        inserted = await writer_task
        print(f"\nCompleted. Total requests: {total_requests:,}, Total DB inserts processed: {inserted:,}\n", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass