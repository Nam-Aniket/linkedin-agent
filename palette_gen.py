#!/usr/bin/env python3
"""Palette GENERATOR: hundreds of on-rule palettes from color theory, not hand-picked.

The point (vs hand-authoring 100s): a palette is math. Sweep the hue wheel x {light,dark}
x {mono, complementary accent}, build each as muted low-saturation GROUND + high-contrast
INK + muted secondary + one saturated (but not neon) ACCENT, then GATE each on WCAG contrast
so only legible ones survive. Finer hue steps => as many palettes as you want. Zero new deps.

  python3 palette_gen.py            # writes drafts/palettes_generated.png (a wall of them)
  python3 palette_gen.py --selftest # asserts the contrast gate actually rejects bad ones
"""
import colorsys, argparse
from pathlib import Path

import config as _profile

DRAFTS = Path(__file__).parent / "drafts"

# saturation bands - YOUR taste knobs, set by the onboarding interview
# (profile.json design.accent_saturation / design.ground_saturation)
ACC_S = _profile.P["design"]["accent_saturation"]    # accent richness ceiling
GROUND_S = _profile.P["design"]["ground_saturation"]  # ground hue bias (near-neutral)


def _hexf(r, g, b):
    return f"#{round(r*255):02X}{round(g*255):02X}{round(b*255):02X}"


def _hsl(h_deg, s, l):
    r, g, b = colorsys.hls_to_rgb((h_deg % 360) / 360.0, l, s)
    return _hexf(r, g, b)


def _lum(hx):
    def f(c):
        c = int(hx[1 + 2 * c:3 + 2 * c], 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(0) + 0.7152 * f(1) + 0.0722 * f(2)


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def make_palette(hue, dark, comp):
    """One palette from (base hue, dark?, complementary-accent?). None if it fails the gate."""
    acc_h = (hue + (180 if comp else 0)) % 360
    if dark:
        ground = _hsl(hue, GROUND_S + 0.02, 0.09)
        ink    = _hsl(hue, 0.05, 0.93)
        muted  = _hsl(hue, 0.14, 0.42)
        accent = _hsl(acc_h, ACC_S, 0.62)         # brighter accent pops on dark
    else:
        ground = _hsl(hue, GROUND_S, 0.955)
        ink    = _hsl(hue, 0.22, 0.12)
        muted  = _hsl(hue, 0.15, 0.68)
        accent = _hsl(acc_h, ACC_S, 0.44)         # darker accent pops on light
    # the design-quality gate: headline must be very legible, accent must actually pop
    if contrast(ground, ink) < 7.0 or contrast(ground, accent) < 2.6:
        return None
    return {"hue": hue, "dark": dark, "comp": comp,
            "ground": ground, "ink": ink, "muted": muted, "accent": accent}


def generate(hue_step=15):
    out = []
    for dark in (False, True):
        for hue in range(0, 360, hue_step):
            for comp in (False, True):
                p = make_palette(hue, dark, comp)
                if p:
                    out.append(p)
    return out


# --- mood -> palette (used by the cover/deck composers) ----------------------------
# A story is tagged with a MOOD; the mood maps to a base hue + light/dark ground
# via profile.json design.moods (the onboarding interview builds this vocabulary).
# The hue jitters a little per seed so the same mood does not always look identical.
HUE_JITTER = [0, 16, -16, 32, -32, 48, -48]


def _last_ground(rows=None):
    """Ground of the most recently PUBLISHED post: last tracking.csv row (append
    order) with a recorded palette_dark. True=dark, False=light, None=no history."""
    if rows is None:
        import tracker
        rows = tracker._read()
    for r in reversed(rows):
        if str(r.get("palette_dark", "")).strip() in ("0", "1"):
            return str(r["palette_dark"]).strip() == "1"
    return None


_ROTATED = []   # print the rotation notice once per process, not per ladder rung


def palette_for(mood, seed, ground=None, _rows=None):
    """Always returns a valid (contrast-gated) palette on the mood's hue. Luminous
    hues (green, yellow) can't pop on a light ground, so we try the mood's ground
    first, then flip to dark - where they DO pop - keeping the mood's hue either way.
    Unknown moods fall back to 'neutral' (or blue-on-light if even that is missing).

    `ground` = 'dark'|'light' pins the ground (an explicit human call, always wins).
    GROUND ROTATION: without a pin, a mood's preferred DARK ground is honored only
    if the last published post wasn't dark - two dark grounds in a row require an
    explicit pin. Guards against dark drift: when one dark-preferring mood
    dominates your stories, a static mood map alone slowly turns the feed dark."""
    moods = _profile.P["design"]["moods"]
    base, dark = moods.get(mood, moods.get("neutral", [210, False]))
    if ground in ("dark", "light"):
        dark = ground == "dark"
    elif dark and _last_ground(_rows):
        dark = False
        if not _ROTATED:
            _ROTATED.append(1)
            print("  [ground rotation] last published post was dark -> light ground "
                  "first (pin with story ground='dark' to override)")
    off0 = seed % len(HUE_JITTER)
    for d in (bool(dark), not dark):
        for k in range(len(HUE_JITTER)):
            off = HUE_JITTER[(off0 + k) % len(HUE_JITTER)]
            p = make_palette((base + off) % 360, d, False)
            if p:
                return p
    return make_palette(210, False, False)  # blue-on-light: always valid


def _sheet(pals, out, cols=8):
    from matplotlib.patches import Rectangle
    import matplotlib.pyplot as plt
    rows = -(-len(pals) // cols)
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 2, rows * 2.5), facecolor="white")
    axes = axes.flatten()
    for ax in axes:
        ax.axis("off")
    for ax, p in zip(axes, pals):
        ax.set_facecolor(p["ground"])
        ax.axis("on"); ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)
        ax.text(0.10, 0.60, "Aa", color=p["ink"], fontsize=24, fontweight="bold", transform=ax.transAxes)
        ax.text(0.10, 0.40, "the quiet ground", color=p["muted"], fontsize=8, transform=ax.transAxes)
        ax.add_patch(Rectangle((0.10, 0.24), 0.34, 0.05, transform=ax.transAxes, color=p["accent"]))
        ax.text(0.94, 0.07, p["accent"], color=p["muted"], fontsize=6.5, ha="right", transform=ax.transAxes)
    fig.suptitle(f"{len(pals)} palettes, GENERATED from color theory + contrast-gated (not hand-picked)",
                 fontsize=14, color="#222", y=0.997)
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    fig.savefig(out, dpi=95, facecolor="white")
    plt.close(fig)
    return out


# --- brand-color extraction (creative engine, chunk 3) ------------------------------
# A Gemini story should wear Gemini's hue - but OUR discipline. So: find the asset's
# dominant saturated hue with pixel math, then feed it through make_palette, which
# already enforces the muted ground / one accent / WCAG gate. Deterministic, no model.

def dominant_hue(img_path, min_s=0.18):
    """The saturation-weighted dominant hue (0-360) of an image's colorful pixels.
    None if the image is effectively colorless (grayscale logos, b/w photos)."""
    from PIL import Image
    import numpy as np
    im = Image.open(img_path).convert("RGB").resize((64, 64))
    buckets = [0.0] * 36                      # 10-degree hue bins
    colorful = 0
    # numpy, not im.getdata() - getdata is deprecated (removed in Pillow 14)
    for r, g, b in np.asarray(im).reshape(-1, 3):
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if s < min_s or l < 0.08 or l > 0.92:  # skip gray / near-black / near-white
            continue
        colorful += 1
        buckets[int(h * 36) % 36] += s         # saturated pixels vote harder
    if colorful < 40:                          # < ~1% of samples: not a colorful asset
        return None
    best = max(range(36), key=lambda i: buckets[i])
    return best * 10 + 5                       # bin centre


def palette_from_asset(img_path, dark=False):
    """Brand-adaptive palette: asset's dominant hue -> our disciplined constructor.
    Falls through (dark flipped, then complementary) if the gate rejects; None when
    the asset is colorless - caller keeps the mood palette."""
    hue = dominant_hue(img_path)
    if hue is None:
        return None
    for d, comp in ((dark, False), (not dark, False), (dark, True)):
        p = make_palette(hue, d, comp)
        if p:
            return {**p, "source": "asset", "src_hue": hue}
    return None


def _selftest():
    # a yellow accent on a light ground is the classic low-contrast trap; the gate must catch some
    assert make_palette(0, False, False), "a red palette should pass"
    total = len(generate(hue_step=10))
    rejected = sum(1 for dark in (False, True) for hue in range(0, 360, 10)
                   for comp in (False, True) if make_palette(hue, dark, comp) is None)
    assert rejected > 0, "gate rejected nothing - it is not doing its job"
    assert total > 40, f"only {total} palettes generated"
    # brand extraction: fixture images with known colors
    import tempfile
    from PIL import Image
    tmp = Path(tempfile.mkdtemp())
    blue = tmp / "blue.png"    # Gemini-ish brand blue on white (white must be ignored)
    img = Image.new("RGB", (64, 64), "white")
    for x in range(64):
        for y in range(20, 44):
            img.putpixel((x, y), (40, 90, 235))
    img.save(blue)
    h = dominant_hue(blue)
    assert h is not None and 200 <= h <= 250, f"expected blue-ish hue, got {h}"
    p = palette_from_asset(blue)
    assert p and p["source"] == "asset" and contrast(p["ground"], p["ink"]) >= 7.0
    gl, gs = None, None
    import colorsys as _cs
    r, g, b = (int(p["ground"][i:i+2], 16) / 255 for i in (1, 3, 5))
    _, gl, gs = _cs.rgb_to_hls(r, g, b)
    assert gs < 0.2, f"ground must stay muted, got saturation {gs:.2f}"
    assert palette_from_asset(blue) == p, "extraction must be deterministic"
    gray = tmp / "gray.png"
    Image.new("RGB", (64, 64), (128, 128, 128)).save(gray)
    assert dominant_hue(gray) is None and palette_from_asset(gray) is None, \
        "colorless assets yield None - caller keeps the mood palette"
    # mood -> palette: deterministic, gate-passing, unknown moods never crash
    p1, p2 = palette_for("neutral", 0, _rows=[]), palette_for("neutral", 0, _rows=[])
    assert p1 == p2 and contrast(p1["ground"], p1["ink"]) >= 7.0
    assert palette_for("a-mood-nobody-defined", 3, _rows=[]), "unknown mood must fall back"
    # ground rotation: dark-preferring mood goes light after a dark post; a pin wins
    dark_hist, light_hist = [{"palette_dark": "1"}], [{"palette_dark": "0"}]
    assert palette_for("bold", 0, _rows=light_hist)["dark"], "light history keeps mood dark"
    assert not palette_for("bold", 0, _rows=dark_hist)["dark"], "dark history must rotate"
    assert palette_for("bold", 0, ground="dark", _rows=dark_hist)["dark"], "pin beats rotation"
    assert _last_ground([{"palette_dark": "1"}, {"palette_dark": "0"}, {}]) is False
    assert _last_ground([]) is None
    print(f"selftest ok - {total} passed, {rejected} rejected by the contrast gate; "
          f"brand extraction ok; palette_for ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--step", type=int, default=15, help="hue step in degrees; smaller = more palettes")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    DRAFTS.mkdir(exist_ok=True)
    pals = sorted(generate(a.step), key=lambda p: (p["dark"], p["hue"], p["comp"]))
    print("wrote", _sheet(pals, DRAFTS / "palettes_generated.png"), f"({len(pals)} palettes)")


if __name__ == "__main__":
    main()
