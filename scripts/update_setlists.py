#!/usr/bin/env python3
"""
Pour chaque groupe qui a des concerts à venir (data/concerts.json), calcule une
« setlist type » à partir de ses 10 derniers concerts sur setlist.fm : morceaux
joués et fréquence, nombre moyen de morceaux. Résultat dans data/setlists.json,
conservé 7 jours par groupe (la limite gratuite de setlist.fm est de ~1400
requêtes/jour, on l'économise).

Secret GitHub requis : SETLISTFM_API_KEY (clé gratuite : https://api.setlist.fm/docs/1.0/index.html).
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
CONCERTS_FILE = os.path.join(DATA, "concerts.json")
OUT_FILE = os.path.join(DATA, "setlists.json")
KEY = os.environ.get("SETLISTFM_API_KEY", "").strip()
API = "https://api.setlist.fm/rest/1.0/search/setlists"
MAX_SHOWS = 10
TTL_DAYS = 7
MAX_PER_RUN = 120  # garde une marge sous la limite quotidienne


def norm(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def fetch_setlists(name):
    for attempt in range(3):
        try:
            r = requests.get(API, params={"artistName": name, "p": 1}, headers={"x-api-key": KEY, "Accept": "application/json", "User-Agent": "CD-Listes-Setlists/1.0"}, timeout=30)
            if r.status_code == 404:
                return []
            if r.status_code == 429:
                time.sleep(5)
                continue
            if r.status_code == 403:
                return None
            r.raise_for_status()
            return r.json().get("setlist", [])
        except requests.RequestException as e:
            print(f"  ! {name}: {e}", file=sys.stderr)
            time.sleep(2)
    return []


def summarize(name, setlists):
    target = norm(name)
    shows = []
    artist_url = ""
    for sl in setlists:
        art = sl.get("artist") or {}
        if norm(art.get("name", "")) != target:
            continue
        artist_url = artist_url or art.get("url", "")
        songs = []
        for st in (sl.get("sets") or {}).get("set", []):
            for s in st.get("song", []):
                t = (s.get("name") or "").strip()
                if t and not s.get("tape"):
                    songs.append(t)
        if songs:
            shows.append({"date": sl.get("eventDate", ""), "songs": songs})
        if len(shows) >= MAX_SHOWS:
            break
    if not shows:
        return {"groupe": name, "n": 0, "url": artist_url, "updated": date.today().isoformat()}
    counts = {}
    for sh in shows:
        for t in set(sh["songs"]):
            counts[t] = counts.get(t, 0) + 1
    n = len(shows)
    songs = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "groupe": name, "n": n, "url": artist_url, "updated": date.today().isoformat(),
        "avg": round(sum(len(sh["songs"]) for sh in shows) / n, 1),
        "derniere": shows[0]["date"],
        "songs": [{"t": t, "pct": round(100 * c / n)} for t, c in songs if c / n >= 0.2][:30],
    }


def main():
    if not KEY:
        print("SETLISTFM_API_KEY absent : aucune setlist récupérée.")
        return
    concerts = load_json(CONCERTS_FILE, {}).get("items", [])
    cache = {s["groupe"]: s for s in load_json(OUT_FILE, {}).get("items", [])}
    groups = []
    for ev in concerts:
        g = ev.get("groupe", "")
        if g and g not in groups:
            groups.append(g)
    cutoff = (date.today() - timedelta(days=TTL_DAYS)).isoformat()
    todo = [g for g in groups if cache.get(g, {}).get("updated", "") < cutoff]
    print(f"{len(groups)} groupe(s) en concert, {len(todo)} à (re)calculer")
    done = 0
    for g in todo[:MAX_PER_RUN]:
        res = fetch_setlists(g)
        if res is None:
            print("  ! setlist.fm refuse la clé (403)", file=sys.stderr)
            break
        cache[g] = summarize(g, res)
        done += 1
        print(f"  {g}: {cache[g].get('n', 0)} concert(s) analysés")
        time.sleep(0.6)
    items = [cache[g] for g in groups if g in cache] + [v for k, v in cache.items() if k not in groups and v.get("updated", "") >= cutoff]
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "items": items}, f, ensure_ascii=False, indent=0)
    print(f"OK : {done} groupe(s) mis à jour, {len(items)} au total")


if __name__ == "__main__":
    main()
