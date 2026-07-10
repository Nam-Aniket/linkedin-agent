#!/usr/bin/env python3
"""The design learning log - closes the loop from design choices to real engagement.

Every post logs WHAT design it used (format, archetype, palette, element, hook, the
design-score metrics) at publish time; performance numbers get recorded as they come in
(24h, 7d). Once enough rows exist, `report` groups performance by design attribute -
that is what turns "taste" into learned, deterministic thresholds (e.g. if dead-bottom
covers underperform, design_score's balance_y_min gets raised WITH EVIDENCE).

Storage = one CSV (tracking.csv, append/update by post_urn) - open it in any spreadsheet.

  python3 tracker.py log --urn URN --format carousel --archetype number_hero ...
  python3 tracker.py record --urn URN --impressions-24h 280 --reactions-24h 3 ...
  python3 tracker.py report
  python3 tracker.py --selftest
"""
import argparse, csv, sys
from pathlib import Path

CSV = Path(__file__).parent / "tracking.csv"
PICKS = Path(__file__).parent / "picks.csv"

FIELDS = [
    "date", "post_urn", "format", "archetype", "palette_dark", "accent",
    "element_kind", "hook", "mood", "whitespace", "dominance", "balance_y", "glance",
    "copy_hook", "composition",   # composition = compose.py axis signature (design-novelty gate)
    "asset_url",                  # published photo's source_url (photo-novelty gate)
    "impressions_24h", "reactions_24h", "comments_24h",
    "impressions_7d", "reactions_7d", "comments_7d", "notes",
]
METRIC_FIELDS = ["impressions_24h", "reactions_24h", "comments_24h",
                 "impressions_7d", "reactions_7d", "comments_7d"]

# design attributes worth grouping performance by (the learnable knobs)
GROUPS = ("format", "archetype", "palette_dark", "element_kind", "hook")


def _read(path=CSV):
    if not Path(path).exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _write(rows, path=CSV):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def log_post(path=CSV, **kw):
    """Append a post's design row (or update it if the urn is already logged)."""
    rows = _read(path)
    urn = kw.get("post_urn", "")
    for r in rows:
        if urn and r["post_urn"] == urn:
            r.update({k: str(v) for k, v in kw.items() if v is not None})
            _write(rows, path)
            return "updated"
    rows.append({k: str(kw.get(k, "")) for k in FIELDS})
    _write(rows, path)
    return "logged"


def record(urn, path=CSV, **metrics):
    """Fill in performance numbers for an already-logged post."""
    rows = _read(path)
    for r in rows:
        if r["post_urn"] == urn:
            r.update({k: str(v) for k, v in metrics.items() if v is not None})
            _write(rows, path)
            return True
    return False


# --- the taste log (creative engine, chunk 5) ---------------------------------------
# Every 3-variant pick logs the WINNER and the LOSERS with their composition axes.
# That is taste as data: after TASTE_MIN_PICKS picks, taste_weights() turns win-rates
# into sampling weights and compose.py starts proposing more of what YOU pick.
# Lives in picks.csv, NOT tracking.csv - losers never publish, so rows keyed by
# post_urn would show up as posts with numbers forever "due".

PICK_AXES = ("placement", "scale", "treatment", "background")
PICK_FIELDS = ["date", "subject"] + list(PICK_AXES) + ["picked"]
TASTE_MIN_PICKS = 20   # below this, win-rates are noise - sample uniformly


def log_pick(subject, specs, winner, date=None, path=PICKS):
    """One pick event = one row per SHOWN variant, picked=1 on the winner."""
    import datetime as dt
    date = date or dt.date.today().isoformat()
    new = not Path(path).exists()
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PICK_FIELDS)
        if new:
            w.writeheader()
        for i, s in enumerate(specs):
            w.writerow({"date": date, "subject": subject,
                        **{k: s.get(k, "") for k in PICK_AXES},
                        "picked": int(i == winner)})


def taste_weights(path=PICKS):
    """Per-axis sampling weights from pick history: {axis: {value: weight}}.
    Weight = Laplace-smoothed win-rate (wins+1)/(shown+2), so an unseen value
    keeps the 0.5 prior and exploration never dies. None until TASTE_MIN_PICKS
    pick events exist - do not learn taste from noise."""
    rows = _read(path)
    if sum(1 for r in rows if r.get("picked") == "1") < TASTE_MIN_PICKS:
        return None
    out = {}
    for ax in PICK_AXES:
        shown, wins = {}, {}
        for r in rows:
            v = r.get(ax)
            if not v:
                continue
            shown[v] = shown.get(v, 0) + 1
            wins[v] = wins.get(v, 0) + (r.get("picked") == "1")
        out[ax] = {v: (wins[v] + 1) / (shown[v] + 2) for v in shown}
    return out


def _trigrams(text):
    words = [w for w in "".join(c if c.isalnum() or c.isspace() else " "
                                for c in text.lower()).split() if w]
    return set(zip(words, words[1:], words[2:])) or {tuple(words)} if words else set()


def novelty(text, path=CSV):
    """How similar is this copy to anything already posted? Returns (max_similarity,
    closest_hook). Jaccard overlap on word trigrams against every logged copy_hook -
    the non-repetition gate: >0.5 means you are re-posting yourself."""
    new = _trigrams(text)
    if not new:
        return 0.0, ""
    best, who = 0.0, ""
    for r in _read(path):
        old = _trigrams(r.get("copy_hook", "") + " " + r.get("notes", ""))
        if not old:
            continue
        j = len(new & old) / len(new | old)
        if j > best:
            best, who = j, r.get("copy_hook", "")[:50]
    return round(best, 3), who


def _rate(r, window):
    """Engagement rate = (reactions+comments)/impressions for a window, or None."""
    try:
        imp = float(r[f"impressions_{window}"])
        eng = float(r[f"reactions_{window}"] or 0) + float(r[f"comments_{window}"] or 0)
        return eng / imp if imp else None
    except (ValueError, KeyError):
        return None


def due(path=CSV, today=None):
    """The loop's trigger: which posts have performance numbers DUE but missing.
    24h numbers are due the day after posting; 7d numbers a week after. (Counts
    must be typed by hand - the API token can post but not read engagement, 403
    verified 2026-07-08.) Returns [(row, window), ...]."""
    import datetime as dt
    today = today or dt.date.today()
    out = []
    for r in _read(path):
        try:
            age = (today - dt.date.fromisoformat(r["date"])).days
        except ValueError:
            continue
        if age >= 1 and not r.get("impressions_24h"):
            out.append((r, "24h"))
        if age >= 7 and not r.get("impressions_7d"):
            out.append((r, "7d"))
    return out


def report(path=CSV):
    rows = _read(path)
    if not rows:
        print("tracking.csv is empty - log posts first")
        return
    scored = [(r, _rate(r, "24h")) for r in rows]
    with_data = [(r, x) for r, x in scored if x is not None]
    print(f"{len(rows)} posts logged, {len(with_data)} with 24h data\n")
    for g in GROUPS:
        buckets = {}
        for r, x in with_data:
            key = r.get(g) or "?"
            buckets.setdefault(key, []).append((x, float(r["impressions_24h"] or 0)))
        if len(buckets) < 2:
            continue
        print(f"by {g}:")
        for key, vals in sorted(buckets.items(), key=lambda kv: -sum(v[0] for v in kv[1]) / len(kv[1])):
            n = len(vals)
            er = sum(v[0] for v in vals) / n
            imp = sum(v[1] for v in vals) / n
            print(f"  {key:16s} n={n}  avg 24h eng-rate {er:.1%}  avg impressions {imp:.0f}")
        print()
    if len(with_data) < 10:
        print(f"NOTE: only {len(with_data)} datapoints - differences are noise until ~10+ per bucket.")


def _selftest():
    import tempfile
    p = Path(tempfile.mkdtemp()) / "t.csv"
    assert log_post(p, date="2026-07-07", post_urn="urn:1", format="image",
                    archetype="number_hero", hook="stat") == "logged"
    assert log_post(p, post_urn="urn:1", mood="cost") == "updated"      # same urn updates
    assert record("urn:1", p, impressions_24h=280, reactions_24h=3, comments_24h=1)
    assert not record("urn:nope", p, impressions_24h=1)                 # unknown urn = False
    rows = _read(p)
    assert len(rows) == 1 and rows[0]["mood"] == "cost" and rows[0]["impressions_24h"] == "280"
    assert abs(_rate(rows[0], "24h") - 4 / 280) < 1e-9
    # novelty: a re-post of logged copy scores high; fresh copy scores low
    log_post(p, post_urn="urn:2", copy_hook="AI agents miss most multi-step tasks on the first try")
    sim, _ = novelty("AI agents miss most multi-step tasks on the first try, here is why", p)
    assert sim > 0.4, sim
    sim2, _ = novelty("a completely different story about database indexing speed", p)
    assert sim2 < 0.2, sim2
    # due: 24h numbers due the day after; 7d a week after; filled rows never due
    import datetime as dt
    today = dt.date(2026, 7, 8)
    log_post(p, date="2026-07-07", post_urn="urn:due1")               # 1 day old, no numbers
    log_post(p, date="2026-07-01", post_urn="urn:due2")               # 7 days old, no numbers
    log_post(p, date="2026-07-08", post_urn="urn:fresh")              # same-day: nothing due
    d = due(p, today)
    windows = {(r["post_urn"], w) for r, w in d}
    assert ("urn:due1", "24h") in windows and ("urn:due2", "7d") in windows, windows
    assert ("urn:fresh", "24h") not in windows
    record("urn:due1", p, impressions_24h=100, reactions_24h=1, comments_24h=0)
    assert ("urn:due1", "24h") not in {(r["post_urn"], w) for r, w in due(p, today)}
    # taste log: winner + losers each get a row; weights stay None until 20 picks,
    # then favour the consistently-picked value
    pk = p.parent / "picks.csv"
    a = {"placement": "left", "scale": "dominant", "treatment": "none", "background": "flat"}
    b = {"placement": "right", "scale": "chip", "treatment": "duotone", "background": "motif"}
    log_pick("s0", [a, b], 0, date="2026-07-08", path=pk)
    rows = _read(pk)
    assert len(rows) == 2 and rows[0]["picked"] == "1" and rows[1]["picked"] == "0"
    assert rows[0]["placement"] == "left" and rows[1]["background"] == "motif"
    assert taste_weights(pk) is None, "no taste from 1 pick"
    for i in range(19):
        log_pick(f"s{i+1}", [a, b], 0, date="2026-07-08", path=pk)
    tw = taste_weights(pk)
    assert tw is not None, "20 picks unlock taste"
    assert tw["placement"]["left"] > tw["placement"]["right"], tw["placement"]
    assert tw["treatment"].get("halftone") is None      # unseen values absent -> prior applies
    assert 0 < tw["placement"]["right"] < 0.5 < tw["placement"]["left"] < 1
    print("tracker selftest ok (incl. novelty gate + due + taste log)")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    lg = sub.add_parser("log")
    for f in FIELDS:
        lg.add_argument(f"--{f.replace('_', '-')}")
    rc = sub.add_parser("record")
    rc.add_argument("--urn", required=True)
    for f in METRIC_FIELDS:
        rc.add_argument(f"--{f.replace('_', '-')}", type=float)
    sub.add_parser("report")
    sub.add_parser("due")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
    elif a.cmd == "log":
        print(log_post(**{f: getattr(a, f) for f in FIELDS if getattr(a, f, None) is not None}))
    elif a.cmd == "record":
        m = {f: getattr(a, f) for f in METRIC_FIELDS if getattr(a, f, None) is not None}
        print("recorded" if record(a.urn, **m) else f"no logged post with urn {a.urn}")
    elif a.cmd == "due":
        items = due()
        if not items:
            print("nothing due - all logged posts have their numbers.")
        for r, w in items:
            print(f"[{w} due] {r['date']}  {r['post_urn']}")
            print(f"    {(r.get('copy_hook') or '')[:70]}")
            print(f"    python3 tracker.py record --urn {r['post_urn']} "
                  f"--impressions-{w} N --reactions-{w} N --comments-{w} N")
    else:
        report()


if __name__ == "__main__":
    main()
