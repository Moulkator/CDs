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
ARTISTS_FILE = os.path.join(DATA, "artists.json")      # surcharges par groupe (search, mbid, mb_query, suivi)
COLLECTION_FILE = os.path.join(DATA, "collection.json")
WISHLIST_FILE = os.path.join(DATA, "wishlist.json")
MANUAL_FILE = os.path.join(DATA, "watchlist-manuel.json")
OUT_FILE = os.path.join(DATA, "sorties.json")
CACHE_FILE = os.path.join(DATA, "mbid-cache.json")
BADGES_FILE = os.path.join(DATA, "mes-badges.json")  # écrit par le site en mode propriétaire

KNOWN = {}  # norm(groupe) -> set(norm(album)) ; rempli dans main()

MB_API = "https://musicbrainz.org/ws/2"
CAA = "https://coverartarchive.org"
DEEZER = "https://api.deezer.com"
UA = "CD-Listes-Sorties/1.0 (site personnel, hébergé sur GitHub Pages)"

# On garde ce qui est sorti depuis moins de N jours (10 ans : le site filtre ensuite
# par 3 / 6 / 12 mois ou par année), et tout ce qui est à venir.
LOOKBACK_DAYS = 3660
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


def titles_match(found_titles, artist):
    """Vrai si au moins un titre trouvé correspond à un album connu du groupe."""
    known = KNOWN.get(norm(artist["groupe"]), set()) | KNOWN.get(norm(artist.get("search", "")), set())
    if not known:
        return True  # rien pour vérifier : on laisse passer
    for t in found_titles:
        nt = norm(t)
        if not nt:
            continue
        for k in known:
            if nt == k or (len(nt) > 6 and nt in k) or (len(k) > 6 and k in nt):
                return True
    return False


# ---------------------------------------------------------------- MusicBrainz

def mb_rg_titles(mbid, limit=100):
    js = mb_get("/release-group", {"artist": mbid, "limit": limit})
    return [rg.get("title", "") for rg in (js or {}).get("release-groups", [])]


def resolve_mbid(artist, cache):
    """Trouve l'identifiant MusicBrainz d'un groupe (mis en cache), en vérifiant
    qu'il a bien au moins un des albums connus (évite les homonymes)."""
    key = norm(artist["search"])
    if artist.get("mbid"):  # identifiant fixé à la main dans artists.json
        cache[key] = {"mbid": artist["mbid"], "name": artist["groupe"], "verified": True, "fixed": True, "checked": TODAY.isoformat()}
        return artist["mbid"]
    if key in cache and cache[key].get("verified") is not None:
        return cache[key].get("mbid")
    query = artist.get("mb_query") or f'artist:"{artist["search"]}"'
    js = mb_get("/artist/", {"query": query, "limit": 8})
    cands = []
    if js and js.get("artists"):
        target = norm(artist["search"])
        for a in js["artists"]:
            name_ok = norm(a.get("name", "")) == target or any(
                norm(al.get("name", "")) == target for al in a.get("aliases", [])
            )
            if not name_ok and int(a.get("score", 0)) < 95 and not artist.get("mb_query"):
                continue
            tags = " ".join(t.get("name", "") for t in a.get("tags", [])).lower()
            score = int(a.get("score", 0))
            if "metal" in tags or "rock" in tags or "punk" in tags:
                score += 15
            if not tags:
                score += 3
            cands.append((score, a))
    cands.sort(key=lambda x: -x[0])
    chosen, verified = None, False
    for score, a in cands[:4]:
        if titles_match(mb_rg_titles(a["id"]), artist):
            chosen, verified = a, True
            break
    if chosen is None and cands and artist.get("mb_query"):
        chosen = cands[0][1]  # requête précisée à la main : on fait confiance
    cache[key] = {
        "mbid": chosen["id"] if chosen else None,
        "name": chosen.get("name") if chosen else None,
        "disambiguation": chosen.get("disambiguation") if chosen else None,
        "verified": verified,
        "checked": TODAY.isoformat(),
    }
    if chosen is None and cands:
        print(f"  ~ MusicBrainz : {len(cands)} homonyme(s) sans album connu, groupe ignoré")
    return cache[key]["mbid"]


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
    if artist.get("deezer_id"):
        hits = [{"id": artist["deezer_id"]}]
    else:
        js = deezer_get("/search/artist", {"q": artist["search"], "limit": 5})
        if not js or not js.get("data"):
            return []
        target = norm(artist["search"])
        hits = [a for a in js["data"] if norm(a.get("name", "")) == target]
    albums = None
    for hit in hits[:3]:
        albums = deezer_get(f"/artist/{hit['id']}/albums", {"limit": 100})
        titles = [al.get("title", "") for al in (albums or {}).get("data", [])]
        if artist.get("deezer_id") or titles_match(titles, artist):
            break
        albums = None
    if albums is None:
        if hits:
            print("  ~ Deezer : homonyme(s) sans album connu, ignoré")
        return []
    out = []
    for al in (albums or {}).get("data", []):
        if al.get("record_type") not in ("album", "ep"):
            continue
        raw = al.get("release_date") or ""
        d, prec = parse_date(raw)
        if not d or d < TODAY - timedelta(days=LOOKBACK_DAYS):
            continue
        item = {
            "groupe": artist["groupe"],
            "album": al.get("title", ""),
            "date": raw,
            "precision": prec,
            "type": al["record_type"],
            "pochette": al.get("cover_big") or al.get("cover_medium") or "",
            "source": "deezer",
            "deezer_id": al.get("id"),
        }
        out.append(item)
    return out


# ------------------------------------------------------------- Pochettes

def html_get(url):
    try:
        r = session.get(url, timeout=30, headers={"Accept": "text/html"})
        if r.status_code == 200:
            return r.text
    except requests.RequestException:
        pass
    return ""


def og_image(url):
    """Image principale d'une page (Bandcamp, Deezer…) via la balise og:image."""
    html = html_get(url)
    m = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', html) or \
        re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', html)
    return m.group(1) if m else ""


def cover_deezer(groupe, album):
    js = deezer_get("/search/album", {"q": f'artist:"{groupe}" album:"{album}"', "limit": 5})
    for c in (js or {}).get("data", []):
        if norm((c.get("artist") or {}).get("name", "")) == norm(groupe) and norm(c.get("title", "")) == norm(album):
            return c.get("cover_big") or c.get("cover_medium") or ""
    return ""


def cover_itunes(groupe, album):
    try:
        r = session.get("https://itunes.apple.com/search", params={"term": f"{groupe} {album}", "entity": "album", "limit": 8}, timeout=30)
        for c in r.json().get("results", []):
            if norm(c.get("artistName", "")) == norm(groupe) and norm(c.get("collectionName", "")) == norm(album):
                return (c.get("artworkUrl100") or "").replace("100x100bb", "600x600bb")
    except Exception:
        pass
    time.sleep(0.5)
    return ""


def cover_bandcamp(groupe, album):
    html = html_get(f"https://bandcamp.com/search?q={requests.utils.quote(groupe + ' ' + album)}&item_type=a")
    for block in re.findall(r'<li class="searchresult[^"]*">(.*?)</li>', html, flags=re.S):
        title = re.search(r'<div class="heading">\s*<a[^>]*>\s*(.*?)\s*</a>', block, flags=re.S)
        sub = re.search(r'<div class="subhead">\s*(.*?)\s*</div>', block, flags=re.S)
        img = re.search(r'<img[^>]+src="([^"]+)"', block)
        if not (title and sub and img):
            continue
        if norm(album) == norm(title.group(1)) and norm(groupe) in norm(sub.group(1)):
            return img.group(1).replace("_7.jpg", "_5.jpg")
    return ""


def find_cover(groupe, album, page_url=""):
    if page_url:
        img = og_image(page_url)
        if img:
            return img
    for fn in (cover_deezer, cover_itunes, cover_bandcamp):
        try:
            img = fn(groupe, album)
        except Exception:
            img = ""
        if img:
            return img
    return ""


# ---------------------------------------------------------------------- Merge

def album_key(groupe, album):
    a = norm(album)
    a = re.sub(r"\b(deluxe|edition|bonus|remaster(ed)?|digipak|version)\b", "", a).strip()
    return norm(groupe) + "|" + a


def build_artists():
    """Liste des groupes à suivre = collection + wishlist, avec les surcharges d'artists.json."""
    overrides = {norm(o["groupe"]): o for o in load_json(ARTISTS_FILE, [])}
    arts = {}
    for row in load_json(COLLECTION_FILE, []) + load_json(WISHLIST_FILE, []):
        g = (row.get("groupe") or "").strip()
        if not g:
            continue
        k = norm(g)
        KNOWN.setdefault(k, set()).add(norm(row.get("album", "")))
        a = arts.setdefault(k, {"groupe": g, "search": g})
        o = overrides.get(k)
        if o:
            for f in ("search", "mbid", "mb_query", "deezer_id", "suivi"):
                if f in o:
                    a[f] = o[f]
    return sorted(arts.values(), key=lambda a: norm(a["groupe"]))


def main():
    artists = build_artists()
    manual = load_json(MANUAL_FILE, [])
    badges = load_json(BADGES_FILE, {})
    ignores = set(badges.get("groupes_ignores", []))      # groupes « ne plus suivre »
    exclus = set(badges.get("sorties_exclues", []))       # sorties masquées une à une
    artists = [a for a in artists if norm(a["groupe"]) not in ignores and norm(a.get("search", "")) not in ignores]
    artists = [a for a in artists if a.get("suivi", True) is not False]   # suivi: false dans artists.json = pas de veille

    if ignores:
        print(f"{len(ignores)} groupe(s) non suivi(s) ignoré(s)")
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
        for f in ("mb_rg", "deezer_id", "duree"):
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

    # liste manuelle : une entrée dont l'album est trouvé automatiquement devient une
    # sortie « auto » et quitte la liste manuelle (sauf si sa date est plus précise).
    rank = {"exact": 3, "month": 2, "year": 1, "unknown": 0}
    manual_kept = []
    for m in manual:
        k = album_key(m["groupe"], m["album"])
        item = {
            "groupe": m["groupe"], "album": m["album"], "date": m.get("date", ""),
            "precision": m.get("precision", "exact" if m.get("date") else "unknown"),
            "type": "album", "pochette": m.get("pochette", ""), "pochette_page": m.get("pochette_page", ""),
            "note": m.get("note", ""), "source": "manuel",
        }
        if k in merged:
            cur = merged[k]
            keep = rank[item["precision"]] > rank[cur["precision"]] or bool(item["pochette"]) or bool(item["pochette_page"]) or bool(item["note"])
            if rank[item["precision"]] > rank[cur["precision"]]:
                cur["date"], cur["precision"] = item["date"], item["precision"]
            if item["pochette"]:
                cur["pochette"] = item["pochette"]
            if item["pochette_page"]:
                cur["pochette_page"] = item["pochette_page"]
            if item["note"]:
                cur["note"] = item["note"]
            if keep:
                cur["source"] = "+".join(sorted(set(cur["source"].split("+") + ["manuel"])))
                manual_kept.append(m)
            else:
                print(f"  → {m['groupe']} — {m['album']} : trouvé automatiquement, retiré de la liste manuelle")
        else:
            merged[k] = item
            manual_kept.append(m)
    if len(manual_kept) != len(manual):
        with open(MANUAL_FILE, "w", encoding="utf-8") as f:
            json.dump(manual_kept, f, ensure_ascii=False, indent=1)

    # on conserve une pochette / durée trouvée lors d'un run précédent si elle a disparu
    for k, it in merged.items():
        for f in ("pochette", "duree"):
            if not it.get(f) and prev_by_key.get(k, {}).get(f):
                it[f] = prev_by_key[k][f]

    items = [it for k, it in merged.items() if k not in exclus and norm(it["groupe"]) not in ignores]
    for it in items:
        if not it.get("pochette"):
            img = find_cover(it["groupe"], it["album"], it.get("pochette_page", ""))
            if img:
                it["pochette"] = img
                print(f"  ✓ pochette trouvée : {it['groupe']} — {it['album']}")
        if not it.get("duree") and it.get("deezer_id"):
            detail = deezer_get(f"/album/{it['deezer_id']}")
            if detail and detail.get("duration") and detail.get("record_type") != "single":
                it["duree"] = str(round(detail["duration"] / 60))
    items = sorted(items, key=lambda x: (x["date"] or "9999", norm(x["groupe"])))
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
