import json

from léxico.database import *
from léxico.rae import get_rae_entry


def main():

    print("Se están extrayendo entradas de la RAE para los lemas restantes")

    connection = get_connection()

    lemmas = get_lemmas_without_rae_entry(connection)

    total = len(lemmas)

    print(f"Se encontraron {total} lemas pendientes.")

    for index, lemma in enumerate(lemmas, start=1):

        lemma_id = lemma["id"]
        word = lemma["lemma"]

        print()
        print(f"[{index}/{total}] {word}")

        try:
            data = get_rae_entry(word)

        except Exception as error:
            print(f"Error: {error}")
            continue

        if data is None:
            print("No encontrado")
            continue

        create_rae_entry(connection, lemma_id, json.dumps(data, ensure_ascii=False,), (None if index is total else index))

    connection.close()

    print()
    print("¡Descarga terminada!")


if __name__ == "__main__":
    main()