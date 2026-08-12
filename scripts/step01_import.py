import json
from pathlib import Path

from léxico.database import (
    PROJECT_ROOT,
    create_raw_word,
    get_connection,
    get_max_raw_word_rank,
    get_raw_words,
)

JSON_FILE = (
    PROJECT_ROOT
    / "datos"
    / "sinProcesar"
    / "spanish_10k.json"
)


def load_words(json_file: Path) -> list[str]:
    print("Cargando palabras desde archivo...")

    with open(json_file, "r", encoding="utf-8") as file:
        data = json.load(file)

    print(f"Se han cargado {len(data['words'])} palabras!")

    return data["words"]


def import_new_words(words: list[str]):
    connection = get_connection()
    
    existing_words = get_raw_words(connection=connection)
    next_rank = get_max_raw_word_rank(connection=connection) + 1
    
    words_to_insert = []
    
    for word in words:        
        if len(word) >= 2 and word.strip().lower() not in existing_words and word.isalpha():
            words_to_insert.append((next_rank, word, JSON_FILE.name))
            existing_words.add(word)
            next_rank += 1
                
    if words_to_insert:
        create_raw_word(connection, words_to_insert)

        print("Ejecución finalizada por completo. Volcando residuos finales...")
        connection.commit()
        print("✓ Base de datos actualizada con éxito")
        print(f"✓ Éxito total: Se agregaron {len(words_to_insert)} palabras nuevas.")
        
    else:
        print("✓ No hay palabras nuevas para ingresar. La base de datos ya está al día.")
        
    # Centralizado al final del ciclo de vida de la función para máxima seguridad de red
    connection.close()


def main():
    words = load_words(JSON_FILE)
    import_new_words(words)


if __name__ == "__main__":
    main()
