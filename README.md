# Stickies

**Post-it notes for your Linux desktop that turn into Claude prompts.**

Stick a note on your screen, keep a running checklist for a project, tick things
off as they land — then hit ✨ and a panel drops out of the bottom of the note.
Your local Ollama model reads what's *still unticked* and rewrites it into a
structured prompt for Claude Code, which you can copy or open straight into a
terminal. Attach your project's README and it writes against your actual stack;
if it still needs something you didn't say, it asks — in a dropdown, not in the
prompt.

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
| **Move** | drag the washi tape across the top, drag the title, or middle-click-drag anywhere |
| **Resize** | drag the ⌄ corner at the bottom right |
| **Roll up** | double-click the title bar |
| **Menu** | ≡, or right-click anywhere on the note |
| 📋 | switch between plain text and checklist |
| **B** | formatting (text mode only) |
| 📎 | attach a file as context — click again to see or detach what's on |
| 🎨 | note colour — seven shades in whichever theme you're using |
| ✕ | hides the note; it stays in the deck until you delete it |
| **Drop a file on it** | attaches that file as context for the note's prompts |

*Keep on top* lives in the ≡ menu rather than the footer — a pin icon next to a
paperclip reads as "pin a file", which is not what it does.

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

## The deck

A slim pill pinned to the top of your screen holds every note as a coloured tab,
with the count of open items on it. It stands in for a tray icon, which GNOME on
this setup has no indicator support for.

- **Click a tab** to bring that note down, click again to put it away
- **Drag a tab downwards** to pull the note out and drop it where you want it
- **Drag a note back up onto the deck** and hold it there for a moment — the deck
  lights up and the note goes back in
- **＋** for a new note, **≡** for the menu (themes, all notes, settings, quit)
- Right-click a tab for that note's own menu

Put-away notes keep everything — they're just off the desktop. Drag the deck by
its ⠿ handle to move it; it remembers where you left it. Hide it entirely from
its menu or in Settings.

## Themes

Six of them, switchable live from the deck's ≡ menu or Settings. Every note
repaints instantly and keeps its colour slot, so a yellow note stays the yellow
one in whichever theme.

| | |
|---|---|
| **Classic Post-it** | the real Post-it range — canary, limeade, blue sky |
| **Pastel** | milky and low-saturation |
| **Bubblegum** | candy pinks and purples |
| **Mint** | cool greens and teals |
| **Highlighter** | loud brights |
| **Night** | dark paper, light ink, for dark desktops |

Night isn't just inverted colours — the input fields, checkboxes and chips flip
with it, so nothing ends up as light text on a light field.

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

**Attach files** for the context a note can't hold. Drop a README, spec or config
onto a note — or use `📎 attach file` inside the dropdown — and it rides along
with every prompt from that note. Attachments are **re-read from disk on each
run**, so editing your README updates the next prompt without re-attaching it. A
`📎3` badge on the note shows what's attached; click a chip to detach it.

This is what turns a vague note into a specific prompt. Attach a project's README
and the model stops guessing at your stack, names your real files, and quits
asking about things the README already answers. Files are sent as *background* —
explicitly not the task — so the checklist stays the scope.

Text files only, capped at 16k characters each and 32k combined; anything longer
is truncated rather than dropped, and a missing or binary file shows as `⚠` with
the reason instead of failing the run.

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
  deck.py             the pinned top-of-screen strip
  settings_window.py  settings
  util.py             small GTK helpers
```

## Notes on the look

Every note is a rounded sheet of paper with a colour gradient, a soft sheen off
the top-left corner, a strip of washi tape holding it up, a layered drop shadow
and a curl at the bottom edge. Checkboxes are round bubbles, buttons are pills,
and the actions are emoji rather than grey glyphs.

The stylesheet overrides the system GTK theme per-colour on every text-bearing
node. Without that, a dark desktop theme paints light text onto light paper —
which is exactly what happened the first time this ran.

## Licence

MIT
