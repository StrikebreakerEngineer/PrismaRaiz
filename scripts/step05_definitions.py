import json

from léxico.database import *


def main():
    print("Extrayendo definiciones y sus metadatos asociados...")

    connection = get_connection()
    meanings = get_meanings(connection)
    total = len(meanings)

    print(f"Se encontraron {total} entradas.")

    for index, row in enumerate(meanings, start=1):
        data = json.loads(row["raw_json"])

        print()
        print(f"[{index}/{total}] {data['word']}")

        homonym_index = row["homonym_index"]

        if homonym_index is None:
            meaning = data["meanings"][0]
        else:
            meaning = next(
                (
                    m
                    for m in data["meanings"]
                    if m.get("homonym_index") == homonym_index
                ),
                None,
            )

            if meaning is None:
                print(f"No se encontró el meaning con homonym_index={homonym_index}")
                continue

        for sense in (meaning.get("senses") or []):
            # Guardamos la definición y obtenemos su ID generado automáticamente
            definition_id = create_definition(
                connection=connection,
                meaning_id=row["id"],
                sense=sense,
                commit_index=-1
            )

            # --- Paso 06: Extraer Ejemplos ---
            for example_text in (sense.get("examples") or []):
                create_example(connection, definition_id, example_text)

            # --- Paso 07 y 08: Relaciones de palabras (Sinónimos / Antónimos) ---
            # Procesamos la lista moderna 'synonyms_v2' tal como planeamos
            for syn in (sense.get("synonyms_v2") or []):
                create_related_word(connection, definition_id, "synonym", syn.get("word"), syn.get("label"))
            
            for ant in (sense.get("antonyms_v2") or []):
                create_related_word(connection, definition_id, "antonym", ant.get("word"), ant.get("label"))

            # --- Paso 09: Notas de Uso ---
            for note in (sense.get("usage_notes") or []):
                create_usage_note(connection, definition_id, note)

            # --- Paso 10: Regiones geográficas ---
            for region in (sense.get("regions") or []):
                create_region(connection, definition_id, region.get("code"), region.get("name"))

            # --- Paso 11: Campos / Dominios semánticos ---
            for field in (sense.get("fields") or []):
                create_field(connection, definition_id, field)

        # Control del lote de confirmación (Commit cada 25 entradas principales)
        if index % 25 == 0:
            print()
            print("Guardando cambios...")
            connection.commit()
            print("✓ Guardado en base de datos")

    print()
    print("Ejecución finalizada. Guardando el estado final de la base de datos...")
    connection.commit()
    print("✓ Guardado completo")
    connection.close()
    print()
    print("¡Definiciones, ejemplos y metadatos extraídos correctamente!")


if __name__ == "__main__":
    main()