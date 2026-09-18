#!/usr/bin/env python3
"""
Met à jour data/sorties.json : albums annoncés ou sortis récemment
pour les groupes de data/artists.json.

Sources :
  1. MusicBrainz (release-groups + first-release-date) + Cover Art Archive
  2. Deezer (albums avec release_date, pochettes)
  3. data/watchlist-manuel.json (liste saisie à la main, prioritaire)

Aucune clé d'API n'est nécessaire.
Lancé par .github/workflows/update-sorties.yml (chaque nuit), ou à la main :
    python scripts/update_sorties.py
"""
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
ARTISTS_FILE = os.path.join(DATA, "artists.json")
MANUAL_FILE = os.path.join(DATA, "watchlist-manuel.json")
OUT_FILE = os.path.join(DATA, "sorties.json")
CACHE_FILE = os.path.join(DATA, "mbid-cache.json")

MB_API = "https://musicbrainz.org/ws/2"
CAA = "https://coverartarchive.org"
DEEZER = "https://api.deezer.com"
UA = "CD-Listes-Sorties/1.0 (site personnel, hébergé sur GitHub Pages)"

# On garde ce qui est sorti depuis moins de N jours, et tout ce qui est à venir.
LOOKBACK_DAYS = 180
TODAY = date.today()

session = requests.Session()
session.headers["User-Agent"] = UA


def norm(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def mb_get(path, params, retries=3):
    """Appel MusicBrainz avec respect de la limite (1 requête / seconde)."""
    params = dict(params, fmt="json")
    for attempt in range(retries):
        try:
            r = session.get(MB_API + path, params=params, timeout=30)
            if r.status_code == 503:
                time.sleep(3)
                continue
            r.raise_for_status()
            time.sleep(1.1)
            return r.json()
        except requests.RequestException as e:
            print(f"  ! MusicBrainz {path}: {e}", file=sys.stderr)
            time.sleep(2)
    return None


def deezer_get(path, params=None, retries=3):
    for attempt in range(retries):
        try:
            r = session.get(DEEZER + path, params=params or {}, timeout=30)
            r.raise_for_status()
            js = r.json()
            if isinstance(js, dict) and js.get("error"):
                code = js["error"].get("code")
                if code == 4:  # quota
                    time.sleep(5)
                    continue
                return None
            time.sleep(0.25)
            return js
        except requests.RequestException as e:
            print(f"  ! Deezer {path}: {e}", file=sys.stderr)
            time.sleep(2)
    return None


# ---------------------------------------------------------------- MusicBrainz

def resolve_mbid(artist, cache):
    """Trouve l'identifiant MusicBrainz d'un groupe (mis en cache)."""
    key = norm(artist["search"])
    if key in cache:
        return cache[key].get("mbid")
    js = mb_get("/artist/", {"query": f'artist:"{artist["search"]}"', "limit": 8})
    best = None
    if js and js.get("artists"):
        target = norm(artist["search"])
        for a in js["artists"]:
            name_ok = norm(a.get("name", "")) == target or any(
                norm(al.get("name", "")) == target for al in a.get("aliases", [])
            )
            if not name_ok and int(a.get("score", 0)) < 95:
                continue
            tags = " ".join(t.get("name", "") for t in a.get("tags", [])).lower()
            score = int(a.get("score", 0))
            if "metal" in tags or "rock" in tags or "punk" in tags:
                score += 15
            if not tags:
                score += 3
            if best is None or score > best[0]:
                best = (score, a)
    mbid = best[1]["id"] if best else None
    cache[key] = {
        "mbid": mbid,
        "name": best[1].get("name") if best else None,
        "disambiguation": best[1].get("disambiguation") if best else None,
        "checked": TODAY.isoformat(),
    }
    return mbid


def caa_front(rg_id):
    """URL de pochette Cover Art Archive si elle existe (sinon '')."""
    url = f"{CAA}/release-group/{rg_id}/front-500"
    try:
        r = session.head(url, allow_redirects=False, timeout=20)
        if r.status_code in (200, 307, 302, 301):
            return url
    except requests.RequestException:
        pass
    return ""


def mb_releases(artist, mbid):
    out = []
    offset = 0
    while True:
        js = mb_get("/release-group", {"artist": mbid, "limit": 100, "offset": offset})
        if not js:
            break
        for rg in js.get("release-groups", []):
            ptype = rg.get("primary-type") or ""
            if ptype not in ("Album", "EP"):
                continue
            if rg.get("secondary-types"):  # live, compilation, remix…
                continue
            raw = rg.get("first-release-date") or ""
            d, prec = parse_date(raw)
            if not d:
                continue
            if d < TODAY - timedelta(days=LOOKBACK_DAYS):
                continue
            out.append({
                "groupe": artist["groupe"],
                "album": rg.get("title", ""),
                "date": raw,
                "precision": prec,
                "type": ptype.lower(),
                "pochette": "",
                "source": "musicbrainz",
                "mb_rg": rg["id"],
            })
        total = js.get("release-group-count", 0)
        offset += 100
        if offset >= total:
            break
    for it in out:
        it["pochette"] = caa_front(it["mb_rg"])
    return out


def parse_date(raw):
    """'2026' -> (date(2026,12,31), 'year') ; '2026-10' -> (…-10-31, 'month') ; complet -> 'exact'."""
    if not raw:
        return None, "unknown"
    parts = raw.split("-")
    try:
        if len(parts) == 1:
            return date(int(parts[0]), 12, 31), "year"
        if len(parts) == 2:
            y, m = int(parts[0]), int(parts[1])
            nxt = date(y + (m == 12), (m % 12) + 1, 1)
            return nxt - timedelta(days=1), "month"
        return date(int(parts[0]), int(parts[1]), int(parts[2])), "exact"
    except ValueError:
        return None, "unknown"


# --------------------------------------------------------------------- Deezer

def deezer_releases(artist):
    js = deezer_get("/search/artist", {"q": artist["search"], "limit": 5})
    if not js or not js.get("data"):
        return []
    target = norm(artist["search"])
    hit = next((a for a in js["data"] if norm(a.get("name", "")) == target), None)
    if not hit:
        return []
    albums = deezer_get(f"/artist/{hit['id']}/albums", {"limit": 100})
    out = []
    for al in (albums or {}).get("data", []):
        if al.get("record_type") not in ("album", "ep"):
            continue
        raw = al.get("release_date") or ""
        d, prec = parse_date(raw)
        if not d or d < TODAY - timedelta(days=LOOKBACK_DAYS):
            continue
        out.append({
            "groupe": artist["groupe"],
            "album": al.get("title", ""),
            "date": raw,
            "precision": prec,
            "type": al["record_type"],
            "pochette": al.get("cover_big") or al.get("cover_medium") or "",
            "source": "deezer",
            "deezer_id": al.get("id"),
        })
    return out


# ---------------------------------------------------------------------- Merge

def album_key(groupe, album):
    a = norm(album)
    a = re.sub(r"\b(deluxe|edition|bonus|remaster(ed)?|digipak|version)\b", "", a).strip()
    return norm(groupe) + "|" + a


def main():
    artists = load_json(ARTISTS_FILE, [])
    manual = load_json(MANUAL_FILE, [])
    cache = load_json(CACHE_FILE, {})
    previous = load_json(OUT_FILE, {"items": []})
    prev_by_key = {album_key(i["groupe"], i["album"]): i for i in previous.get("items", [])}

    merged = {}

    def add(item):
        k = album_key(item["groupe"], item["album"])
        cur = merged.get(k)
        if cur is None:
            merged[k] = item
            return
        # on garde la date la plus précise, et une pochette si l'une des sources en a
        rank = {"exact": 3, "month": 2, "year": 1, "unknown": 0}
        if rank[item["precision"]] > rank[cur["precision"]]:
            cur["date"], cur["precision"] = item["date"], item["precision"]
        if not cur.get("pochette") and item.get("pochette"):
            cur["pochette"] = item["pochette"]
        cur["source"] = "+".join(sorted(set(cur["source"].split("+") + item["source"].split("+"))))
        for f in ("mb_rg", "deezer_id"):
            if item.get(f) and not cur.get(f):
                cur[f] = item[f]

    n = len(artists)
    for i, artist in enumerate(artists, 1):
        print(f"[{i}/{n}] {artist['groupe']}")
        try:
            mbid = resolve_mbid(artist, cache)
            if mbid:
                for it in mb_releases(artist, mbid):
                    add(it)
        except Exception as e:  # on ne veut jamais planter tout le run pour un groupe
            print(f"  ! MusicBrainz échec {artist['groupe']}: {e}", file=sys.stderr)
        try:
            for it in deezer_releases(artist):
                add(it)
        except Exception as e:
            print(f"  ! Deezer échec {artist['groupe']}: {e}", file=sys.stderr)
        if i % 25 == 0:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=1)

    # liste manuelle : prioritaire sur la date
    for m in manual:
        k = album_key(m["groupe"], m["album"])
        item = {
            "groupe": m["groupe"], "album": m["album"], "date": m.get("date", ""),
            "precision": m.get("precision", "exact" if m.get("date") else "unknown"),
            "type": "album", "pochette": m.get("pochette", ""), "source": "manuel",
        }
        if k in merged:
            cur = merged[k]
            if item["date"]:
                cur["date"], cur["precision"] = item["date"], item["precision"]
            if item["pochette"]:
                cur["pochette"] = item["pochette"]
            cur["source"] = "+".join(sorted(set(cur["source"].split("+") + ["manuel"])))
        else:
            merged[k] = item

    # on conserve une pochette trouvée lors d'un run précédent si elle a disparu
    for k, it in merged.items():
        if not it.get("pochette") and prev_by_key.get(k, {}).get("pochette"):
            it["pochette"] = prev_by_key[k]["pochette"]

    items = sorted(merged.values(), key=lambda x: (x["date"] or "9999", norm(x["groupe"])))
    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": ["manuel", "musicbrainz", "deezer"],
        "lookback_days": LOOKBACK_DAYS,
        "items": items,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    print(f"OK : {len(items)} sorties écrites dans {OUT_FILE}")


if __name__ == "__main__":
    main()
