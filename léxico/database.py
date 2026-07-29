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


def create_rae_entry(connection, lemma_id: int, raw_json: str, index = None):
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO rae_entries
        (lemma_id, raw_json)
        VALUES (?, ?)
        """,
        (
            lemma_id,
            raw_json,
        ),
    )

    if index is None or index % 25 == 0:
        connection.commit()
        print("✓ Guardado en rae_entries")

    return cursor.lastrowid


def create_definition(connection, rae_entry_id, meaning):

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

def get_unprocessed_raw_words(connection):
    cursor = connection.cursor()

    cursor.execute("""
        SELECT rw.id, rw.word
        FROM raw_words rw
        LEFT JOIN word_lemmas wl
            ON wl.raw_word_id = rw.id
        WHERE wl.raw_word_id IS NULL
    """)

    return cursor.fetchall()

def get_lemmas_without_rae_entry(connection):

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            l.id,
            l.lemma

        FROM lemmas l

        LEFT JOIN rae_entries r
            ON r.lemma_id = l.id

        WHERE r.id IS NULL

        ORDER BY l.id
        """
    )

    return cursor.fetchall()