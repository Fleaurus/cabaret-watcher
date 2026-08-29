#!/usr/bin/env python3
"""
Stadsschouwburg Utrecht agenda-watcher.

Checkt de agenda (default: genre=cabaret) en meldt:
  - NIEUW      : voorstelling stond er de vorige keer nog niet bij
  - WEER VRIJ  : was uitverkocht, is nu weer te koop (returns!)
  - UITVERKOCHT: was te koop, nu vol (alleen als --meld-uitverkocht)

Geen dependencies buiten de standard library.
"""

import argparse
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime

BASE = "https://stadsschouwburg-utrecht.nl/agenda"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")
CONFIG = os.path.join(HERE, "config.json")


# ---------- ophalen ----------

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "nl"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def txt(s):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


CARD_RE = re.compile(r'<li class="paging-container".*?</li>', re.S)


def parse_cards(page_html):
    out = []
    for block in CARD_RE.findall(page_html):
        m = re.search(r'<a class="covering-link[^"]*" href="(/agenda/[^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        slug, title = m.group(1), txt(m.group(2))
        subs = re.findall(r'<p class="subtitle[^"]*">(.*?)</p>', block, re.S)
        artist = txt(subs[0]) if subs else ""
        t = re.search(r'<time datetime="([^"]*)">(.*?)</time>', block, re.S)
        when = txt(t.group(2)) if t else ""
        iso = t.group(1) if t else ""
        zaal_m = re.search(r'<p class="location[^"]*">(.*?)</p>', block, re.S)
        zaal = txt(zaal_m.group(1)) if zaal_m else ""
        tags = [txt(x) for x in re.findall(r'<span class="tag[^"]*">(.*?)</span>', block, re.S)]
        labels = [txt(x).lower() for x in re.findall(r"<span>\s*([^<>]{2,40}?)\s*</span>", block)]
        soldout = "uitverkocht" in labels
        ticket = re.search(r'href="(https://apps\.ticketmatic\.com/widgets/[^"]+)"', block)
        out.append({
            "id": slug,
            "titel": title,
            "artiest": artist,
            "datum": when,
            "datum_iso": iso,
            "zaal": zaal,
            "tags": tags,
            "uitverkocht": soldout,
            "labels": [l for l in labels if l in ("uitverkocht", "reprise", "try-out", "premiere")],
            "url": "https://stadsschouwburg-utrecht.nl" + slug,
            "ticket_url": html.unescape(ticket.group(1)) if ticket else None,
        })
    return out


def scrape(params):
    """params: dict, bv. {'genre': 'cabaret'}. Loopt alle pagina's af."""
    q = urllib.parse.urlencode(params)
    first = fetch(f"{BASE}?{q}&page=1")
    pages = [int(n) for n in re.findall(r"page=(\d+)", first)] or [1]
    cards = parse_cards(first)
    for p in range(2, max(pages) + 1):
        cards += parse_cards(fetch(f"{BASE}?{q}&page={p}"))
    # dedupe op id, eerste wint
    seen, uniq = set(), []
    for c in cards:
        if c["id"] not in seen:
            seen.add(c["id"])
            uniq.append(c)
    return uniq


# ---------- notificaties ----------

def notify_mac(title, body, url=None):
    """Alleen op macOS; op Linux (GitHub Actions) stil overslaan."""
    if sys.platform != "darwin":
        return
    import subprocess
    body = body.replace('"', "'")
    title = title.replace('"', "'")
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification "{body}" with title "{title}" sound name "Glass"'],
                       check=False)
    except OSError:
        pass


def notify_ntfy(topic, title, body, url=None, prio="high"):
    if not topic:
        return
    endpoint = topic if topic.startswith("http") else f"https://ntfy.sh/{topic}"
    headers = {
        "Title": title.encode("utf-8").decode("latin-1", "replace"),
        "Priority": prio,
        "Tags": "performing_arts",
        "User-Agent": UA,
    }
    if url:
        headers["Click"] = url
    req = urllib.request.Request(endpoint, data=body.encode("utf-8"), headers=headers, method="POST")
    try:
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:
        print(f"[ntfy] mislukt: {e}", file=sys.stderr)


# ---------- main ----------

def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def main():
    cfg = load(CONFIG, {})
    ap = argparse.ArgumentParser()
    ap.add_argument("--genre", default=cfg.get("genre", "cabaret"),
                    help="genre-filter, of 'alles' voor de hele agenda")
    ap.add_argument("--ntfy", default=cfg.get("ntfy_topic", os.environ.get("NTFY_TOPIC", "")),
                    help="ntfy.sh topic voor push naar je telefoon")
    ap.add_argument("--meld-uitverkocht", action="store_true",
                    default=cfg.get("meld_uitverkocht", False))
    ap.add_argument("--geen-mac-melding", action="store_true")
    ap.add_argument("--init", action="store_true",
                    help="alleen huidige stand opslaan, niks melden")
    ap.add_argument("--lijst", action="store_true", help="print de huidige agenda en stop")
    args = ap.parse_args()

    params = {} if args.genre in ("alles", "all", "") else {"genre": args.genre}
    shows = scrape(params)
    if not shows:
        print("Geen voorstellingen gevonden — site-structuur veranderd?", file=sys.stderr)
        sys.exit(1)

    if args.lijst:
        for s in shows:
            vlag = "UITVERKOCHT" if s["uitverkocht"] else "te koop"
            print(f"{s['datum']:<28} {s['titel']} — {s['artiest']}  [{vlag}]")
        print(f"\n{len(shows)} voorstellingen.")
        return

    state = load(STATE, {})
    old = state.get("shows", {})
    # ticket_url bevat Ticketmatic accesskey/signature -> niet in state (repo kan public zijn)
    new_state = {s["id"]: {k: v for k, v in s.items() if k != "ticket_url"} for s in shows}

    nieuw = [s for s in shows if s["id"] not in old]
    weer_vrij = [s for s in shows
                 if s["id"] in old and old[s["id"]].get("uitverkocht") and not s["uitverkocht"]]
    vol = [s for s in shows
           if s["id"] in old and not old[s["id"]].get("uitverkocht") and s["uitverkocht"]]

    with open(STATE, "w") as f:
        # alleen de datum: anders verandert state.json elke run en commit Actions elk uur
        json.dump({"laatst": datetime.now().strftime("%Y-%m-%d"),
                   "genre": args.genre, "shows": new_state}, f, ensure_ascii=False, indent=1)

    if args.init or not old:
        print(f"Startstand opgeslagen: {len(shows)} voorstellingen ({args.genre}). "
              f"Vanaf nu meld ik alleen wijzigingen.")
        return

    def regel(s):
        vlag = " [UITVERKOCHT]" if s["uitverkocht"] else ""
        return f"• {s['titel']} — {s['artiest']} ({s['datum']}){vlag}"

    meldingen = []
    if nieuw:
        meldingen.append(("Nieuw in de agenda", nieuw, "high"))
    if weer_vrij:
        meldingen.append(("Weer kaarten beschikbaar", weer_vrij, "urgent"))
    if vol and args.meld_uitverkocht:
        meldingen.append(("Nu uitverkocht", vol, "default"))

    if not meldingen:
        print(f"{datetime.now():%Y-%m-%d %H:%M} — niets nieuws ({len(shows)} voorstellingen).")
        return

    for kop, groep, prio in meldingen:
        body = "\n".join(regel(s) for s in groep)
        titel = f"{kop} ({len(groep)})"
        print(f"\n=== {titel} ===\n{body}")
        link = groep[0]["url"] if len(groep) == 1 else \
            f"{BASE}?{urllib.parse.urlencode(params)}"
        if not args.geen_mac_melding:
            notify_mac(f"Schouwburg: {titel}", body.replace("\n", " · ")[:200])
        notify_ntfy(args.ntfy, f"🎭 {titel}", body, link, prio)


if __name__ == "__main__":
    main()
