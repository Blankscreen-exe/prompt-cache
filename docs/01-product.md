# 01 · Product

## The user

- A developer who runs a small agency and also does freelance work.
- Works on **Windows 11** and **Linux**, across two machines.
- Uses ChatGPT and other AI tools daily. Keeps prompts in **Obsidian** today.
- Maintains **kit**, a personal cross-platform terminal toolbox. prompt-cache will be registered with kit so
  `kit prompt-cache` launches it, but it stays a standalone program in its own repo.

## What they actually do

Writing to people across several social channels, plus proposals and email replies. The specific channels are
theirs and will change over time — **the engine must not care which one it is.**

The detail lives in `docs/local/owner-context.md`, which is not published. It is motivation, not specification:
none of it may reach the code.

## The problem

1. **Managing prompts is friction.** In Obsidian every prompt means choosing a folder, creating a file and naming
   it. They want to *write and retrieve prompts in a jiffy* and explicitly **do not want to manage anything**.
2. **Most prompting is repetitive assembly.** The real work is copy-pasting the same pieces into ChatGPT again and
   again, then doing it all over for follow-ups.

## The shape of the work

Any one of their prompts is made of three layers:

| Layer | Example | Changes |
|---|---|---|
| Instructions | "Write a comment on this post. Under 80 words, no hashtags, no emojis." | Never |
| Standing context | Agency info, personal profile, case studies, voice | Rarely |
| The situation | The post, my comment, their reply | Every time |

prompt-cache must make the fixed layers free, and the changing layer **one paste or zero pastes** — zero when the
value comes straight from the clipboard.

There is a second axis: the same prompt is often needed **as the person** or **as the agency**, each with its own
profile, projects and case studies. The grammar handles this with a choice-of-block blank
(`{{persona: @me-profile | @agency-info}}`) rather than duplicating every template.

## What prompt-cache is

A single-process Python terminal app (Textual) that:

1. **Stores prompts without folders or files.** You write; it saves. The first line is the title. Every edit keeps
   the previous version.
2. **Finds anything from one search box**, ranked by match, recency and frequency. Enter copies.
3. **Turns prompts into templates with blanks** — `{{post: clipboard}}`, `{{angle: a | b | c}}` — showing a small
   form and a live preview, then copying the finished prompt.
4. **Includes reusable blocks** such as `{{@agency-info}}`, so standing context is written once and updated in one
   place, and `{{persona: @me | @agency}}` to switch between sets of them.
5. **Remembers threads.** Every fill is saved with its values, so follow-ups reuse the post and your earlier
   comment automatically.

## Principles

1. **Generic engine, personal content.** Nothing about marketing, social platforms or agencies is in the code.
   This is the hard one — it is easy to drift, and every drift makes the tool less reusable and harder to change.
2. **Speed over structure.** Copy → open → Enter should take a few seconds. Every extra click needs a reason.
3. **Zero management.** No folders, file names, save buttons or required tags. Organisation is automatic: recent,
   most used, pinned, plus optional inline `#tags`.
4. **Keyboard first.** Everything reachable by keyboard, with shortcuts visible in a footer. Mouse works too —
   Textual supports it — but it is never required.
5. **Local first and private.** Prompts, standing context and threads stay on the machine. No accounts, telemetry
   or network calls.
6. **Nothing is ever lost.** Autosave, version history, soft delete.
7. **Works on Windows and Linux.** Both code paths written, and it is stated plainly which were tested where.

## Out of scope

- **A web UI.** Considered at length and rejected: it costs a server, a port, a build step, a security model and a
  second language, for no gain here. (D9)
- **A general notes app.** This is not Obsidian or CherryTree. There is no folder tree. (D3)
- **Calling AI APIs.** v1 assembles and copies; you paste into ChatGPT yourself. Nothing in the design may block
  adding drafting later. (D13)
- **Importing from Obsidian.** Dropped — existing prompts get re-typed. (D17)
- **Sync machinery.** Template packs moved by hand cover it. The SQLite file must never live in a cloud-synced
  folder. (D16, D25)
- **Starting at login, global hotkeys, launchers.** You run `kit prompt-cache` in a terminal. (D14, D15)
- Multi-user accounts, sharing, teams. Posting to any platform automatically.
