from léxico.database import get_connection


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
            ON json_extract(r.raw_json, '$.word') = w.word
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
        SELECT
            status
        FROM t04_allwords_rae_status
        WHERE word_id = ?
        """,
        (word_id,)
    )

    return cursor.fetchone()


connection = get_connection()


words = get_pending_allwords_words(connection)

print("Pending:", len(words))

for word_id, word in words[:20]:

    status = get_rae_status(
        connection,
        word_id
    )

    print(
        word_id,
        word,
        status
    )


connection.close()