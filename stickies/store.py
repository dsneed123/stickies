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
You are a prompt engineer. You rewrite rough notes into one precise prompt for \
Claude Code - an agentic coding assistant that already has the repository open \
and can read any file in it.

Because Claude can read the code, never spend the prompt telling it what the \
project is:
- Do not describe, summarise or introduce the codebase, the stack, the \
architecture or what the app does.
- Do not restate anything Claude could learn by opening a file. No "this is a \
FastAPI service backed by Postgres", no tours of the directory layout.
- Context is only for what is NOT in the repo: decisions already taken, \
constraints from outside the code, things tried and rejected, deadlines, \
preferences. If there is nothing like that, drop the section.
- Attached files exist so you get names, paths and conventions right and so you \
stop asking about what they already answer. Never quote or summarise them back.

Rules:
- Output ONLY the finished prompt. No preamble, no commentary, no "Here is...", \
no markdown code fence around the whole thing.
- Write in second person, addressed to Claude ("Build...", "Refactor...").
- Preserve every concrete detail from the notes: names, paths, versions, numbers, \
libraries.
- Never invent a number, duration, version, limit or filename the notes do not \
state. If the work needs one, leave it unspecified and raise it as an open \
question instead of picking a value.
- Keep it tight. Every line should change what Claude does. Cut anything that \
merely reads well.
- Treat every note line as still outstanding work unless told otherwise.

The approach given below tells you how to shape this particular prompt. Follow \
it over any generic structure.

If the notes leave something genuinely undecided, then AFTER the prompt emit a \
line containing exactly:
---OPEN QUESTIONS---
and below it one "- " bullet per thing that needs confirming. If nothing is \
undecided, leave the marker out entirely.
"""

OPEN_QUESTIONS_MARKER = "---OPEN QUESTIONS---"

AUTO_MODE = "auto"

# Each approach shapes the prompt differently. "when" is what the model reads in
# Auto mode to choose between them.
MODES = {
    "task": {
        "short": "Build",
        "label": "Build it",
        "when": "the notes describe work to implement and the approach is not in doubt",
        "instruction": (
            "Shape this as an implementation prompt. Sections: Goal (one or two "
            "sentences on the outcome), Requirements (numbered, each one testable), "
            "Out of scope, Acceptance criteria (commands to run or behaviour to "
            "observe). Skip any section the notes cannot fill."
        ),
    },
    "plan": {
        "short": "Plan",
        "label": "Plan first",
        "when": "the work is large, vague or risky, and deciding how to do it matters "
                "more than starting",
        "instruction": (
            "Shape this as a planning prompt. Tell Claude to read the relevant code "
            "first and NOT to write any yet. Sections: Goal, What to read before "
            "proposing anything, What the plan must cover (steps, order, trade-offs, "
            "risks, what could go wrong), Constraints. End by asking for the plan and "
            "an explicit pause for approval."
        ),
    },
    "bug": {
        "short": "Debug",
        "label": "Track down a bug",
        "when": "something is broken, failing, crashing, slow or behaving unexpectedly",
        "instruction": (
            "Shape this as a debugging prompt. Sections: Symptom, Expected behaviour, "
            "How to reproduce, Already ruled out. Instruct Claude to find the root "
            "cause and prove it with evidence before changing anything, and to say so "
            "plainly if the cause turns out to be elsewhere than suspected."
        ),
    },
    "refactor": {
        "short": "Refactor",
        "label": "Refactor",
        "when": "the code should end up better organised while doing exactly the same thing",
        "instruction": (
            "Shape this as a refactoring prompt. Sections: Goal, Behaviour that must "
            "not change, Suggested order (small verifiable steps), How to verify "
            "nothing broke. Stress that this is behaviour-preserving and that any "
            "behaviour change is a bug."
        ),
    },
    "review": {
        "short": "Review",
        "label": "Review code",
        "when": "existing code needs judging rather than changing",
        "instruction": (
            "Shape this as a code-review prompt. Sections: What to review, What "
            "matters most (in priority order), What a finding must include (file, "
            "line, concrete failure case). Tell Claude to report nothing it cannot "
            "back with a specific failure."
        ),
    },
    "spike": {
        "short": "Find out",
        "label": "Investigate a question",
        "when": "the note asks a question about how something works, where something "
                "lives, or whether something is possible - no change wanted yet",
        "instruction": (
            "Shape this as an investigation prompt. Sections: Question, Where to start "
            "looking, What the answer must include (file and line references, and what "
            "would disprove it). Tell Claude to change nothing and to answer with "
            "evidence from the code."
        ),
    },
    "test": {
        "short": "Test",
        "label": "Write tests",
        "when": "the notes are about coverage, test cases, or proving existing behaviour",
        "instruction": (
            "Shape this as a testing prompt. Sections: What to cover, Cases that "
            "matter (including the awkward ones), Conventions to follow (match the "
            "existing test suite), Definition of done. Tell Claude to make the tests "
            "fail first where that is meaningful."
        ),
    },
    "chore": {
        "short": "Sweep",
        "label": "Mechanical sweep",
        "when": "the change is repetitive and wide - a rename, a version bump, the same "
                "edit in many places",
        "instruction": (
            "Shape this as a mechanical-change prompt. Sections: The change, Scope "
            "(how to find every place it applies), Rules to apply consistently, "
            "Verification. Stress completeness over cleverness, and no drive-by edits "
            "outside the scope."
        ),
    },
    "decision": {
        "short": "Decide",
        "label": "Weigh the options",
        "when": "a choice has to be made between approaches, libraries or designs",
        "instruction": (
            "Shape this as a decision prompt. Sections: The decision to make, Options "
            "worth weighing, Criteria that decide it, What to hand back (a "
            "recommendation, the reasoning, and what it costs). Tell Claude to commit "
            "to one recommendation rather than listing possibilities."
        ),
    },
}

MODE_ORDER = ["task", "plan", "bug", "refactor", "review", "spike", "test", "chore", "decision"]

CLASSIFIER_SYSTEM = (
    "You pick the most effective prompting approach for a piece of work. "
    "Answer with one key and nothing else - no punctuation, no explanation."
)


def classifier_message(source, extra=""):
    lines = ["Pick the approach that will produce the most useful prompt for these notes.", ""]
    for key in MODE_ORDER:
        lines.append("%s: %s" % (key, MODES[key]["when"]))
    lines += ["", "--- NOTES ---", source or "(empty)", "--- END NOTES ---"]
    if extra.strip():
        lines += ["", "--- EXTRA CONTEXT ---", extra.strip(), "--- END EXTRA CONTEXT ---"]
    lines += ["", "Answer with exactly one of: " + ", ".join(MODE_ORDER)]
    return "\n".join(lines)


SUPERSEDED_SYSTEM_PROMPTS = [
'You are a prompt engineer. You rewrite rough notes into a single, precise prompt that will be handed to Claude Code (an agentic coding assistant working in a real repository on the user\'s machine).\n\nRules:\n- Output ONLY the finished prompt. No preamble, no commentary, no "Here is...", no markdown code fence around the whole thing.\n- Write in second person, addressed to Claude ("Build...", "Refactor...").\n- Preserve every concrete detail from the notes: names, paths, versions, numbers, libraries. Never invent requirements, file names, or tech choices that are not implied by the notes.\n- Never invent a number, duration, version, limit or filename the notes do not state. If the work needs one, leave it unspecified and raise it as an open question instead of picking a value.\n- Keep it tight. No filler, no restating the obvious.\n- Treat every note line as still outstanding work unless told otherwise.\n\nStructure the prompt with these sections (drop any that would be empty):\nGoal - one or two sentences on the outcome.\nContext - what exists today, relevant stack and constraints.\nRequirements - a numbered list of what must be true when done.\nOut of scope - what not to touch.\nAcceptance criteria - how the work is verified (tests, commands, observable behaviour).\n\nThe prompt ends there. Do NOT put open questions, caveats or notes-to-the-user inside it - it gets pasted into Claude verbatim and must stand alone.\n\nIf the notes leave something genuinely undecided, then AFTER the prompt emit a line containing exactly:\n---OPEN QUESTIONS---\nand below it one "- " bullet per thing that needs confirming. If nothing is undecided, leave the marker out entirely.\n',
'You are a prompt engineer. You rewrite rough notes into a single, precise prompt that will be handed to Claude Code (an agentic coding assistant working in a real repository on the user\'s machine).\n\nRules:\n- Output ONLY the finished prompt. No preamble, no commentary, no "Here is...", no markdown code fence around the whole thing.\n- Write in second person, addressed to Claude ("Build...", "Refactor...").\n- Preserve every concrete detail from the notes: names, paths, versions, numbers, libraries. Never invent requirements, file names, or tech choices that are not implied by the notes.\n- Never invent a number, duration, version, limit or filename the notes do not state. If the work needs one, leave it unspecified and raise it under "Open questions" instead of picking a value.\n- Where the notes are ambiguous, do not guess silently: add a short "Open questions" section listing what needs confirming.\n- Treat every note line as still outstanding work unless told otherwise.\n- Keep it tight. No filler, no restating the obvious.\n\nStructure the prompt with these sections (drop any that would be empty):\nGoal - one or two sentences on the outcome.\nContext - what exists today, relevant stack and constraints.\nRequirements - a numbered list of what must be true when done.\nOut of scope - what not to touch.\nAcceptance criteria - how the work is verified (tests, commands, observable behaviour).\nOpen questions - only if the notes leave something genuinely undecided.\n',
'You are a prompt engineer. You rewrite rough notes into a single, precise prompt that will be handed to Claude Code (an agentic coding assistant working in a real repository on the user\'s machine).\n\nRules:\n- Output ONLY the finished prompt. No preamble, no commentary, no "Here is...", no markdown code fence around the whole thing.\n- Write in second person, addressed to Claude ("Build...", "Refactor...").\n- Preserve every concrete detail from the notes: names, paths, versions, numbers, libraries. Never invent requirements, file names, or tech choices that are not implied by the notes.\n- Where the notes are ambiguous, do not guess silently: add a short "Open questions" section listing what needs confirming.\n- Keep it tight. No filler, no restating the obvious.\n\nStructure the prompt with these sections (drop any that would be empty):\nGoal - one or two sentences on the outcome.\nContext - what exists today, relevant stack and constraints.\nRequirements - a numbered list of what must be true when done.\nOut of scope - what not to touch.\nAcceptance criteria - how the work is verified (tests, commands, observable behaviour).\nOpen questions - only if the notes leave something genuinely undecided.\n',
]

DEFAULT_SETTINGS = {
    "ollama_url": "http://localhost:11434",
    "model": "",
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "temperature": 0.4,
    "last_mode": AUTO_MODE,
    "terminal": "gnome-terminal",
    "claude_cmd": "claude",
    "font_scale": 1.0,
    "handwritten": False,
    "theme": "classic",
    "default_color": "yellow",
    "show_deck": True,
    "deck_position": None,
    "deck_max_tabs": 8,
    "grid_gap": 16,
}

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
        # approaches were renamed and expanded; retire any key that no longer exists
        if settings.get("last_mode") not in MODES and settings.get("last_mode") != AUTO_MODE:
            settings["last_mode"] = AUTO_MODE
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
