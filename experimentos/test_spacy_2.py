import spacy

nlp = spacy.load("es_dep_news_trf")

for word in [
    "hablábamos",
    "cantábamos",
    "estábamos",
    "íbamos",
    "comíamos",
    "vivíamos",
    "quito",
    "quisiéremos"
]:
    token = nlp(word)[0]
    print(f"{word:12} -> {token.lemma_:12} | {token.pos_}")

"""
FAILED:
->
hablábamos   -> hablábar     | VERB
cantábamos   -> cantár       | VERB
estábamos    -> estár        | AUX
íbamos       -> ír           | AUX
comíamos     -> comer        | VERB
vivíamos     -> vivir        | VERB
"""