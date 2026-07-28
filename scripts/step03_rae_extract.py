import json

from léxico.database import *
from léxico.rae import get_rae_entry


def main():

    connection = get_connection()

    lemmas = get_lemmas_without_rae_entry(connection)

    total_cycles = len(lemmas)

    for cycle, lemma in enumerate(lemmas, start = 1):

        lemma_id = lemma["id"]
        word = lemma["lemma"]

        print()
        print("Consultando:", word)

        try:
            data = get_rae_entry(word)

        except Exception as e:
            print(f"Error con {lemma.lemma}: {e}")
            continue

        if not data:
            print("No encontrado")
            continue

        entry_id = create_rae_entry(
            connection,
            lemma_id,
            json.dumps(
                data.get("meanings")[0].get("origin"),
                ensure_ascii=False
            ),
            json.dumps(
                data,
                ensure_ascii=False
            )
        )

        for meaning_group in data["meanings"]:

            senses = meaning_group.get("senses")

            if not senses:
                print(f"'{word}' tiene un grupo sin acepciones.")
                continue

            for sense in senses:
                create_definition(
                    connection,
                    entry_id,
                    sense,
                )

        print("Guardado:", word)

        if cycle % 24 == 0:
                print(f"{cycle}/{total_cycles}")


if __name__ == "__main__":
    main()