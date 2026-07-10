#!/usr/bin/env python3
"""HTML/CSS -> PNG (and optional PDF) renderer for the carousel cover layer.

WHY this exists: matplotlib can't do real display fonts, web layout, gradients, or
crisp SVG. Chromium can. We render a full 1080x1350 HTML page in headless Chromium
and screenshot it. That gives us Georgia as a real display serif, letter-spacing,
flexbox grids, the works.

HOW IT'S INVOKED (important — two-python setup):
  The MAIN pipeline python has NO playwright. Playwright lives ONLY in the sibling
  venv `.venv-render/bin/python`. So `render()` writes the HTML to a temp file, writes
  a tiny driver script, and SUBPROCESSES `.venv-render/bin/python driver.py ...`.
  You call `render()` from the normal pipeline python — it shells out for you.

    from render_html import render
    render(html_str, "drafts/cover.png")                 # PNG only
    render(html_str, "drafts/cover.png", "drafts/c.pdf") # + PDF
    render(html_str, "drafts/cover.png", check=True)     # + browser layout lint

  You can also run this module directly with the render venv for a smoke test:
    .venv-render/bin/python render_html.py

The optional `check=True` runs a BROWSER-NATIVE design lint: after the page loads it
reads the bounding boxes (via page.evaluate) of every element tagged
`data-lint="text"` and asserts none clip the 1080x1350 frame and none overlap. This
is the browser twin of design_lint.py — it catches a headline that ran off the frame
or collided with the number, which is exactly the class of bug you can't see from the
python side.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
RENDER_PY = HERE / ".venv-render" / "bin" / "python"
W, H = 1080, 1350

# The driver runs INSIDE the render venv. Kept as a string so render_html.py itself
# has no playwright import (the pipeline python can import this module freely).
_DRIVER = r'''
import json, sys
from playwright.sync_api import sync_playwright

args = json.load(open(sys.argv[1]))
html = open(args["html"], encoding="utf-8").read()
W, H = args["w"], args["h"]

# Browser-native layout lint: bounding boxes of tagged text must sit inside the frame
# and not overlap each other. Runs in the page so it sees REAL rendered geometry.
LINT_JS = """() => {
  const F = {w: %d, h: %d};
  const els = [...document.querySelectorAll('[data-lint="text"]')];
  const boxes = els.map(e => {
    const r = e.getBoundingClientRect();
    return {t: (e.textContent||'').trim().slice(0,24),
            x: r.left, y: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height};
  });
  const bad = [];
  for (const box of boxes) {
    if (box.w < 1 || box.h < 1) continue;               // hidden/empty, skip
    if (box.x < -1 || box.y < -1 || box.r > F.w+1 || box.b > F.h+1)
      bad.push(`clips frame: "${box.t}" (${Math.round(box.x)},${Math.round(box.y)})-(${Math.round(box.r)},${Math.round(box.b)})`);
  }
  const overlap = (a,b) => !(a.r <= b.x || b.r <= a.x || a.b <= b.y || b.b <= a.y);
  const area = z => Math.max(0, z.w) * Math.max(0, z.h);
  for (let i=0;i<boxes.length;i++) for (let j=i+1;j<boxes.length;j++){
    const a=boxes[i], b=boxes[j];
    if (area(a)<1 || area(b)<1) continue;
    if (overlap(a,b)) {
      // tolerate a hair of touching; flag only real intrusion
      const ox = Math.min(a.r,b.r)-Math.max(a.x,b.x), oy = Math.min(a.b,b.b)-Math.max(a.y,b.y);
      if (ox > 4 && oy > 4) bad.push(`overlap: "${a.t}" x "${b.t}"`);
    }
  }
  return bad;
}""" % (W, H)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    # kill the UA stylesheet's default 8px body margin: it shifted every page
    # 8px right/down (white sliver top-left, 8px clipped bottom-right)
    pg.set_content("<style>html,body{margin:0;padding:0}</style>" + html,
                   wait_until="networkidle")
    if args.get("check"):
        viol = pg.evaluate(LINT_JS)
        if viol:
            print("LAYOUT_LINT_FAIL\n" + "\n".join(viol), file=sys.stderr)
            b.close(); sys.exit(3)
    pg.screenshot(path=args["png"], clip={"x":0,"y":0,"width":W,"height":H})
    if args.get("pdf"):
        # PDF must use print media + exact page size; screenshots are screen media
        pg.emulate_media(media="print")
        pg.pdf(path=args["pdf"], width=f"{W}px", height=f"{H}px",
               print_background=True, margin={"top":"0","bottom":"0","left":"0","right":"0"})
    b.close()
print("OK")
'''


def render(html_str, out_png, out_pdf=None, check=False):
    """Rasterize a full-page HTML string to a 1080x1350 PNG (and optional PDF).

    Shells out to the render venv's python. Raises RuntimeError if the render fails
    or (when check=True) the browser layout lint finds a clip/overlap.
    """
    out_png = str(Path(out_png))
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        html_f = td / "page.html"
        html_f.write_text(html_str, encoding="utf-8")
        driver_f = td / "driver.py"
        driver_f.write_text(_DRIVER, encoding="utf-8")
        args = {"html": str(html_f), "png": out_png, "pdf": out_pdf and str(Path(out_pdf)),
                "w": W, "h": H, "check": bool(check)}
        if out_pdf:
            Path(out_pdf).parent.mkdir(parents=True, exist_ok=True)
        args_f = td / "args.json"
        args_f.write_text(json.dumps(args), encoding="utf-8")
        r = subprocess.run([str(RENDER_PY), str(driver_f), str(args_f)],
                           capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"render failed (rc={r.returncode}):\n{r.stderr.strip() or r.stdout.strip()}")
    return out_png


def _smoke():
    """Runnable check: renders a trivial page and asserts the PNG exists + is non-trivial.
    Run with the render venv: `.venv-render/bin/python render_html.py`."""
    out = HERE / "drafts" / "_render_smoke.png"
    html = ("<div style='width:1080px;height:1350px;background:#EDE9E1;"
            "font-family:Georgia'><h1 data-lint='text' "
            "style='margin:120px 90px;font-size:80px'>render ok</h1></div>")
    render(html, out, check=True)
    assert out.exists() and out.stat().st_size > 5000, "smoke PNG missing/too small"
    print("smoke ok ->", out)


if __name__ == "__main__":
    _smoke()
