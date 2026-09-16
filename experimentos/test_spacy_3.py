import spacy

# 1. Load the Spanish model
nlp = spacy.load("es_core_news_lg")

# 2. Define your list of Spanish words
spanish_words = ["gatos",
                "corriendo",
                "mejores",
                "comieron",
                "casas",
                "fácilmente",
                "hablábamos",
                "cantábamos",
                "estábamos",
                "íbamos",
                "comíamos",
                "vivíamos",
                "quito",
                "quisiéremos",
                "gamo-"]

# 3. Process the words as a single string separated by spaces
# spaCy performs best when words are evaluated with spacing context
text = " ".join(spanish_words)
doc = nlp(text)

# 4. Extract the lemmas
# Use .lemma_ to get the string representation
lemmas = [token.lemma_ for token in doc if not token.is_space]

# Print the results side by side
for original, lemma in zip(spanish_words, lemmas):
    print(f"{original} -> {lemma}")

"""
MODELS TESTING:

- es_dep_news_trf
gatos -> gato
corriendo -> correr
mejores -> mejor
comieron -> comer
casas -> casa
fácilmente -> fácilmente
hablábamos -> hablábar
cantábamos -> cantábamos
estábamos -> estár
íbamos -> ír
comíamos -> comíir
vivíamos -> vivíamos
quito -> quito
quisiéremos -> quisiéer

- es_core_news_sm
gatos -> gato
mejores -> mejor
comieron -> comer
casas -> casa
fácilmente -> fácilmente
hablábamos -> hablár
cantábamos -> cantár
estábamos -> estár
íbamos -> ír
comíamos -> comer
vivíamos -> vivir
quito -> quito
quisiéremos -> quisiéremos

- es_core_news_lg
gatos -> gato
corriendo -> correr
mejores -> mejor
comieron -> comer
casas -> casa
fácilmente -> fácilmente
hablábamos -> hablár
cantábamos -> cantár
estábamos -> estár
íbamos -> ír
comíamos -> comer
vivíamos -> vivir
quito -> quitar
quisiéremos -> quisiéremos
"""