import json

from léxico.database import *
from léxico.rae import get_rae_entry


def get_lemmas(connection):

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id, lemma
        FROM lemmas
        """
    )

    return cursor.fetchall()


def main():

    connection = get_connection()

    lemmas = get_lemmas(connection)


    for lemma in lemmas:

        lemma_id = lemma["id"]
        word = lemma["lemma"]

        print()
        print("Consultando:", word)


        data = get_rae_entry(word)


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

            for sense in meaning_group["senses"]:

                create_definition(
                    connection,
                    entry_id,
                    sense
                )


        print("Guardado:", word)



if __name__ == "__main__":
    main()