# 05 · Architecture

One Python process. No server, no port, no browser, no build step, no JavaScript anywhere (D9).

```
terminal ──▶ prompt_cache (Textual app) ──▶ SQLite file
                     │
                     └──▶ OS clipboard, filesystem (packs, backup)
```

## Stack

| Layer | Choice | Notes |
|---|---|---|
| Language | **Python 3.11+** | Installed is 3.10.11; `uv` supplies a newer one. Pin in `pyproject.toml`. |
| Package / env manager | **uv** (D10) | Matches kit. No Node toolchain anywhere. |
| UI | **Textual** | The TUI framework |
| Storage | **`sqlite3` + FTS5**, stdlib (D12) | No ORM, no migrations framework — plain SQL in a `migrations/` list |
| Clipboard | **pyperclip** | Solved problem; do not hand-roll. Wayland support confirmed at M1. |
| ULIDs | **python-ulid** | Solved problem; do not hand-roll |
| Fuzzy matching | **rapidfuzz** | Solved problem; do not hand-roll |
| Tests | **pytest** | The parser gets the heavy coverage |
| Lint / format | **ruff** | Single tool, fast |
| Packaging | `pyproject.toml`, console script `prompt-cache` | Installable with `uv tool install .` |

**Library-first, always.** If a maintained package solves a problem, use it rather than writing our own —
see `CLAUDE.md`. Adding a dependency is the expected outcome, not a cost to be minimised. The only code we write
by hand is what is genuinely specific to prompt-cache: the template grammar, the schema, and the UI.

## Package layout

```
prompt-cache/
  docs/
  pyproject.toml
  README.md
  src/prompt_cache/
    __init__.py
    __main__.py          entry point, `prompt-cache`
    core/                PURE. no I/O, no DB, no Textual.
      parser.py            {{…}} → Blank objects, warnings
      render.py            resolve includes, detect cycles, assemble output
      models.py            Prompt, Blank, Fill, Conversation dataclasses
      slug.py              title → name, tag extraction
    store/
      db.py                connection, pragmas, migrations
      migrations/          001_init.sql, …
      prompts.py           CRUD, versions, soft delete
      conversations.py     conversations and fills
      search.py            FTS5 + fuzzy + frecency ranking
    clipboard.py         thin wrapper over pyperclip: error handling + BOM strip
    ui/
      app.py               the Textual App, global bindings
      app.tcss             all styling
      screens/             search.py, fill.py, editor.py, conversation.py, settings.py
      widgets/             result list, blank fields, preview pane
    packs/
      export.py  import.py
      examples/            the shipped example pack (generic text only)
  tests/
    test_parser.py  test_render.py  test_search.py  test_clipboard.py
```

**`core/` is the heart and must stay pure** — no database, no filesystem, no Textual imports. It takes text and
values in and returns text and warnings out. It carries the bulk of the test suite, and it is the piece that
would survive if the UI were ever replaced.

## Data model

```sql
prompts (
  id              TEXT PRIMARY KEY,   -- ULID: sortable, generated locally
  name            TEXT UNIQUE NOT NULL,  -- slug used by {{@name}}
  title           TEXT NOT NULL,
  title_is_custom INTEGER NOT NULL DEFAULT 0,
  body            TEXT NOT NULL,
  pinned          INTEGER NOT NULL DEFAULT 0,
  use_count       INTEGER NOT NULL DEFAULT 0,
  last_used_at    TEXT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  deleted_at      TEXT                -- soft delete
);
prompt_versions  (id, prompt_id → prompts, title, body, created_at);
prompt_tags      (prompt_id → prompts, tag);          -- rebuilt from #tags on save
conversations    (id, label, label_is_custom, values_json,
                  created_at, updated_at, archived_at, deleted_at);
fills            (id, conversation_id → conversations, prompt_id → prompts,
                  prompt_version_id → prompt_versions, values_json, output, created_at);
settings         (key PRIMARY KEY, value_json);

prompts_fts        -- FTS5 over title, body, name, tags
conversations_fts  -- FTS5 over label, values
```

Notes:

- **Blanks are never rows.** They are parsed from the body by `core/parser.py` whenever needed. Storing them would
  create two sources of truth.
- `values_json` maps blank name → value. For choice-of-block blanks it stores the **chosen block name**.
- `fills.output` stores the fully assembled text, which is why editing a block never rewrites history.
- Timestamps are ISO-8601 UTC strings.
- Pragmas: `journal_mode=WAL`, `foreign_keys=ON`, `synchronous=NORMAL`.
- Migrations are a numbered list of SQL files applied in order, tracked by `PRAGMA user_version`.

## Where the data lives

| OS | Path |
|---|---|
| Windows | `%APPDATA%\prompt-cache\prompt-cache.db` |
| Linux | `$XDG_DATA_HOME/prompt-cache/prompt-cache.db` (default `~/.local/share/prompt-cache/`) |

`PROMPT_CACHE_DATA` overrides the directory. **Never inside the repo** — the repo is public (D19).

**Do not put this file in a cloud-synced folder.** Two machines writing a SQLite file through Dropbox or OneDrive
corrupts it. Template packs (D25) are the supported way to move things between machines.

## Clipboard

Critical to the product, and the most platform-sensitive part of it — which is exactly why it uses a library
rather than our own `ctypes` and `subprocess` code.

**Use `pyperclip`.** It already handles the Windows clipboard API and the Linux `xclip`/`xsel` tools, and it is
the established choice. Our own `clipboard.py` is a **thin wrapper** that does only what pyperclip does not:

- turn a missing backend into a clear, actionable message instead of an exception
- strip a leading BOM (U+FEFF) if one ever appears
- guarantee a clipboard failure never takes down the UI — catch, warn in the footer, carry on

**Verified at M1 (2026-09-20):** pyperclip 1.11.0 ships `init_wl_clipboard`, so `wl-copy`/`wl-paste` are
supported alongside `xclip`, `xsel`, Klipper and WSL. **No fallback of our own is needed.** A real OS round trip
passes on Windows with multi-line and non-ASCII text, and `tests/test_clipboard.py` repeats it on any machine that
has a backend (skipping where none exists).

Still to confirm on Linux: that a backend is actually installed on the owner's machine, and which session type it
runs.

If no backend is available, show a one-line message naming the package to install
(`wl-clipboard`, `xclip` or `xsel`) and fall back to manual paste. A missing clipboard tool must degrade the app,
never crash it.

Always UTF-8. Never alter the user's text beyond removing a BOM.

Clipboard behaviour is the thing most likely to differ between the two machines, so its tests should be runnable
on demand on each, and results reported honestly per platform.

## kit integration

prompt-cache is **standalone** (D8). It must run with `prompt-cache` on a machine with no kit installed, and it
must never import kit.

kit discovers tools by folder — every directory under its `tools/` **is** a tool, so there is no registry to
edit. The registration lives entirely in the **kit** repo as `tools/prompt-cache/`:

| File | What it does |
|---|---|
| `main.py` | Finds the `prompt-cache` console script on PATH and runs it, passing arguments and the exit code straight through |
| `tool.json` | `category: productivity`, aliases `pc` and `prompts`, `interactive: true` (a full-screen app, so kit hub does not try to embed it), and a `data` setting mapped to `PROMPT_CACHE_DATA` |
| `README.md` | Usage, settings, and how to install prompt-cache |

**kit never imports prompt-cache.** It launches the installed console script in a separate process, so the two keep
their own dependencies and either works without the other (D8). If the script is not on PATH, kit falls back to
`uv run --project $PROMPT_CACHE_HOME` when that variable points at a checkout, and otherwise prints install
instructions rather than a traceback.

`kit config prompt-cache.data <folder>` moves the database, which is the only thing kit knows about prompt-cache's
internals — and it goes through the documented `PROMPT_CACHE_DATA` variable rather than any private arrangement.

All this repo owes kit is a stable console-script name, arguments it can pass through, and a clean exit code.

## Security and privacy

Small surface, because there is no server:

- **No network calls.** None. v1 has no AI integration (D13) and no telemetry, ever.
- All data is local, in a file outside the repo.
- Template packs must **never include conversations**, since those contain the content of real posts and replies.
- The shipped example pack contains generic placeholder text only (D28).
- If AI drafting is added later, the key belongs in the local database or an environment variable — never in the
  repo, never in a pack.

## Running it

```
uv sync                         # set up the environment
uv run prompt-cache             # run from source
uv run pytest                   # tests
uv run ruff check src tests     # lint
uv tool install .               # install the console script
```

Then `prompt-cache`, or `kit prompt-cache` once registered.

## Environment gotchas

- **Security software that intercepts HTTPS** can break certificate validation for `uv`. If fetching a Python
  build or a package fails with an unknown-issuer error, that is the first suspect. This repo sets
  `native-tls = true` under `[tool.uv]` so the system certificate store is used — prefer that over ever disabling
  TLS verification.
- **PowerShell 5.1** has no `&&`; use `;` or `if ($?) { … }`. Piping text through it can prepend a UTF-8 BOM.
- **`NO_COLOR`** may be set; Textual should respect it.
- Windows terminals vary in their support for mouse events and true colour. Target Windows Terminal, and make sure
  the app is still usable in a plain console host.
- More detail, including the specific failures seen on the owner's machines, is in `docs/local/environment.md`
  (not published).
