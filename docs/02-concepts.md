# 02 · Concepts and the template grammar

The model is deliberately small: **prompts** (which may contain **blanks** and **includes**), **conversations**
made of **fills**, and automatic **versions**. There is only one kind of stored text — a "block" such as agency
info is just a prompt that other prompts include.

> **The rule (D26).** Nothing in this file names a domain. `post`, `my_comment`, `agency-info` are *examples*.
> The engine knows the grammar below and nothing else. No blank name, template or block may be special-cased in
> code.

---

## Prompt

A piece of text the user saves.

| Field | Behaviour |
|---|---|
| **Title** | The first line of the body, with leading `#` stripped. Overridable, never required. |
| **Body** | Plain text or Markdown. May contain blanks, includes and inline tags. |
| **Name** (slug) | Generated from the title, used by includes (`{{@agency-info}}`). Unique, editable; renaming rewrites includes that point at it, or warns if it cannot. |
| **Tags** | Parsed from inline `#word` tokens, ignoring fenced code blocks. Never required. |
| **Pinned** | One keypress. |
| **Usage** | `use_count` and `last_used_at`, updated on copy or fill. Feeds ranking. |
| **Soft delete** | Deleted prompts are recoverable from a trash view. |

A prompt with no blanks is simply copied as-is. There is no separate "template" type — a template is just a prompt
that happens to contain blanks.

---

## The template grammar

This is the whole language. It is the part that is code, and the part that is expensive to change.

```
blank    := "{{" name [ ":" spec ] "}}"
include  := "{{" "@" block-name "}}"
name     := [A-Za-z] [A-Za-z0-9_-]*
spec     := part ("," part)*
part     := "clipboard" | "optional" | choices
choices  := option ("|" option)* [ "=" default ]
option   := text | "@" block-name | "none"
escape   := "\{{"      -- renders a literal "{{"
```

### Forms

| Written | Means |
|---|---|
| `{{post}}` | Text blank named `post`, multi-line input |
| `{{post: clipboard}}` | Text blank, **pre-filled from the clipboard** when the form opens |
| `{{tone: professional \| friendly \| witty}}` | Choice blank. The **first option is the default**. |
| `{{tone: professional \| friendly = friendly}}` | Choice blank with an explicit default |
| `{{persona: @me-profile \| @agency-info}}` | **Choice-of-block.** Picking an option inserts that block's body. |
| `{{proof: @my-cases \| @agency-cases \| none}}` | Choice-of-block with an opt-out (see `none` below) |
| `{{my_comment: optional}}` | May be left empty (see below) |
| `{{note: clipboard, optional}}` | Parts combine with commas |
| `{{@agency-info}}` | **Static include** — always inserts that block |
| `\{{` | A literal `{{` |

### Parsing rules

- **Names are case-insensitive** identifiers: letters, digits, `_`, `-`. `{{Post}}` and `{{post}}` are one blank.
- **The same name may appear many times** in a template. It is one input, repeated in the output.
- **Spec parsing:** split the spec on commas; any part that is exactly `clipboard` or `optional` is taken as a
  flag; the remaining parts are re-joined **with their original spacing** and treated as the choice list. This
  means a choice option may contain a comma (`{{tone: short, punchy | long}}` gives two options) but an option may
  not *be* the bare word `clipboard` or `optional`.
- **`=` is only special in the final option**, so `{{x: a=b | c}}` keeps `a=b` as an option rather than reading it
  as a default. A default that matches no option warns and falls back to the first.
- **A repeated name keeps its first declaration.** `{{post: clipboard}} … {{post}}` is one clipboard blank; a
  second *differing* declaration warns and is ignored. The label shown uses the first spelling.
- `clipboard` on a choice blank makes no sense and is ignored with a warning.
- **Tolerance:** an unrecognised spec is a **warning shown in the editor, not a crash**. The blank degrades to a
  plain text blank so the template still works.
- Whitespace around names, options and `=` is trimmed.
- The editor highlights blanks and includes, and flags includes that point at prompts which do not exist.

### `optional`

If an optional blank is left empty, **the entire line it sits on is removed** from the output. Blank lines then
collapse to at most one — **but only when something was actually removed.** If no line was dropped, the author's
spacing is reproduced byte for byte, so a deliberate double blank line in a template survives.

This is what makes a labelled section disappear cleanly:

```
MY COMMENT: {{my_comment: optional}}
```

Empty, that whole line goes — you do not get a dangling `MY COMMENT:`.

### `none`

In a choice-of-block list, a bare option written as `none` means **insert nothing, and remove the line**. Because
every other option in such a list starts with `@`, a bare word is unambiguous. `none` is only special inside a
choice-of-block list; elsewhere it is ordinary option text.

---

## Includes and blocks

- `{{@name}}` inserts another prompt's **whole body** at fill time — including its first
  line, which is also its title. That is usually wanted (the title reads as a section label), but it is worth
  knowing when authoring blocks. **Open: see Q22.**
- **Blanks inside an included block become blanks of the template being filled.** A block can therefore carry its
  own placeholders.
- Includes may nest. **Cycles are detected** (A includes B includes A) and reported by naming the whole chain
  (`a -> b -> a`); the cycle contributes nothing and the rest of the output survives. Depth is capped at **10**.
- A **diamond is not a cycle**: two different paths reaching the same block both resolve.
- A block that does not exist (or has been deleted) is reported as a **missing include** and contributes nothing,
  rather than failing the fill.
- Editing a block changes every template that includes it, immediately. A fill stores the **fully assembled
  output**, so past conversations never change retroactively.
- Choice-of-block blanks resolve the same way as static includes once an option is chosen, including nesting and
  cycle checks.

---

## Fill

One use of a prompt.

1. **Resolve** static includes and collect every blank, in order of first appearance.
2. **Pre-fill** each value, first match wins:
   1. A value already in the current conversation, matched **by blank name**
   2. The clipboard, for `clipboard` blanks
   3. An explicit default (`= x`)
   4. The first option, for choice blanks
   5. Empty
3. The user edits values in a form with a **live preview** of the assembled output.
4. On confirm: assemble, **copy to the clipboard**, and save the fill into a conversation (new or existing).

A fill stores the prompt id, the **prompt version** used, all blank values, the assembled output and a timestamp.
For choice-of-block blanks it stores **the option as written** (`@agency-info`), never the expanded text — so a
later edit to that block does not rewrite what a past fill recorded.

---

## Conversation

A thread of related fills — one post and its replies (D27).

- **Created automatically** by the first fill of a template. No naming required. The label is derived from the
  longest text value in the fill, truncated to roughly eight words. Editable.
- Holds a **merged map of values** by blank name, built from its fills plus anything added directly. Later fills
  overwrite earlier values of the same name; the fill history keeps the old ones.
- **Continue with…** — pick another template; its blanks pre-fill from the conversation by name. This is what
  makes reply-to-a-reply nearly free, and it is why **consistent blank naming across your templates matters**.
- The user can **set a value from the clipboard** at any time (for example, saving the comment they actually
  posted).
- Conversations are searchable by label and values, and appear under Recent.
- **Kept forever** (D18). Archive by hand; nothing expires.

Grouping is per thread, not per person. Following the same person across two different posts is a search, not a
feature.

---

## Versions

- Every save of a prompt body creates a version, **debounced** — at most one per ~30 s of continuous editing, and
  always one on blur or close. Typing must not create hundreds.
- Full text is kept per version. Prompts are small.
- The user can view history, diff two versions and restore one. **Restore creates a new version** and never
  destroys history.

---

## Search and ranking

One search box covers **prompts** (title, body, tags, name) and **conversations** (label, values).

- SQLite **FTS5** full-text, plus fuzzy/prefix matching so "lnkd rep" finds "LinkedIn reply to reply".
- Ranked by match quality blended with **frecency** (recency × frequency of use), with a boost for pinned items.
- An empty query shows **Pinned**, then **Recent**, then **Most used**.
- Enter runs the primary action: copy for a plain prompt, open the fill form for a template, open for a
  conversation. Edit, pin and continue are separate bindings.

---

## Template packs

A pack is a portable set of **prompts and blocks — never conversations** (D25).

- **Export:** choose prompts (or all), write a folder of Markdown files plus a `pack.json` manifest holding names,
  tags and pin state.
- **Import:** read a pack, preview what it contains, flag name collisions, then merge.
- This is also the **sync mechanism** between the PC and the laptop (D16). There is no automatic sync, and the
  SQLite file itself must never be put in a cloud-synced folder — concurrent access corrupts it.
- A separate full **JSON dump** of everything (prompts, versions, conversations) exists for backup.

The prompts that ship with the app are just a pack, imported on first run (D24, D28) — the user's template
structures with **generic example text** in the blocks, since the repo is public.
