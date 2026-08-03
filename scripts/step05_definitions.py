import json

from léxico.database import *


def main():

    print("Extrayendo definiciones...")

    connection = get_connection()

    meanings = get_meanings(connection)

    total = len(meanings)

    print(f"Se encontraron {total} entradas.")

    for index, row in enumerate(meanings, start=1):

        data = json.loads(row["raw_json"])

        print()
        print(f"[{index}/{total}] {data['word']}")

        homonym_index = row["homonym_index"]

        if homonym_index is None:
            meaning = data["meanings"][0]

        else:
            meaning = next(
                (
                    m
                    for m in data["meanings"]
                    if m.get("homonym_index") == homonym_index
                ),
                None,
            )

            if meaning is None:
                print(f"No se encontró el meaning con homonym_index={homonym_index}")
                continue

        for sense in (meaning.get("senses") or []):

            create_definition(
                connection = connection,
                meaning_id = row["id"],
                sense = sense,
                commit_index = -1
            )

        if index % 25 == 0:
            print()
            print("Guardando cambios...")
            connection.commit()
            print("✓ Guardado en definitions")

    print()
    print("Ejecución finalizada. Guardando el estado final de la base de datos...")

    connection.commit()

    print("✓ Guardado")

    connection.close()

    print()
    print("¡Definiciones extraídas correctamente!")


if __name__ == "__main__":
    main()