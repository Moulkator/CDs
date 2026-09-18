#!/usr/bin/env python3
"""
Envoie sur Discord (webhook) un message par nouveauté dans data/sorties.json :
  🆕 album annoncé  (absent de la version précédente)
  💿 album sorti    (sa date vient d'être atteinte)

Le fichier data/sorties-prev.json garde la version précédente pour comparer.
Au tout premier lancement (pas de fichier précédent), rien n'est envoyé : on
prend juste la photo de départ, pour ne pas recevoir 200 messages d'un coup.

Variables d'environnement :
  DISCORD_WEBHOOK  URL du webhook (secret GitHub)  — obligatoire
  SITE_URL         adresse du site, pour les pochettes hébergées dans le dépôt
"""
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date, timedelta
from urllib.parse import quote

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CUR_FILE = os.path.join(DATA, "sorties.json")
PREV_FILE = os.path.join(DATA, "sorties-prev.json")
COLL_FILE = os.path.join(DATA, "collection.json")
WISH_FILE = os.path.join(DATA, "wishlist.json")
BADGES_FILE = os.path.join(DATA, "mes-badges.json")

WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "").strip()
SITE_URL = os.environ.get("SITE_URL", "https://moulkator.github.io/CDs/").rstrip("/") + "/"
MAX_MESSAGES = 15  # au-delà, un message récapitulatif
TODAY = date.today()

MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def norm(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def album_key(groupe, album):
    a = norm(album)
    a = re.sub(r"\b(deluxe|edition|bonus|remaster(ed)?|digipak|version)\b", "", a).strip()
    return norm(groupe) + "|" + a


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def parse_date(raw):
    if not raw:
        return None
    p = raw.split("-")
    try:
        if len(p) == 1:
            return date(int(p[0]), 12, 31)
        if len(p) == 2:
            y, m = int(p[0]), int(p[1])
            return date(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)
        return date(int(p[0]), int(p[1]), int(p[2]))
    except ValueError:
        return None


def fmt_date(raw, prec):
    p = (raw or "").split("-")
    if prec == "year":
        return p[0]
    if prec == "month":
        return f"{MOIS[int(p[1]) - 1]} {p[0]}"
    if prec == "exact":
        return f"{int(p[2])} {MOIS[int(p[1]) - 1]} {p[0]}"
    return "date inconnue"


def fmt_duree(m):
    try:
        m = int(m)
    except (TypeError, ValueError):
        return ""
    if m <= 0:
        return ""
    return f"{m // 60} h {m % 60:02d}" if m >= 60 else f"{m} min"


def is_past(it):
    d = parse_date(it.get("date"))
    return bool(d) and d <= TODAY


def artist_info(groupe, rows):
    """Style / pays / langue les plus fréquents parmi tes albums de ce groupe."""
    out = {}
    for f in ("style", "pays", "langue"):
        cnt = {}
        for r in rows:
            if norm(r.get("groupe", "")) == norm(groupe) and (r.get(f) or "").strip():
                cnt[r[f].strip()] = cnt.get(r[f].strip(), 0) + 1
        if cnt:
            out[f] = max(cnt, key=cnt.get)
    return out


def build_embed(it, kind, known, arts_rows):
    g, a = it["groupe"], it["album"]
    k = album_key(g, a)
    info = artist_info(g, arts_rows)
    q = quote(f"{g} {a}")
    fields = []
    fields.append({"name": "Date de sortie", "value": fmt_date(it.get("date"), it.get("precision", "unknown"))
                   + (" *(approximative)*" if it.get("precision") in ("month", "year") else ""), "inline": True})
    if it.get("type") == "ep":
        fields.append({"name": "Format", "value": "EP", "inline": True})
    if fmt_duree(it.get("duree")):
        fields.append({"name": "Durée", "value": fmt_duree(it.get("duree")), "inline": True})
    if info.get("style"):
        fields.append({"name": "Style", "value": info["style"], "inline": True})
    if info.get("pays"):
        fields.append({"name": "Pays", "value": info["pays"], "inline": True})
    if info.get("langue"):
        fields.append({"name": "Langue", "value": info["langue"], "inline": True})
    if known.get(k):
        fields.append({"name": "Chez toi", "value": "Déjà dans la collection" if known[k] == "collection" else "Dans la liste de souhaits", "inline": True})
    if it.get("note"):
        fields.append({"name": "Note", "value": it["note"][:1000], "inline": False})
    links = (f"[Deezer](https://www.deezer.com/search/{q}) · [Bandcamp](https://bandcamp.com/search?q={q})"
             f" · [Metallum](https://www.metal-archives.com/search?searchString={quote(g)}&type=band_name)"
             f" · [Sur le site]({SITE_URL}sorties.html#sorties)")
    fields.append({"name": "Liens", "value": links, "inline": False})

    embed = {
        "title": f"{g} — {a}",
        "url": f"{SITE_URL}sorties.html#sorties",
        "color": 0x4CAF50 if kind == "sorti" else 0xC9A227,
        "fields": fields,
        "footer": {"text": f"Source : {it.get('source', '?')}"},
    }
    cover = it.get("pochette") or ""
    if cover:
        if not cover.startswith("http"):
            cover = SITE_URL + cover.lstrip("/")
        embed["thumbnail"] = {"url": cover}
        embed["image"] = {"url": cover}
    else:
        embed["description"] = "*Pochette pas encore dévoilée*"
    return embed


def send(payload):
    for attempt in range(4):
        r = requests.post(WEBHOOK, json=payload, timeout=30)
        if r.status_code == 429:
            wait = float(r.headers.get("Retry-After", "2"))
            time.sleep(min(wait, 10) + 0.5)
            continue
        if r.status_code >= 400:
            print(f"  ! Discord {r.status_code} : {r.text[:200]}", file=sys.stderr)
        return r.status_code < 400
    return False


def main():
    cur = load_json(CUR_FILE, {}).get("items", [])
    prev_data = load_json(PREV_FILE, None)

    if prev_data is None:
        with open(PREV_FILE, "w", encoding="utf-8") as f:
            json.dump({"items": cur}, f, ensure_ascii=False, indent=0)
        print("Premier passage : photo de départ enregistrée, aucune notification envoyée.")
        return
    if not WEBHOOK:
        print("DISCORD_WEBHOOK absent : aucune notification (le secret GitHub n'est pas défini).")
        return

    prev = {album_key(i["groupe"], i["album"]): i for i in prev_data.get("items", [])}
    known = {}
    coll, wish = load_json(COLL_FILE, []), load_json(WISH_FILE, [])
    for r in coll:
        known[album_key(r.get("groupe", ""), r.get("album", ""))] = "collection"
    for r in wish:
        known.setdefault(album_key(r.get("groupe", ""), r.get("album", "")), "wishlist")
    badges = load_json(BADGES_FILE, {})
    exclus = set(badges.get("sorties_exclues", []))
    ignores = set(badges.get("groupes_ignores", []))

    events = []
    for it in cur:
        k = album_key(it["groupe"], it["album"])
        if k in exclus or norm(it["groupe"]) in ignores:
            continue
        old = prev.get(k)
        if old is None:
            # nouvelle entrée ; si elle est déjà sortie depuis longtemps, c'est un rattrapage, pas une annonce
            d = parse_date(it.get("date"))
            if d and d < TODAY - timedelta(days=45):
                continue
            events.append(("sorti" if is_past(it) else "annonce", it))
        elif is_past(it) and not is_past(old) and it.get("precision") == "exact":
            events.append(("sorti", it))

    if not events:
        print("Rien de nouveau, pas de notification.")
    else:
        events.sort(key=lambda e: (e[0] != "sorti", e[1].get("date") or "9999"))
        sent = 0
        for kind, it in events[:MAX_MESSAGES]:
            content = ("💿 **Sorti aujourd'hui !**" if kind == "sorti" else "🆕 **Album annoncé**")
            ok = send({"content": content, "embeds": [build_embed(it, kind, known, coll + wish)]})
            sent += ok
            print(f"  {'✓' if ok else '✗'} {kind} : {it['groupe']} — {it['album']}")
            time.sleep(1.2)
        if len(events) > MAX_MESSAGES:
            rest = events[MAX_MESSAGES:]
            lines = "\n".join(f"• {'💿' if kd == 'sorti' else '🆕'} {i['groupe']} — {i['album']} ({fmt_date(i.get('date'), i.get('precision', 'unknown'))})" for kd, i in rest[:40])
            send({"content": f"… et **{len(rest)}** autre(s) :\n{lines}\n{SITE_URL}sorties.html#sorties"})
        print(f"{sent}/{len(events)} notification(s) envoyée(s)")

    with open(PREV_FILE, "w", encoding="utf-8") as f:
        json.dump({"items": cur}, f, ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main()
