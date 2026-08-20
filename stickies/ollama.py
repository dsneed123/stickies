"""Minimal streaming Ollama client (stdlib only)."""

import json
import re
import threading
import urllib.error
import urllib.request

TIMEOUT = 20


class OllamaError(Exception):
    pass


def _url(base, path):
    return base.rstrip("/") + path


def list_models(base_url, timeout=TIMEOUT):
    """-> list of model names. Raises OllamaError if the server is unreachable."""
    try:
        with urllib.request.urlopen(_url(base_url, "/api/tags"), timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise OllamaError(
            "Can't reach Ollama at %s (%s).\nIs `ollama serve` running?" % (base_url, exc.reason)
        )
    except Exception as exc:
        raise OllamaError("Bad response from Ollama: %s" % exc)
    return sorted(m.get("name", "") for m in payload.get("models", []) if m.get("name"))


def pick_default(models):
    """Prefer a mid-size instruct model; reasoning models are slow for this job."""
    if not models:
        return ""
    for want in ("qwen2.5:14b", "qwen2.5:7b", "llama3.1:8b", "qwen3-coder:30b"):
        if want in models:
            return want
    plain = [m for m in models if not re.search(r"embed|r1|reason", m, re.I)]
    return (plain or models)[0]


class ThinkSplitter:
    """Routes <think>...</think> spans away from the visible answer."""

    def __init__(self):
        self._buf = ""
        self._in_think = False

    def feed(self, chunk):
        """-> (visible_text, thinking_text)"""
        self._buf += chunk
        visible, thinking = [], []
        while self._buf:
            if self._in_think:
                end = self._buf.find("</think>")
                if end == -1:
                    # hold back a possible partial closing tag
                    keep = min(len(self._buf), 8)
                    thinking.append(self._buf[:-keep] if len(self._buf) > keep else "")
                    self._buf = self._buf[len(self._buf) - keep:] if len(self._buf) > keep else self._buf
                    break
                thinking.append(self._buf[:end])
                self._buf = self._buf[end + len("</think>"):]
                self._in_think = False
            else:
                start = self._buf.find("<think>")
                if start == -1:
                    keep = min(len(self._buf), 7)
                    if len(self._buf) > keep:
                        visible.append(self._buf[:-keep])
                        self._buf = self._buf[-keep:]
                    break
                visible.append(self._buf[:start])
                self._buf = self._buf[start + len("<think>"):]
                self._in_think = True
        return "".join(visible), "".join(thinking)

    def flush(self):
        rest, self._buf = self._buf, ""
        return ("", rest) if self._in_think else (rest, "")


class MarkerSplitter:
    """Splits a stream in two at the first occurrence of a marker line.

    Used to keep the model's open questions out of the prompt itself - the text
    before the marker is what gets copied into Claude."""

    def __init__(self, marker):
        self.marker = marker
        self._buf = ""
        self._past = False

    def feed(self, chunk):
        """-> (before_marker, after_marker)"""
        if self._past:
            return "", chunk
        self._buf += chunk
        index = self._buf.find(self.marker)
        if index != -1:
            before, after = self._buf[:index], self._buf[index + len(self.marker):]
            self._buf = ""
            self._past = True
            return before, after
        # hold back enough to catch a marker straddling two chunks
        keep = len(self.marker) - 1
        if len(self._buf) > keep:
            out, self._buf = self._buf[:-keep], self._buf[-keep:]
            return out, ""
        return "", ""

    def flush(self):
        rest, self._buf = self._buf, ""
        return ("", rest) if self._past else (rest, "")


class StreamJob:
    """One streaming /api/chat call, on its own thread. Callbacks fire on that
    thread - the caller is responsible for hopping back to the GTK loop."""

    def __init__(self, base_url, model, system, user, temperature=0.4):
        self.base_url = base_url
        self.model = model
        self.system = system
        self.user = user
        self.temperature = temperature
        self._cancel = threading.Event()
        self._thread = None

    def cancel(self):
        self._cancel.set()

    @property
    def cancelled(self):
        return self._cancel.is_set()

    def start(self, on_chunk, on_done, on_error):
        self._thread = threading.Thread(
            target=self._run, args=(on_chunk, on_done, on_error), daemon=True
        )
        self._thread.start()
        return self

    def _run(self, on_chunk, on_done, on_error):
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.system},
                    {"role": "user", "content": self.user},
                ],
                "stream": True,
                "options": {"temperature": float(self.temperature)},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            _url(self.base_url, "/api/chat"),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        splitter = ThinkSplitter()
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                for raw in resp:
                    if self._cancel.is_set():
                        return
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw.decode("utf-8"))
                    except ValueError:
                        continue
                    if event.get("error"):
                        on_error(str(event["error"]))
                        return
                    piece = (event.get("message") or {}).get("content", "")
                    if piece:
                        visible, thinking = splitter.feed(piece)
                        if visible or thinking:
                            on_chunk(visible, thinking)
                    if event.get("done"):
                        visible, thinking = splitter.flush()
                        if visible or thinking:
                            on_chunk(visible, thinking)
                        if not self._cancel.is_set():
                            on_done(
                                {
                                    "eval_count": event.get("eval_count"),
                                    "total_duration": event.get("total_duration"),
                                }
                            )
                        return
            visible, thinking = splitter.flush()
            if visible or thinking:
                on_chunk(visible, thinking)
            if not self._cancel.is_set():
                on_done({})
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:400]
            except Exception:
                pass
            if not self._cancel.is_set():
                on_error("Ollama returned HTTP %s. %s" % (exc.code, detail))
        except urllib.error.URLError as exc:
            if not self._cancel.is_set():
                on_error("Can't reach Ollama at %s (%s)." % (self.base_url, exc.reason))
        except Exception as exc:  # noqa: BLE001 - surfaced in the UI
            if not self._cancel.is_set():
                on_error("%s: %s" % (type(exc).__name__, exc))
