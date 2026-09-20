-- 001_init: the whole schema from docs/05-architecture.md.
--
-- Blanks are deliberately NOT stored. They are parsed from prompt bodies by core/ whenever
-- needed; storing them would create a second source of truth that can drift from the text.

CREATE TABLE prompts (
    id              TEXT PRIMARY KEY,           -- ULID: sortable, generated locally
    name            TEXT NOT NULL UNIQUE,       -- slug used by {{@name}}
    title           TEXT NOT NULL,
    title_is_custom INTEGER NOT NULL DEFAULT 0,
    body            TEXT NOT NULL,
    pinned          INTEGER NOT NULL DEFAULT 0,
    use_count       INTEGER NOT NULL DEFAULT 0,
    last_used_at    TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT                        -- soft delete
);

CREATE INDEX idx_prompts_live    ON prompts (deleted_at, updated_at DESC);
CREATE INDEX idx_prompts_pinned  ON prompts (pinned, last_used_at DESC);
CREATE INDEX idx_prompts_used    ON prompts (use_count DESC, last_used_at DESC);

CREATE TABLE prompt_versions (
    id         TEXT PRIMARY KEY,
    prompt_id  TEXT NOT NULL REFERENCES prompts (id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_versions_prompt ON prompt_versions (prompt_id, created_at DESC);

-- Rebuilt from the #tags found in the body on every save.
CREATE TABLE prompt_tags (
    prompt_id TEXT NOT NULL REFERENCES prompts (id) ON DELETE CASCADE,
    tag       TEXT NOT NULL,
    PRIMARY KEY (prompt_id, tag)
);

CREATE INDEX idx_tags_tag ON prompt_tags (tag);

-- One post and its replies (D27). Grouping is per thread, never per person.
CREATE TABLE conversations (
    id              TEXT PRIMARY KEY,
    label           TEXT NOT NULL,
    label_is_custom INTEGER NOT NULL DEFAULT 0,
    values_json     TEXT NOT NULL DEFAULT '{}', -- blank name -> value
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    archived_at     TEXT,
    deleted_at      TEXT
);

CREATE INDEX idx_conversations_live ON conversations (deleted_at, archived_at, updated_at DESC);

-- output holds the FULLY ASSEMBLED text, so editing a block never rewrites history.
CREATE TABLE fills (
    id                TEXT PRIMARY KEY,
    conversation_id   TEXT NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    prompt_id         TEXT NOT NULL REFERENCES prompts (id),
    prompt_version_id TEXT REFERENCES prompt_versions (id),
    values_json       TEXT NOT NULL DEFAULT '{}',
    output            TEXT NOT NULL,
    created_at        TEXT NOT NULL
);

CREATE INDEX idx_fills_conversation ON fills (conversation_id, created_at DESC);
CREATE INDEX idx_fills_prompt       ON fills (prompt_id, created_at DESC);

CREATE TABLE settings (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);

-- Full-text search.
--
-- These are plain FTS5 tables rather than external-content ones: `tags` is derived rather than a
-- column of `prompts`, and `values_text` is flattened JSON, so there is no content table to point
-- at. The store layer keeps them in sync on write (delete + insert by id).

CREATE VIRTUAL TABLE prompts_fts USING fts5 (
    prompt_id UNINDEXED,
    title,
    body,
    name,
    tags,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE VIRTUAL TABLE conversations_fts USING fts5 (
    conversation_id UNINDEXED,
    label,
    values_text,
    tokenize = 'unicode61 remove_diacritics 2'
);
