import spacy

# 50 words chosen to heavily test specific structural limits in Spanish
test_words = [
    # 1. Clitic Pronouns (Attached Object Pronouns)
    "hacerlo", "decirme", "vete", "dímelo", "búscala", "hablándote", "escribirle", "comprárselo", "míralo", "ayúdame",
    # 2. Vosotros / Complex Verb Conjugations
    "habláis", "queréis", "vivisteis", "coméis", "erais", "fuisteis", "anduvisteis", "trajeseis", "oiréis", "saldréis",
    # 3. Noun / Verb Lexical Ambiguity
    "cuenta", "falta", "canto", "planta", "mañana", "vino", "cerca", "bajo", "lista", "pese",
    # 4. Short Tokens, Adverbs & Abbreviations
    "solo", "tan", "dios", "sí", "etc", "dr", "bueno", "mal", "muy", "peor",
    # 5. Complex Plurals / Morphological Shift Roots
    "estado", "ferretería", "pomada", "memoria", "industria", "anciana", "actrices", "jóvenes", "leyes", "bueyes"
]

def benchmark_expanded_set():
    print("🤖 Cargando los 4 modelos de spaCy (sm, md, lg, trf)...")
    
    # Load all models to check side-by-side
    nlp_sm = spacy.load("es_core_news_sm", disable=["parser", "ner"])
    nlp_md = spacy.load("es_core_news_md", disable=["parser", "ner"])
    nlp_lg = spacy.load("es_core_news_lg", disable=["parser", "ner"])
    nlp_trf = spacy.load("es_dep_news_trf", disable=["ner"])
    print("✓ Modelos cargados.")

    # Format long grid strings scannably
    row_fmt = "{:<15} | {:<15} | {:<15} | {:<15} | {:<20}"
    print("\n" + "="*86)
    print(row_fmt.format("Palabra Cruda", "spaCy SM", "spaCy MD", "spaCy LG", "spaCy TRF (BERT)"))
    print("="*86)

    for word in test_words:
        doc_sm = nlp_sm(word)
        doc_md = nlp_md(word)
        doc_lg = nlp_lg(word)
        doc_trf = nlp_trf(word)

        # Pull strings cleanly out of token containers
        lemma_sm = doc_sm[0].lemma_ if len(doc_sm) > 0 else word
        lemma_md = doc_md[0].lemma_ if len(doc_md) > 0 else word
        lemma_lg = doc_lg[0].lemma_ if len(doc_lg) > 0 else word
        lemma_trf = doc_trf[0].lemma_ if len(doc_trf) > 0 else word

        print(row_fmt.format(word, lemma_sm, lemma_md, lemma_lg, lemma_trf))
    print("="*86)

if __name__ == "__main__":
    benchmark_expanded_set()