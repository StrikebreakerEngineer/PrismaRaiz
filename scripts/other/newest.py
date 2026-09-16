import json
from pathlib import Path

from léxico.database import (
    PROJECT_ROOT,
    create_raw_word,
    create_raw_word_source,
    get_connection,
)

JSON_FILE = (
    PROJECT_ROOT
    / "datos"
    / "sinProcesar"
    / "spanish_words.json"
)


def load_words(json_file: Path) -> list[str]:
    """
    Carga las palabras desde un archivo JSON.

    El JSON debe contener directamente una lista:

    [
        "a",
        "aba",
        "ababa",
        ...
    ]
    """

    print(f"Cargando palabras desde {json_file.name}...")

    with open(json_file, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(
            "El archivo JSON debe contener directamente una lista de palabras."
        )

    print(f"Se han cargado {len(data):,} palabras!")
    print()

    return data


def import_new_words(words: list[str], source: str) -> None:
    """
    Importa las palabras y sus fuentes.

    Cuenta por separado:

    - palabras procesadas
    - palabras nuevas añadidas a t01a
    - palabras que ya existían en t01a
    - palabras descartadas por no ser alfabéticas
    """

    connection = get_connection()

    processed = 0
    added = 0
    existing = 0
    discarded = 0

    try:
        for index, word in enumerate(words, start=1):

            processed += 1

            word = word.strip().lower()

            # Descartar palabras no válidas
            if not word.isalpha():
                discarded += 1

            else:
                # create_raw_word devuelve:
                #
                #   (word_id, was_created)
                #
                # was_created = True  -> palabra nueva
                # was_created = False -> ya existía
                word_id, was_created = create_raw_word(
                    connection,
                    word,
                    commit_index=-1,
                )

                if word_id is not None:

                    if was_created:
                        added += 1
                    else:
                        existing += 1

                    # Registrar la fuente y posición original
                    create_raw_word_source(
                        connection,
                        word_id,
                        index,
                        source,
                        commit_index=-1,
                    )

            # Mostrar progreso cada 2.000 palabras
            if index % 2000 == 0:
                connection.commit()

                print(
                    f"Procesadas: {index:,} | "
                    f"Añadidas: {added:,} | "
                    f"Ya existían: {existing:,} | "
                    f"Descartadas: {discarded:,}"
                )

        connection.commit()

        print()
        print("✓ Importación terminada")
        print(f"  Palabras procesadas:  {processed:,}")
        print(f"  Palabras añadidas:    {added:,}")
        print(f"  Palabras ya existían: {existing:,}")
        print(f"  Palabras descartadas: {discarded:,}")

    finally:
        connection.close()


def main():
    words = load_words(JSON_FILE)

    import_new_words(
        words,
        source=JSON_FILE.name,
    )


if __name__ == "__main__":
    main()