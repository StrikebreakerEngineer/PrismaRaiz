from léxico.database import get_connection


def inspect_tables(connection):

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        ORDER BY name;
        """
    )

    tables = cursor.fetchall()

    print("\nTABLAS EN LA BASE DE DATOS:")
    print("-" * 40)

    for table in tables:
        print(table["name"])


def inspect_schema(connection):

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        ORDER BY name;
        """
    )

    tables = cursor.fetchall()

    print("\n\nESTRUCTURA DE TABLAS:")
    print("=" * 40)

    for table in tables:

        table_name = table["name"]

        print()
        print(f"TABLA: {table_name}")
        print("-" * 40)

        cursor.execute(
            f"""
            PRAGMA table_info({table_name});
            """
        )

        columns = cursor.fetchall()

        for column in columns:
            print(
                f"{column['name']:<25}"
                f"{column['type']:<15}"
                f"{'NOT NULL' if column['notnull'] else ''}"
            )


def inspect_counts(connection):

    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        ORDER BY name;
        """
    )

    tables = cursor.fetchall()

    print("\n\nCANTIDAD DE REGISTROS:")
    print("=" * 40)

    for table in tables:

        table_name = table["name"]

        cursor.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM {table_name};
            """
        )

        result = cursor.fetchone()

        print(
            f"{table_name:<25}"
            f"{result['total']}"
        )


def main():

    connection = get_connection()

    inspect_tables(connection)

    inspect_schema(connection)

    inspect_counts(connection)

    connection.close()


if __name__ == "__main__":
    main()