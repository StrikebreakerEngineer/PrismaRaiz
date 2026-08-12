import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASE_FILE = (
    PROJECT_ROOT
    / "datos"
    / "baseDeDatos"
    / "léxico.db"
)

SCHEMA_FILE = (
    PROJECT_ROOT
    / "schema.sql"
    )


def create_database():
    print("Creando base de datos...")
    print(f'Raíz del proyecto: {PROJECT_ROOT}')

    connection = sqlite3.connect(DATABASE_FILE)
    cursor = connection.cursor()

    with open(SCHEMA_FILE, "r", encoding="utf-8") as file:
        schema = file.read()

    cursor.executescript(schema)
        
    connection.commit()
    connection.close()
    
    print("Base de datos creada correctamente!")


def main():
    create_database()


if __name__ == "__main__":
    main()