import simplemma

# Define the exact list of words causing failures in the neural models
words = [
    "gatos", "corriendo", "mejores", "comieron", "casas", "fácilmente", 
    "hablábamos", "cantábamos", "estábamos", "íbamos", "comíamos", 
    "vivíamos", "quisiéremos", "quito","paciente",
    "conseguir",
    "máximo",
    "noviembre",
    "jamones",
    "líder",
    "hospital",
    "diversas",
    "Rafael",
    "vuelve",
    "destino",
    "torno",
    "proyectos",
    "flores",
    "niveles",     "verdugueaseis",
    "verdugueásemos",
    "verdugueasen",
    "verdugueases",
    "verdugueaste",
    "verdugueasteis",
]

# Run the strict dictionary lemmatizer using the Spanish language code ('es')
for word in words:
    lemma = simplemma.lemmatize(word, lang='es')
    print(f"{word:15} -> {lemma}")
