# Stickies

**Post-it notes for your Linux desktop that turn into Claude prompts.**

Stick a note on your screen, keep a running checklist for a project, tick things
off as they land — then hit ✨ and a panel drops out of the bottom of the note.
Your local Ollama model reads what's *still unticked* and rewrites it into a
structured prompt for Claude Code, which you can copy or open straight into a
terminal. If it needs something you didn't say, it asks — in a dropdown, not in
the prompt.

Nothing leaves your machine. Notes are a JSON file in `~/.local/share/stickies/`,
and the rewriting runs on your own Ollama server.

![Three sticky notes on a desktop, one with the prompt panel open](docs/screenshot.png)

---

## Why

A note app that only stores text makes you do the translation work twice: once
when you jot the idea down, again when you turn it into something an agent can
act on. Stickies keeps the note as the source of truth. The checklist *is* the
scope — tick an item and it drops out of the next prompt, add one and it's in.
The prompt is generated, not maintained.

## Install

```bash
git clone https://github.com/dsneed123/stickies.git
cd stickies
./install.sh
stickies
```

`install.sh` puts a `stickies` launcher on your PATH and an entry in the app
grid, and offers to start it at login. Nothing is copied — the launcher points
back at the clone, so `git pull` updates it.

Requirements: `python3-gi` and `gir1.2-gtk-3.0` (preinstalled on Ubuntu GNOME),
plus [Ollama](https://ollama.com) running locally with at least one model pulled.
No third-party Python packages — GTK 3 via PyGObject, `urllib` for Ollama.

```bash
stickies          # start, or raise the notes if it's already running
stickies --new    # start and add a fresh note
stickies -f       # run in the foreground, logging to the terminal
```

It detaches by default, so your shell comes straight back. A second `stickies`
raises the existing instance instead of starting a duplicate.

## The notes

Each note is its own borderless, always-on-top window.

| | |
|---|---|
| **Move** | drag the ⠿ bar across the top, drag the title, or middle-click-drag anywhere |
| **Resize** | drag the ⌄ corner at the bottom right |
| **Roll up** | double-click the title bar |
| **Menu** | ≡, or right-click anywhere on the note |
| ☑ | switch between plain text and checklist |
| **B** | formatting (text mode only) |
| 🎨 | note colour — seven real Post-it shades |
| 📌 | keep on top |
| ✕ | hides the note; it stays in **All notes** until you delete it |

**Checklists:** Enter starts the next item · Backspace on an empty item deletes it
· Alt+↑/↓ reorders · Ctrl+Enter ticks. Items wrap, so long ones stay readable.

**Formatting** (plain-text notes): Ctrl+B bold · Ctrl+I italic · Ctrl+U underline
· Ctrl+Shift+X strikethrough · Ctrl+Shift+8 bullet list · Ctrl+Shift+7 numbered
list · Ctrl+Shift+Space clears it. Typing Enter at the end of `- thing` or
`3. thing` starts the next item and keeps the numbering going; Enter on an empty
one ends the list. Formatting is stored as offset spans next to the plain text,
so the file stays greppable and converts cleanly to markdown when it reaches the
model.

**Shortcuts:** `Ctrl+N` new · `Ctrl+Enter` prompt panel · `Ctrl+T` text/checklist
· `Ctrl+D` duplicate · `Ctrl+L` all notes · `Ctrl+W` hide · `Ctrl+,` settings ·
`Ctrl+Q` quit.

## The ✨ prompt panel

Hit **✨ Prompt** and the note grows downward into a panel — no second window.
The button shows how many items are in scope, e.g. `✨ Prompt (3)`.

**A ticked box means done, so it stays out of the prompt.** That's the whole
idea: keep one note per project, add to it as things come up, tick them off as
they ship, and every generation covers only what's still outstanding. The
*ticked too* toggle overrides it when you want the full list.

**Extra thoughts** is one dropdown, closed until you want it. Inside is a free-text
box for whatever the note leaves out — the repo, the stack, constraints like "no
new dependencies". It's saved with the note, so it's still there next time.

It's also where the model talks back. **Open questions never go inside the
prompt** — a prompt you paste into Claude has to stand on its own, not carry a
list of things nobody answered. Instead, anything the model needs decided shows
up as `▸ Extra thoughts · 2 questions`. Open it, read what it asked, type the
answers into the same box, hit Generate again. That's the whole loop.

Pick what kind of prompt you want:

| Mode | Produces |
|---|---|
| **Task** | an implementation prompt for Claude Code |
| **Plan** | asks Claude to explore and plan before writing any code |
| **Bug** | observed vs expected, repro steps, what's already ruled out |
| **Refactor** | behaviour-preserving, incremental, verifiable |
| **Review** | what to review, and what a finding has to include |

The result streams in live and is editable in place. **Copy** and **→ Claude**
send the prompt alone — never the questions. **Save** keeps it as its own note,
and **→ Claude** opens a terminal running `claude` with the prompt already
passed in.

Models that emit `<think>` blocks are handled — the reasoning is stripped out of
the prompt rather than pasted into it.

## Settings

`Ctrl+,` or the ≡ menu: Ollama server and model, temperature, default note
colour, text size, a handwritten-font toggle, and which terminal **→ Claude**
should use.

The **prompt-writer instructions** box is the system prompt your local model
follows. The default forbids inventing details — anything the notes leave
undecided has to come back as a question rather than a guess, which is what stops
a 7B model quietly deciding your refresh tokens last 30 days. It also tells the
model to emit those questions *after* a `---OPEN QUESTIONS---` marker, which is
how they get kept out of the prompt. Edit it freely; *Restore default
instructions* brings it back. If you never touched it, upgrades replace it
automatically; if you did, yours is left alone.

## Where things live

```
~/.local/share/stickies/notes.json          notes + settings
~/.local/share/stickies/notes.backup.json   previous save
~/.local/share/stickies/stickies.log        launcher output
```

Saves are debounced and atomic, so a crash mid-keystroke can't shred the file.

## Layout

```
stickies/
  app.py              application controller, owns every window
  note_window.py      one note = one window: drag, resize, checklist, rich text
  prompt_panel.py     the ✨ drop-down: builds the request, streams the result
  ollama.py           streaming /api/chat client, stdlib only
  store.py            JSON persistence, default system prompt, prompt modes
  theme.py            the Post-it palette and stylesheet
  board.py            "All notes"
  settings_window.py  settings
  util.py             small GTK helpers
```

## Notes on the look

Real Post-it colours (Canary, Limeade, Blue Sky, Power Pink, Iris, Marrakesh,
White), square corners, a paper gradient, an adhesive strip across the top, a
drop shadow and a curl at the bottom edge. The stylesheet overrides the system
GTK theme per-colour, so the ink stays dark on the paper whether your desktop
is light or dark.

## Licence

MIT
