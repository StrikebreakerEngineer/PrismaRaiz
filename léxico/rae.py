import time

import requests
from dotenv import dotenv_values

# - Configuración
config = dotenv_values(".env") # Carga el archivo .env como un diccionario ordinario
RAE_API_KEY = config.get("RAE_API_KEY")# Accede la clave usando la sintaxis de diccionario
URL = "https://rae-api.com/api/words" # API URL
HEADERS = { # El encabezado
    "X-API-Key": RAE_API_KEY
}


def get_rae_entry(word: str):

    while True:

        response = requests.get(
            f"{URL}/{word}",
            headers=HEADERS,
            timeout=15,
        )

        # Rate limit
        if response.status_code == 429:

            data = response.json()

            retry = data.get("retry_after", 60)

            print(f"Límite de tasa. Esperando {retry} segundos...")

            time.sleep(retry)

            continue

        response.raise_for_status()

        data = response.json()

        if not data.get("ok"):
            return None

        return data["data"]


def main():
    print(get_rae_entry("ser"))


if __name__ == "__main__":
    main()