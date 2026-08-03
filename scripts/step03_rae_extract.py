import json

import requests

from léxico.database import *
from léxico.rae import RAE_API_KEY, get_rae_entry


def main():
    print()
    print("Se están extrayendo entradas de la RAE para los lemas restantes.")

    connection = get_connection()
    lemmas = get_lemmas_without_rae_entry(connection)
    total = len(lemmas)

    print(f"Se encontraron {total} lemas pendientes.")

    # Inicializamos la sesión HTTP persistente usando un gestor de contexto
    with requests.Session() as session:
        # Configuramos el encabezado de autenticación global una sola vez para toda la sesión
        session.headers.update({
            "X-API-Key": RAE_API_KEY
        })

        for index, lemma in enumerate(lemmas, start=1):
            lemma_id = lemma["id"]
            word = lemma["lemma"]

            print()
            print(f"[{index}/{total}] {word}")

            # Pasamos la sesión persistente como argumento para reutilizar la conexión TCP
            data = get_rae_entry(session, word)

            if not data:
                print(f'No se pudo encontrar una entrada para "{word}"')
                continue

            create_rae_entry(
                connection,
                lemma_id,
                json.dumps(data, ensure_ascii=False),
                None if index == total else index,
            )

    # El bloque 'with' termina aquí. La sesión de red ya se ha cerrado de forma segura.
    
    connection.commit()
    print()
    print("✓ Todo guardado en rae_entries")

    connection.close()

    print()
    print("¡Descarga terminada!")


if __name__ == "__main__":
    main()
