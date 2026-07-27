import requests
import json
from pathlib import Path

WORDS = [
    "zaparrastraríamos"
]

for word in WORDS:
    print("=" * 60)
    print(word)

    url = f"https://rae-api.com/api/words/{word}"

    response = requests.get(url)

    print("Status:", response.status_code)

    try:
        data = response.json()
        # Save the entire JSON payload to a file
        with open(Path(__file__).resolve().parent/"api_response.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("Saved full data to api_response.json")

    except Exception:
        with open(Path(__file__).resolve().parent/"api_response.json", "w", encoding="utf-8") as f:
            f.write(response.text)
        print("Saved raw text to api_response.txt")