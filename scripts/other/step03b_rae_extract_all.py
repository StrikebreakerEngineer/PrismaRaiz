import json

import requests

from léxico.database import (
    create_rae_entry,
    get_connection,
    get_pending_allwords_words,
    get_rae_status,
    rae_entry_exists,
    set_rae_status,
)
from léxico.rae import UNOFFICIAL_RAE_API_KEY, DailyQuotaExceeded, get_rae_entry


def extract_rae_entries():

    connection = get_connection()

    words = get_pending_allwords_words(connection)

    total = len(words)

    print()
    print("=" * 60)
    print("ALLWORDS → RAE DOWNLOADER")
    print("=" * 60)
    print()
    print(f"Pending words: {total}")

    downloaded = 0
    existing = 0
    missing = 0

    with requests.Session() as session:
        session.headers.update({"X-API-Key": UNOFFICIAL_RAE_API_KEY})

        try:
            for index, (word_id, word) in enumerate(words, start=1):
                status = get_rae_status(connection, word_id)

                if status == "completed":
                    continue

                if rae_entry_exists(connection, word):
                    set_rae_status(connection, word_id, "completed")

                    existing += 1

                    continue

                print(f"[{index}/{total}] {word}")

                data = get_rae_entry(session, word)

                if data:
                    create_rae_entry(connection, word, None, json.dumps(data, ensure_ascii=False), commit_index = index, commit_batch = 25)

                    set_rae_status(connection, word_id, "completed")

                    downloaded += 1

                else:
                    set_rae_status(connection, word_id, "missing")

                    missing += 1

                if index % 25 == 0:
                    print(f"{index}/{total} | downloaded: {downloaded} | existing: {existing} | missing: {missing}")

        except DailyQuotaExceeded:
            print()
            print("🚨 Daily RAE quota reached.")

        finally:
            connection.close()

    print()
    print("Finished.")


def main():
    extract_rae_entries()


if __name__ == "__main__":
    main()