#!/usr/bin/env python3
"""
Récupère les concerts annoncés des groupes de data/collection.json, data/wishlist.json,
des groupes « à écouter », souhaits et découvertes de data/mes-badges.json,
et écrit data/concerts.json. Lancé par le workflow après update_sorties.py.

Sources (au moins une doit être configurée dans les secrets GitHub du dépôt) :
  - TICKETMASTER_API_KEY : clé gratuite (developer.ticketmaster.com, « Consumer Key »).
    5 000 requêtes/jour : largement assez pour ~500 groupes une fois par jour.
  - BANDSINTOWN_APP_ID   : identifiant d'application APPROUVÉ par Bandsintown.
    Sans identifiant approuvé, Bandsintown ne renvoie plus rien (c'est ce qui donnait
    0 concert jusqu'ici).

Les deux sources sont fusionnées (un même concert n'apparaît qu'une fois).
Si la dernière collecte date de moins de 20 h, le script ne refait rien (le workflow
tourne deux fois par jour).
"""
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT_FILE = os.path.join(DATA, "concerts.json")
BIT_APP = os.environ.get("BANDSINTOWN_APP_ID", "").strip()
TM_KEY = os.environ.get("TICKETMASTER_API_KEY", "").strip()
BIT_API = "https://rest.bandsintown.com/artists/{name}/events?app_id={app}&date=upcoming"
TM_API = "https://app.ticketmaster.com/discovery/v2/events.json"
MIN_HOURS_BETWEEN_RUNS = 20

session = requests.Session()
session.headers["User-Agent"] = "La-Moulkotheque-Concerts/2.0 (site personnel)"


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
    masques = {norm(x) for x in badges.get("masques", [])}
    for name in badges.get("decouvertes", []):
        if norm(name) not in masques:
            add(name, "decouverte")
    return out


STATS = {"bandsintown": {"ok": 0, "vide": 0, "refus": 0, "erreur": 0},
         "ticketmaster": {"ok": 0, "vide": 0, "refus": 0, "erreur": 0}}


def get(url, params=None, src=""):
    for _ in range(3):
        try:
            r = session.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            print(f"  ! {src}: {e}", file=sys.stderr)
            time.sleep(2)
            continue
        if r.status_code == 429:
            time.sleep(5)
            continue
        return r
    return None


# ---------------------------------------------------------------- Bandsintown
def fetch_bit(a):
    r = get(BIT_API.format(name=quote(a["search"], safe=""), app=quote(BIT_APP)), src="bandsintown")
    st = STATS["bandsintown"]
    if r is None:
        st["erreur"] += 1
        return []
    if r.status_code in (401, 403):
        st["refus"] += 1
        return None
    if r.status_code == 404:
        st["vide"] += 1
        return []
    try:
        js = r.json()
    except ValueError:
        st["erreur"] += 1
        return []
    if not isinstance(js, list):
        st["refus" if "auth" in json.dumps(js).lower() else "erreur"] += 1
        return []
    st["ok" if js else "vide"] += 1
    out = []
    for ev in js:
        v = ev.get("venue") or {}
        try:
            lat, lng = float(v.get("latitude")), float(v.get("longitude"))
        except (TypeError, ValueError):
            lat = lng = None
        out.append({
            "date": (ev.get("datetime") or "")[:16], "titre": ev.get("title") or "",
            "salle": v.get("name") or "", "ville": v.get("city") or "", "region": v.get("region") or "",
            "pays": v.get("country") or "", "lat": lat, "lng": lng,
            "lineup": [x for x in (ev.get("lineup") or []) if norm(x) != norm(a["groupe"])][:6],
            "url": ev.get("url") or "",
            "festival": bool(ev.get("festival_datetime_display_start")) or "festival" in (ev.get("title") or "").lower(),
            "src": "bandsintown",
        })
    return out


# --------------------------------------------------------------- Ticketmaster
COUNTRY_FR = {"FR": "France", "BE": "Belgique", "CH": "Suisse", "DE": "Allemagne", "ES": "Espagne", "IT": "Italie",
              "NL": "Pays-Bas", "GB": "Royaume-Uni", "IE": "Irlande", "PT": "Portugal", "AT": "Autriche", "LU": "Luxembourg",
              "DK": "Danemark", "SE": "Suède", "NO": "Norvège", "FI": "Finlande", "PL": "Pologne", "CZ": "Tchéquie"}


def fetch_tm(a):
    params = {"apikey": TM_KEY, "keyword": a["search"], "classificationName": "music",
              "size": 100, "sort": "date,asc", "locale": "*"}
    r = get(TM_API, params=params, src="ticketmaster")
    st = STATS["ticketmaster"]
    if r is None:
        st["erreur"] += 1
        return []
    if r.status_code in (401, 403):
        st["refus"] += 1
        return None
    try:
        js = r.json()
    except ValueError:
        st["erreur"] += 1
        return []
    evs = ((js.get("_embedded") or {}).get("events")) or []
    target = norm(a["search"])
    out = []
    for ev in evs:
        emb = ev.get("_embedded") or {}
        names = [x.get("name") or "" for x in emb.get("attractions") or []]
        # Ticketmaster cherche par mot-clé : on ne garde que les dates où le groupe est vraiment à l'affiche
        if not any(norm(n) == target for n in names):
            continue
        if (ev.get("dates") or {}).get("status", {}).get("code") in ("cancelled", "canceled"):
            continue
        start = (ev.get("dates") or {}).get("start") or {}
        d = start.get("localDate") or ""
        if not d:
            continue
        t = (start.get("localTime") or "")[:5]
        v = (emb.get("venues") or [{}])[0]
        loc = v.get("location") or {}
        try:
            lat, lng = float(loc.get("latitude")), float(loc.get("longitude"))
        except (TypeError, ValueError):
            lat = lng = None
        cc = ((v.get("country") or {}).get("countryCode") or "")
        title = ev.get("name") or ""
        out.append({
            "date": d + ("T" + t if t else ""), "titre": title,
            "salle": v.get("name") or "", "ville": (v.get("city") or {}).get("name") or "",
            "region": (v.get("state") or {}).get("name") or "", "pays": COUNTRY_FR.get(cc, (v.get("country") or {}).get("name") or cc),
            "lat": lat, "lng": lng,
            "lineup": [n for n in names if norm(n) != target][:6],
            "url": ev.get("url") or "",
            "festival": "festival" in title.lower() or " fest" in title.lower(),
            "src": "ticketmaster",
        })
    st["ok" if out else "vide"] += 1
    return out


def main():
    prev = load_json(OUT_FILE, {})
    if prev.get("generated") and prev.get("items") and os.environ.get("FORCE_CONCERTS") != "1":
        try:
            age = datetime.now(timezone.utc) - datetime.strptime(prev["generated"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if age < timedelta(hours=MIN_HOURS_BETWEEN_RUNS):
                print(f"Concerts collectés il y a {age}, rien à faire.")
                return
        except ValueError:
            pass

    arts = artists()
    sources = (["ticketmaster"] if TM_KEY else []) + (["bandsintown"] if BIT_APP else [])
    print(f"{len(arts)} groupe(s) ; sources actives : {', '.join(sources) or 'AUCUNE'}")
    if not sources:
        print("  ! Aucune source configurée : ajoute le secret TICKETMASTER_API_KEY (voir l'en-tête du script).", file=sys.stderr)

    events, seen = [], set()
    bit_on, tm_on = bool(BIT_APP), bool(TM_KEY)
    for i, a in enumerate(arts, 1):
        found = []
        if tm_on:
            res = fetch_tm(a)
            if res is None and STATS["ticketmaster"]["refus"] >= 3 and STATS["ticketmaster"]["ok"] + STATS["ticketmaster"]["vide"] == 0:
                print("  ! Ticketmaster refuse la clé : vérifie le secret TICKETMASTER_API_KEY", file=sys.stderr)
                tm_on = False
            found += res or []
            time.sleep(0.22)  # limite Ticketmaster : 5 requêtes/seconde
        if bit_on:
            res = fetch_bit(a)
            if res is None and STATS["bandsintown"]["refus"] >= 5 and STATS["bandsintown"]["ok"] + STATS["bandsintown"]["vide"] == 0:
                print("  ! Bandsintown refuse l'identifiant : il doit être approuvé par Bandsintown", file=sys.stderr)
                bit_on = False
            found += res or []
            time.sleep(0.25)
        for ev in found:
            k = (norm(a["groupe"]), ev["date"][:10], norm(ev["ville"]))
            if k in seen:
                continue
            seen.add(k)
            ev.update({"groupe": a["groupe"], "sources": a["sources"]})
            if "decouverte" in a["sources"] and len(a["sources"]) == 1:
                ev["decouverte"] = True
            events.append(ev)
        if i % 50 == 0:
            print(f"[{i}/{len(arts)}] {len(events)} concert(s)")

    events.sort(key=lambda e: (e["date"], norm(e["groupe"])))
    diag = ""
    if not sources:
        diag = "aucune_source"
    elif STATS["ticketmaster"]["refus"] and not tm_on and not bit_on:
        diag = "cle_refusee"
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "sources": sources, "diagnostic": diag, "stats": STATS,
           "app_id_refuse": bool(BIT_APP) and not bit_on,
           "artistes": len(arts), "items": events}
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
    for s in sources:
        st = STATS[s]
        print(f"{s} : {st['ok']} groupe(s) avec concerts, {st['vide']} sans, {st['refus']} refus, {st['erreur']} erreurs")
    print(f"OK : {len(events)} concert(s) pour {len(arts)} groupe(s)")


if __name__ == "__main__":
    main()
