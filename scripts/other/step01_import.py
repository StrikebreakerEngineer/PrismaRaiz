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
    / "spanish_650k.json"
)


def load_words(json_file: Path) -> list[str]:
    """
    Carga las palabras desde un archivo JSON.
    """

    print("Cargando palabras desde archivo...")

    with open(json_file, "r", encoding="utf-8") as file:
        data = json.load(file)

    print(
        f"Se han cargado {len(data['words'])} palabras!"
    )

    return data["words"]


def import_new_words(words: list[str]) -> None:
    """
    Importa las palabras y sus fuentes en las tablas t01a y t01b.

    t01a contiene cada palabra una sola vez.

    t01b registra en qué fuente apareció cada palabra
    y cuál era su posición original (rank).
    """

    connection = get_connection()

    source = JSON_FILE.name

    for index, word in enumerate( words, start=1):

        word = word.strip().lower()

        if not word.isalpha():
            continue

        word_id = create_raw_word(connection, word, commit_index = -1)

        create_raw_word_source(connection, word_id, index,source, commit_index = -1)

        if index % 2000 == 0:
            connection.commit()
            print(f"Procesadas {index} palabras...")

    connection.commit()
    print("✓ Base de datos actualizada con éxito")

    connection.close()


def main():
    words = load_words(JSON_FILE)

    import_new_words(words)


if __name__ == "__main__":
    main()