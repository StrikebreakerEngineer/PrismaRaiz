import json

from léxico.database import *
from léxico.rae import get_rae_entry


def main():

    print()
    print("Se están extrayendo entradas de la RAE para los lemas restantes.")

    connection = get_connection()

    lemmas = get_lemmas_without_rae_entry(connection)

    total = len(lemmas)

    print(f"Se encontraron {total} lemas pendientes.")

    for index, lemma in enumerate(lemmas, start=1):

        lemma_id = lemma["id"]
        word = lemma["lemma"]

        print()
        print(f"[{index}/{total}] {word}")

        data = get_rae_entry(word)

        if not data:
            print(f'No se pudo encontrar una entrada para "{word}"')
            continue

        create_rae_entry(
            connection,
            lemma_id,
            json.dumps(data, ensure_ascii=False),
            None if index == total else index,
        )

    connection.commit()
    print()
    print("✓ Todo guardado en rae_entries")

    connection.close()

    print()
    print("¡Descarga terminada!")


if __name__ == "__main__":
    main()