# prompt-cache

Write, find and fill reusable AI prompts in seconds — from the terminal.

Most prompting is assembly work: pasting the same standing context, the same instructions and one new piece of
text into a chat window, over and over, then doing it again for the follow-up. prompt-cache keeps the fixed parts,
pulls the changing part off your clipboard, and hands you the finished prompt ready to paste.

```
Write a comment on the post below. Under 80 words. No hashtags, no emojis.

{{@my-voice}}
{{persona: @me-profile | @agency-info}}

POST:
{{post: clipboard}}
```

Copy a post, run `prompt-cache`, type a few letters, press Enter. The assembled prompt is on your clipboard.

> **Status: in development.** The scaffold and database layer exist; prompts, search and fill do not yet.
> See [docs/07-roadmap.md](docs/07-roadmap.md).

## Preview

![preview](/docs/images/preview.png)

## Why

- **No folders, no file names, no save button.** You write; it saves. The first line is the title.
- **One search box.** Fuzzy, ranked by how recently and often you use things.
- **Templates with blanks**, filled from the clipboard, a dropdown, or a reusable block.
- **It remembers threads**, so a reply to a reply reuses the original post and your earlier comment.
- **Local and private.** One SQLite file on your machine. No accounts, no network calls, no telemetry.

Nothing about any particular use case is built into the app. It ships a template grammar; every template, block
and field name is yours.

## Install

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+ (uv will fetch Python if you don't have it).

```bash
git clone https://github.com/Blankscreen-exe/prompt-cache
cd prompt-cache
uv tool install .
prompt-cache
```

### Run from source

```bash
uv sync
uv run prompt-cache
```

On **Windows** (PowerShell 5.1 has no `&&`):

```powershell
uv sync; if ($?) { uv run prompt-cache }
```

### Linux clipboard

Clipboard access needs one of these installed — most desktops already have one:

| Session | Package |
|---|---|
| Wayland | `wl-clipboard` |
| X11 | `xclip` or `xsel` |

Windows needs nothing extra.

## Usage

| Key | Does |
|---|---|
| type | search everything |
| `Enter` | use the selected result — copy it, or open its fill form |
| `Ctrl+Enter` | confirm a fill and copy the assembled prompt |
| `Ctrl+N` | new prompt |
| `Ctrl+E` | edit the selected prompt |
| `Ctrl+P` | pin |
| `Esc` | back one level |
| `Ctrl+Q` | quit |

### Template syntax

| Written | Means |
|---|---|
| `{{post}}` | a text field |
| `{{post: clipboard}}` | a text field, pre-filled from the clipboard |
| `{{tone: brief \| detailed}}` | a dropdown; the first option is the default |
| `{{tone: brief \| detailed = detailed}}` | a dropdown with an explicit default |
| `{{persona: @me \| @agency}}` | a dropdown that inserts one of those blocks |
| `{{note: optional}}` | may be left empty — its line disappears if it is |
| `{{@my-voice}}` | always insert that block |
| `\{{` | a literal `{{` |

Full reference: [docs/02-concepts.md](docs/02-concepts.md).

## Where your data lives

| OS | Path |
|---|---|
| Windows | `%APPDATA%\prompt-cache\prompt-cache.db` |
| Linux | `$XDG_DATA_HOME/prompt-cache/prompt-cache.db` (default `~/.local/share/prompt-cache/`) |

Set `PROMPT_CACHE_DATA` to put it somewhere else. `prompt-cache --where` prints the current path.

**Don't put this file in Dropbox, OneDrive or any synced folder** — two machines writing one SQLite file will
corrupt it. To move templates between machines, export a template pack instead.

## Development

```bash
uv sync
uv run pytest
uv run ruff check src tests
uv run ruff format src tests
```

The design docs in [`docs/`](docs/README.md) are the source of truth — read
[`docs/06-decisions.md`](docs/06-decisions.md) before proposing changes.

`src/prompt_cache/core/` is pure: no database, no filesystem, no Textual imports. It holds the parser and
renderer, and carries most of the test suite. Keep it that way.

## Licence

MIT — see [LICENSE](LICENSE).
