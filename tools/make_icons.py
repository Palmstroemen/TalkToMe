"""Generate the icons in Resources/icons in FreeCAD's style (Tango: gradients, light from the upper
left, dark outline, highlight). One microphone, its states differ in color and overlay.

    python tools/make_icons.py
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "Resources", "icons")

# Tango palette: light, middle, dark
ALUMINIUM = ("#eeeeec", "#babdb6", "#555753")
RED = ("#ef2929", "#cc0000", "#a40000")
ORANGE = ("#fcaf3e", "#f57900", "#ce5c00")
BUTTER = ("#fce94f", "#edd400", "#c4a000")
BLUE = ("#729fcf", "#3465a4", "#204a87")
GREEN = ("#8ae234", "#73d216", "#4e9a06")
OUTLINE = "#2e3436"

ICONS = {
    # file           capsule color  overlay
    "mic_off":      (ALUMINIUM, "slash_red"),
    "mic_wait":     (BUTTER, None),
    "mic_on":       (RED, None),
    "mic_busy":     (BLUE, None),
    "mic_error":    (ALUMINIUM, "badge"),
    "mic_muted":    (ORANGE, "slash_orange"),
    "train":        (BLUE, "check"),
    "TalkToMe":     (RED, None),
    "preferences-talk_to_me": (RED, None),
}


def gradient(name, colors, x2="1", y2="0"):
    light, middle, dark = colors
    return ('<linearGradient id="{n}" x1="0" y1="0" x2="{x2}" y2="{y2}">'
            '<stop offset="0" stop-color="{l}"/><stop offset="0.45" stop-color="{m}"/>'
            '<stop offset="1" stop-color="{d}"/></linearGradient>').format(n=name, l=light, m=middle, d=dark, x2=x2, y2=y2)


def stroke(path, color, width):
    """A line with a dark outline: the outline drawn wider underneath."""
    return ('<path d="{p}" fill="none" stroke="{o}" stroke-width="{w2}" stroke-linecap="round"/>'
            '<path d="{p}" fill="none" stroke="{c}" stroke-width="{w}" stroke-linecap="round"/>').format(
                p=path, o=OUTLINE, c=color, w=width, w2=width + 3)


def overlay(kind):
    if kind and kind.startswith("slash"):
        color = RED[1] if kind == "slash_red" else ORANGE[1]
        return stroke("M10 10 L54 54", color, 5)
    if kind == "badge":
        return ('<circle cx="49" cy="49" r="12" fill="url(#badge)" stroke="{d}" stroke-width="2"/>'
                '<rect x="47" y="40" width="4" height="11" rx="1.5" fill="#fff"/>'
                '<circle cx="49" cy="55" r="2.2" fill="#fff"/>').format(d=RED[2])
    if kind == "check":
        return ('<path d="M36 50 l8 8 l16 -18" fill="none" stroke="{o}" stroke-width="10" '
                'stroke-linecap="round" stroke-linejoin="round"/>'
                '<path d="M36 50 l8 8 l16 -18" fill="none" stroke="url(#check)" stroke-width="6" '
                'stroke-linecap="round" stroke-linejoin="round"/>').format(o=OUTLINE)
    return ""


def icon(colors, kind):
    defs = [gradient("capsule", colors), gradient("metal", ALUMINIUM),
            gradient("base", ALUMINIUM, x2="0", y2="1"),
            gradient("badge", RED, x2="0.6", y2="1"), gradient("check", GREEN, x2="0", y2="1")]
    grill = "".join('<path d="M24 {y} H40" stroke="{o}" stroke-opacity="0.35" stroke-width="1.5"/>'.format(
        y=y, o=OUTLINE) for y in (13, 18, 23, 28))
    body = [
        stroke("M13 27 a19 19 0 0 0 38 0", "url(#metal)", 4),            # holder
        stroke("M32 47 V55", "url(#metal)", 4),                            # stem
        '<rect x="19" y="54" width="26" height="7" rx="3.5" fill="url(#base)" stroke="{}" stroke-width="2"/>'.format(OUTLINE),
        '<rect x="21" y="3" width="22" height="38" rx="11" fill="url(#capsule)" stroke="{}" stroke-width="2"/>'.format(OUTLINE),
        grill,
        '<rect x="24.5" y="7" width="5" height="28" rx="2.5" fill="#fff" fill-opacity="0.45"/>',   # highlight
        overlay(kind),
    ]
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">\n'
            '<defs>{}</defs>\n{}\n</svg>\n').format("".join(defs), "\n".join(b for b in body if b))


def main():
    for name, (colors, kind) in ICONS.items():
        with open(os.path.join(OUT, name + ".svg"), "w", encoding="utf-8") as f:
            f.write(icon(colors, kind))
        print("wrote", name + ".svg")


if __name__ == "__main__":
    main()
