from léxico.analyzer import dictionary_lemmatizer
from léxico.database import (
    create_lemma,
    create_lemma_raw_relation,
    get_connection,
    get_lemmas,
    get_unprocessed_raw_words,
)

LEMMATIZER = "simplemma"


def main():
    print("Iniciando Paso 02B: Lematización con simplemma...")

    connection = get_connection()

    raw_words = get_unprocessed_raw_words(
        connection,
        LEMMATIZER,
    )

    total = len(raw_words)

    print(
        f"Se encontraron {total} palabras crudas pendientes "
        f"para {LEMMATIZER}."
    )

    if total == 0:
        print(f"✓ El procesamiento con {LEMMATIZER} ya está al día.")
        connection.close()
        return

    lemma_cache = get_lemmas(connection)

    print(
        f"✓ Caché de lemas inicializado con "
        f"{len(lemma_cache)} registros."
    )

    print("\nProcesando palabras...")

    for index, raw_row in enumerate(raw_words, start=1):

        word_id = raw_row["id"]
        word_text = raw_row["word"]

        analysis = dictionary_lemmatizer(word_text)

        lemma_text = analysis.lemma.strip()
        lemma_key = lemma_text.lower()

        if lemma_key in lemma_cache:

            lemma_id = lemma_cache[lemma_key]

        else:

            lemma_id = create_lemma(
                connection,
                (
                    lemma_text,
                    analysis.part_of_speech,
                ),
                commit_index=-1,
            )

            lemma_cache[lemma_key] = lemma_id

        create_lemma_raw_relation(
            connection,
            (
                word_id,
                lemma_id,
                LEMMATIZER,
            ),
            commit_index=-1,
        )

        if index % 1000 == 0:
            connection.commit()
            print(
                f"Progreso: [{index}/{total}] "
                f"relaciones guardadas..."
            )

    print("\nVolcando lote de cierre final...")

    connection.commit()

    print("\n" + "=" * 50)
    print("¡Paso 02B completado exitosamente!")
    print(f"✓ Procesamiento completo con {LEMMATIZER}.")
    print("=" * 50)

    connection.close()


if __name__ == "__main__":
    main()