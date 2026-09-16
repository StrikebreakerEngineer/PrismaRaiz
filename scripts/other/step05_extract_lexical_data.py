import json

from léxico.database import *


def main():
    print("Iniciando la extracción unificada de datos léxicos (Significados, Definiciones, Locuciones y Conjugaciones)...")

    connection = get_connection()

    # Leemos directamente de la tabla core de descargas históricas t04_rae_entries
    entries = get_rae_entries(connection)
    total = len(entries)

    print(f"Se encontraron {total} entradas crudas para procesar.")

    for index, entry in enumerate(entries, start=1):
        data = json.loads(entry["raw_json"])

        print(f"[{index}/{total}] Procesando lema: {data.get('word', 'Desconocido')}")

        # --- CAPA 05-A & 05-B & 05-D: SIGNIFICADOS, SENTIDOS Y LOCUCIONES ---
        for meaning_data in (data.get("meanings") or []):
            
            # 1. Insertamos el significado base y extraemos su ID generado automáticamente
            meaning_id = create_meaning(connection=connection, rae_entry_id=entry["id"], meaning_data=meaning_data, commit_index=-1)

            # 2. Procesamos la sub-capa de acepciones y definiciones principales (t05b1 a t05b6)
            for sense in (meaning_data.get("senses") or []):
                definition_id = create_definition(connection=connection, meaning_id=meaning_id, sense=sense, commit_index=-1)

                # Ejemplos correlativos de la definición
                for example_text in (sense.get("examples") or []):
                    create_def_example(connection, definition_id, example_text)

                # Sinónimos v2 enriquecidos
                for syn in (sense.get("synonyms_v2") or []):
                    create_related_word(connection, definition_id, "synonym", syn.get("word"), syn.get("label"))
                
                # Antónimos v2 enriquecidos
                for ant in (sense.get("antonyms_v2") or []):
                    create_related_word(connection, definition_id, "antonym", ant.get("word"), ant.get("label"))

                # Notas aclaratorias de uso
                for note in (sense.get("usage_notes") or []):
                    create_usage_note(connection, definition_id, note)

                # Códigos de regiones geográficas
                for region in (sense.get("regions") or []):
                    create_region(connection, definition_id, region.get("code"), region.get("name"))

                # Dominios semánticos / Campos técnicos
                for field in (sense.get("fields") or []):
                    create_field(connection, definition_id, field)

                # Referencias cruzadas integradas
                for ref in (sense.get("cross_references") or []):
                    create_related_word(connection, definition_id, "cross_reference", ref, None)

            # 3. Procesamos la sub-capa de locuciones complejas e idiotismos (t05d1 a t05d7)
            for loc in (meaning_data.get("locutions") or []):
                locution_id = create_locution(connection, meaning_id, loc.get("expression"))
                
                for loc_sense in (loc.get("senses") or []):
                    loc_sense_id = create_locution_sense(connection, locution_id, loc_sense)
                    
                    for loc_ex in (loc_sense.get("examples") or []):
                        create_locution_example(connection, loc_sense_id, loc_ex)
                    
                    for loc_syn in (loc_sense.get("synonyms_v2") or []):
                        create_locution_related_word(connection, loc_sense_id, "synonym", loc_syn.get("word"), loc_syn.get("label"))
                    
                    for loc_ant in (loc_sense.get("antonyms_v2") or []):
                        create_locution_related_word(connection, loc_sense_id, "antonym", loc_ant.get("word"), loc_ant.get("label"))

                    for loc_note in (loc_sense.get("usage_notes") or []):
                        create_locution_usage_note(connection, loc_sense_id, loc_note)

                    for loc_reg in (loc_sense.get("regions") or []):
                        create_locution_region(connection, loc_sense_id, loc_reg.get("code"), loc_reg.get("name"))

                    for loc_fld in (loc_sense.get("fields") or []):
                        create_locution_field(connection, loc_sense_id, loc_fld)

            # --- CAPA 05-C: FLEXIÓN Y PARADIGMAS VERBALES ---
            conjugations_data = meaning_data.get("conjugations")
            if conjugations_data:
                lemma_id = entry["lemma_id"]
                moods = ["indicative", "subjunctive", "imperative", "non_personal"]

                for mood in moods:
                    mood_block = conjugations_data.get(mood)
                    if not mood_block:
                        continue

                    for tense, persons_block in mood_block.items():
                        if not persons_block:
                            continue

                        # Casos especiales de flexiones infinitivas y participios
                        if mood == "non_personal":
                            if isinstance(persons_block, str):
                                create_verb_conjugation(connection, lemma_id, mood, tense, "none", persons_block)
                            continue

                        # Casos estándar agrupados por personas gramaticales discretas
                        if isinstance(persons_block, dict):
                            for person, form_value in persons_block.items():
                                if not form_value:
                                    continue
                                
                                if isinstance(form_value, list):
                                    for single_form in form_value:
                                        create_verb_conjugation(connection, lemma_id, mood, tense, person, single_form)
                                else:
                                    create_verb_conjugation(connection, lemma_id, mood, tense, person, str(form_value))

        # Control transaccional optimizado: Guardado por bloques en ráfagas de 25 lemas
        if index % 25 == 0:
            print()
            print("Guardando lote de transacciones en la base de datos...")
            connection.commit()
            print("✓ Lote confirmado correctamente")
            print()

    print()
    print("Ejecución finalizada por completo. Volcando residuos finales...")
    connection.commit()
    print("✓ Base de datos actualizada con éxito")
    
    connection.close()
    print()
    print("¡Diccionario relacional jerárquico compilado al 100%!")


if __name__ == "__main__":
    main()