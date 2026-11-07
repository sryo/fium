"""Generates the fium mark: a geometric capital F tilted 45°, its outline swept back
into one solid trail, split from the F by a gap so the mark stays transparent."""
import math, os, sys

U = 44
# F on a grid (x right, y down): stem, top bar, middle bar
BARS = [[(0, 0), (U, 0), (U, 5 * U), (0, 5 * U)],
        [(0, 0), (3.4 * U, 0), (3.4 * U, U), (0, U)],
        [(0, 2.1 * U), (2.6 * U, 2.1 * U), (2.6 * U, 3.1 * U), (0, 3.1 * U)]]
TILT = -45     # degrees, about the F's centre
TRAIL = 300    # how far back each bar is swept
GAP = 18       # clear space between the F and its trail

LIGHT, DARK = "#1d1c1a", "#ecebe6"
PAPER, TERRACOTTA = "#f4ead6", "#c8471d"


def rotate(pts, deg, c=(1.7 * U, 2.5 * U)):
    t = math.radians(deg); co, si = math.cos(t), math.sin(t)
    return [(c[0] + (x - c[0]) * co - (y - c[1]) * si, c[1] + (x - c[0]) * si + (y - c[1]) * co) for x, y in pts]


def hull(pts):
    """Convex hull, counter-clockwise (monotone chain)."""
    pts = sorted(set((round(x, 3), round(y, 3)) for x, y in pts))
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0: lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0: up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def d(polys):
    return "".join("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in p) + "Z" for p in polys)


def shapes():
    f = [rotate(b, TILT) for b in BARS]
    # a convex bar swept along a straight line covers the hull of its start and end
    trail = [hull(b + [(x - TRAIL, y) for x, y in b]) for b in f]
    return f, trail


def mark(paint, pad=4, css=None):
    """paint: a fill colour, or None with css to switch colour by theme."""
    f, trail = shapes()
    xs = [x for p in f + trail for x, _ in p]; ys = [y for p in f + trail for _, y in p]
    x0, y0, w, h = min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad
    box = f'x="{x0-GAP:.0f}" y="{y0-GAP:.0f}" width="{w+2*GAP:.0f}" height="{h+2*GAP:.0f}"'
    fill = 'class="m"' if css else f'fill="{paint}"'
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.1f} {y0:.1f} {w:.1f} {h:.1f}" width="{w:.0f}" height="{h:.0f}">']
    if css:
        out.append(f"<style>{css}</style>")
    # the trail is cut by the F's outline grown by GAP, which leaves the clear space
    out.append(f'<defs><mask id="gap" maskUnits="userSpaceOnUse" {box}><rect {box} fill="#fff"/>'
               f'<path d="{d([hull([q for p in f for q in p])])}" fill="#000" stroke="#000" stroke-width="{2*GAP}"/></mask></defs>')
    out.append(f'<path d="{d(trail)}" {fill} mask="url(#gap)"/>')
    out.append(f'<path d="{d(f)}" {fill}/>')
    out.append("</svg>")
    return "\n".join(out)


def icon(bg, fg, size=512, scale=0.8):
    """The mark centred in a squircle tile."""
    inner = mark(fg, pad=0)
    vb = [float(v) for v in inner.split('viewBox="')[1].split('"')[0].split()]
    body = inner.split(">", 1)[1].rsplit("</svg>", 1)[0]
    s = scale * size / max(vb[2], vb[3])
    cx, cy = vb[0] + vb[2] / 2, vb[1] + vb[3] / 2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
            f'<defs><clipPath id="tile"><rect width="{size}" height="{size}" rx="{size*0.225:.1f}"/></clipPath></defs>'
            f'<g clip-path="url(#tile)"><rect width="{size}" height="{size}" fill="{bg}"/>'
            f'<g transform="translate({size/2} {size/2}) scale({s:.4f}) translate({-cx:.1f} {-cy:.1f})">{body}</g></g></svg>')


if __name__ == "__main__":
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    os.makedirs(outdir, exist_ok=True)
    def save(name, s): open(os.path.join(outdir, name), "w").write(s + "\n")
    save("fium-light.svg", mark(LIGHT))
    save("fium-dark.svg", mark(DARK))
    save("fium.svg", mark(None, css=f".m{{fill:{LIGHT}}}@media (prefers-color-scheme:dark){{.m{{fill:{DARK}}}}}"))
    save("fium-icon.svg", icon(PAPER, TERRACOTTA))
