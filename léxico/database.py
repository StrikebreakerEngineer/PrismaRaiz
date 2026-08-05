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


# ==================================
# FUNCIONES AUXILIARES DE EXTRACCIÓN
# ==================================

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


def get_rae_entries(connection):

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            raw_json
        FROM t04_rae_entries
        ORDER BY id
        """
    )

    return cursor.fetchall()


def get_meanings(connection):

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            m.id,
            m.homonym_index,
            r.raw_json
        FROM t05a_meanings AS m
        JOIN t04_rae_entries AS r
            ON r.id = m.rae_entry_id
        ORDER BY
            m.id
        """
    )

    return cursor.fetchall()


# =================================
# FUNCIONES AUXILIARES DE INSERCIÓN
# =================================

def create_rae_entry(connection, lemma_id: int, raw_json: str, commit_index: int | None = None) -> int:
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO t04_rae_entries
        (lemma_id, raw_json)
        VALUES (?, ?)
        """,
        (
            lemma_id,
            raw_json,
        ),
    )

    if commit_index != -1 and (commit_index is None or commit_index % 25 == 0):
        connection.commit()
        print("✓ Guardado en t04_rae_entries")
        
    return cursor.lastrowid


def create_relation(connection, raw_word_id: int, lemma_id: int):
    cursor = connection.cursor()

    cursor.execute(
        '''
        INSERT OR IGNORE INTO t03_word_lemmas
        (raw_word_id, lemma_id)
        VALUES (?, ?)
        ''',
        (raw_word_id, lemma_id)
    )

    connection.commit()


def create_meaning(connection, rae_entry_id: int, meaning_data: dict, commit_index: int | None = None) -> int:
    origin = meaning_data.get("origin") or {}
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO t05a_meanings 
        (rae_entry_id, homonym_index, origin_raw, origin_type, origin_voice, origin_text)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            rae_entry_id,
            meaning_data.get("homonym_index"),
            origin.get("raw"),
            origin.get("type"),
            origin.get("voice"),
            origin.get("text")
        )
    )

    if commit_index != -1 and (commit_index is None or commit_index % 25 == 0):
        connection.commit()
        print("✓ Guardado en t05a_meanings")

    return cursor.lastrowid


def create_definition(connection, meaning_id: int, sense: dict, commit_index: int | None = None):
    article = sense.get("article") or {}
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO t05b1_definitions
        (meaning_id, meaning_number, category, verb_category, gender, article_category, article_gender, usage, description, raw_text)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            meaning_id,
            sense.get("meaning_number"),
            sense.get("category"),
            sense.get("verb_category"),
            sense.get("gender"),
            article.get("category"),
            article.get("gender"),
            sense.get("usage"),
            sense.get("description"),
            sense.get("raw"),
        ),
    )

    if commit_index != -1 and (commit_index is None or commit_index % 25 == 0):
        connection.commit()
        print("✓ Guardado en t05b1_definitions")

    return cursor.lastrowid


def create_def_example(connection, definition_id: int, example: str):
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO t05b2_def_examples (definition_id, example) VALUES (?, ?)",
        (definition_id, example)
    )


def create_related_word(connection, definition_id: int, relation: str, word: str, label: str | None):
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO t05b3_def_related_words (definition_id, relation, word, label) VALUES (?, ?, ?, ?)",
        (definition_id, relation, word, label)
    )


def create_region(connection, definition_id: int, code: str | None, name: str):
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO t05b4_def_regions (definition_id, code, name) VALUES (?, ?, ?)",
        (definition_id, code, name)
    )


def create_field(connection, definition_id: int, field: str):
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO t05b5_def_fields (definition_id, field) VALUES (?, ?)",
        (definition_id, field)
    )


def create_usage_note(connection, definition_id: int, note: str):
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO t05b6_def_usage_notes (definition_id, note) VALUES (?, ?)",
        (definition_id, note)
    )


def create_verb_conjugation(connection, lemma_id: int, mood: str, tense: str, person: str, form: str):
    """
    Inserta una forma verbal conjugada en la tabla 'conjugations'.
    """
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO t05c1_verb_conjugations (lemma_id, mood, tense, person, form)
        VALUES (?, ?, ?, ?, ?)
        """,
        (lemma_id, mood, tense, person, form)
    )
    
    return cursor.lastrowid


def create_locution(connection, meaning_id: int, expression: str):
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO t05d1_locutions (meaning_id, expression) VALUES (?, ?)",
        (meaning_id, expression)
    )
    return cursor.lastrowid


def create_locution_sense(connection, locution_id: int, sense: dict):
    article = sense.get("article") or {}
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO t05d2_loc_senses
        (locution_id, meaning_number, category, verb_category, gender, article_category, article_gender, usage, description, raw_text)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            locution_id,
            sense.get("meaning_number"),
            sense.get("category"),
            sense.get("verb_category"),
            sense.get("gender"),
            article.get("category"),
            article.get("gender"),
            sense.get("usage"),
            sense.get("description"),
            sense.get("raw"),
        ),
    )
    return cursor.lastrowid


def create_locution_example(connection, locution_sense_id: int, example: str):
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO t05d3_loc_examples (locution_sense_id, example) VALUES (?, ?)",
        (locution_sense_id, example)
    )


def create_locution_related_word(connection, locution_sense_id: int, relation: str, word: str, label: str | None):
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO t05d4_loc_related_words (locution_sense_id, relation, word, label) VALUES (?, ?, ?, ?)",
        (locution_sense_id, relation, word, label)
    )


def create_locution_region(connection, locution_sense_id: int, code: str | None, name: str):
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO t05d5_loc_regions (locution_sense_id, code, name) VALUES (?, ?, ?)",
        (locution_sense_id, code, name)
    )


def create_locution_field(connection, locution_sense_id: int, field: str):
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO t05d6_loc_fields (locution_sense_id, field) VALUES (?, ?)",
        (locution_sense_id, field)
    )


def create_locution_usage_note(connection, locution_sense_id: int, note: str):
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO t05d7_loc_usage_notes (locution_sense_id, note) VALUES (?, ?)",
        (locution_sense_id, note)
    )



if __name__ == "__main__":
    print("¡Alto!\n\nEste programa actúa como una biblioteca y solo contiene\n" \
    "funciones auxiliares para editar y acceder al archivo léxico.db")