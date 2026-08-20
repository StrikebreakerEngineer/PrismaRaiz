import json

from léxico.database import *


def main():

    print("Extrayendo meanings...")

    connection = get_connection()

    entries = get_rae_entries(connection)

    total = len(entries)

    print(f"Se encontraron {total} entradas.")

    for index, entry in enumerate(entries, start=1):

        print()
        print(f"[{index}/{total}]")

        data = json.loads(entry["raw_json"])

        for meaning in data["meanings"]:

            create_meaning(connection, entry["id"], meaning, index)

    print()
    print("Ejecución finalizada. Guardando el estado final de la base de datos...")
    connection.commit()
    print("✓ Guardado")

    connection.close()

    print()
    print("¡Meanings extraídos correctamente!")


if __name__ == "__main__":
    main()