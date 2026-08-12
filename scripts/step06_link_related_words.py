from léxico.database import get_connection


def main():
    print("Iniciando Fase 2: Indexación y vinculación semántica de palabras relacionadas...")
    
    connection = get_connection()
    cursor = connection.cursor()
    
    # 1. Extraemos todas las palabras relacionadas que aún no han sido vinculadas
    cursor.execute("""
        SELECT id, word 
        FROM t05b3_def_related_words 
        WHERE matched_lemma_id IS NULL
    """)
    
    related_rows = cursor.fetchall()
    total = len(related_rows)
    print(f"Se encontraron {total} registros de palabras relacionadas por procesar.")
    
    if total == 0:
        print("✓ Todo está completamente al día.")
        connection.close()
        return

    # 2. Precargamos los lemas en un diccionario en memoria para búsquedas instantáneas O(1)
    print("Cargando índice de lemas en memoria para optimizar el rendimiento...")
    cursor.execute("SELECT id, lemma FROM t02_lemmas")
    lemma_cache = {row["lemma"].strip().lower(): row["id"] for row in cursor.fetchall()}
    print(f"✓ {len(lemma_cache)} lemas cargados en el mapa de memoria.")

    linked_count = 0
    skipped_count = 0
    updates_batch = []

    print("\nProcesando y cruzando referencias...")
    for index, row in enumerate(related_rows, start=1):
        record_id = row["id"]
        raw_word = row["word"].strip().lower()
        
        # Intentamos buscar una coincidencia exacta en nuestro mapa de lemas
        matched_id = lemma_cache.get(raw_word)
        
        if matched_id:
            updates_batch.append((matched_id, record_id))
            linked_count += 1
        else:
            skipped_count += 1

        # Control transaccional: Actualización por lotes cada 500 registros para velocidad masiva
        if len(updates_batch) >= 500:
            cursor.executemany("""
                UPDATE t05b3_def_related_words 
                SET matched_lemma_id = ? 
                WHERE id = ?
            """, updates_batch)
            connection.commit()
            updates_batch = []
            print(f" Progress: [{index}/{total}] vinculados con éxito...")

    # Forzar volcado final de lotes restantes
    if updates_batch:
        cursor.executemany("""
            UPDATE t05b3_def_related_words 
            SET matched_lemma_id = ? 
            WHERE id = ?
        """, updates_batch)
        connection.commit()

    print("\n" + "="*50)
    print("¡Proceso de vinculación finalizado!")
    print(f" - Registros vinculados con éxito a t02_lemmas: {linked_count}")
    print(f" - Registros sin coincidencia (palabras externas): {skipped_count}")
    print("="*50)
    
    connection.close()

if __name__ == "__main__":
    main()
