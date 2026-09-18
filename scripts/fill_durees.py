#!/usr/bin/env python3
"""
Complète le champ « duree » (en minutes) des albums de data/collection.json et
data/wishlist.json qui n'en ont pas encore, en interrogeant Deezer.

Ne touche à rien d'autre : les albums déjà renseignés sont laissés tels quels.
Lancé à la main depuis GitHub (Actions → « Compléter les durées » → Run workflow),
ou en local : python scripts/fill_durees.py
"""
import json
import os
import re
import sys
import time
import unicodedata

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
FILES = [os.path.join(DATA, "collection.json"), os.path.join(DATA, "wishlist.json")]
DEEZER = "https://api.deezer.com"

session = requests.Session()
session.headers["User-Agent"] = "CD-Listes-Durees/1.0 (site personnel)"


def norm(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def clean_title(a):
    """Retire les mentions d'édition pour la recherche : (Reissue), (Digipak), EP…"""
    a = re.sub(r"\((?:[^)]*(?:reissue|digipak|deluxe|edition|re-recorded|normal|ep|split|bonus)[^)]*)\)", "", a, flags=re.I)
    return a.strip(" -–")


def deezer_get(path, params=None):
    for _ in range(3):
        try:
            r = session.get(DEEZER + path, params=params or {}, timeout=30)
            r.raise_for_status()
            js = r.json()
            if isinstance(js, dict) and js.get("error"):
                if js["error"].get("code") == 4:  # quota
                    time.sleep(5)
                    continue
                return None
            time.sleep(0.2)
            return js
        except requests.RequestException:
            time.sleep(2)
    return None


def find_album(groupe, album):
    """Cherche l'album sur Deezer ; renvoie sa durée en minutes ou None."""
    q1 = deezer_get("/search/album", {"q": f'artist:"{groupe}" album:"{clean_title(album)}"', "limit": 5})
    cands = (q1 or {}).get("data", [])
    if not cands:
        q2 = deezer_get("/search/album", {"q": f"{groupe} {clean_title(album)}", "limit": 8})
        cands = (q2 or {}).get("data", [])
    tg, ta = norm(groupe), norm(clean_title(album))
    best = None
    for c in cands:
        if norm((c.get("artist") or {}).get("name", "")) != tg:
            continue
        ct = norm(c.get("title", ""))
        if ct == ta or (len(ta) > 6 and ta in ct) or (len(ct) > 6 and ct in ta):
            best = c
            break
    if not best:
        return None
    detail = deezer_get(f"/album/{best['id']}")
    if detail and detail.get("duration"):
        return str(round(detail["duration"] / 60))
    return None


def main():
    total_done = total_miss = 0
    for path in FILES:
        try:
            with open(path, encoding="utf-8") as f:
                rows = json.load(f)
        except (OSError, ValueError):
            print(f"! impossible de lire {path}", file=sys.stderr)
            continue
        done = miss = 0
        for r in rows:
            if str(r.get("duree", "")).strip():
                continue
            g, a = (r.get("groupe") or "").strip(), (r.get("album") or "").strip()
            if not g or not a:
                continue
            d = find_album(g, a)
            if d:
                r["duree"] = d
                done += 1
                print(f"  {g} — {a} : {d} min")
            else:
                miss += 1
                print(f"  ~ {g} — {a} : non trouvé")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=0)
        print(f"{os.path.basename(path)} : {done} durée(s) ajoutée(s), {miss} non trouvée(s)")
        total_done += done
        total_miss += miss
    print(f"OK : {total_done} ajoutées, {total_miss} restent à saisir à la main")


if __name__ == "__main__":
    main()
