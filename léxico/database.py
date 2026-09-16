import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASE_FILE = (
    PROJECT_ROOT
    / "datos"
    / "baseDeDatos"
    / "léxico.db"
)

BACKUP_FILE = (
    PROJECT_ROOT
    / "datos"
    / "exportaciones"
    / "léxico_backup.bak"
)

EXPERIMENTS_FOLDER = (
    PROJECT_ROOT
    / "experimentos"
)


# ===============================
# FUNCIONES DE COPIA DE SEGUIRDAD
# ===============================
def backup_database(source_db_path=DATABASE_FILE, backup_db_path=BACKUP_FILE):
    src_conn = sqlite3.connect(source_db_path)
    dst_conn = sqlite3.connect(backup_db_path)
    
    with dst_conn:
        src_conn.backup(dst_conn)
        
    src_conn.close()
    dst_conn.close()
    print(f"✓ Backup successfully created at {backup_db_path}")


# ==================================
# FUNCIONES AUXILIARES DE EXTRACCIÓN
# ==================================

def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_FILE)

    # Permite acceder a las columnas por nombre.
    connection.row_factory = sqlite3.Row

    return connection


def get_raw_words(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """
    Recupera todas las palabras crudas de t01a_raw_words.

    Returns:
        Una lista de filas conteniendo id y word, ordenadas por id.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id, word
        FROM t01a_raw_words
        ORDER BY id
        """
    )

    return cursor.fetchall()


def get_max_raw_word_rank(connection: sqlite3.Connection) -> int:
    """
    Obtiene el rango máximo actual para calcular de forma segura la continuación de índices.
    """
    cursor = connection.cursor()
    cursor.execute("SELECT COALESCE(MAX(rank), 0) FROM t01_raw_words")
    return cursor.fetchone()[0]


def get_unprocessed_raw_words(connection: sqlite3.Connection, lemmatizer: str) -> list[sqlite3.Row]:
    """
    Recupera las palabras crudas que todavía no han sido procesadas
    por el lematizador especificado.

    Cada lematizador se considera de forma independiente. Por lo tanto,
    una palabra que ya fue procesada por Stanza todavía será devuelta
    cuando se solicite el procesamiento de simplemma.

    Args:
        connection: Conexión activa a SQLite.
        lemmatizer: Nombre del lematizador que se desea comprobar.

    Returns:
        Una lista de filas conteniendo id y word.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id, word
        FROM t01a_raw_words
        WHERE NOT EXISTS (
            SELECT 1
            FROM t03_word_lemmas
            WHERE t03_word_lemmas.raw_word_id = t01a_raw_words.id
              AND t03_word_lemmas.lemmatizer = ?
        )
        ORDER BY id
        """,
        (lemmatizer,),
    )

    return cursor.fetchall()


def get_lemmas(connection: sqlite3.Connection) -> dict[str, int]:
    """
    Recupera todos los lemas existentes en t02_lemmas y los carga
    en un diccionario para búsquedas O(1).

    La clave es el texto normalizado del lema y el valor es su
    identificador en t02_lemmas.
    """

    cursor = connection.cursor()

    print("Cargando lemas existentes para la verificación de duplicados...")

    cursor.execute(
        """
        SELECT id, lemma
        FROM t02_lemmas
        """
    )

    return {
        row["lemma"].strip().lower(): row["id"]
        for row in cursor.fetchall()
    }


def get_lemmas_without_rae_entry(
    connection: sqlite3.Connection,
) -> list[sqlite3.Row]:
    """
    Devuelve los lemas que aún no tienen una entrada correspondiente en la RAE.

    Se considera que un lema tiene una entrada en la RAE cuando al menos una fila
    de ``rae_entries`` hace referencia a su ID mediante ``lemma_id``.

    Argumentos:
        connection: Conexión activa a SQLite.

    Retorno:
        Lista de filas que contienen ``id`` y ``lemma``, ordenadas por ID.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            l.id,
            l.lemma
        FROM t02_lemmas AS l
        WHERE NOT EXISTS (
            SELECT 1
            FROM t04_rae_entries AS r
            WHERE r.lemma_id = l.id
        )
        ORDER BY l.id
        """
    )

    return cursor.fetchall()


def rae_entry_exists(connection, word):

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT 1
        FROM t04_rae_entries
        WHERE word = ?
        LIMIT 1
        """,
        (word,)
    )

    return cursor.fetchone() is not None


def get_rae_entries(connection):
    """
    Obtiene todas las entradas crudas descargadas de la RAE incluyendo sus IDs asociadas.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT 
            id,
            lemma_id,
            raw_json
        FROM t04_rae_entries
        ORDER BY id
        """
    )

    return cursor.fetchall()


def get_pending_allwords_words(connection):

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            w.id,
            w.word
        FROM t01a_raw_words w
        JOIN t01b_raw_word_sources s
            ON s.word_id = w.id
        LEFT JOIN t04_rae_entries r
            ON r.word = w.word
        WHERE s.source = 'allwords.txt'
          AND r.id IS NULL
        ORDER BY w.id
        """
    )

    return cursor.fetchall()


def get_rae_status(connection, word_id):

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT status
        FROM t04_allwords_rae_status
        WHERE word_id = ?
        """,
        (word_id,)
    )

    row = cursor.fetchone()

    if row:
        return row[0]

    return None


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

def create_raw_word(
    connection: sqlite3.Connection,
    word: str,
    *,
    commit_index: int | None = None,
    commit_batch: int = 25,
) -> tuple[int | None, bool]:
    """
    Inserta una palabra cruda en t01a_raw_words.

    Returns:
        (word_id, was_created)

        word_id:
            ID de la palabra, tanto si era nueva como si ya existía.

        was_created:
            True si la palabra fue insertada ahora.
            False si ya existía.
    """

    cursor = connection.cursor()

    # Intentar insertar
    cursor.execute(
        """
        INSERT INTO t01a_raw_words (word)
        VALUES (?)
        ON CONFLICT(word) DO NOTHING
        """,
        (word,),
    )

    was_created = cursor.rowcount == 1

    # Obtener el ID
    cursor.execute(
        """
        SELECT id
        FROM t01a_raw_words
        WHERE word = ?
        """,
        (word,),
    )

    # Gestionar la confirmación
    if (
        commit_index is None
        or commit_index != 0
        and commit_index % commit_batch == 0
    ):
        connection.commit()
        print("✓ Guardado en t01a_raw_words")

    row = cursor.fetchone()

    if row:
        return row[0], was_created

    return None, False


def create_raw_word_source(connection: sqlite3.Connection, word_id: int, rank: int, source: str, *,
                           commit_index: int | None = None, commit_batch: int = 25) -> None:
    """
    Registra que una palabra apareció en una fuente concreta
    en una posición determinada.

    Args:
        connection: Conexión activa a la base de datos SQLite.
        word_id: Identificador de la palabra en t01a_raw_words.
        rank: Posición de la palabra dentro de la fuente.
        source: Nombre del archivo o fuente de origen.
        commit_index: Controla cuándo se confirma la transacción.
            - None: realiza ``commit()`` inmediatamente.
            - -1: no realiza ``commit()``; el código llamador lo gestiona.
            - >= 0: realiza ``commit()`` cada ``commit_batch`` llamadas.
        commit_batch: Número de llamadas entre cada ``commit()`` cuando
            ``commit_index`` es mayor o igual que 0.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO t01b_raw_word_sources
            (word_id, rank, source)
        VALUES (?, ?, ?)
        ON CONFLICT(word_id, source) DO NOTHING
        """,
        (word_id, rank, source),
    )

    # Gestiona la confirmación de la transacción según la configuración.
    if commit_index is None or commit_index != 0 and commit_index % commit_batch == 0:
            connection.commit()
            print("✓ Guardado en t01b_raw_word_sources")


def create_lemma(
    connection: sqlite3.Connection,
    lemma: tuple[str, str],
    *,
    commit_index: int | None = None,
    commit_batch: int = 25,
) -> int | None:
    """
    Inserta un lema en t02_lemmas si todavía no existe y devuelve
    su identificador.

    Si el lema ya existe, devuelve el identificador de la fila
    existente.

    Args:
        connection: Conexión activa a SQLite.
        lemma: Tupla con (texto_del_lema, categoría_gramatical).
        commit_index: Controla cuándo se confirma la transacción.
            - None: realiza commit inmediatamente.
            - -1: no realiza commit.
            - >= 0: realiza commit cada commit_batch llamadas.
        commit_batch: Número de llamadas entre commits.

    Returns:
        El identificador del lema.
    """

    cursor = connection.cursor()

    lemma_text, part_of_speech = lemma

    cursor.execute(
        """
        INSERT INTO t02_lemmas (lemma, part_of_speech)
        VALUES (?, ?)
        ON CONFLICT(lemma) DO NOTHING
        """,
        (lemma_text, part_of_speech),
    )

    cursor.execute(
        """
        SELECT id
        FROM t02_lemmas
        WHERE lemma = ?
        """,
        (lemma_text,),
    )

    result = cursor.fetchone()

    if result is None:
        raise RuntimeError(
            f"No se pudo recuperar el lema después de insertarlo: {lemma_text}"
        )

    lemma_id = result["id"]

    if (
        commit_index is None
        or (commit_index >= 0 and commit_index % commit_batch == 0)
    ):
        connection.commit()

    return lemma_id


def create_lemma_raw_relation(
    connection: sqlite3.Connection,
    relation: tuple[int, int, str],
    *,
    commit_index: int | None = None,
    commit_batch: int = 25,
) -> int | None:
    """
    Registra la relación entre una palabra cruda, un lema y el
    lematizador que produjo dicha relación.

    Args:
        connection: Conexión activa a SQLite.
        relation: Tupla con:
            (raw_word_id, lemma_id, lemmatizer)
        commit_index: Controla cuándo se confirma la transacción.
            - None: realiza commit inmediatamente.
            - -1: no realiza commit.
            - >= 0: realiza commit cada commit_batch llamadas.
        commit_batch: Número de llamadas entre commits.

    Returns:
        El identificador de la última fila insertada.
    """

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO t03_word_lemmas
            (raw_word_id, lemma_id, lemmatizer)
        VALUES (?, ?, ?)
        """,
        relation,
    )

    if (
        commit_index is None
        or (commit_index >= 0 and commit_index % commit_batch == 0)
    ):
        connection.commit()
        print("✓ Guardado en t03_word_lemmas")

    return cursor.lastrowid


def create_rae_entry(connection, word, lemma_id, raw_json, *,
                     commit_index: int | None = None, commit_batch: int = 25) -> int | None:
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT OR IGNORE INTO t04_rae_entries
        (
            word,
            lemma_id,
            raw_json
        )
        VALUES (?, ?, ?)
        """,
        (
            word,
            lemma_id,
            raw_json,
        ),
    )

    if (commit_index is None or (commit_index >= 0 and commit_index % commit_batch == 0)):
            print(f"💾 Volcando lote de {commit_batch} palabras...")
            connection.commit()
            print("✅ Guardado en t04_rae_entries!")

    return cursor.lastrowid


def set_rae_status(connection, word_id, status):

    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO t04_allwords_rae_status
        (word_id, status)
        VALUES (?, ?)
        ON CONFLICT(word_id)
        DO UPDATE SET status = excluded.status
        """,
        (word_id, status)
    )

    connection.commit()


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

    backup_database()