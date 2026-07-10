"""daily.py - morning shortlist stager.

Deterministic ONLY - no LLM runs here (recall stage = code; judgment = the
session). Stages drafts/queue/<date>/SHORTLIST.md with the top-ranked topics.
YOU pick one in a session; research -> brief -> deck -> gates -> approval
all happen there, unchanged.

  python3 daily.py                 # stage today's shortlist (idempotent)
  python3 daily.py --park "idea"   # park a topic - tomorrow's shortlist leads with it
  python3 daily.py --selftest

Wire it to a scheduler if you want it automatic (cron / launchd / Task Scheduler),
or just run it at the start of your posting session.
"""
import argparse
import time
from pathlib import Path

import topic_engine

QUEUE = Path(__file__).parent / "drafts" / "queue"
SHORTLIST_N = 3


def _ideas(path=None):
    p = path or topic_engine.IDEAS
    return topic_engine._parse(p.read_text()) if p.exists() else []


def park(text, path=None):
    """Append a parked idea block - tomorrow's shortlist puts parked first."""
    p = path or topic_engine.IDEAS
    block = (f"\n## {text[:60]}\n- angle: {text}\n- utility: \n- surprise: \n"
             f"- capability: \n- status: parked\n")
    p.write_text(p.read_text() + block if p.exists() else block)
    return block


def _fmt(idea, tag=""):
    lines = [f"## {tag}{idea.get('name', '?')}"]
    for k in ("angle", "value", "freshness_label", "trend", "url", "note"):
        if idea.get(k) not in (None, ""):
            lines.append(f"- {k}: {idea[k]}")
    return "\n".join(lines)


def stage(day=None, offline=False, ideas=None, out_root=None):
    """Write drafts/queue/<day>/SHORTLIST.md (skip if it exists). Returns path."""
    day = day or time.strftime("%Y-%m-%d")
    out = (out_root or QUEUE) / day / "SHORTLIST.md"
    if out.exists():
        print(f"already staged: {out}")
        return out
    pool = ideas if ideas is not None else _ideas()
    live = [i for i in pool if i.get("status", "new") not in ("posted", "dropped")]
    parked_ideas = [i for i in live if i.get("status") == "parked"]
    rest = [i for i in live if i.get("status") != "parked"]
    try:
        scored = sorted((topic_engine.score(i, offline) for i in rest),
                        key=lambda i: i["value"], reverse=True)
    except Exception as e:      # network down -> offline scoring, never skip a day
        print(f"scoring fell back offline ({e})")
        scored = sorted((topic_engine.score(i, True) for i in rest),
                        key=lambda i: i["value"], reverse=True)
    picks = (parked_ideas + scored)[:SHORTLIST_N]
    body = [f"# Shortlist {day} - pick one, then run the session loop",
            "(research -> brief -> research_check -> deck -> check.py -> approve)"]
    body += [_fmt(i, "PARKED: " if i.get("status") == "parked" else "")
             for i in picks]
    body.append("No fit? `python3 scout.py floor` for fresh candidates, or bring "
                "your own topic/image to the session.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n\n".join(body) + "\n")
    print(f"staged {len(picks)} candidates -> {out}")
    return out


def _selftest():
    import tempfile
    root = Path(tempfile.mkdtemp())
    ideas = [
        {"name": "old", "status": "posted", "angle": "x"},
        {"name": "fresh tool", "status": "new", "angle": "a",
         "utility": 3, "surprise": 3, "capability": 1},
        {"name": "tomorrow topic", "status": "parked", "angle": "b"},
    ]
    p = stage(day="2099-01-01", offline=True, ideas=ideas, out_root=root)
    text = p.read_text()
    assert "old" not in text, "posted ideas must be excluded"
    assert text.index("PARKED: tomorrow topic") < text.index("fresh tool"), \
        "parked must lead the shortlist"
    # idempotent: second call returns the same file untouched
    before = p.stat().st_mtime_ns
    assert stage(day="2099-01-01", offline=True, ideas=ideas, out_root=root) == p
    assert p.stat().st_mtime_ns == before, "re-run must not rewrite"
    # park appends a status: parked block
    f = root / "ideas.md"
    f.write_text("# x\n")
    park("test idea", path=f)
    assert "status: parked" in f.read_text()
    print("daily selftest ok - parked-first, exclusions, idempotency, park")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--park", metavar="IDEA")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
    elif a.park:
        park(a.park)
        print(f"parked for tomorrow: {a.park}")
    else:
        stage(offline=a.offline)


if __name__ == "__main__":
    main()
