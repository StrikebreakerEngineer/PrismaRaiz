import json

from léxico.database import *


def main():
    print("Extrayendo definiciones y metadatos asociados...")

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
            # Si el arreglo viene nulo o vacío por seguridad, saltamos de forma segura
            meanings_list = data.get("meanings") or []
            meaning = meanings_list[0] if meanings_list else None
        else:
            meaning = next(
                (
                    m
                    for m in (data.get("meanings") or [])
                    if m.get("homonym_index") == homonym_index
                ),
                None,
              )

        if meaning is None:
            print(f"No se encontró el meaning con homonym_index={homonym_index}")
            continue

        # --- EXTRACCIÓN A NIVEL DE SENTIDOS (SENSES) ---
        for sense in (meaning.get("senses") or []):
            # Guardamos la definición y obtenemos su ID relacional
            definition_id = create_definition(
                connection=connection,
                meaning_id=row["id"],
                sense=sense,
                commit_index=-1
            )

            # Paso 06: Ejemplos
            for example_text in (sense.get("examples") or []):
                create_example(connection, definition_id, example_text)

            # Paso 07: Sinónimos v2
            for syn in (sense.get("synonyms_v2") or []):
                create_related_word(connection, definition_id, "synonym", syn.get("word"), syn.get("label"))
            
            # Paso 08: Antónimos v2
            for ant in (sense.get("antonyms_v2") or []):
                create_related_word(connection, definition_id, "antonym", ant.get("word"), ant.get("label"))

            # Paso 09: Notas de Uso
            for note in (sense.get("usage_notes") or []):
                create_usage_note(connection, definition_id, note)

            # Paso 10: Regiones geográficas
            for region in (sense.get("regions") or []):
                create_region(connection, definition_id, region.get("code"), region.get("name"))

            # Paso 11: Campos / Dominios semánticos
            for field in (sense.get("fields") or []):
                create_field(connection, definition_id, field)

            # Paso 12: Referencias cruzadas (Se guardan de forma nativa en related_words)
            for ref in (sense.get("cross_references") or []):
                create_related_word(connection, definition_id, "cross_reference", ref, None)

        # --- EXTRACCIÓN A NIVEL DE LOCUCIONES (LOCUTIONS) ---
        # Pasos 13 al 17 mapeados directamente bajo el objeto 'meaning'
        for loc in (meaning.get("locutions") or []):
            locution_id = create_locution(connection, row["id"], loc.get("expression"))
            
            for loc_sense in (loc.get("senses") or []):
                loc_sense_id = create_locution_sense(connection, locution_id, loc_sense)
                
                # Ejemplos de locución
                for loc_ex in (loc_sense.get("examples") or []):
                    create_locution_example(connection, loc_sense_id, loc_ex)
                
                # Sinónimos v2 de locución
                for loc_syn in (loc_sense.get("synonyms_v2") or []):
                    create_locution_related_word(connection, loc_sense_id, "synonym", loc_syn.get("word"), loc_syn.get("label"))
                
                # Antónimos v2 de locución
                for loc_ant in (loc_sense.get("antonyms_v2") or []):
                    create_locution_related_word(connection, loc_sense_id, "antonym", loc_ant.get("word"), loc_ant.get("label"))

                # Notas de uso de locución
                for loc_note in (loc_sense.get("usage_notes") or []):
                    create_locution_usage_note(connection, loc_sense_id, loc_note)

                # Regiones de locución
                for loc_reg in (loc_sense.get("regions") or []):
                    create_locution_region(connection, loc_sense_id, loc_reg.get("code"), loc_reg.get("name"))

                # Campos de locución
                for loc_fld in (loc_sense.get("fields") or []):
                    create_locution_field(connection, loc_sense_id, loc_fld)

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
    print("¡Definiciones, locuciones y metadatos extraídos correctamente!")


if __name__ == "__main__":
    main()
