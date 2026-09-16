from léxico.database import get_connection


def main():
    connection = get_connection()

    try:
        cursor = connection.cursor()

        # Total unique raw words that have allwords.txt as a source
        cursor.execute("""
            SELECT COUNT(DISTINCT word_id)
            FROM t01b_raw_word_sources
            WHERE source = 'allwords.txt'
        """)
        total = cursor.fetchone()[0]

        # Number of those words whose exact text exists as a lemma
        # AND that lemma has an RAE entry.
        cursor.execute("""
            SELECT COUNT(DISTINCT s.word_id)
            FROM t01b_raw_word_sources AS s
            JOIN t01a_raw_words AS w
                ON w.id = s.word_id
            WHERE s.source = 'allwords.txt'
              AND EXISTS (
                  SELECT 1
                  FROM t02_lemmas AS l
                  JOIN t04_rae_entries AS r
                      ON r.lemma_id = l.id
                  WHERE l.lemma = w.word
              )
        """)
        found = cursor.fetchone()[0]

        print()
        print("=" * 60)
        print("RAE CHECK — allwords.txt")
        print("=" * 60)
        print()
        print(f"allwords.txt words:       {total:,}")
        print(f"RAE entries found:        {found:,}")
        print(f"RAE entries missing:      {total - found:,}")
        print()
        print("No individual words printed.")
        print("=" * 60)

    finally:
        connection.close()


if __name__ == "__main__":
    main()