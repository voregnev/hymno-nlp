-- scripts/init_postgres.sql
-- Полная схема для гимнографического корпуса

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- для нечёткого поиска

-- ─── Основная таблица текстовых единиц ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS text_units (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_ref      TEXT NOT NULL UNIQUE,   -- "oktoih_cu/0012/block_034"
    lang            CHAR(3) NOT NULL,        -- cu | grc | ru
    book            TEXT NOT NULL,           -- octoechos | menaion | triodion | pentecostarion

    -- Суточный круг
    office          TEXT,     -- vespers_small | vespers_great | matins | liturgy | midnight | hours_1..9
    section         TEXT,     -- lihc | aposticha | praises | canon | kathisma | hypakoe | exapost | litya
    ode_number      SMALLINT, -- 1-9, только для canon
    unit_type       TEXT,     -- stichera | troparion | hirmos | kontakion | kathisma_hymn | theotokion | doxasticon | exapostilarion | katavasia
    section_order   SMALLINT,
    total_in_section SMALLINT,

    -- Седмичный круг (Октоих)
    glas            SMALLINT,  -- 1-8
    day_of_week     SMALLINT,  -- 0=Вс..6=Сб

    -- Годичный круг — неподвижный (Минея)
    menaion_month   SMALLINT,
    menaion_day     SMALLINT,

    -- Годичный круг — подвижный (Триодь/Пятидесятница)
    pascha_offset   SMALLINT,  -- дней от Пасхи: -70..+56

    -- Атрибуты текста
    full_text       TEXT NOT NULL,
    incipit         TEXT GENERATED ALWAYS AS (left(full_text, 100)) STORED,
    genre           TEXT,      -- дублирует unit_type, может быть уточнён
    author          TEXT,
    author_confidence TEXT,    -- high | medium | low
    podoben         TEXT,      -- инципит подобна
    acrostic        TEXT,      -- "alphabetic:АБВГ" или "named:ИОАНН"
    translation_type TEXT,     -- literal | paraphrase | original

    -- Флаги
    is_doxasticon   BOOL DEFAULT FALSE,
    is_theotokion   BOOL DEFAULT FALSE,
    theotokion_source TEXT,    -- feast | resurrection | sunday | weekday

    -- Техническая информация
    parse_method    JSONB,     -- {"glas":"regex","author":"llm",...}
    needs_review    BOOL DEFAULT FALSE,
    edition         TEXT,      -- synodal | studion | jerusalem
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),

    -- Полнотекстовый поиск
    search_vec      tsvector GENERATED ALWAYS AS
                    (to_tsvector('russian', coalesce(full_text, ''))) STORED
);

-- ─── Строфы ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS strophes (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    unit_id     UUID NOT NULL REFERENCES text_units(id) ON DELETE CASCADE,
    position    SMALLINT NOT NULL,
    text        TEXT NOT NULL,
    refrain     TEXT,           -- рефрен перед строфой, если есть
    UNIQUE(unit_id, position)
);

-- ─── Экспертные аннотации ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS annotations (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    unit_id     UUID NOT NULL REFERENCES text_units(id) ON DELETE CASCADE,
    annotator   TEXT NOT NULL,
    type        TEXT NOT NULL,  -- philological | theological | translation | liturgical
    body        TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Библейские аллюзии ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS biblical_refs (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    unit_id     UUID NOT NULL REFERENCES text_units(id) ON DELETE CASCADE,
    book        TEXT NOT NULL,
    chapter     SMALLINT,
    verse       SMALLINT,
    ref_type    TEXT DEFAULT 'allusion',  -- direct | allusion | paraphrase
    confidence  TEXT DEFAULT 'medium'
);

-- ─── Индексы ─────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_tu_lang_genre     ON text_units (lang, genre);
CREATE INDEX IF NOT EXISTS idx_tu_glas_dow       ON text_units (glas, day_of_week) WHERE book = 'octoechos';
CREATE INDEX IF NOT EXISTS idx_tu_menaion        ON text_units (menaion_month, menaion_day) WHERE book = 'menaion';
CREATE INDEX IF NOT EXISTS idx_tu_pascha         ON text_units (pascha_offset) WHERE pascha_offset IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tu_position       ON text_units (book, office, section, lang);
CREATE INDEX IF NOT EXISTS idx_tu_search         ON text_units USING GIN (search_vec);
CREATE INDEX IF NOT EXISTS idx_tu_incipit_trgm   ON text_units USING GIN (incipit gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_tu_needs_review   ON text_units (needs_review) WHERE needs_review = TRUE;
CREATE INDEX IF NOT EXISTS idx_strophe_unit      ON strophes (unit_id);
CREATE INDEX IF NOT EXISTS idx_annot_unit        ON annotations (unit_id);
CREATE INDEX IF NOT EXISTS idx_bibl_unit         ON biblical_refs (unit_id);
