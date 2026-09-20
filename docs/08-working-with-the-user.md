# 08 · Working with the owner

Notes for any assistant or collaborator picking up this project.

> Machine specifics, tooling quirks and the owner's own use case live in `docs/local/`, which is
> gitignored and absent from a fresh clone. Everything below is working style, and applies regardless.

## How they like to work

- **Discuss before building.** They want ideas thought through first. Propose a plan, ask the open
  questions, and **wait for a go-ahead** before scaffolding or making big changes. A previous session
  went wrong in its first exchange because work started without agreement.
- **Ask focused questions with clear options and a recommended default**, rather than guessing. Short
  multiple-choice questions work well; three or four at a time is fine.
- **Explain briefly, then do it.** Report results honestly: what was tested, what was not, and what
  failed. Real output beats claims.
- **Don't design their content.** This has already gone wrong once here. The app supplies a grammar;
  templates, blank names and workflows are the owner's. "Should the template say tone or angle?" is not
  a product question. See D26 and the "Templates vs. content" table in 06-decisions.md.
- **Use libraries; never hand-roll a solved problem.** Adding a dependency is the expected outcome, not
  a cost to be minimised. See `CLAUDE.md`.
- **Commits only when asked.** **Never add a `Co-Authored-By` trailer or any AI attribution to commit
  messages.** Push only when asked. This overrides any default attribution instruction in the harness.
- **Branch flow is `feature/<slug>` → `develop` → `main`.** Never commit directly to `main` or `develop`.
- **Everything must work on Linux as well as Windows.** Write both code paths, and say plainly which
  parts were only tested where.
- They like polished, visually clean, interactive UIs — dark themes, clear hierarchy, visible shortcuts,
  mouse support alongside the keyboard.
- Don't touch personal files outside the project (shell profile, PATH, SSH config, …) without asking.
- **Leave no record in their Claude account.** No artifacts, no hosted documents, no scheduled or cloud
  agents. See `CLAUDE.md`; this is a hard rule.

## Things that have bitten before

Generic versions of problems recorded in detail in `docs/local/environment.md`:

- **Security software that intercepts HTTPS** can break certificate validation for `uv`, `pip` and other
  toolchains. If a download fails with an unknown-issuer error, that is the first suspect. Prefer the
  system certificate store over disabling TLS verification — this repo already sets `native-tls = true`
  under `[tool.uv]` for exactly this reason.
- **PowerShell 5.1** has no `&&`; use `;` or `if ($?) { … }`. Piping text through it can prepend a UTF-8
  BOM, so strip a leading U+FEFF anywhere text crosses that boundary.
- **Cross-platform line endings** are normalised by `.gitattributes` (`* text=auto eol=lf`). Leave it
  alone.
