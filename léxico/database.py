import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASE_FILE = (
    PROJECT_ROOT
    / "datos"
    / "baseDeDatos"
    / "léxico.db"
)

EXPERIMENTS_FOLDER = (
    PROJECT_ROOT
    / "experimentos"
)

def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_FILE)

    # Permite acceder a las columnas por nombre.
    connection.row_factory = sqlite3.Row

    return connection

def get_raw_words(connection):
    cursor = connection.cursor()

    cursor.execute('''
        SELECT id, word
        FROM raw_words
    ''')

    return cursor.fetchall()

def get_or_create_lemma(connection, lemma: str, pos: str):
    cursor = connection.cursor()

    cursor.execute(
        '''
        SELECT id
        FROM lemmas
        WHERE lemma = ?
        ''',
        (lemma,)
    )

    result = cursor.fetchone()

    if result:
        return result[0]

    cursor.execute(
        '''
        INSERT INTO lemmas (lemma, part_of_speech)
        VALUES (?, ?)
        ''',
        (lemma, pos)
    )

    connection.commit()

    return cursor.lastrowid

def create_relation(connection, raw_word_id: int, lemma_id: int):
    cursor = connection.cursor()

    cursor.execute(
        '''
        INSERT OR IGNORE INTO word_lemmas
        (raw_word_id, lemma_id)
        VALUES (?, ?)
        ''',
        (raw_word_id, lemma_id)
    )

    connection.commit()

def create_rae_entry(connection, lemma_id, origin, raw_json):

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO rae_entries
        (
            lemma_id,
            origin,
            raw_json
        )
        VALUES (?, ?, ?)
        """,
        (
            lemma_id,
            origin,
            raw_json
        )
    )

    connection.commit()

    cursor.execute(
        """
        SELECT id
        FROM rae_entries
        WHERE lemma_id = ?
        """,
        (lemma_id,)
    )

    return cursor.fetchone()[0]

def create_definition(
    connection,
    rae_entry_id,
    meaning
):

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO definitions
        (
            rae_entry_id,
            meaning_number,
            category,
            subcategory,
            gender,
            usage,
            description,
            raw
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rae_entry_id,
            meaning.get("meaning_number"),
            meaning.get("category"),
            meaning.get("verb_category"),
            meaning.get("gender"),
            meaning.get("usage"),
            meaning.get("description"),
            meaning.get("raw")
        )
    )

    connection.commit()

    return cursor.lastrowid