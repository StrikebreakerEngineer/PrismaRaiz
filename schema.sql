-- ============================================
-- BORRAR TABLAS (para desarrollo)
-- ============================================

DROP TABLE IF EXISTS synonyms;
DROP TABLE IF EXISTS definitions;
DROP TABLE IF EXISTS locution_senses;
DROP TABLE IF EXISTS locutions;
DROP TABLE IF EXISTS conjugations;
DROP TABLE IF EXISTS rae_entries;
DROP TABLE IF EXISTS examples;

DROP TABLE IF EXISTS word_lemmas;
DROP TABLE IF EXISTS lemmas;
DROP TABLE IF EXISTS raw_words;


-- ============================================
-- PALABRAS ORIGINALES DEL CORPUS
-- ============================================

CREATE TABLE raw_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    rank INTEGER NOT NULL,

    word TEXT NOT NULL,

    source TEXT NOT NULL,

    imported_at TEXT DEFAULT CURRENT_TIMESTAMP
);


-- ============================================
-- LEMAS
-- (hablar, comer, ser...)
-- ============================================

CREATE TABLE lemmas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    lemma TEXT NOT NULL UNIQUE,

    part_of_speech TEXT,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);


-- ============================================
-- RELACIÓN:
-- hablábamos → hablar
-- niños → niño
-- ============================================

CREATE TABLE word_lemmas (
    raw_word_id INTEGER NOT NULL,

    lemma_id INTEGER NOT NULL,

    PRIMARY KEY (raw_word_id, lemma_id),

    FOREIGN KEY (raw_word_id)
        REFERENCES raw_words(id),

    FOREIGN KEY (lemma_id)
        REFERENCES lemmas(id)
);


-- ============================================
-- ENTRADA COMPLETA DE LA RAE
-- ser, vino, entretejer...
-- ============================================

CREATE TABLE rae_entries (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    lemma_id INTEGER NOT NULL UNIQUE,

    origin TEXT,

    raw_json TEXT,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (lemma_id)
        REFERENCES lemmas(id)
);


-- ============================================
-- DEFINICIONES / ACEPCIONES
--
-- ser:
-- 1. copulativo
-- 2. auxiliar
-- 3. existir
--
-- vino:
-- 1. bebida
-- 2. zumo fermentado
-- ============================================

CREATE TABLE definitions (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    rae_entry_id INTEGER NOT NULL,

    meaning_number INTEGER,

    category TEXT,

    subcategory TEXT,

    gender TEXT,

    usage TEXT,

    description TEXT,

    raw TEXT,

    FOREIGN KEY (rae_entry_id)
        REFERENCES rae_entries(id)
);


-- ============================================
-- EJEMPLOS
--
-- "Son las tres."
-- "Antonio es de Madrid."
-- ============================================

CREATE TABLE examples (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    definition_id INTEGER NOT NULL,

    example TEXT NOT NULL,

    FOREIGN KEY (definition_id)
        REFERENCES definitions(id)
);


-- ============================================
-- SINÓNIMOS
--
-- ser → existir
-- vino → caldo
-- ============================================

CREATE TABLE synonyms (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    definition_id INTEGER NOT NULL,

    word TEXT NOT NULL,

    label TEXT,

    FOREIGN KEY (definition_id)
        REFERENCES definitions(id)
);


-- ============================================
-- LOCUCIONES
--
-- vino:
-- dormir el vino
-- ser de lo que no hay
-- ============================================

CREATE TABLE locutions (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    rae_entry_id INTEGER NOT NULL,

    expression TEXT NOT NULL,

    FOREIGN KEY (rae_entry_id)
        REFERENCES rae_entries(id)
);


CREATE TABLE locution_senses (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    locution_id INTEGER NOT NULL,

    meaning_number INTEGER,

    category TEXT,

    usage TEXT,

    description TEXT,

    raw TEXT,

    FOREIGN KEY (locution_id)
        REFERENCES locutions(id)
);


-- ============================================
-- CONJUGACIONES
--
-- ser:
-- present
-- first_person
-- soy
--
-- entretejer:
-- future_subjunctive
-- nosotros
-- entretejiéremos
-- ============================================

CREATE TABLE conjugations (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    lemma_id INTEGER NOT NULL,

    mood TEXT,

    tense TEXT,

    person TEXT,

    form TEXT,

    FOREIGN KEY (lemma_id)
        REFERENCES lemmas(id)
);