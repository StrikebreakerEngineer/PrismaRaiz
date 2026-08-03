import time
import requests
from dotenv import dotenv_values
from léxico.analyzer import remove_accents

# - Configuración
config = dotenv_values(".env") # Carga el archivo .env como un diccionario ordinario
RAE_API_KEY = config.get("RAE_API_KEY")# Accede la clave usando la sintaxis de diccionario
URL = "https://rae-api.com/api/words" # API URL
HEADERS = { # El encabezado
    "X-API-Key": RAE_API_KEY
}


def _request_rae(word: str):
    while True:

        response = requests.get(
            f"{URL}/{word}",
            headers=HEADERS,
            timeout=15,
        )

        # Límite de tasa
        if response.status_code == 429:

            data = response.json()

            retry = data.get("retry_after", 60)

            print(f"Error de límite de tasa. Esperando {retry} segundos...")

            time.sleep(retry)

            continue

        # La palabra no existe en el diccionario
        if response.status_code == 404:
            return None

        response.raise_for_status()

        data = response.json()

        if not data.get("ok"):
            return None

        return data["data"]


def get_rae_entry(word: str):
    print(f"Buscando {word} en el diccionario RAE")

    try:
        data = _request_rae(word)

        if data:
            return data

        simplified = remove_accents(word)

        if simplified != word:
            return _request_rae(simplified)

        return None

    except requests.RequestException as error:
        print(f"Error consultando '{word}': {error}")
        return None


def main():
    print(get_rae_entry("ser"))


if __name__ == "__main__":
    main()