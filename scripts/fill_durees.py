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


EDITION_WORDS = re.compile(r"\b(deluxe|bonus|edition|édition|remaster|remastered|expanded|anniversary|special|limited|digipak|2cd|tour|live|instrumental|version|reissue|re-issue)\b", re.I)


def is_ep_title(a):
    return bool(re.search(r"\bep\b", a, re.I))


def find_album(groupe, album):
    """Cherche l'album sur Deezer ; renvoie (durée en minutes, titre Deezer) ou (None, None).

    Règles : jamais un single ; le titre doit correspondre ; on préfère l'édition
    standard (titre exact, sans mention deluxe/bonus…) et, à titre égal, la plus
    courte (les rééditions 2 CD sont les plus longues)."""
    title = clean_title(album)
    seen, cands = set(), []
    for q in (f'artist:"{groupe}" album:"{title}"', f"{groupe} {title}"):
        js = deezer_get("/search/album", {"q": q, "limit": 10})
        for c in (js or {}).get("data", []):
            if c.get("id") in seen:
                continue
            seen.add(c.get("id"))
            cands.append(c)
        if len(cands) >= 3:
            break
    tg, ta = norm(groupe), norm(title)
    scored = []
    for c in cands:
        if norm((c.get("artist") or {}).get("name", "")) != tg:
            continue
        rt = c.get("record_type", "")
        if rt == "single":
            continue
        if rt == "ep" and not is_ep_title(album):
            continue
        ct_raw = c.get("title", "")
        ct = norm(clean_title(ct_raw))
        exact = ct == ta
        partial = (len(ta) > 6 and ta in ct) or (len(ct) > 6 and ct in ta)
        if not (exact or partial):
            continue
        detail = deezer_get(f"/album/{c['id']}")
        if not detail or not detail.get("duration"):
            continue
        minutes = round(detail["duration"] / 60)
        if minutes < 10 and not is_ep_title(album):
            continue  # trop court pour un album : c'est un single / une piste
        std = not EDITION_WORDS.search(ct_raw) and not EDITION_WORDS.search(album)
        # tri : titre exact d'abord, puis édition standard, puis la plus courte
        scored.append(((0 if exact else 1), (0 if std else 1), minutes, ct_raw))
    if not scored:
        return None, None
    scored.sort()
    return str(scored[0][2]), scored[0][3]


def main():
    total_done = total_miss = 0
    for path in FILES:
        try:
            with open(path, encoding="utf-8") as f:
                rows = json.load(f)
        except (OSError, ValueError):
            print(f"! impossible de lire {path}", file=sys.stderr)
            continue
        done = miss = fixed = 0
        for r in rows:
            cur = str(r.get("duree", "")).strip()
            g, a = (r.get("groupe") or "").strip(), (r.get("album") or "").strip()
            if not g or not a:
                continue
            # on (re)calcule si vide, ou si la valeur actuelle est suspecte (single confondu / réédition 2 CD)
            suspect = cur and (int(cur) < 20 or int(cur) > 85) and not r.get("duree_verifiee")
            if cur and not suspect:
                continue
            d, dz_title = find_album(g, a)
            if d and d != cur:
                r["duree"] = d
                if cur:
                    fixed += 1
                    print(f"  {g} — {a} : {cur} → {d} min ({dz_title})")
                else:
                    done += 1
                    print(f"  {g} — {a} : {d} min ({dz_title})")
            elif not d and not cur:
                miss += 1
                print(f"  ~ {g} — {a} : non trouvé")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=0)
        print(f"{os.path.basename(path)} : {done} ajoutée(s), {fixed} corrigée(s), {miss} non trouvée(s)")
        total_done += done
        total_miss += miss
    print(f"OK : {total_done} ajoutées, {total_miss} restent à saisir à la main")


if __name__ == "__main__":
    main()
