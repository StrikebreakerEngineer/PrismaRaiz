import requests

RAE_API = "https://rae-api.com/api/words"


def get_rae_entry(word: str):

    response = requests.get(
        f"{RAE_API}/{word}",
        timeout=10
    )

    if response.status_code != 200:
        return None

    data = response.json()

    if not data.get("ok"):
        return None

    return data["data"]