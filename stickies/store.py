"""Persistence for sticky notes: a single JSON file, debounced atomic writes."""

import json
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone

DATA_DIR = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "stickies"
)
NOTES_FILE = os.path.join(DATA_DIR, "notes.json")
BACKUP_FILE = os.path.join(DATA_DIR, "notes.backup.json")

DEFAULT_SYSTEM_PROMPT = """\
You are a prompt engineer. You rewrite rough notes into a single, precise prompt \
that will be handed to Claude Code (an agentic coding assistant working in a real \
repository on the user's machine).

Rules:
- Output ONLY the finished prompt. No preamble, no commentary, no "Here is...", \
no markdown code fence around the whole thing.
- Write in second person, addressed to Claude ("Build...", "Refactor...").
- Preserve every concrete detail from the notes: names, paths, versions, numbers, \
libraries. Never invent requirements, file names, or tech choices that are not \
implied by the notes.
- Never invent a number, duration, version, limit or filename the notes do not \
state. If the work needs one, leave it unspecified and raise it as an open \
question instead of picking a value.
- Keep it tight. No filler, no restating the obvious.
- Treat every note line as still outstanding work unless told otherwise.

Structure the prompt with these sections (drop any that would be empty):
Goal - one or two sentences on the outcome.
Context - what exists today, relevant stack and constraints.
Requirements - a numbered list of what must be true when done.
Out of scope - what not to touch.
Acceptance criteria - how the work is verified (tests, commands, observable behaviour).

The prompt ends there. Do NOT put open questions, caveats or notes-to-the-user \
inside it - it gets pasted into Claude verbatim and must stand alone.

If the notes leave something genuinely undecided, then AFTER the prompt emit a \
line containing exactly:
---OPEN QUESTIONS---
and below it one "- " bullet per thing that needs confirming. If nothing is \
undecided, leave the marker out entirely.
"""

OPEN_QUESTIONS_MARKER = "---OPEN QUESTIONS---"

MODES = {
    "claude_code": {
        "short": "Task",
        "label": "Claude Code task",
        "instruction": "Turn the notes below into an implementation prompt for Claude Code.",
    },
    "plan": {
        "short": "Plan",
        "label": "Plan / spec",
        "instruction": (
            "Turn the notes below into a prompt asking Claude to produce a detailed "
            "implementation plan first, without writing code yet. Emphasise that Claude "
            "should explore the codebase, state assumptions, and propose a step-by-step "
            "plan with trade-offs before implementing."
        ),
    },
    "bug": {
        "short": "Bug",
        "label": "Bug report",
        "instruction": (
            "Turn the notes below into a debugging prompt for Claude Code. Structure it "
            "around: observed behaviour, expected behaviour, reproduction steps, what has "
            "already been ruled out, and where to start looking. Ask Claude to find the "
            "root cause and prove it before fixing."
        ),
    },
    "refactor": {
        "short": "Refactor",
        "label": "Refactor / cleanup",
        "instruction": (
            "Turn the notes below into a refactoring prompt for Claude Code. Stress that "
            "behaviour must not change, that the work should be incremental and verifiable, "
            "and spell out how to confirm nothing broke."
        ),
    },
    "review": {
        "short": "Review",
        "label": "Review checklist",
        "instruction": (
            "Turn the notes below into a code-review prompt for Claude Code: what to review, "
            "which dimensions matter most, and what a finding must include to be worth reporting."
        ),
    },
}

DEFAULT_SETTINGS = {
    "ollama_url": "http://localhost:11434",
    "model": "",
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "temperature": 0.4,
    "terminal": "gnome-terminal",
    "claude_cmd": "claude",
    "font_scale": 1.0,
    "default_color": "yellow",
}

# Older built-in system prompts. If a user is still carrying one of these
# verbatim they never customised it, so it is safe to upgrade in place.
SUPERSEDED_SYSTEM_PROMPTS = [
'You are a prompt engineer. You rewrite rough notes into a single, precise prompt that will be handed to Claude Code (an agentic coding assistant working in a real repository on the user\'s machine).\n\nRules:\n- Output ONLY the finished prompt. No preamble, no commentary, no "Here is...", no markdown code fence around the whole thing.\n- Write in second person, addressed to Claude ("Build...", "Refactor...").\n- Preserve every concrete detail from the notes: names, paths, versions, numbers, libraries. Never invent requirements, file names, or tech choices that are not implied by the notes.\n- Never invent a number, duration, version, limit or filename the notes do not state. If the work needs one, leave it unspecified and raise it under "Open questions" instead of picking a value.\n- Where the notes are ambiguous, do not guess silently: add a short "Open questions" section listing what needs confirming.\n- Treat every note line as still outstanding work unless told otherwise.\n- Keep it tight. No filler, no restating the obvious.\n\nStructure the prompt with these sections (drop any that would be empty):\nGoal - one or two sentences on the outcome.\nContext - what exists today, relevant stack and constraints.\nRequirements - a numbered list of what must be true when done.\nOut of scope - what not to touch.\nAcceptance criteria - how the work is verified (tests, commands, observable behaviour).\nOpen questions - only if the notes leave something genuinely undecided.\n',
'You are a prompt engineer. You rewrite rough notes into a single, precise prompt that will be handed to Claude Code (an agentic coding assistant working in a real repository on the user\'s machine).\n\nRules:\n- Output ONLY the finished prompt. No preamble, no commentary, no "Here is...", no markdown code fence around the whole thing.\n- Write in second person, addressed to Claude ("Build...", "Refactor...").\n- Preserve every concrete detail from the notes: names, paths, versions, numbers, libraries. Never invent requirements, file names, or tech choices that are not implied by the notes.\n- Where the notes are ambiguous, do not guess silently: add a short "Open questions" section listing what needs confirming.\n- Keep it tight. No filler, no restating the obvious.\n\nStructure the prompt with these sections (drop any that would be empty):\nGoal - one or two sentences on the outcome.\nContext - what exists today, relevant stack and constraints.\nRequirements - a numbered list of what must be true when done.\nOut of scope - what not to touch.\nAcceptance criteria - how the work is verified (tests, commands, observable behaviour).\nOpen questions - only if the notes leave something genuinely undecided.\n',
]

COLORS = ["yellow", "green", "blue", "pink", "purple", "orange", "white"]


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_note(color="yellow", x=None, y=None):
    return {
        "id": uuid.uuid4().hex[:12],
        "title": "",
        "mode": "text",
        "text": "",
        "spans": [],
        "items": [],
        "color": color,
        "x": x,
        "y": y,
        "w": 236,
        "h": 248,
        "pinned": True,
        "sticky": False,
        "visible": True,
        "collapsed": False,
        "prompt_context": "",
        "attachments": [],
        "created": _now(),
        "updated": _now(),
    }


class Store:
    """Holds all notes + settings. Thread-safe enough: one GTK thread mutates,
    a timer thread serialises to disk."""

    def __init__(self, path=NOTES_FILE):
        self.path = path
        self._lock = threading.RLock()
        self._timer = None
        self.data = {"version": 1, "notes": [], "settings": dict(DEFAULT_SETTINGS)}
        self.load()

    # ---------- io ----------

    def load(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception as exc:  # corrupt file: keep it, start clean
            print("stickies: could not read %s (%s); starting fresh" % (self.path, exc))
            try:
                shutil.copy2(self.path, self.path + ".corrupt")
            except Exception:
                pass
            return
        notes = raw.get("notes") or []
        template = new_note()
        for note in notes:
            for key, value in template.items():
                note.setdefault(key, value)
            # notes still sitting at an old default size were never deliberately
            # resized, so bring them down to the new compact default
            if (note.get("w"), note.get("h")) in ((320, 340), (340, 360)):
                note["w"], note["h"] = 236, 248
            note["items"] = [
                {"text": str(i.get("text", "")), "done": bool(i.get("done"))}
                for i in (note.get("items") or [])
                if isinstance(i, dict)
            ]
        settings = dict(DEFAULT_SETTINGS)
        settings.update(raw.get("settings") or {})
        if settings.get("system_prompt") in SUPERSEDED_SYSTEM_PROMPTS:
            settings["system_prompt"] = DEFAULT_SYSTEM_PROMPT
        self.data = {"version": 1, "notes": notes, "settings": settings}

    def save_now(self):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            payload = json.dumps(self.data, indent=2, ensure_ascii=False)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            if os.path.exists(self.path):
                try:
                    shutil.copy2(self.path, BACKUP_FILE)
                except Exception:
                    pass
            os.replace(tmp, self.path)
        except Exception as exc:
            print("stickies: save failed: %s" % exc)

    def save(self, delay=1.0):
        """Debounced save - safe to call on every keystroke."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(delay, self.save_now)
            self._timer.daemon = True
            self._timer.start()

    # ---------- notes ----------

    @property
    def notes(self):
        return self.data["notes"]

    @property
    def settings(self):
        return self.data["settings"]

    def get(self, note_id):
        for note in self.data["notes"]:
            if note["id"] == note_id:
                return note
        return None

    def add(self, note=None, **kwargs):
        note = note or new_note(color=self.settings.get("default_color", "yellow"), **kwargs)
        self.data["notes"].append(note)
        self.save()
        return note

    def duplicate(self, note_id):
        src = self.get(note_id)
        if src is None:
            return None
        copy = json.loads(json.dumps(src))
        copy["id"] = uuid.uuid4().hex[:12]
        copy["title"] = (src.get("title") or "Note") + " (copy)"
        copy["created"] = copy["updated"] = _now()
        if copy.get("x") is not None:
            copy["x"] += 28
            copy["y"] = (copy.get("y") or 0) + 28
        self.data["notes"].append(copy)
        self.save()
        return copy

    def remove(self, note_id):
        self.data["notes"] = [n for n in self.data["notes"] if n["id"] != note_id]
        self.save()

    def touch(self, note):
        note["updated"] = _now()
        self.save()


# rich-text span name -> the markdown that carries it into a prompt
SPAN_MARKERS = {"bold": "**", "italic": "*", "underline": "__", "strike": "~~"}


def text_with_markdown(note):
    """Rebuild the note body with its formatting spans as markdown markers."""
    text = note.get("text", "") or ""
    spans = note.get("spans") or []
    if not spans:
        return text
    opens, closes = {}, {}
    for span in spans:
        try:
            start, end, name = int(span[0]), int(span[1]), span[2]
        except (TypeError, ValueError, IndexError):
            continue
        marker = SPAN_MARKERS.get(name)
        if not marker or end <= start or start < 0 or end > len(text):
            continue
        opens.setdefault(start, []).append(marker)
        closes.setdefault(end, []).append(marker)
    out = []
    for i in range(len(text) + 1):
        out.extend(closes.get(i, ()))
        out.extend(opens.get(i, ()))
        if i < len(text):
            out.append(text[i])
    return "".join(out)


# Attached files are read fresh at generation time, so editing a README on disk
# feeds the next prompt without re-attaching it.
MAX_ATTACHMENT_CHARS = 16000
MAX_ATTACHMENT_TOTAL = 32000
MAX_ATTACHMENT_BYTES = 4 * 1024 * 1024


def read_attachment(path, limit=MAX_ATTACHMENT_CHARS):
    """-> (text, error). Long files are truncated rather than dropped."""
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        return "", "missing (%s)" % (exc.strerror or "no such file")
    if size > MAX_ATTACHMENT_BYTES:
        return "", "too big (%.1f MB)" % (size / 1e6)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read(limit + 1)
    except UnicodeDecodeError:
        return "", "not a text file"
    except OSError as exc:
        return "", "unreadable (%s)" % (exc.strerror or "error")
    if len(text) > limit:
        text = text[:limit].rstrip() + "\n\n[... truncated, the file continues ...]"
    return text, ""


def collect_attachments(note, total_limit=MAX_ATTACHMENT_TOTAL):
    """Read every attached file, honouring a combined budget."""
    out, used = [], 0
    for path in note.get("attachments") or []:
        entry = {"path": path, "name": os.path.basename(path), "text": "", "error": ""}
        text, error = read_attachment(path)
        if error:
            entry["error"] = error
            out.append(entry)
            continue
        room = total_limit - used
        if len(text) > room:
            if room < 500:
                entry["error"] = "left out, context budget full"
                out.append(entry)
                continue
            text = text[:room].rstrip() + "\n\n[... truncated to fit ...]"
        used += len(text)
        entry["text"] = text
        out.append(entry)
    return out


def note_to_markdown(note, include_done=True, marks=True):
    """Plain-text rendering of a note.

    include_done=False drops ticked items - a ticked box means "handled", so it
    stays out of the prompt."""
    lines = []
    title = (note.get("title") or "").strip()
    if title:
        lines.append("# " + title)
        lines.append("")
    if note.get("mode") == "list":
        for item in note.get("items", []):
            text = item.get("text", "").strip()
            if not text:
                continue
            done = bool(item.get("done"))
            if done and not include_done:
                continue
            if marks:
                lines.append("- [%s] %s" % ("x" if done else " ", text))
            else:
                lines.append("- " + text)
    else:
        lines.append(text_with_markdown(note).rstrip())
    return "\n".join(lines).strip()


def item_counts(note):
    """(open, done) counts of non-empty checklist items."""
    items = [i for i in note.get("items", []) if i.get("text", "").strip()]
    done = sum(1 for i in items if i.get("done"))
    return len(items) - done, done
