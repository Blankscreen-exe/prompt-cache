# 07 · Roadmap

Each milestone ends in a **working, tested, committed** state. All the decisions these depend on are made
(06-decisions.md, D1–D28) — no milestone is blocked on a question.

Commits happen **only when the owner asks**, with no AI attribution in the message.

---

## M0 · Scaffold — **done (2026-09-20, Windows only)**

> Verified on Windows 11: `uv sync`, 26 tests passing, ruff clean, the app renders and quits, and the database is
> created and migrated at the correct path. **Not yet run on Linux** — that half of the acceptance criterion is
> outstanding. `uv` needed `native-tls = true` in `pyproject.toml` to get past HTTPS interception by local
> security software.

- `uv` project, `pyproject.toml`, `src/prompt_cache/` layout, console script `prompt-cache`.
- ruff and pytest configured and passing on an empty suite.
- SQLite connection with pragmas, the migration runner, and `001_init.sql` creating the full schema from
  05-architecture.md including both FTS5 tables.
- The database resolves to the correct per-OS path, honouring `PROMPT_CACHE_DATA`.
- A Textual app that opens, shows an empty search box and a footer, and quits cleanly.
- Root `README.md` with install and run instructions for Windows **and** Linux.
- MIT `LICENSE` (D19).

**Done when:** a fresh clone runs with `uv sync && uv run prompt-cache` on both Windows and Linux, the database
file is created in the right place on each, and the app opens and exits without error.

---

## M1 · Prompts: write, find, copy — **done (2026-09-20, Windows only)**

> 129 tests passing, ruff clean. Verified headlessly through Textual's pilot: typing plus Enter creates a prompt,
> a few characters plus Enter copies one, pin/delete/restore all work, and a broken clipboard warns instead of
> crashing. Search at 1,000 prompts is well inside budget. Libraries used rather than hand-rolled: `pyperclip`,
> `python-ulid`, `rapidfuzz`, `python-slugify`. **Not yet run on Linux.**
>
> Editor syntax highlighting deferred to M2 as the milestone allows.

- Create, edit with autosave, soft delete and restore. Title from the first line; `#tags` parsed; slug generated.
- The search palette: FTS5 plus fuzzy matching, grouped results, keyboard navigation, "Create prompt: *…*" when
  nothing matches.
- `Enter` copies — the clipboard module, working on both platforms.
- Pin, use counts, frecency ranking. Empty query shows Pinned / Recent / Most used.
- Trash view.

Syntax highlighting in the editor may slip to M2 if Textual's `TextArea` makes it awkward (see 04-ui.md).

**Done when:** writing a new prompt is typing plus `Enter` with no dialogs; finding and copying one is two or
three keystrokes; search stays responsive at 1,000 prompts; copy verified by hand on Windows and Linux.

---

## M2 · The template grammar and the fill form — **done (2026-09-20, Windows only)**

> 243 tests passing, ruff clean. The parser covers every form in 02-concepts.md and never raises: 15 malformed
> inputs are asserted to degrade rather than crash. The fill form pre-fills from the clipboard, previews live, and
> copies with Ctrl+Enter; focus lands on the copy button when nothing needs typing, so the whole flow really is
> open-then-copy. **Not yet run on Linux.**
>
> Editor syntax highlighting is still outstanding and now sits in M5.

The heart of the project. `core/` stays pure, and this is where the test suite earns its keep.

- `core/parser.py`: every form in 02-concepts.md — plain, `clipboard`, choices, explicit defaults, `optional`,
  comma-separated parts, escapes, case-insensitive names, repeated names. Unknown specs degrade to text blanks
  with a warning rather than raising.
- `core/render.py`: assemble output, apply the `optional` line-removal rule, collapse blank lines.
- The fill form: a field per blank by type, source badges, live preview, first-empty-field focus, `Ctrl+Enter` to
  copy.
- Clipboard pre-fill for `clipboard` blanks.

**Done when:** the parser has thorough unit tests including the awkward cases (a comma inside a choice option, an
option named `none` outside a block list, an unclosed `{{`, an escaped `\{{`, a blank repeated three times); and
the flow from "post copied" to "assembled prompt on clipboard" is a handful of keystrokes.

---

## M3 · Blocks, includes and choice-of-block

- `{{@name}}` resolution, nesting, **cycle detection reported by name**, depth cap of 10.
- `{{persona: @a | @b | none}}` — choice-of-block, resolving the same way once chosen.
- Blanks inside included blocks surface as blanks of the filling template.
- Editor: autocomplete for include names, warnings for missing includes, **"used by N templates"**.

**Done when:** editing one block changes the output of every template that includes it; a cycle produces a clear
message naming the prompts involved rather than a stack overflow; and one template serves both personas.

---

## M4 · Conversations and follow-ups

- Every fill saves into a conversation — created automatically, labelled from the longest value, editable.
- Values merge by blank name; later fills overwrite, history retains.
- **Continue with…**: pick another template, pre-filled from the conversation by name.
- Set a value from the clipboard (`Ctrl+S`).
- Conversations in search and Recent; conversation view with the values panel and the fill timeline.

**Done when:** the full follow-up flow (F5) works — the post and the earlier comment fill themselves, only the new
reply comes from the clipboard, and nothing needed naming along the way.

---

## M5 · Safety, packs and polish

- Versions with debounce, a diff view, restore.
- Template pack export and import, with a collision preview.
- Full JSON backup of everything.
- The shipped example pack, and the first-run offer to import it (F11).
- Editor syntax highlighting for `{{blanks}}`, `{{@includes}}` and `#tags` (deferred from M1 and M2).
- Settings screen and the key binding reference.

**Done when:** templates can be moved between the PC and the laptop by exporting a pack and importing it, and no
edit is unrecoverable.

---

## After v1

Nothing below is committed. Listed so the design does not accidentally block them.

- **AI drafting** (D13, Q1): provider setting, key in the local DB or an env var, two or three drafts to pick
  from, chosen one to the clipboard. The design must keep this possible, not prepare for it.
- **More value sources**: `{{x: date}}`, `{{x: shell: <cmd>}}`, `{{x: file}}`. The source registry in `core/`
  exists from M2 precisely so these are a few lines each rather than a parser rewrite (D23).
- Grouping conversations by person rather than by thread (rejected for v1, D27).
- A second UI over the same `core/` — the purity rule is what keeps this cheap.

---

## Remaining open questions

Both are deliberately deferred, and both answer themselves once real templates exist:

- **Q19** — the rest of the standing-context blocks the owner could not recall.
- **Q21** — what the shipped example templates should actually say. Draft them at M5 and have the owner correct
  them, rather than guessing up front.
