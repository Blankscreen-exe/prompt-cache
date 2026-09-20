# prompt-cache: project docs

**Start here.** These documents describe what prompt-cache is and what will be built in this repository.

Nothing has been built yet — the repo contains only these docs. They were rewritten on **2026-09-20** after the
tech stack and scope were decided with the owner. An earlier version of this folder described a React web app with
a separate backend; **that plan is gone.** If you find a reference to React, Node, pnpm, Hono or a localhost API
server anywhere, it is a leftover and it is wrong.

## In one paragraph

prompt-cache is a **local-first terminal app for writing, finding and filling in reusable AI prompts in seconds**.
Its owner writes prompts in Obsidian today and dislikes managing folders and files. More importantly, most of their
prompting is **assembly work**: commenting on a LinkedIn or X or Reddit post means pasting the post, pasting their
agency info, and asking ChatGPT for a comment. When someone replies, they paste everything again. prompt-cache
turns that into: copy the post, run `kit prompt-cache`, pick a template (the post is filled from the clipboard and
the standing context is included automatically), press Enter, and the finished prompt is on the clipboard. It
remembers the thread, so a reply-to-a-reply is one more step, not a rebuild.

## The one rule that shapes everything

**The app supplies a template grammar. The user supplies all content.** No blank name, template, block, platform
or workflow is known to the code. `post` and `my_comment` are examples in these docs, not schema. Anyone should be
able to install prompt-cache and use it for something entirely unrelated to marketing. See D26 in
[06-decisions.md](06-decisions.md).

## Reading order

| File | What's in it |
|---|---|
| [01-product.md](01-product.md) | The problem, the user, the core use case, principles, and what's out of scope |
| [02-concepts.md](02-concepts.md) | The domain model and the **full template grammar** — the heart of the app |
| [03-user-flows.md](03-user-flows.md) | Step-by-step flows, including the comment and reply-to-reply |
| [04-ui.md](04-ui.md) | Textual screens, key bindings and layouts |
| [05-architecture.md](05-architecture.md) | Package layout, SQLite schema, clipboard, kit integration, running it |
| [06-decisions.md](06-decisions.md) | **D1–D28, all decided.** Read this before proposing anything |
| [07-roadmap.md](07-roadmap.md) | Milestones with acceptance criteria |
| [08-working-with-the-user.md](08-working-with-the-user.md) | How the owner likes to work, plus environment gotchas |

Also read [`../CLAUDE.md`](../CLAUDE.md) — it carries a hard privacy rule about not creating records in the
owner's Claude account.

## Status

- Product direction, scope and tech stack: **decided** (06-decisions.md, D1–D28).
- Code: **none yet.** Do not scaffold without a go-ahead.
- Two questions remain open (Q19, Q21) and both are deliberately deferred until real templates exist.
