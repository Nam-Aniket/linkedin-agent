#!/usr/bin/env python3
"""config.py - YOUR voice, niche, and design taste, in one file.

Everything personal lives in profile.json next to this file: the pipeline code
is machinery, profile.json is the paint. It is created by the onboarding
interview (see ONBOARDING.md) - if it does not exist yet, the defaults below
keep every module importable and every selftest green, but the output will be
deliberately generic. Run the onboarding before publishing anything.

Shape (all keys optional - missing keys fall back to DEFAULTS):

{
  "author": "Jane Doe",                       // footer signature on every slide
  "contact": "jane@example.com",              // polite API User-Agent contact
  "niche": {
    "hn_query": "LLM OR agent OR RAG",        // default Hacker News scout query
    "gh_scout_query": "llm OR agent OR rag",  // default GitHub trending query
    "pain_queries": ["llm costs", "..."],     // HN threads where your audience hurts
    "backlog_floor": 7                        // ready topics to keep on hand
  },
  "own_work": {                               // the build-story mines (all optional)
    "repo_roots": ["~/Documents"],            // scanned 1 level deep for git repos
    "repo_alias": {"dir-name": "Public Name"},
    "failure_log": "~/Documents/failure-log.md",
    "learning_log": "~/Documents/learning-log.md"
  },
  "voice": {
    "banned_extra": ["thrilled to announce"], // adds to check.py's banned list
    "jargon_extra": {"word": "plainer twin"}  // adds to the plain-language map
  },
  "design": {
    "fonts": {
      "display_name": "Your Display Font",    // headline face (any TTF you like)
      "display_file": "elements/fonts/YourFont.ttf",  // relative to repo root
      "sans": "'Helvetica Neue', Arial, 'Segoe UI', sans-serif",
      "serif": "Georgia, 'Times New Roman', serif"
    },
    "accent_saturation": 0.60,                // 0.4 muted .. 0.9 loud
    "ground_saturation": 0.11,                // near-0 neutral .. 0.25 tinted
    "moods": {                                // mood name -> [base hue 0-360, dark ground?]
      "urgency": [0, false],
      "calm":    [210, true]
    }
  },
  "thresholds": {                             // design_score gate bands (see ONBOARDING
    "cover": {"whitespace_max": 0.98, ...},   //  step 5: calibrate on YOUR first renders)
    "media": {...}
  }
}
"""
import json
from pathlib import Path

PROFILE_PATH = Path(__file__).parent / "profile.json"

DEFAULTS = {
    "author": "Your Name",
    "contact": "you@example.com",
    "niche": {
        "hn_query": "LLM OR agent OR RAG",
        "gh_scout_query": "llm OR agent OR rag",
        "pain_queries": ["llm costs", "ai spend", "agents unreliable"],
        "backlog_floor": 7,
    },
    "own_work": {
        "repo_roots": [],          # empty = own-work scouting off until onboarded
        "repo_alias": {},
        "failure_log": "",
        "learning_log": "",
    },
    "voice": {"banned_extra": [], "jargon_extra": {}},
    "design": {
        "fonts": {
            "display_name": "",    # empty = system sans headlines (works, but bland -
            "display_file": "",    #  onboarding step 4 picks a real display face)
            "sans": "'Helvetica Neue', Arial, 'Segoe UI', sans-serif",
            "serif": "Georgia, 'Times New Roman', serif",
        },
        "accent_saturation": 0.60,
        "ground_saturation": 0.11,
        # PLACEHOLDER moods - the onboarding interview replaces these with the
        # mood vocabulary of YOUR content. Unknown moods fall back to "neutral".
        "moods": {
            "neutral": [35, False],
            "urgency": [0, False],
            "growth": [150, False],
            "calm": [210, False],
            "bold": [270, True],
        },
    },
    "thresholds": {},              # empty = design_score's permissive defaults
}


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(base.get(k), dict) and isinstance(v, dict) else v
    return out


def load():
    """The merged profile dict. Missing/invalid profile.json = pure defaults."""
    try:
        return _merge(DEFAULTS, json.loads(PROFILE_PATH.read_text()))
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULTS


P = load()


def onboarded():
    return PROFILE_PATH.exists()


def _selftest():
    assert _merge({"a": 1, "b": {"c": 2}}, {"b": {"c": 3}}) == {"a": 1, "b": {"c": 3}}
    assert _merge(DEFAULTS, {})["author"] == "Your Name"
    deep = _merge(DEFAULTS, {"design": {"accent_saturation": 0.8}})
    assert deep["design"]["accent_saturation"] == 0.8
    assert deep["design"]["moods"]["neutral"] == [35, False], "merge must keep sibling keys"
    print("profile selftest ok" + ("" if onboarded() else " (no profile.json - defaults)"))


if __name__ == "__main__":
    _selftest()
