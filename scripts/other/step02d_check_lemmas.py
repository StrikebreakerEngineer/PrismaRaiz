import collections

from spellchecker import SpellChecker

from léxico.database import get_connection, get_lemmas


def generate_structured_audit():
    print("Iniciando auditoría estructurada de lemas...")
    spell = SpellChecker(language='es')
    
    connection = get_connection()
    lemma_cache = get_lemmas(connection) # {lemma_text: id}
    connection.close()
    
    # Categories for sorting suspects
    symbols_and_numbers = []
    capitalized_names = []
    extremely_short = []
    potential_gibberish = []
    standard_dictionary_words = []
    
    print(f"Clasificando {len(lemma_cache)} registros...")
    
    for lemma in lemma_cache:
        text = lemma.strip()
        if not text:
            continue
            
        # 1. Check for digits, symbols, or mixed punctuation junk
        if not text.isalpha():
            symbols_and_numbers.append(text)
            continue
            
        # 2. Capitalized words (Names, Places, Brands) - Spellcheckers hate these
        if text[0].isupper():
            capitalized_names.append(text)
            continue
            
        # 3. Micro-words (usually parsing artifacts if not matching standard vowels)
        if len(text) < 2 and text.lower() not in ['a', 'o', 'e', 'y', 'u']:
            extremely_short.append(text)
            continue
            
        # 4. Standard Spell Check
        if spell.known([text.lower()]):
            standard_dictionary_words.append(text)
        else:
            potential_gibberish.append(text)

    # Output Scannable Summary
    print("\n" + "="*50)
    print(" RESUMEN DE CONTROL DE CALIDAD DE LEMAS")
    print("="*50)
    print(f"✓ Lemas Válidos Reconocidos:        {len(standard_dictionary_words)}")
    print(f"⚠ Nombres Propios / Mayúsculas:    {len(capitalized_names)}")
    print(f"❌ Basura de Símbolos / Números:    {len(symbols_and_numbers)}")
    print(f"❌ Monosílabos sospechosos (<2 car): {len(extremely_short)}")
    print(f"❓ Desconocidos / Posible Jerga:    {len(potential_gibberish)}")
    print("="*50)

    # Print top samples of each category to spot patterns
    print("\n--- MUESTRA: BASURA DE SÍMBOLOS/NÚMEROS (Eliminación Segura) ---")
    print(symbols_and_numbers[:30])
    
    print("\n--- MUESTRA: MONOSÍLABOS SOSPECHOSOS (Errores de Extracción) ---")
    print(extremely_short[:30])

    print("\n--- MUESTRA: NOMBRES PROPIOS (Probablemente válidos, no borrar) ---")
    print(capitalized_names[:30])

    print("\n--- MUESTRA: DESCONOCIDOS / POSIBLE JERGA (Revisar de cerca) ---")
    # Show words grouped by their suffix/ending patterns to find algorithmic bugs
    endings = collections.Counter([w[-3:] for w in potential_gibberish if len(w) > 3])
    print("Terminaciones comunes en palabras desconocidas (Ayuda a detectar errores del lematizador):")
    for suffix, count in endings.most_common(5):
        print(f" - Terminados en '-{suffix}': {count} palabras")
    
    print("\nPrimeras 50 palabras desconocidas:")
    print(potential_gibberish[:50])


def analyze_discrepancies():
    print("🤖 Analizando discrepancias entre Simplemma, Stanza y spaCy...")
    connection = get_connection()
    cursor = connection.cursor()

    # SQL Query to pull words where the three models disagreed on the lemma
    query = """
        SELECT 
            rw.id, 
            rw.word AS raw_word,
            MAX(CASE WHEN wl.lemmatizer = 'simplemma' THEN l.lemma END) AS lemma_simplemma,
            MAX(CASE WHEN wl.lemmatizer = 'Stanza' THEN l.lemma END) AS lemma_stanza,
            MAX(CASE WHEN wl.lemmatizer = 'spaCy' THEN l.lemma END) AS lemma_spacy
        FROM t01a_raw_words rw
        JOIN t03_word_lemmas wl ON rw.id = wl.raw_word_id
        JOIN t02_lemmas l ON wl.lemma_id = l.id
        GROUP BY rw.id, rw.word
        HAVING 
            lemma_simplemma != lemma_stanza 
            OR lemma_stanza != lemma_spacy 
            OR lemma_simplemma != lemma_spacy
        LIMIT 50;
    """

    cursor.execute(query)
    rows = cursor.fetchall()
    connection.close()

    if not rows:
        print("✨ ¡Increíble! Los tres lematizadores coinciden perfectamente en todas las palabras.")
        return

    print(f"\n📢 Se encontraron discrepancias. Mostrando una muestra de las primeras {len(rows)}:")
    print("-" * 90)
    print(f"{'Palabra Cruda':<20} | {'Simplemma':<20} | {'Stanza':<20} | {'spaCy':<20}")
    print("-" * 90)
    
    for row in rows:
        # Adjust dictionary key access if your database utility returns objects/tuples
        print(f"{row['raw_word']:<20} | {str(row['lemma_simplemma']):<20} | {str(row['lemma_stanza']):<20} | {str(row['lemma_spacy']):<20}")


if __name__ == "__main__":
    analyze_discrepancies()