# 03 · User flows

Key bindings are proposals; the screens in 04-ui.md carry the same set. The rule is that the primary path needs
**no more than a couple of keys**, and every action is also reachable by mouse.

The examples below use marketing templates because that is what the owner does. **They are examples.** Nothing in
the flows depends on the template names, blank names or subject matter.

---

## F1 · Open the app

Run `kit prompt-cache` (or `prompt-cache`) in whatever terminal is open. It starts straight into the **search
box**, focused, cold start well under a second.

`Esc` steps back one level; from the top level it clears the search box. `Ctrl+Q` quits.

There is no daemon, no background server, no tray icon and no global hotkey (D14, D15). If the launch ever feels
too slow in practice, Q3 in 06-decisions.md is worth reopening.

---

## F2 · Write a new prompt (zero management)

1. Type in the search box. Nothing matches.
2. Press `Enter`, or select the row **"Create prompt: *<typed text>*"**. The editor opens with the typed text as
   the first line.
3. Write. **Autosave** runs continuously; the first line becomes the title; `#tags` are picked up.
4. `Esc` returns to search. No save button, no file name, no folder.

Also: `Ctrl+N` for a new prompt from anywhere, and **new from clipboard** — creates a prompt whose body is
whatever is on the clipboard, useful for capturing a prompt you just wrote elsewhere.

---

## F3 · Find and copy a plain prompt

1. Type a few characters. Matching is fuzzy; the best match is selected.
2. `Enter` copies it and shows a brief "Copied" confirmation. `use_count` and `last_used_at` update.

Two or three keystrokes, total.

---

## F4 · Fill a template — the core flow

Set up once:

- A block `agency-info`, holding standing context.
- A block `social-voice`, holding how you write.
- A template, for example `linkedin-comment`:

  ```
  Write a LinkedIn comment on the post below. Under 80 words.
  No hashtags, no emojis, no "Great post!". Lead with the point.

  {{@social-voice}}
  {{persona: @me-profile | @agency-info}}
  {{proof: @my-cases | @agency-cases | none}}

  ANGLE: {{angle: add a counterpoint | share a relevant experience | ask a sharp question}}

  POST:
  {{post: clipboard}}
  ```

Each use:

1. Copy the post.
2. Run the app. Type `lin com` — the template is on top. Press `Enter`.
3. The **fill form** opens. POST is already filled from the clipboard. PERSONA, PROOF and ANGLE show their
   defaults. The live preview shows the whole assembled prompt.
4. Adjust anything you want — usually persona and angle, both single keypresses in a dropdown.
5. Press `Ctrl+Enter` (or `Enter` when focus is not in a multi-line field).
6. The assembled prompt is **on the clipboard**. A conversation is created, labelled from the post's first words.
7. Paste into ChatGPT, get the comment, post it.
8. Optional but worth it: copy the comment as you actually posted it, and press `Ctrl+S` on the conversation to
   store it as `my_comment`. This is what makes F5 free.

---

## F5 · Continue a thread (reply to a reply)

A second template, `linkedin-reply`, reusing the same blank names:

```
Someone replied to my comment. Write a short, conversational reply.

{{@social-voice}}
{{persona: @me-profile | @agency-info}}

ORIGINAL POST:
{{post}}

MY COMMENT:
{{my_comment: optional}}

THEIR REPLY:
{{their_reply: clipboard}}
```

1. Copy the new reply.
2. Find the conversation: type words from the original post, or open **Recent**.
3. Choose **Continue with…** and pick `linkedin-reply`.
4. `post` and `my_comment` come from the conversation, `their_reply` from the clipboard. Nothing to paste.
5. `Ctrl+Enter` copies the assembled prompt and adds the fill to the same conversation.
6. Repeat as the thread continues.

If `my_comment` was never saved it is simply empty — and because it is marked `optional`, its line disappears
rather than leaving an empty label.

**The naming is the mechanism.** `post` in one template pre-fills `post` in another because the names match. This
is a convention the user controls, not a feature the app enforces.

---

## F6 · Edit a block that everything uses

1. Search `agency`, select `agency-info`, press `Ctrl+E`.
2. Edit. Every template that includes it uses the new text from the next fill onward.
3. Past conversations keep the text that was actually sent — fills store assembled output.
4. The editor side panel shows **"used by N templates"** so you know the blast radius.

---

## F7 · History and restore

1. Open a prompt, then History.
2. Pick a version to see it diffed against the current text.
3. Restore. That creates a new version; nothing is destroyed.

---

## F8 · Pin, recent, most used

- An empty search box shows **Pinned**, then **Recent** (prompts and conversations), then **Most used**.
- `Ctrl+P` on a result toggles pin.

---

## F9 · Delete and undo

- `Delete` on a result soft-deletes it, with an undo toast.
- A **Trash** view lists soft-deleted items and restores them.

---

## F10 · Template packs

- **Export:** Settings → Export pack. Pick prompts (or all), choose a folder. You get Markdown files plus
  `pack.json`. Conversations are never included.
- **Import:** Settings → Import pack. Preview what is in it, see name collisions, merge.
- This is how templates move between the PC and the laptop, and how a pack is shared with someone else.
- **Full backup** is a separate JSON dump of everything, including conversations and versions.

---

## F11 · First run

On a fresh install the database is empty. The app offers to import the **example pack** that ships with it —
template structures with generic placeholder text in the blocks. Accepting gives a working shape to edit;
declining leaves it empty. Either way nothing personal is ever in the repo.
