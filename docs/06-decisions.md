# 06 · Decisions

## Decided (by the user)

### Product (from the original design discussion)

| # | Decision | Notes |
|---|---|---|
| D1 | prompt-cache lives in **its own git repo** (this folder) | Standalone, but **registered with kit** so `kit prompt-cache` launches it (see D8) |
| D2 | ~~React web UI~~ **Superseded by D9 (2026-09-20): Textual TUI** | React was chosen for "rich interaction"; simplicity won instead |
| D3 | Focus is a **prompt cache**, not a general notes app | The CherryTree/Obsidian-style notes idea was dropped |
| D4 | **Zero management** is a hard requirement | No folders, files or naming. Write and retrieve "in a jiffy". |
| D5 | The core use case is **assembling prompts** from fixed instructions, standing context and clipboard content, with **follow-ups** | The comment and reply-to-reply flows (03-user-flows.md) |
| D6 | Must work on **Windows and Linux** | The user works on both |
| D7 | A blog idea tool was discussed and **dropped** | Don't build it here |

### Tech stack and scope (decided 2026-09-20)

| # | Was | Decision | Notes |
|---|---|---|---|
| D8 | — | **Standalone, registered with kit** | Own repo, own entry point, runs on its own. kit registers it so `kit prompt-cache` works. prompt-cache must not *require* kit. |
| D9 | Q2 + Q10 | **Textual TUI, pure Python** | No web UI, no separate backend/frontend, no server, no port, no build step, no Node. Reverses D2. |
| D10 | Q11 | **uv + Python** | Matches kit. No Node toolchain anywhere in the project. |
| D11 | Q7 | **Blank syntax as documented** | `{{post}}`, `{{post: clipboard}}`, `{{tone: a \| b \| c}}`, `{{tone: a \| b = b}}`, `{{x: optional}}`, `{{@block}}`, `\{{` escape. Exactly as 02-concepts.md. |
| D12 | — | **SQLite + FTS5** | Python stdlib `sqlite3`, no ORM. One file in the user data folder, outside the repo. |
| D13 | Q1 | **Clipboard only for v1** | Assemble → copy → paste into ChatGPT. No API calls, no API keys. Nothing in the design should block adding drafting later. |
| D14 | Q3 | **No launcher work** | Just run `kit prompt-cache` in whatever terminal is open. No global hotkey, no always-on window. See the note on the 5-second target below. |
| D15 | Q4 | **Moot** | A TUI has no background server, so there is nothing to start at login. |
| D16 | Q5 | **Export / import only** | A JSON dump copied between the PC and the laptop by hand. No sync machinery. The SQLite file must not go in a cloud-synced folder. |
| D17 | Q6 | **No Obsidian import** | Dropped. Existing prompts get re-typed. M6 is removed from the roadmap. |
| D18 | Q9 | **Keep conversations forever** | Nothing auto-deletes or auto-archives. Archive by hand. Matches principle 5, "nothing is ever lost". |
| D19 | Q12 | **Public repo, MIT licence** | Personal data (agency info, conversations) lives in the local DB outside the repo, so nothing personal is published. Starter templates will be public. |
| D20 | Q13 | **Shared voice block + thin per-platform templates** | A `{{@social-voice}}` block holds how the user writes; `linkedin-comment`, `x-reply`, `reddit-comment` etc. are thin wrappers holding only that platform's rules. X's character limit and Reddit's hostility to marketing-speak are real structural differences, not tone settings. |
| D21 | Q15 | **Standing-context blocks are a personal/agency pair** | Confirmed so far: social profile, freelancer profile, agency info, my projects, agency projects, my case studies, agency case studies. The user expects more to surface later. See "The me/agency split" below. |
| D22 | Q14 | **The original docs were discarded and rewritten** | The user: *"the old docs are not to be heeded. I tell you what to do."* The first version of 01–05 and 07 described a React web app and invented the LinkedIn templates wholesale. All of it was **rewritten on 2026-09-20** against D1–D28. If anything anywhere still mentions React, Node, pnpm, Hono or an HTTP API, it is a leftover and it is wrong. |
| D23 | Q16 | **Grammar = documented set + choice-of-block** | D11's syntax plus `{{persona: @me-profile \| @agency-info}}`, a choice blank whose options are includes. Value sources are a **registry** internally, so `date`/`shell`/`file` can be added later without touching the parser. |
| D24 | — | **Ship the user's own templates as defaults** | Not generic examples — the user's real templates are the shipped starter pack. See the caveat on blocks below. |
| D25 | — | **Template packs, covering sync** | Export/import a curated set of templates + blocks (no conversations). Doubles as the PC↔laptop sync mechanism, satisfying D16. |
| D26 | — | **Placeholders are entirely user-defined** | No blank name is known to the app. `post`, `my_comment` etc. in these docs are examples, not schema. The app supplies the *grammar*; the user supplies all content. This is a design constraint: nothing about LinkedIn, agencies or marketing may be hardcoded. |
| D27 | Q18 | **Conversations group by thread** | A fill is saved into a conversation representing **one post and its replies**, auto-labelled from the post's first words. Opening it pre-fills values by blank name into the next template. Broadly as 02-concepts.md describes. Cross-thread grouping by person is **not** in scope. |
| D28 | Q20 | **Shipped blocks carry generic example text** | Not the user's real business content (public repo), and not empty stubs either — **basic example prompts**, so a new user (and the user on a fresh machine) sees a working shape immediately and overwrites it with their own. |

### What the user actually does (from Q8, 2026-09-20)

The owner's answer to Q8 widened the core use case. It is **not specific to any one platform** — it is writing to
people across several social channels, and the channels will change. Their own wording is kept in
`docs/local/owner-context.md`, which is not published. Starter templates to ship:

| Template | Status |
|---|---|
| Social comment + reply-to-reply (LinkedIn, X, Reddit) | **Yes** — the core flow. See Q13 on how to handle per-platform differences. |
| Email replies | **Yes** — thread from clipboard + tone + signature block |
| Generic proposal | **Yes** — for use where no dedicated tool already exists |
| Code review / commit messages | Not requested |

### Templates vs. content (the line that matters)

A recurring mistake in this project's design discussions has been treating the user's *template content* as if it
were a product feature. It is not.

| The user's, entirely | The app's (code) |
|---|---|
| Blank **names** — any identifier | The `{{name}}` syntax |
| Choice **options** and defaults | `\|` choices, `=` default, `optional` |
| **Blocks** and their text | `@` includes, cycle detection |
| **Templates** — all of them | `clipboard` and other value sources |
| Which flows they run | Search, conversations, versions |

Design questions are only real if they fall in the right-hand column. "Should the social template use tone or
angle?" is not a product question — it is one word in a template the user edits in five seconds.


### The me/agency split (from Q15)

The block list is not a flat list — it is **the same set of facts, twice**: *my* profile/projects/case studies and
*the agency's* profile/projects/case studies. The user markets both, sometimes in the same channel.

This matters for template design. A static `{{@agency-info}}` include (as 02-concepts.md assumes) forces a separate
copy of every template per persona. The proposed fix is a **choice blank whose options are includes** — see Q16.


## Open questions: ask the user before building

| # | Question | Options / notes | Suggested default |
|---|---|---|---|
| Q22 | **Should an include drag in the block's title line?** Every prompt's first line is its title, so `{{@agency-info}}` currently inserts `Agency info` as well as the body. | (a) keep the whole body, as now and as specified; (b) skip the first line when including; (c) a modifier such as `{{@agency-info: body}}` to choose | (a) until it annoys |
| Q19 | **The remaining blocks.** The user could not recall the full list beyond social profile, freelancer profile, agency info, my/agency projects, my/agency case studies. | Revisit once the first real templates are written — the gaps show up fast in practice | Defer |
| Q21 | **What do the shipped example templates look like?** D24 + D28: the user's template structure, generic example block text. | Write them at M2 and have the user correct them, rather than asking for real wording up front | Draft, then review |

### Note on the 5-second target

D14 ("just type it") is in tension with the target in 03-user-flows.md of **under 5 seconds** from "post copied" to
"prompt on clipboard". Switching to a terminal and typing `kit prompt-cache` costs a couple of seconds before the app
is even up. This is the user's call and was made knowingly — but if the flow feels slow in practice, Q3 is worth
reopening (a PowerToys hotkey on Windows / desktop shortcut on Linux was the alternative).

## Convention

When a question is answered, move it to "Decided" with the date.
