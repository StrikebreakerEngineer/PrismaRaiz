from léxico.analyzer import analyze_word
from léxico.database import *


def main():
    connection = get_connection()

    for raw_word in get_raw_words(connection):
        Analysis = analyze_word(raw_word["word"])

    lemma_id = get_or_create_lemma(
        connection,
        Analysis.lemma,
        Analysis.part_of_speech,
)

    create_relation(
        connection,
        raw_word["id"],
        lemma_id,
        )

    connection.close()

    print('¡Lemas extraídos correctamente!')


if __name__ == '__main__':
    main()