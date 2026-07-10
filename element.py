#!/usr/bin/env python3
"""The per-post DIFFERENTIATING ELEMENT — a small graphic tied to THIS topic.

The generative design engine gives every cover a fitting archetype + palette, but two
posts on different topics can still land on the same archetype and feel generic. This
layer adds ONE small topic-specific graphic (the way the "ponytail" post carried the
ponytail logo) so the cover reads as bespoke, about THIS subject.

Three flavours, picked by a short ladder — most specific wins:
  logo   the post names a known tool/brand (OpenAI, GitHub, ...) -> its mark
  icon   a topic keyword maps to a fitting concept icon (cost -> coin, speed -> bolt)
  motif  nothing obvious -> a clean generated geometric motif, seeded by the subject

Contract (the renderer depends on this EXACTLY):
    element(topic) -> {"svg": <str>, "kind": "icon"|"logo"|"motif"}
    topic = {"hook":.., "mood":.., "subject": <short str>, "keywords": [..]}

Every returned SVG is self-contained, scalable (has a viewBox), sized for a ~180-260px
slot, and colours ONLY with currentColor / var(--accent|ink|muted) — so it inherits the
cover's palette. No hardcoded colours, no bounding boxes/borders — the graphic FLOATS.

  python3 element.py            # self-test: asserts contract + no hex + sensible picks
"""
import hashlib
import re
from pathlib import Path

ELEMENTS = Path(__file__).parent / "elements"
ICONS = ELEMENTS / "icons"
LOGOS = ELEMENTS / "logos"

# --- 1. LOGOS: aliases people actually type -> the vendored simple-icons file (no .svg) ---
LOGO_ALIASES = {
    "openai": "openai", "chatgpt": "openai", "gpt": "openai", "gpt-4": "openai", "o1": "openai",
    "anthropic": "anthropic", "claude": "anthropic",
    "github": "github", "copilot": "github", "git": "github",
    "python": "python",
    "langchain": "langchain",
    "huggingface": "huggingface", "hugging face": "huggingface", "hf": "huggingface",
    "notion": "notion",
    "nvidia": "nvidia", "cuda": "nvidia", "gpu": "nvidia",
    "gemini": "googlegemini", "google gemini": "googlegemini", "bard": "googlegemini",
    "ollama": "ollama",
}

# --- 2. ICONS: topic keyword -> vendored Tabler icon (no .svg). First match wins, so
# order the map from most-specific concept to most-generic. Keys are matched as whole
# words against the subject + keyword list. ---
ICON_KEYWORDS = [
    # speed / latency first — a latency topic is about latency even if the copy also
    # says "budget"/"cost" (first-match wins, so the sharper concept goes above money).
    (("speed", "fast", "latency", "throughput", "performance", "faster", "instant"), "bolt"),
    # cost / money
    (("cost", "price", "pricing", "bill", "billing", "spend", "budget", "cheap", "expensive"), "currency-dollar"),
    (("token", "credits", "coin", "cents", "per-call"), "coin"),
    # growth / performance
    (("growth", "up", "increase", "gain", "scale", "adoption", "surge", "rising"), "trending-up"),
    (("drop", "decline", "down", "fall", "churn", "loss"), "trending-down"),
    (("benchmark", "metric", "measure", "gauge", "score", "eval"), "gauge"),
    (("chart", "trend", "graph", "analytics", "stat", "stats", "data-viz"), "chart-line"),
    # ai / model
    (("ai", "model", "llm", "neural", "reasoning", "intelligence", "brain"), "brain"),
    (("agent", "bot", "assistant", "robot", "automation", "autonomous"), "robot"),
    (("chatbot", "chat", "conversation", "prompt", "message"), "message-chatbot"),
    (("gpu", "chip", "compute", "hardware", "cpu", "inference", "silicon"), "cpu"),
    # data / infra
    (("data", "database", "sql", "warehouse", "storage", "dataset", "table"), "database"),
    (("cloud", "serverless", "hosting", "deploy", "saas"), "cloud"),
    (("api", "endpoint", "integration", "webhook", "rest"), "api"),
    (("pipeline", "workflow", "graph", "network", "orchestration", "rag"), "network"),
    (("stack", "layers", "architecture", "system"), "stack-2"),
    (("plugin", "connect", "integration", "adapter", "connector"), "plug"),
    # trust / security / reliability
    (("security", "secure", "safe", "trust", "reliable", "protect", "guardrail"), "shield-check"),
    (("privacy", "auth", "password", "secret", "credential", "lock", "encrypt"), "lock"),
    (("key", "apikey", "access", "permission"), "key"),
    (("risk", "warning", "danger", "alert", "fail", "failure", "error", "broken"), "alert-triangle"),
    (("bug", "debug", "issue", "defect", "fix"), "bug"),
    (("time", "latency", "delay", "wait", "clock", "hours", "minutes", "deadline"), "clock"),
    # dev / build
    (("launch", "ship", "release", "startup", "rocket", "growth-hack"), "rocket"),
    (("code", "terminal", "cli", "shell", "script", "command"), "terminal-2"),
    (("branch", "version", "commit", "merge", "repo", "vcs"), "git-branch"),
    (("puzzle", "solve", "solution", "piece", "problem"), "puzzle"),
    (("doc", "docs", "document", "guide", "report", "text", "glossary", "definition"), "file-text"),
    (("search", "find", "retrieval", "query", "lookup", "discover"), "search"),
    (("watch", "monitor", "observe", "visibility", "insight", "see"), "eye"),
    (("email", "outreach", "newsletter", "inbox", "mail"), "mail"),
]

# --- 3. MOTIF: mood -> which of the four families to draw (deterministic fallback). ---
MOTIF_BY_MOOD = {
    "cost": "waveform",   # a signal / burn-down line
    "growth": "arcs",     # expanding concentric arcs
    "trust": "grid",      # a stable dot-grid
    "ai": "orbit",        # nodes on offset rings
    "premium": "arcs",
    "neutral": "grid",
}

_HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def _tokens(topic):
    """Lower-cased word tokens from subject + keywords, plus the raw subject string."""
    words = []
    for kw in topic.get("keywords", []):
        words += re.split(r"[\s/_-]+", str(kw).lower())
    subj = str(topic.get("subject", "")).lower()
    words += re.split(r"[\s/_-]+", subj)
    return [w for w in words if w], subj


def _load(path):
    """Read a vendored SVG and confirm it carries no hardcoded colour."""
    svg = path.read_text().strip()
    assert not _HEX.search(svg), f"{path.name} still has a hardcoded colour"
    return svg


def _find_logo(tokens, subj):
    # match multi-word aliases against the whole subject, single words against tokens
    for alias, fname in LOGO_ALIASES.items():
        if (" " in alias and alias in subj) or alias in tokens:
            f = LOGOS / f"{fname}.svg"
            if f.exists():
                return _load(f)
    return None


def _find_icon(tokens):
    tset = set(tokens)
    for keys, fname in ICON_KEYWORDS:
        if tset & set(keys):
            f = ICONS / f"{fname}.svg"
            if f.exists():
                return _load(f)
    return None


# ---------------------------------------------------------------------------
# MOTIF generator — clean geometric marks from palette vars. All stroke/fill use
# var(--accent|ind|muted); nothing is boxed. Seeded by the subject so a topic is stable.
# ---------------------------------------------------------------------------
def _seed(subject):
    return int(hashlib.md5(str(subject).encode()).hexdigest(), 16)


def _motif(subject, mood):
    fam = MOTIF_BY_MOOD.get(mood, "grid")
    s = _seed(subject)
    if fam == "arcs":
        return _m_arcs(s), "arcs"
    if fam == "waveform":
        return _m_wave(s), "waveform"
    if fam == "orbit":
        return _m_orbit(s), "orbit"
    return _m_grid(s), "grid"


def _svg(body, vb=24):
    return (f'<svg viewBox="0 0 {vb} {vb}" xmlns="http://www.w3.org/2000/svg" '
            f'fill="none">\n  {body}\n</svg>\n')


def _m_arcs(s):
    # concentric quarter-arcs radiating from the bottom-left, the outermost in accent
    cx, cy = 4, 20
    parts = []
    for i, r in enumerate((5, 9, 13, 17)):
        col = "var(--accent)" if i == 3 else "var(--muted)"
        w = 1.8 if i == 3 else 1.1
        parts.append(f'<path d="M {cx+r} {cy} A {r} {r} 0 0 0 {cx} {cy-r}" '
                     f'stroke="{col}" stroke-width="{w}" stroke-linecap="round"/>')
    return _svg("\n  ".join(parts))


def _m_wave(s):
    # a single smooth waveform; amplitude/phase jittered by seed; one accent dot at a peak
    amp = 3.0 + (s % 3)
    ph = (s >> 3) % 6
    pts = []
    import math
    for x in range(0, 25):
        y = 12 - amp * math.sin((x + ph) / 3.2)
        pts.append(f"{x},{round(y,2)}")
    peak_x = 3
    peak_y = 12 - amp
    line = (f'<polyline points="{" ".join(pts)}" stroke="var(--accent)" '
            f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>')
    dot = f'<circle cx="{peak_x}" cy="{round(peak_y,2)}" r="1.6" fill="var(--accent)"/>'
    base = ('<line x1="0" y1="12" x2="24" y2="12" stroke="var(--muted)" '
            'stroke-width="0.6" stroke-dasharray="1 2"/>')
    return _svg("\n  ".join([base, line, dot]))


def _m_grid(s):
    # 5x5 dot grid; one dot promoted to the accent (position from seed) = the "signal"
    n = 5
    step = 4
    off = 3
    hot = s % (n * n)
    dots = []
    for i in range(n):
        for j in range(n):
            k = i * n + j
            cx, cy = off + j * step, off + i * step
            if k == hot:
                dots.append(f'<circle cx="{cx}" cy="{cy}" r="1.5" fill="var(--accent)"/>')
            else:
                dots.append(f'<circle cx="{cx}" cy="{cy}" r="0.9" fill="var(--muted)"/>')
    return _svg("\n  ".join(dots))


def _m_orbit(s):
    # two offset rings with nodes; one node in accent = the active model/agent
    import math
    parts = [
        '<circle cx="12" cy="12" r="9" stroke="var(--muted)" stroke-width="0.9"/>',
        '<circle cx="12" cy="12" r="4.5" stroke="var(--muted)" stroke-width="0.9"/>',
    ]
    hot = s % 5
    for i in range(5):
        a = (s % 360) * math.pi / 180 + i * 2 * math.pi / 5
        r = 9 if i % 2 == 0 else 4.5
        cx, cy = 12 + r * math.cos(a), 12 + r * math.sin(a)
        col = "var(--accent)" if i == hot else "var(--ink)"
        rad = 1.5 if i == hot else 1.0
        parts.append(f'<circle cx="{round(cx,2)}" cy="{round(cy,2)}" r="{rad}" fill="{col}"/>')
    return _svg("\n  ".join(parts))


# ---------------------------------------------------------------------------
def element(topic):
    """Pick the differentiating element for a topic. See module docstring for the contract."""
    tokens, subj = _tokens(topic)

    svg = _find_logo(tokens, subj)
    if svg:
        return {"svg": svg, "kind": "logo"}

    svg = _find_icon(tokens)
    if svg:
        return {"svg": svg, "kind": "icon"}

    svg, _ = _motif(subj or topic.get("mood", "neutral"), topic.get("mood", "neutral"))
    return {"svg": svg, "kind": "motif"}


# --- self-test ---------------------------------------------------------------
def _selftest():
    cases = [
        # (topic, expected kind, expected substring-of-picked-file-or-motif or None)
        ({"mood": "ai", "subject": "ChatGPT plugins", "keywords": ["openai", "plugin"]}, "logo", "22.28"),
        ({"mood": "ai", "subject": "Claude vs GPT", "keywords": ["anthropic", "model"]}, "logo", None),
        ({"mood": "cost", "subject": "token pricing", "keywords": ["cost", "billing"]}, "icon", None),
        ({"mood": "growth", "subject": "adoption is surging", "keywords": ["growth", "scale"]}, "icon", None),
        ({"mood": "trust", "subject": "RAG retrieval quality", "keywords": ["retrieval", "search"]}, "icon", None),
        ({"mood": "premium", "subject": "a quiet essay on craft", "keywords": ["craft", "taste"]}, "motif", None),
        ({"mood": "ai", "subject": "some abstract musing", "keywords": []}, "motif", None),
    ]
    kinds = set()
    for topic, want_kind, want_sub in cases:
        r = element(topic)
        assert set(r.keys()) == {"svg", "kind"}, f"bad keys: {r.keys()}"
        assert r["kind"] in ("icon", "logo", "motif"), r["kind"]
        assert r["kind"] == want_kind, f"{topic['subject']!r}: got {r['kind']} want {want_kind}"
        assert r["svg"].lstrip().startswith("<svg"), "not an svg"
        assert "viewBox" in r["svg"], "no viewBox (not scalable)"
        assert not _HEX.search(r["svg"]), f"{topic['subject']!r}: hardcoded hex in svg"
        # must inherit palette: uses currentColor OR a var(--...)
        assert "currentColor" in r["svg"] or "var(--" in r["svg"], "no palette inheritance"
        # no bounding box: forbid a full-canvas rect
        assert "<rect" not in r["svg"], "element is boxed"
        if want_sub:
            assert want_sub in r["svg"], f"{topic['subject']!r}: expected {want_sub} in picked svg"
        kinds.add(r["kind"])
    assert kinds == {"icon", "logo", "motif"}, f"did not exercise all kinds: {kinds}"
    # motif is deterministic per subject
    a = element({"mood": "ai", "subject": "xyz", "keywords": []})["svg"]
    b = element({"mood": "ai", "subject": "xyz", "keywords": []})["svg"]
    assert a == b, "motif not deterministic for same subject"
    print(f"selftest ok - all 3 kinds exercised, no hex, all inherit palette ({len(cases)} cases)")


if __name__ == "__main__":
    _selftest()
