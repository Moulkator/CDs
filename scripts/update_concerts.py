#!/usr/bin/env python3
"""
Récupère sur Bandsintown les concerts annoncés des groupes de data/collection.json
et data/wishlist.json (plus les groupes « à écouter » et souhaits de mes-badges.json),
et écrit data/concerts.json. Lancé par le workflow après update_sorties.py.

Variable d'environnement facultative : BANDSINTOWN_APP_ID (identifiant d'application).
"""
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timezone
from urllib.parse import quote

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT_FILE = os.path.join(DATA, "concerts.json")
APP_ID = os.environ.get("BANDSINTOWN_APP_ID", "").strip() or "site-cd-moulkator"
API = "https://rest.bandsintown.com/artists/{name}/events?app_id={app}&date=upcoming"

session = requests.Session()
session.headers["User-Agent"] = "CD-Listes-Concerts/1.0 (site personnel)"


def norm(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def artists():
    overrides = {norm(o["groupe"]): o for o in load_json(os.path.join(DATA, "artists.json"), [])}
    seen, out = {}, []
    def add(g, source):
        g = (g or "").strip()
        if not g:
            return
        k = norm(g)
        o = overrides.get(k, {})
        if o.get("suivi") is False:
            return
        if k in seen:
            if source not in seen[k]["sources"]:
                seen[k]["sources"].append(source)
            return
        seen[k] = {"groupe": g, "search": o.get("search") or g, "sources": [source]}
        out.append(seen[k])
    for r in load_json(os.path.join(DATA, "collection.json"), []):
        add(r.get("groupe"), "collection")
    for r in load_json(os.path.join(DATA, "wishlist.json"), []):
        add(r.get("groupe"), "wishlist")
    badges = load_json(os.path.join(DATA, "mes-badges.json"), {})
    for r in badges.get("souhaits", []):
        add(r.get("groupe"), "wishlist")
    for r in badges.get("a_ecouter", []):
        add(r.get("groupe"), "ecouter")
    return out


def fetch(artist):
    url = API.format(name=quote(artist["search"], safe=""), app=quote(APP_ID))
    for attempt in range(3):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 429:
                time.sleep(3)
                continue
            if r.status_code in (403, 404):
                return [] if r.status_code == 404 else None
            r.raise_for_status()
            js = r.json()
            return js if isinstance(js, list) else []
        except requests.RequestException as e:
            print(f"  ! {artist['groupe']}: {e}", file=sys.stderr)
            time.sleep(2)
    return []


def main():
    arts = artists()
    events, forbidden = [], False
    for i, a in enumerate(arts, 1):
        res = fetch(a)
        if res is None:
            forbidden = True
            print("  ! Bandsintown refuse l'identifiant d'application (403) : définis le secret BANDSINTOWN_APP_ID", file=sys.stderr)
            break
        for ev in res:
            v = ev.get("venue") or {}
            try:
                lat, lng = float(v.get("latitude")), float(v.get("longitude"))
            except (TypeError, ValueError):
                lat = lng = None
            dt = (ev.get("datetime") or "")[:16]
            events.append({
                "groupe": a["groupe"], "sources": a["sources"],
                "date": dt, "titre": ev.get("title") or "",
                "salle": v.get("name") or "", "ville": v.get("city") or "", "region": v.get("region") or "", "pays": v.get("country") or "",
                "lat": lat, "lng": lng,
                "lineup": [x for x in (ev.get("lineup") or []) if norm(x) != norm(a["groupe"])][:6],
                "url": ev.get("url") or "", "festival": bool(ev.get("festival_datetime_display_start")) or "festival" in (ev.get("title") or "").lower(),
            })
        if i % 50 == 0:
            print(f"[{i}/{len(arts)}] {len(events)} concert(s)")
        time.sleep(0.25)
    events.sort(key=lambda e: (e["date"], norm(e["groupe"])))
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "app_id_refuse": forbidden, "artistes": len(arts), "items": events}
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
    print(f"OK : {len(events)} concert(s) pour {len(arts)} groupe(s)")


if __name__ == "__main__":
    main()
