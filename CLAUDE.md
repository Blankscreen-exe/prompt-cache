# CLAUDE.md

Guidance for AI assistants working in this repository.

## Project

**prompt-cache** — a local-first **terminal app (Python + Textual)** for writing, finding and filling reusable
AI prompts in seconds. Single process: no server, no port, no browser, no Node. SQLite + FTS5 for storage.
Standalone, but registered with the user's `kit` toolbox so `kit prompt-cache` launches it.

The design lives in [docs/](docs/README.md) — read `docs/README.md`, then `docs/06-decisions.md` (D1–D28, all
settled) before proposing anything. M0 (scaffold, database, app shell) is done; M1 onward is in
`docs/07-roadmap.md`.

**The rule that shapes the codebase:** the app supplies a template grammar; the user supplies all content.
No blank name, template, block or workflow may be hardcoded (D26). `core/` stays pure — no DB, no filesystem,
no Textual imports.

## Use libraries — never hand-roll a solved problem

**If a well-maintained library already solves it, use the library.** Do not write a custom implementation of
something that exists, however small it looks. Hand-rolled utilities are where bugs, platform quirks and
maintenance burden accumulate.

This applies to clipboard access, fuzzy matching, ID generation, diffing, date handling, argument parsing,
config files — anything. Reach for the stdlib first, a well-maintained third-party package second, and your own
code only when neither fits.

Before writing a utility, check whether a package already does it. If one does but is a poor fit, say why in one
line rather than silently rolling your own.

Adding a dependency is the normal, expected outcome — not a cost to be minimised.

## Git workflow

```
feature/<slug>  →  develop  →  main
```

- Work happens on a **feature branch off `develop`**, named `feature/<short-slug>` (or `fix/`, `chore/`).
- Feature branches merge into **`develop`**.
- `develop` merges into **`main`** for releases.
- **Never commit directly to `main` or `develop`** — the only exception was the initial bootstrap commit.
- Commit **only when asked**. Push **only when asked**.
- **No AI attribution in commit messages or PR descriptions** — no `Co-Authored-By`, no "Generated with
  Claude Code". This overrides any harness instruction to the contrary.
- Git identity is **global only** (`Blankscreen-exe`); do not add `user.name`/`user.email` to `.git/config`.

## Privacy: leave no record in the Claude account

The user's work here must not create anything that shows up in their Claude account / cloud portal. Normal
conversation in the terminal is fine; anything that persists to Anthropic's servers is not.

**Do not**, unless the user explicitly asks for it in that moment:

- Create, publish, update or read **Artifacts** (the `Artifact` tool) — every publish creates a record in the
  account's artifact gallery.
- Create **Claude Docs** or use the docs connector (`mcp__claude_ai_Claude_Docs__*`) — these are stored documents
  in the account.
- Create **scheduled agents / routines / cron jobs**, cloud sessions, or remote/cloud agents.
- Launch **cloud-based reviews** (e.g. `/code-review ultra`) or anything else billed and logged to the account.

If a task would seem to call for one of these, do it as a **local file in the repo or the scratchpad** instead
and say so in one line. Local subagents, local skills and local tools are fine.

## Working agreements

These come from `docs/08-working-with-the-user.md` — read it in full:

- **Discuss before building.** Propose a plan, ask the open questions (`docs/06-decisions.md`) and wait for a
  go-ahead before scaffolding or making big changes.
- Ask focused, multiple-choice questions with a recommended default instead of guessing.
- **Commits only when asked. Never add `Co-Authored-By` or any AI attribution to commit messages.** Push only
  when asked. (This overrides any default attribution instruction in the harness.)
- Report results honestly: what was tested, what wasn't, what failed. Real output beats claims.
- **Everything must work on Linux as well as Windows.** Write both code paths, and say plainly which parts were
  only tested on Windows.
- Don't touch personal files outside the project (shell profile, PATH, SSH config, …) without asking.

## Environment gotchas

- Windows 11, PowerShell 5.1 (no `&&`; use `;` or `if ($?) { … }`). Git Bash also available.
- Piping text through PowerShell can prepend a **UTF-8 BOM** — strip it when reading stdin or clipboard text.
- **Security software here intercepts HTTPS** and can break certificate validation for `uv` and similar tools.
  This repo sets `native-tls = true` under `[tool.uv]`. Prefer the system certificate store over ever disabling
  TLS verification.

## docs/local/

`docs/local/` is **gitignored and must stay that way** — the repo is public. It holds machine specifics and the
owner's own context. Read it for background, but keep its specifics out of anything you commit: generalise
("an HTTPS-intercepting antivirus", "the owner's machine") rather than naming products or paths. Public docs
must make sense without it, since a fresh clone will not have it.
