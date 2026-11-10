#!/usr/bin/env python3
import base64
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import OrderedDict
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "cards"
DATA = Path(os.environ.get("DATA", ROOT / "data" / "github.json"))
README = ROOT / "README.md"
STATIC = os.environ.get("STATIC") == "1"

PROFILE = {
    "name": "Muhammet Yusuf Aksu",
    "login": "mysfks",
    "role": "Software Engineer · Yalova, TR",
    "tagline": "Building enterprise ERP at Tersan Shipyard with .NET, React and SQL Server, with a soft spot for computer vision and AI.",
    "portrait": "assets/portrait.jpg",
    "featured": [],
    "max_repos": 4,
    "tiles": [
        {"icon": "mail", "label": "Email", "value": "myusufaksu0@gmail.com", "href": "mailto:myusufaksu0@gmail.com"},
        {"icon": "work", "label": "LinkedIn", "value": "in/myusufaksu", "href": "https://www.linkedin.com/in/myusufaksu"},
        {"icon": "globe", "label": "Website", "value": "mysfks.com", "href": "https://mysfks.com"},
    ],
}

THEME = {
    "bg": "#0A141C",
    "panel": "#0F1E29",
    "line": "#1B3343",
    "cell": "#14283A",
    "brand": "#57BCDA",
    "brand2": "#A6E6F5",
    "text": "#EAF6FA",
    "muted": "#86A1AE",
    "radius": 18,
}

FONTS = {
    "d": "SpaceGrotesk-700.ttf",
    "b": "SpaceGrotesk-500.ttf",
    "m": "JetBrainsMono-400.ttf",
}

ORDER_GAP = 0.15


class Face:
    def __init__(self, key, file):
        self.key = key
        self.path = ROOT / "fonts" / file
        font = TTFont(self.path)
        self.upm = font["head"].unitsPerEm
        self.cmap = font.getBestCmap()
        self.adv = {g: m[0] for g, m in font["hmtx"].metrics.items()}

    def width(self, s, size, ls=0.0):
        units = sum(self.adv.get(self.cmap.get(ord(c), ".notdef"), self.upm // 2) for c in s)
        return units * size / self.upm + ls * max(len(s) - 1, 0)

    def fit(self, s, size, maxw, ls=0.0, floor=9):
        while size > floor and self.width(s, size, ls) > maxw:
            size -= 0.5
        return size

    def wrap(self, s, size, maxw, lines):
        words, out, cur = s.split(), [], ""
        for w in words:
            nxt = f"{cur} {w}".strip()
            if self.width(nxt, size) <= maxw:
                cur = nxt
            else:
                out.append(cur)
                cur = w
        out.append(cur)
        out = [l for l in out if l]
        if len(out) > lines:
            last = " ".join(out[lines - 1:])
            while self.width(last + "…", size) > maxw and " " in last:
                last = last.rsplit(" ", 1)[0]
            out = out[: lines - 1] + [last.rstrip(",.;:—- ") + "…"]
        return out

    def clip(self, s, size, maxw, ls=0.0):
        if self.width(s, size, ls) <= maxw:
            return s
        while s and self.width(s + "…", size, ls) > maxw:
            s = s[:-1]
        return s + "…"


FACES = {k: Face(k, f) for k, f in FONTS.items()}


def woff_data_uri(face, chars):
    text = "".join(sorted(set(chars) | {" "}))
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "s.woff"
        subprocess.run(
            [sys.executable, "-m", "fontTools.subset", str(face.path),
             f"--text={text}", "--flavor=woff", f"--output-file={out}",
             "--layout-features=kern,liga,calt", "--no-hinting", "--desubroutinize",
             "--name-IDs=", "--drop-tables+=DSIG,STAT"],
            check=True,
        )
        return "data:font/woff;base64," + base64.b64encode(out.read_bytes()).decode()


def esc(s):
    return html.escape(str(s), quote=True)


def mix(a, b, t):
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ca, cb))


BASE_CSS = """
.up{animation:up .8s cubic-bezier(.2,.75,.25,1) backwards}
.fade{animation:fade .7s ease-out backwards}
.pop{animation:pop .6s cubic-bezier(.3,1.5,.5,1) backwards;transform-box:fill-box;transform-origin:center}
.grow{animation:grow .9s cubic-bezier(.2,.8,.2,1) backwards;transform-box:fill-box;transform-origin:50% 100%}
.growx{animation:growx 1s cubic-bezier(.2,.8,.2,1) backwards;transform-box:fill-box;transform-origin:0 50%}
.draw{stroke-dasharray:1;animation:draw 1.2s cubic-bezier(.6,0,.2,1) backwards}
@keyframes up{from{opacity:0;transform:translateY(14px)}}
@keyframes fade{from{opacity:0}}
@keyframes pop{from{opacity:0;transform:scale(.3)}}
@keyframes grow{from{transform:scaleY(0)}}
@keyframes growx{from{transform:scaleX(0)}}
@keyframes draw{from{stroke-dashoffset:1}}
.s{display:none}
@media (prefers-reduced-motion:reduce){*{animation:none!important}.m{display:none}.s{display:inline}}
"""


class Card:
    def __init__(self, name, w, h, t0, title):
        self.name, self.w, self.h, self.t0, self.title = name, w, h, t0, title
        self.defs, self.body = [], []
        self.used = {k: set() for k in FACES}

    def a(self, cls, dt_=0.0):
        if STATIC:
            return ""
        return f' class="{cls}" style="animation-delay:{self.t0 + dt_:.2f}s"'

    def at(self, dt_=0.0):
        return f"{self.t0 + dt_:.2f}s"

    def add(self, s):
        self.body.append(s)

    def loop(self, moving, still):
        if STATIC:
            self.add(still)
        else:
            self.add(f'<g class="m">{moving}</g><g class="s">{still}</g>')

    def text(self, x, y, s, face, size, fill, anchor="start", ls=0.0, anim="", extra=""):
        self.used[face].update(s)
        ls_attr = f' letter-spacing="{ls}"' if ls else ""
        anc = f' text-anchor="{anchor}"' if anchor != "start" else ""
        return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{face}" font-size="{size}" '
                f'fill="{fill}"{anc}{ls_attr}{anim}{extra}>{esc(s)}</text>')

    def frame(self, fill=None):
        r = THEME["radius"]
        return (f'<rect x=".5" y=".5" width="{self.w - 1}" height="{self.h - 1}" rx="{r}" '
                f'fill="{fill or THEME["panel"]}" stroke="{THEME["line"]}"/>')

    def render(self):
        faces = "".join(
            f'@font-face{{font-family:{k};src:url({woff_data_uri(FACES[k], ch)}) format("woff")}}'
            for k, ch in self.used.items() if ch
        )
        css = faces + ("" if STATIC else BASE_CSS)
        css += "text{font-kerning:normal}"
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-labelledby="t">'
            f'<title id="t">{esc(self.title)}</title><style>{css}</style>'
            f'<defs>{"".join(self.defs)}</defs>{"".join(self.body)}</svg>'
        )


ICONS = {
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M3.5 7.5 12 13l8.5-5.5"/>',
    "work": '<rect x="3" y="7" width="18" height="13" rx="2.5"/><path d="M8.5 7V5.5A2 2 0 0 1 10.5 3.5h3a2 2 0 0 1 2 2V7M3 13h18"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="3.8" ry="9"/><path d="M3 12h18"/>',
    "arrow": '<path d="M7 17 17 7M9 7h8v8"/>',
    "repo": '<path d="M5 4.5A2.5 2.5 0 0 1 7.5 2H19v16H7.5A2.5 2.5 0 0 0 5 20.5zM5 20.5A2.5 2.5 0 0 0 7.5 23H19v-5"/>',
    "star": '<path d="M12 2.8l2.8 5.8 6.4.9-4.6 4.5 1.1 6.3L12 17.3l-5.7 3 1.1-6.3-4.6-4.5 6.4-.9z"/>',
    "fork": '<circle cx="6" cy="5" r="2.2"/><circle cx="18" cy="5" r="2.2"/><circle cx="12" cy="19" r="2.2"/><path d="M6 7.2V9a3 3 0 0 0 3 3h6a3 3 0 0 0 3-3V7.2M12 12v4.8"/>',
}


def icon(name, x, y, size, color, width=1.8, fill="none"):
    s = size / 24
    return (f'<g transform="translate({x:.1f} {y:.1f}) scale({s:.4f})" fill="{fill}" stroke="{color}" '
            f'stroke-width="{width / s:.2f}" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</g>')


def fmt_int(n):
    return f"{n:,}"


def fmt_day(d, year=True):
    return d.strftime("%b %-d, %Y") if year else d.strftime("%b %-d")


def fmt_range(a, b):
    if not a:
        return "—"
    if a == b:
        return fmt_day(a, a.year != b.year)
    return f"{fmt_day(a, a.year != b.year)} – {fmt_day(b, a.year != b.year)}"


def load():
    if not DATA.exists():
        sys.exit(f"{DATA} not found. Run: scripts/fetch_data.sh {PROFILE['login']} {DATA.relative_to(ROOT)}")
    raw = json.loads(DATA.read_text())
    user = raw.get("data", raw)["user"]
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = [(dt.date.fromisoformat(d["date"]), d["contributionCount"]) for w in cal["weeks"] for d in w["contributionDays"]]
    return user, sorted(days)


def compute(days):
    counts = OrderedDict(days)
    dates = list(counts)
    today = dates[-1]
    i = len(dates) - 1
    if counts[dates[i]] == 0:
        i -= 1
    cur, cur_end = 0, dates[i] if i >= 0 else None
    while i >= 0 and counts[dates[i]] > 0:
        cur += 1
        i -= 1
    cur_start = dates[i + 1] if cur else None
    best = run = 0
    best_s = best_e = run_s = None
    for d in dates:
        if counts[d]:
            run += 1
            run_s = d if run == 1 else run_s
            if run > best:
                best, best_s, best_e = run, run_s, d
        else:
            run = 0
    busiest = max(dates, key=lambda d: (counts[d], d))
    keys = []
    y, m = today.year, today.month
    for _ in range(12):
        keys.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    keys.reverse()
    months = OrderedDict((k, 0) for k in keys)
    for d, c in days:
        if (d.year, d.month) in months:
            months[(d.year, d.month)] += c
    return {
        "counts": counts, "today": today, "total": sum(counts.values()),
        "active": sum(1 for c in counts.values() if c), "span": len(dates),
        "cur": cur, "cur_range": (cur_start, cur_end if cur else None),
        "best": best, "best_range": (best_s, best_e),
        "busiest": busiest, "busiest_n": counts[busiest], "months": months,
    }


def pick_repos(user):
    pinned = [r for r in (user.get("pinnedItems") or {}).get("nodes", []) if r]
    owned = [r for r in (user.get("repositories") or {}).get("nodes", []) if r]
    pool = {r["name"]: r for r in owned + pinned}
    login = user.get("login", PROFILE["login"]).lower()
    if PROFILE["featured"]:
        chosen = [pool[n] for n in PROFILE["featured"] if n in pool]
    elif pinned:
        chosen = pinned
    else:
        chosen = sorted(
            (r for r in owned if not r.get("isFork") and r["name"].lower() != login),
            key=lambda r: (r.get("stargazerCount", 0), r.get("pushedAt", "")), reverse=True,
        )
    return chosen[: PROFILE["max_repos"]]


def hero(t0):
    W, H = 1000, 300
    c = Card("hero", W, H, t0, f"{PROFILE['name']} — {PROFILE['tagline']}")
    T = THEME
    c.defs.append(
        f'<radialGradient id="orb" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="{T["brand"]}" stop-opacity=".35"/>'
        f'<stop offset="1" stop-color="{T["brand"]}" stop-opacity="0"/></radialGradient>'
        f'<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.1" fill="{T["line"]}"/></pattern>'
        f'<linearGradient id="fadeR" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".55" stop-color="#fff" stop-opacity=".9"/><stop offset="1" stop-color="#fff"/></linearGradient>'
        f'<mask id="dm"><rect width="{W}" height="{H}" fill="url(#fadeR)"/></mask>'
        f'<clipPath id="card"><rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="{T["radius"]}"/></clipPath>'
        f'<linearGradient id="rule" x1="0" x2="1"><stop offset="0" stop-color="{T["brand"]}"/><stop offset="1" stop-color="{T["brand2"]}" stop-opacity="0"/></linearGradient>'
    )
    c.add(c.frame(T["bg"]))
    c.add(f'<g clip-path="url(#card)"><rect width="{W}" height="{H}" fill="url(#dots)" mask="url(#dm)"/>')
    orb_moving = (f'<circle cx="800" cy="120" r="260" fill="url(#orb)">'
                  f'<animate attributeName="cx" values="800;730;860;800" dur="18s" begin="{c.at(0.4)}" repeatCount="indefinite"/>'
                  f'<animate attributeName="cy" values="120;190;90;120" dur="18s" begin="{c.at(0.4)}" repeatCount="indefinite"/></circle>')
    c.loop(orb_moving, '<circle cx="800" cy="120" r="260" fill="url(#orb)"/>')
    c.add("</g>")

    has_portrait = (ROOT / PROFILE["portrait"]).exists() if PROFILE.get("portrait") else False
    left, avail = 56, (W - 56 - 300)
    c.add(c.text(left, 76, PROFILE["role"].upper(), "m", 13, T["brand"], ls=2.4, anim=c.a("up", 0.05)))
    size = FACES["d"].fit(PROFILE["name"], 58, avail, ls=-1)
    c.add(c.text(left, 140, PROFILE["name"], "d", size, T["text"], ls=-1, anim=c.a("up", 0.15)))
    name_w = FACES["d"].width(PROFILE["name"], size, -1)
    cx = left + name_w + 8
    caret_still = f'<rect x="{cx:.1f}" y="{140 - size * 0.72:.1f}" width="5" height="{size * 0.78:.1f}" rx="1.5" fill="{T["brand"]}"/>'
    caret_moving = caret_still.replace("/>", f'><animate attributeName="opacity" values="1;1;0;0" keyTimes="0;.5;.55;1" dur="1.1s" begin="{c.at(0.9)}" repeatCount="indefinite"/></rect>')
    c.add(f'<g{c.a("fade", 0.6)}>')
    c.loop(caret_moving, caret_still)
    c.add("</g>")
    c.add(f'<path d="M{left} 164H{left + min(name_w, avail) * 0.7:.0f}" stroke="url(#rule)" stroke-width="3" stroke-linecap="round" pathLength="1"{c.a("draw", 0.45)}/>')
    lines = FACES["b"].wrap(PROFILE["tagline"], 20, avail, 2)
    for i, ln in enumerate(lines):
        c.add(c.text(left, 204 + i * 28, ln, "b", 20, T["muted"], anim=c.a("up", 0.55 + i * 0.08)))
    c.add(c.text(left, 204 + len(lines) * 28 + 14, f"@{PROFILE['login']}", "m", 13, T["brand"], anim=c.a("fade", 0.8)))

    px, py, pr = 830, 150, 92
    if has_portrait:
        p = ROOT / PROFILE["portrait"]
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        uri = f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"
        c.defs.append(f'<clipPath id="pc"><circle cx="{px}" cy="{py}" r="{pr}"/></clipPath>')
        c.add(f'<g{c.a("pop", 0.35)}><image href="{uri}" x="{px - pr}" y="{py - pr}" width="{pr * 2}" height="{pr * 2}" '
              f'preserveAspectRatio="xMidYMid slice" clip-path="url(#pc)"/></g>')
    else:
        initials = "".join(w[0] for w in PROFILE["name"].split()[:2]).upper()
        c.add(f'<g{c.a("pop", 0.35)}><circle cx="{px}" cy="{py}" r="{pr}" fill="{T["panel"]}" stroke="{T["line"]}"/>'
              + c.text(px, py + 17, initials, "d", 50, T["text"], anchor="middle", ls=-1) + "</g>")
    c.add(f'<circle cx="{px}" cy="{py}" r="{pr + 12}" fill="none" stroke="{T["brand"]}" stroke-width="2" '
          f'stroke-opacity=".8" pathLength="1" transform="rotate(-90 {px} {py})"{c.a("draw", 0.5)}/>')
    c.add(f'<circle cx="{px}" cy="{py}" r="{pr + 26}" fill="none" stroke="{T["line"]}" stroke-dasharray="2 7"{c.a("fade", 0.7)}/>')
    sat = f'<circle cx="{px}" cy="{py - pr - 26}" r="5" fill="{T["brand2"]}"/>'
    sat_moving = (f'<g>{sat}<animateTransform attributeName="transform" type="rotate" from="0 {px} {py}" '
                  f'to="360 {px} {py}" dur="16s" begin="{c.at(1.2)}" repeatCount="indefinite"/></g>')
    c.add(f'<g{c.a("fade", 1.1)}>')
    c.loop(sat_moving, f'<g transform="rotate(40 {px} {py})">{sat}</g>')
    c.add("</g>")
    return c


def tile(t0, i, spec):
    W, H = 330, 112
    T = THEME
    c = Card(f"tile-{i + 1}", W, H, t0, f"{spec['label']}: {spec['value']}")
    c.add(f'<g{c.a("up")}>')
    c.add(c.frame())
    c.add(f'<rect x="22" y="28" width="56" height="56" rx="15" fill="{T["brand"]}" fill-opacity=".12" stroke="{T["brand"]}" stroke-opacity=".35"/>')
    c.add(f'<g{c.a("pop", 0.25)}>{icon(spec["icon"], 36, 42, 28, T["brand"])}</g>')
    c.add(c.text(96, 50, spec["label"].upper(), "m", 11, T["muted"], ls=1.6, anim=c.a("fade", 0.2)))
    vmax = W - 96 - 44
    size = FACES["b"].fit(spec["value"], 19, vmax)
    c.add(c.text(96, 78, FACES["b"].clip(spec["value"], size, vmax), "b", size, T["text"], anim=c.a("fade", 0.3)))
    arrow = icon("arrow", W - 40, 18, 20, T["brand"], 2)
    arrow_moving = (f'<g>{arrow}<animateTransform attributeName="transform" type="translate" values="0 0;3 -3;0 0" '
                    f'keyTimes="0;.5;1" dur="2.4s" begin="{c.at(0.8)}" repeatCount="indefinite"/></g>')
    c.add(f'<g{c.a("fade", 0.45)}>')
    c.loop(arrow_moving, arrow)
    c.add("</g></g>")
    return c


def contributions(t0, st):
    W, H = 1000, 360
    T = THEME
    c = Card("contributions", W, H, t0, f"{st['total']} contributions in the last year, current streak {st['cur']} days")
    c.defs.append(
        f'<linearGradient id="bar" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="{T["brand"]}" stop-opacity=".55"/>'
        f'<stop offset="1" stop-color="{T["brand"]}"/></linearGradient>'
        f'<linearGradient id="barHi" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="{T["brand"]}"/>'
        f'<stop offset="1" stop-color="{T["brand2"]}"/></linearGradient>'
    )
    c.add(f'<g{c.a("up")}>{c.frame()}</g>')
    c.add(c.text(40, 52, "CONTRIBUTIONS · LAST 12 MONTHS", "m", 12, T["brand"], ls=2, anim=c.a("fade", 0.1)))
    c.add(c.text(40, 92, fmt_int(st["total"]), "d", 34, T["text"], ls=-0.5, anim=c.a("up", 0.15)))
    tw = FACES["d"].width(fmt_int(st["total"]), 34, -0.5)
    c.add(c.text(40 + tw + 10, 92, "contributions", "b", 16, T["muted"], anim=c.a("up", 0.2)))

    x0, x1, base, hmax = 40, 620, 312, 170
    vals = list(st["months"].values())
    top = max(vals) or 1
    slot = (x1 - x0) / len(vals)
    bw = slot * 0.6
    for g in (0.5, 1.0):
        y = base - hmax * g
        c.add(f'<path d="M{x0} {y:.1f}H{x1}" stroke="{T["line"]}" stroke-dasharray="3 5"{c.a("fade", 0.2)}/>')
    c.add(f'<path d="M{x0} {base}H{x1}" stroke="{T["line"]}"{c.a("growx", 0.2)}/>')
    hi = vals.index(top) if any(vals) else -1
    for i, ((yy, mm), v) in enumerate(st["months"].items()):
        bx = x0 + slot * i + (slot - bw) / 2
        h = max(hmax * v / top, 3)
        d = 0.3 + i * 0.05
        fill = "url(#barHi)" if i == hi else ("url(#bar)" if v else T["line"])
        c.add(f'<rect x="{bx:.1f}" y="{base - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="5" fill="{fill}"{c.a("grow", d)}/>')
        if v:
            c.add(c.text(bx + bw / 2, base - h - 9, fmt_int(v), "m", 11, T["text"] if i == hi else T["muted"], anchor="middle", anim=c.a("fade", d + 0.5)))
        c.add(c.text(bx + bw / 2, base + 22, dt.date(yy, mm, 1).strftime("%b"), "m", 11, T["muted"], anchor="middle", anim=c.a("fade", d)))

    c.add(f'<path d="M656 40V320" stroke="{T["line"]}"{c.a("fade", 0.3)}/>')
    rows = [
        ("CURRENT STREAK", st["cur"], "days" if st["cur"] != 1 else "day", fmt_range(*st["cur_range"]) if st["cur"] else "start one today"),
        ("LONGEST STREAK", st["best"], "days" if st["best"] != 1 else "day", fmt_range(*st["best_range"])),
        ("ACTIVE DAYS", st["active"], f"/ {st['span']}", f"{100 * st['active'] / max(st['span'], 1):.0f}% of days"),
        ("BUSIEST DAY", st["busiest_n"], "contribs", fmt_day(st["busiest"]) if st["busiest_n"] else "—"),
    ]
    rx, rw = 690, 270
    for i, (label, num, unit, sub) in enumerate(rows):
        y = 64 + i * 70
        d = 0.5 + i * 0.12
        c.add(c.text(rx, y, label, "m", 11, T["muted"], ls=1.6, anim=c.a("fade", d)))
        c.add(c.text(rx, y + 34, fmt_int(num), "d", 30, T["text"], ls=-0.5, anim=c.a("up", d + 0.05)))
        nw = FACES["d"].width(fmt_int(num), 30, -0.5)
        c.add(c.text(rx + nw + 8, y + 34, unit, "b", 14, T["muted"], anim=c.a("up", d + 0.08)))
        c.add(c.text(rx + rw, y + 34, FACES["m"].clip(sub, 11, rw - nw - 80), "m", 11, T["brand"], anchor="end", anim=c.a("fade", d + 0.15)))
        if i == 0 and st["cur"]:
            lx = rx + FACES["m"].width(label, 11, 1.6) + 12
            dot = f'<circle cx="{lx:.1f}" cy="{y - 4}" r="4" fill="{T["brand2"]}"/>'
            ring = (f'<circle cx="{lx:.1f}" cy="{y - 4}" r="4" fill="none" stroke="{T["brand2"]}" stroke-width="1.5">'
                    f'<animate attributeName="r" values="4;12" dur="1.8s" begin="{c.at(1.2)}" repeatCount="indefinite"/>'
                    f'<animate attributeName="stroke-opacity" values=".9;0" dur="1.8s" begin="{c.at(1.2)}" repeatCount="indefinite"/></circle>')
            c.add(f'<g{c.a("pop", d + 0.2)}>{dot}')
            c.loop(ring, "")
            c.add("</g>")
    return c


def repo_card(t0, i, r, now):
    W, H = 490, 170
    T = THEME
    name = r["name"]
    c = Card(f"repo-{i + 1}", W, H, t0, f"{name}: {r.get('description') or ''}")
    c.add(f'<g{c.a("up")}>{c.frame()}')
    c.add(f'<g{c.a("pop", 0.2)}>{icon("repo", 26, 26, 24, T["brand"])}</g>')
    c.add(c.text(62, 46, FACES["d"].clip(name, 21, W - 62 - 26, -0.3), "d", 21, T["text"], ls=-0.3, anim=c.a("fade", 0.15)))
    desc = r.get("description") or "No description yet."
    for j, ln in enumerate(FACES["b"].wrap(desc, 15, W - 52, 2)):
        c.add(c.text(26, 86 + j * 22, ln, "b", 15, T["muted"], anim=c.a("fade", 0.25 + j * 0.06)))
    y = 149
    x = 26
    lang = r.get("primaryLanguage") or {}
    bits = []
    if lang.get("name"):
        bits.append(f'<circle cx="{x + 5}" cy="{y - 4.5}" r="5.5" fill="{lang.get("color") or T["brand"]}"/>')
        bits.append(c.text(x + 17, y, lang["name"], "m", 12, T["text"]))
        x += 17 + FACES["m"].width(lang["name"], 12) + 20
    for ic, n in (("star", r.get("stargazerCount", 0)), ("fork", r.get("forkCount", 0))):
        bits.append(icon(ic, x, y - 13, 16, T["muted"], 1.8))
        bits.append(c.text(x + 21, y, fmt_int(n), "m", 12, T["text"]))
        x += 21 + FACES["m"].width(fmt_int(n), 12) + 18
    c.add(f'<g{c.a("fade", 0.4)}>{"".join(bits)}</g>')
    if r.get("pushedAt"):
        pushed = dt.datetime.fromisoformat(r["pushedAt"].replace("Z", "+00:00"))
        days = (now - pushed).days
        ago = "today" if days < 1 else f"{days}d ago" if days < 30 else f"{days // 30}mo ago" if days < 365 else f"{days // 365}y ago"
        c.add(c.text(W - 26, y, f"updated {ago}", "m", 11, T["muted"], anchor="end", anim=c.a("fade", 0.5)))
    c.add(f'<path d="M26 121H{W - 26}" stroke="{T["line"]}" pathLength="1"{c.a("draw", 0.35)}/>')
    c.add("</g>")
    return c


def graph(t0, st, days):
    W, H = 1000, 238
    T = THEME
    c = Card("graph", W, H, t0, f"Contribution graph: {st['total']} contributions in the last year")
    c.add(f'<g{c.a("up")}>{c.frame()}</g>')
    c.add(c.text(40, 48, "CONTRIBUTION GRAPH", "m", 12, T["brand"], ls=2, anim=c.a("fade", 0.1)))
    c.add(c.text(W - 40, 48, f"{fmt_int(st['total'])} contributions in the last year", "b", 15, T["muted"], anchor="end", anim=c.a("fade", 0.15)))
    nz = sorted(v for _, v in days if v)
    q = [nz[int(len(nz) * f)] if nz else 1 for f in (0.25, 0.5, 0.75)]
    levels = [T["cell"]] + [mix(T["cell"], T["brand"], t) for t in (0.35, 0.58, 0.8, 1.0)]

    def lvl(v):
        if not v:
            return 0
        return 1 + sum(v > x for x in q)

    step, cell = 16, 12.5
    x0, y0 = W - 40 - 53 * step + (step - cell), 80
    first = days[0][0]
    col0 = first - dt.timedelta(days=first.isoweekday() % 7)
    cols = {}
    for d, v in days:
        cols.setdefault((d - col0).days // 7, []).append((d, v))
    for r, lab in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        c.add(c.text(x0 - 10, y0 + r * step + cell - 2, lab, "m", 10, T["muted"], anchor="end", anim=c.a("fade", 0.2)))
    last_month = None
    for ci in sorted(cols):
        d0 = cols[ci][0][0]
        if d0.month != last_month and ci < max(cols) - 1 and (d0.day <= 7 or ci == 0):
            if ci > 0 or d0.day <= 14:
                c.add(c.text(x0 + ci * step, y0 - 10, d0.strftime("%b"), "m", 10, T["muted"], anim=c.a("fade", 0.2 + ci * 0.02)))
            last_month = d0.month
        cells = "".join(
            f'<rect x="{x0 + ci * step:.1f}" y="{y0 + (d.isoweekday() % 7) * step:.1f}" width="{cell}" height="{cell}" rx="3" fill="{levels[lvl(v)]}"/>'
            for d, v in cols[ci]
        )
        c.add(f'<g{c.a("fade", 0.25 + ci * 0.022)}>{cells}</g>')
    td, tv = days[-1]
    ci = (td - col0).days // 7
    tx, ty = x0 + ci * step, y0 + (td.isoweekday() % 7) * step
    ring = (f'<rect x="{tx - 2:.1f}" y="{ty - 2:.1f}" width="{cell + 4}" height="{cell + 4}" rx="4.5" '
            f'fill="none" stroke="{T["brand2"]}" stroke-width="1.5"')
    c.add(f'<g{c.a("fade", 1.5)}>')
    c.loop(ring + f'><animate attributeName="stroke-opacity" values="1;.15;1" dur="2s" begin="{c.at(1.6)}" repeatCount="indefinite"/></rect>', ring + "/>")
    c.add("</g>")
    ly = y0 + 7 * step + 22
    lx = W - 40 - 5 * step - FACES["m"].width("More", 10) - 8
    leg = [c.text(lx - 8, ly + cell - 2, "Less", "m", 10, T["muted"], anchor="end")]
    for k, col in enumerate(levels):
        leg.append(f'<rect x="{lx + k * step:.1f}" y="{ly}" width="{cell}" height="{cell}" rx="3" fill="{col}"/>')
    leg.append(c.text(lx + 5 * step + 4, ly + cell - 2, "More", "m", 10, T["muted"]))
    c.add(f'<g{c.a("fade", 1.5)}>{"".join(leg)}</g>')
    c.add(c.text(40, ly + cell - 2, f"Busiest: {fmt_day(st['busiest'])} · {st['busiest_n']} contributions" if st["busiest_n"] else "", "m", 10, T["muted"], anim=c.a("fade", 1.5)))
    return c


def update_readme(repos):
    if not README.exists():
        return
    rows = []
    for i, r in enumerate(repos):
        rows.append(f'<a href="{esc(r["url"])}"><img src="cards/repo-{i + 1}.svg" width="49.5%" alt="{esc(r["name"])}"></a>')
    block = "<!-- repos:start -->\n<p align=\"center\">\n" + "\n".join(rows) + "\n</p>\n<!-- repos:end -->"
    text = README.read_text()
    new = re.sub(r"<!-- repos:start -->.*?<!-- repos:end -->", lambda _: block, text, flags=re.S)
    if new != text:
        README.write_text(new)


def main():
    user, days = load()
    st = compute(days)
    repos = pick_repos(user)
    now = dt.datetime.now(dt.timezone.utc)
    t = 0.0
    cards = [hero(t)]
    t += 0.45
    for i, spec in enumerate(PROFILE["tiles"]):
        cards.append(tile(t + i * ORDER_GAP, i, spec))
    t += 0.45 + 2 * ORDER_GAP
    cards.append(contributions(t, st))
    t += 0.6
    for i, r in enumerate(repos):
        cards.append(repo_card(t + (i // 2) * ORDER_GAP * 2 + (i % 2) * ORDER_GAP, i, r, now))
    t += ((len(repos) + 1) // 2) * ORDER_GAP * 2 + 0.2
    cards.append(graph(t, st, days))
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.svg"):
        old.unlink()
    for c in cards:
        svg = c.render()
        (OUT / f"{c.name}.svg").write_text(svg)
        print(f"cards/{c.name}.svg  {len(svg) / 1024:.1f} KB")
    update_readme(repos)


if __name__ == "__main__":
    main()
