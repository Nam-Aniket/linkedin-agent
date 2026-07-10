#!/usr/bin/env python3
"""Design-score: measurable composition quality, computed from the RENDERED pixels.

The third leg of the design gate (palette_gen gates colour, design_lint gates layout
geometry). This scores what those can't see: does the cover read like thumbnail CRAFT
or like a sparse template? Metrics are proxies from YouTube-thumbnail research
(one dominant subject, readable at feed size ~160px, balanced composition):

  whitespace  fraction of pixels ~= the ground colour  (sparse-template tell: too high)
  dominance   largest connected ink blob's share of all ink  (one dominant subject)
  balance_y   vertical centre of ink mass, 0=top 1=bottom  (dead bottom third tell)
  glance      luminance stddev at 160px wide  (does it still pop at feed size)

The shipped thresholds are permissive STARTER bands. Calibrate them to YOUR designs
with `--measure` (see the method in THRESHOLDS' comment), then override per band in
profile.json under "thresholds".

  python3 design_score.py --measure drafts/cover_*.png   # print metric distribution
  python3 design_score.py drafts/cover_3_index.png       # score one (exit 1 = fails)
  python3 design_score.py --selftest
"""
import argparse, sys
import numpy as np
import matplotlib.image as mpimg


def _load(png):
    a = mpimg.imread(png)
    if a.dtype != np.float32 and a.dtype != np.float64:
        a = a / 255.0
    return a[:, :, :3]


def _lum(rgb):
    return 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]


def _downscale(a, w):
    """Box-downscale by integer strides (no PIL needed)."""
    h = int(a.shape[0] * w / a.shape[1])
    ys = (np.linspace(0, a.shape[0] - 1, h)).astype(int)
    xs = (np.linspace(0, a.shape[1] - 1, w)).astype(int)
    return a[np.ix_(ys, xs)]


def _ink_mask(rgb):
    """True where a pixel differs from the ground (= the image's modal colour)."""
    small = _downscale(rgb, 108)                      # cheap grid, plenty for masses
    q = (small * 24).astype(int)                      # quantize to find the mode
    flat = q.reshape(-1, 3)
    vals, counts = np.unique(flat, axis=0, return_counts=True)
    ground = vals[counts.argmax()] / 24.0
    return (np.abs(small - ground).sum(axis=2) > 0.18), small


def _components(mask):
    """Sizes of 4-connected components (tiny union-find; no scipy)."""
    h, w = mask.shape
    parent = {}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(h):
        for j in range(w):
            if not mask[i, j]:
                continue
            parent[(i, j)] = (i, j)
            if i and mask[i - 1, j]:
                parent[find((i - 1, j))] = find((i, j))
            if j and mask[i, j - 1]:
                parent[find((i, j - 1))] = find((i, j))
    sizes = {}
    for p in list(parent):
        r = find(p)
        sizes[r] = sizes.get(r, 0) + 1
    return sorted(sizes.values(), reverse=True) or [0]


def metrics(png):
    rgb = _load(png)
    mask, small = _ink_mask(rgb)
    ink = int(mask.sum())
    comps = _components(mask)
    ys, _ = np.nonzero(mask)
    thumb = _lum(_downscale(rgb, 160))
    return {
        "whitespace": round(1 - ink / mask.size, 3),
        "dominance": round(comps[0] / ink, 3) if ink else 0.0,
        "balance_y": round(float(ys.mean()) / mask.shape[0], 3) if ink else 0.5,
        "glance": round(float(thumb.std()), 3),
    }


# STARTER bands - deliberately permissive: they catch only the unarguable failures
# (near-blank, cluttered chaos, confetti with no subject, everything crammed at one
# edge, washes out at feed size). They encode NO taste yet.
#
# CALIBRATE THEM TO YOUR OWN DESIGNS (onboarding step 5 - this is the method, do it
# once you have ~10 renders you actually like):
#   1. render a batch of covers you approve of
#   2. python3 design_score.py --measure drafts/cover_*.png   (prints each metric's range)
#   3. set each band just OUTSIDE your measured envelope, in profile.json:
#        "thresholds": {"cover": {"whitespace_max": ..., ...}, "media": {...}}
# That way the gate catches regressions from YOUR normal, not someone else's taste.
# Later, tracker.py's engagement data is what justifies tightening a band further.
# NOTE: typographic covers and media covers (photo/logo/screenshot panels) measure
# structurally differently - a full-bleed photo legitimately fills the frame, a
# screenshot shatters into many small ink blobs. Calibrate the two profiles separately.
THRESHOLDS = {
    "whitespace_max": 0.985,  # emptier than this = a near-blank template
    "whitespace_min": 0.55,   # fuller than this = cluttered chaos
    "dominance_min": 0.06,    # no blob >=6% of ink = confetti, no dominant subject
    "balance_y_max": 0.70,    # ink mass all in the bottom (media profile allows lower)
    "balance_y_min": 0.15,    # ink mass all at the very top
    "glance_min": 0.06,       # washes out at 160px feed size
}

MEDIA_THRESHOLDS = {
    "whitespace_max": 0.985,
    "whitespace_min": 0.25,   # a full-bleed photo legitimately fills the frame
    "dominance_min": 0.03,    # screenshots/logos shatter into small blobs - floor is lower
    "balance_y_max": 0.82,    # a lower-third media panel is legitimately bottom-heavy
    "balance_y_min": 0.12,
    "glance_min": 0.06,
}

import config as _config
PROFILES = {
    "cover": {**THRESHOLDS, **_config.P["thresholds"].get("cover", {})},
    "media": {**MEDIA_THRESHOLDS, **_config.P["thresholds"].get("media", {})},
}


def score(png, profile="cover"):
    t = PROFILES[profile]
    m = metrics(png)
    fails = []
    if m["whitespace"] > t["whitespace_max"]:
        fails.append(f"nearly blank (whitespace {m['whitespace']})")
    if m["whitespace"] < t["whitespace_min"]:
        fails.append(f"cluttered (whitespace {m['whitespace']})")
    if m["dominance"] < t["dominance_min"]:
        fails.append(f"no dominant subject (dominance {m['dominance']})")
    if not (t["balance_y_min"] <= m["balance_y"] <= t["balance_y_max"]):
        fails.append(f"vertically unbalanced (balance_y {m['balance_y']})")
    if m["glance"] < t["glance_min"]:
        fails.append(f"washes out at feed size (glance {m['glance']})")
    return m, fails


def _selftest():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())

    def _fig(draw):
        f = plt.figure(figsize=(5.4, 6.75), dpi=100)
        f.patch.set_facecolor("#FBF3E8")
        draw(f)
        p = d / f"{draw.__name__}.png"
        f.savefig(p, facecolor="#FBF3E8")
        plt.close(f)
        return p

    def blank(f):
        f.text(0.05, 0.95, "x", fontsize=8, color="#888")
    def healthy(f):
        # mimics the number_hero archetype: one dominant mass + supporting caption
        f.text(0.08, 0.55, "70%", fontsize=110, color="#B01C3C", fontweight="bold", va="center")
        f.text(0.08, 0.30, "of a real bold caption line", fontsize=18, color="#222", fontweight="bold")

    m, fails = score(_fig(blank))
    assert any("blank" in x for x in fails), (m, fails)
    m, fails = score(_fig(healthy))
    assert fails == [], (m, fails)

    def bottom_heavy(f):
        # a lower-third media panel: legit for media covers, unbalanced for type covers
        f.gca().add_patch(__import__("matplotlib.patches", fromlist=["Rectangle"])
                          .Rectangle((0.05, 0.02), 0.9, 0.30, color="#B01C3C"))
        f.gca().axis("off")
        f.text(0.08, 0.94, "top line of a real caption", fontsize=14, color="#222")
    p = _fig(bottom_heavy)
    m, fails = score(p)
    assert any("unbalanced" in x for x in fails), (m, fails)
    m, fails = score(p, profile="media")
    assert not any("unbalanced" in x for x in fails), (m, fails)
    print("design_score selftest ok - blank fails, healthy passes, "
          "media profile admits lower-third layouts the cover profile rejects")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pngs", nargs="*")
    ap.add_argument("--measure", action="store_true", help="print metrics only, no verdict")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    bad = False
    for p in a.pngs:
        m, fails = score(p)
        line = "  ".join(f"{k}={v}" for k, v in m.items())
        if a.measure:
            print(f"{p:44s} {line}")
        else:
            print(f"{p:44s} {line}  {'FAIL: ' + '; '.join(fails) if fails else 'ok'}")
            bad = bad or bool(fails)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
