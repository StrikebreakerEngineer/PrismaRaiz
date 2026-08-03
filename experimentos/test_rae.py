import json
from pathlib import Path

import requests

WORDS = ["pero"]

for word in WORDS:
    print("=" * 60)
    print(word)

    url = f"https://rae-api.com{word}"
    response = requests.get(url)

    print("Status:", response.status_code)

    # Definimos la ruta del archivo una sola vez
    output_path = Path(__file__).resolve().parent / "api_response.json"

    try:
        data = response.json()
        # Guarda el JSON formateado si la conversión es exitosa

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print("Saved full data to api_response.json")

    except requests.exceptions.JSONDecodeError:
        # Si falla (ej. si el API devuelve HTML o error 429 de texto), guarda el texto crudo

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(response.text)
            
        print("Saved raw text to api_response.json")
