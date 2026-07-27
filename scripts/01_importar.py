import json
import sqlite3
from pathlib import Path

# Variables globales
project_root = Path(__file__).resolve().parent.parent

schema_file = (
    project_root
    / "datos"
    / "baseDeDatos"
    / "schema.sql"
    )

database_file = (
        project_root
        / "datos"
        / "baseDeDatos"
        / "léxico.db"
    )

json_file = (
    project_root
    / "datos"
    / "sinProcesar"
    / "spanish_1k.json"
)


def load_words(json_file: Path) -> list[str]:
    print("Cargando palabras desde archivo...")

    with open(json_file, "r", encoding="utf-8") as file:
        data = json.load(file)

    print(f"Se han cargado {len(data["words"])} palabras!")

    return data["words"]


def create_database():
    print("Creando base de datos...")
    print(f'Raíz del proyecto: {project_root}')

    connection = sqlite3.connect(database_file)
    cursor = connection.cursor()

    with open(schema_file, "r", encoding="utf-8") as file:
        schema = file.read()

    cursor.executescript(schema)
        
    connection.commit()
    connection.close()
    
    print("Base de datos creada correctamente!")


def import_words(words: list[str], json_file: Path) -> None:
    source = json_file.name
    sql_data = [(rank, word, source) for rank, word in enumerate(words, start = 1)]

    connection = sqlite3.connect(database_file)
    cursor = connection.cursor()

    sql_query = """
    INSERT INTO raw_words (
    rank,
    word,
    source
    )

    VALUES (?, ?, ?)
    """

    cursor.executemany(sql_query, sql_data)
    connection.commit()
    connection.close()
    print(f"Se han importado {len(words)} palabras de {source}!")


def main():
    create_database()

    words = load_words(json_file)

    import_words(words, json_file)


if __name__ == "__main__":
    main()