#!/usr/bin/env python3
"""Design-lint: the LAYOUT half of the quality gate (the color half lives in palette_gen).

After a figure is drawn, every text element has a real pixel bounding box. This reads them
back and flags the arrangement problems that make a design look 'AI-sloppy':
  - text CLIPPED by the frame edge (e.g. a giant '?' bleeding off the top)
  - text COLLISIONS (two text blocks overlapping - 'vs' sitting on 'FINE-TUNE')
  - text TOO SMALL to read on mobile
It does NOT judge taste; it catches the mechanical, auto-rejectable stuff (same split as
check.py for copy). Connector geometry (an arrow tip piercing a number) is still fixed by
design - a known gap noted below.

  python3 design_lint.py --selftest   # asserts it catches a deliberately broken layout
"""
import argparse


def _frac(bb, W, H):
    return (bb.x0 / W, bb.y0 / H, bb.x1 / W, bb.y1 / H)


def _inter(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy


def _area(a):
    return max(0, a[2] - a[0]) * max(0, a[3] - a[1])


def lint(fig, margin=0.02, min_pt=8.0, overlap=0.12):
    """Return a list of arrangement violations. Empty = clean."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    W, H = fig.canvas.get_width_height()
    boxes, out = [], []
    for t in fig.texts:
        s = t.get_text().strip()
        if not s:
            continue
        f = _frac(t.get_window_extent(r), W, H)
        boxes.append((s, f))
        if f[0] < margin or f[1] < margin or f[2] > 1 - margin or f[3] > 1 - margin:
            out.append(f"clipped by frame edge: '{s[:20]}'")
        if t.get_fontsize() < min_pt:
            out.append(f"text too small ({t.get_fontsize():.0f}pt): '{s[:20]}'")
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            (si, fi), (sj, fj) = boxes[i], boxes[j]
            amin = min(_area(fi), _area(fj))
            if amin > 0 and _inter(fi, fj) / amin > overlap:
                out.append(f"text collision: '{si[:14]}' x '{sj[:14]}'")
    return out


def _selftest():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(5.4, 6.75), dpi=200)
    fig.text(0.5, 0.5, "AAAA", fontsize=60, ha="center", va="center")   # two big texts...
    fig.text(0.52, 0.5, "BBBB", fontsize=60, ha="center", va="center")  # ...deliberately overlapping
    fig.text(0.99, 0.99, "edge", fontsize=40, ha="right", va="top")     # jammed into the corner
    v = lint(fig)
    plt.close(fig)
    assert any("collision" in x for x in v), v
    assert any("clipped" in x for x in v), v
    # a clean layout trips nothing
    fig2 = plt.figure(figsize=(5.4, 6.75), dpi=200)
    fig2.text(0.1, 0.8, "Headline here", fontsize=30, va="top")
    fig2.text(0.1, 0.2, "footer", fontsize=9, va="top")
    assert lint(fig2) == [], lint(fig2)
    plt.close(fig2)
    print("design_lint selftest ok - catches collisions + clipping, passes a clean layout")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest:
        _selftest()
