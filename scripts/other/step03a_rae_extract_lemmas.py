import json

import requests

from léxico.database import *
from léxico.rae import RAE_API_KEY, DailyQuotaExceeded, get_rae_entry


def extract_rae_entries(entry_limit: int|None = None):
    print()
    print("🚀 Se están extrayendo entradas de la RAE para los lemas restantes.")

    connection = get_connection()
    lemmas = get_lemmas_without_rae_entry(connection)
    total = len(lemmas)

    print(f"📊 Se encontraron {total} lemas pendientes.")

    # Inicializamos la sesión HTTP persistente usando un gestor de contexto
    with requests.Session() as session:
        session.headers.update({"X-API-Key": RAE_API_KEY})

        try:
            for index, lemma in enumerate(lemmas, start=1):
                lemma_id = lemma["id"]
                word = lemma["lemma"]

                print()
                print(f"--- [Progreso: {index}/{total}] Procesando: '{word}' ---")

                # Esto arrojará de manera limpia la excepción si remaining == 0
                data = get_rae_entry(session, word)

                if not data:
                    print(f'❌ Omitiendo: No se pudo guardar entrada para "{word}"')
                    continue

                create_rae_entry(connection, lemma_id, json.dumps(data, ensure_ascii=False), commit_index=index, commit_batch=50)

                if entry_limit is not None and index >= entry_limit:
                    print(f"\n🛑 Se alcanzó el límite configurado de {entry_limit} palabras.")
                    break
                    
        except DailyQuotaExceeded:
            print("\n💾 Deteniendo ejecución de forma segura debido a cuota diaria agotada.")
            print("Guardando los cambios procesados hasta el momento...")

    # El script salta aquí de forma segura, ejecuta el commit final y cierra la BD
    print("\n💾 Volcando lote de cierre final...")
    connection.commit()

    connection.close()

    print("\n🎉 ¡Descarga terminada con éxito!")


def main():
    extract_rae_entries()


if __name__ == "__main__":
    main()
