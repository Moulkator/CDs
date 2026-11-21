#!/usr/bin/env python3
"""
Copie locale des pochettes (miniatures 250 px) pour qu'elles s'affichent toujours.

- Source : uniquement les pochettes enregistrées dans les données (collection, liste de
  souhaits, sorties). Jamais les pochettes de remplacement devinées par le site.
- Contrôle qualité : on refuse les images illisibles, trop petites (< 120 px) ou
  quasi unies (toutes noires, grises… = « pas d'image » chez Deezer).
- La correspondance adresse d'origine -> fichier local est dans data/pochettes-map.json.
  Si une pochette est corrigée (nouvelle adresse), la nouvelle est copiée et l'ancienne
  miniature n'est plus utilisée (elle est supprimée au passage suivant).
- Au plus MAX_PER_RUN nouvelles copies par passage (le reste au passage suivant).
"""
import hashlib
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image, ImageStat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
THUMBS = os.path.join(DATA, "pochettes", "mini")
MAP_FILE = os.path.join(DATA, "pochettes-map.json")
SIZE = 250
MAX_PER_RUN = int(os.environ.get("MAX_COVERS", "500"))
RETRY_REJECTED_DAYS = 14  # une image refusée ou injoignable est retentée après 2 semaines

session = requests.Session()
session.headers["User-Agent"] = "La-Moulkotheque-Pochettes/1.0 (site personnel)"


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def wanted_urls():
    urls = []
    for name in ("collection.json", "wishlist.json"):
        for r in load_json(os.path.join(DATA, name), []):
            urls.append(r.get("pochette") or "")
    for it in load_json(os.path.join(DATA, "sorties.json"), {}).get("items", []):
        urls.append(it.get("pochette") or "")
    seen, out = set(), []
    for u in urls:
        if u.startswith("http") and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def fname(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".jpg"


def check_and_resize(raw):
    """Renvoie (octets jpeg, None) ou (None, raison du refus)."""
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception:
        return None, "illisible"
    if min(im.size) < 120:
        return None, f"trop petite ({im.size[0]}x{im.size[1]})"
    im = im.convert("RGB")
    stat = ImageStat.Stat(im.convert("L"))
    if stat.stddev[0] < 6:
        return None, "image unie (pas de vraie pochette)"
    im.thumbnail((SIZE, SIZE), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80, optimize=True, progressive=True)
    return buf.getvalue(), None


def fetch(url):
    for attempt in range(2):
        try:
            r = session.get(url, timeout=25, allow_redirects=True)
            if r.status_code == 200 and r.content:
                return r.content, None
            if r.status_code in (404, 410):
                return None, f"HTTP {r.status_code}"
        except requests.RequestException as e:
            err = type(e).__name__
            if attempt:
                return None, err
        time.sleep(2)
    return None, "injoignable"


def work(url):
    raw, err = fetch(url)
    if err:
        return url, None, err
    data, why = check_and_resize(raw)
    if why:
        return url, None, why
    name = fname(url)
    with open(os.path.join(THUMBS, name), "wb") as f:
        f.write(data)
    return url, "data/pochettes/mini/" + name, None


def main():
    os.makedirs(THUMBS, exist_ok=True)
    old = load_json(MAP_FILE, {})
    mapping = old.get("ok", {})
    rejected = old.get("refus", {})
    urls = wanted_urls()
    wanted = set(urls)
    now = time.time()

    todo = []
    for u in urls:
        if u in mapping and os.path.exists(os.path.join(ROOT, mapping[u])):
            continue
        r = rejected.get(u)
        if r and now - r.get("t", 0) < RETRY_REJECTED_DAYS * 86400:
            continue
        todo.append(u)
    print(f"{len(urls)} pochettes dans les données, {len(mapping)} déjà copiées, {len(todo)} à copier (max {MAX_PER_RUN} ce passage)")
    todo = todo[:MAX_PER_RUN]

    done = refused = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for url, local, err in pool.map(work, todo):
            if local:
                mapping[url] = local
                rejected.pop(url, None)
                done += 1
            else:
                rejected[url] = {"raison": err, "t": int(now)}
                refused += 1

    # ménage : pochettes qui ne sont plus utilisées (corrigées ou supprimées)
    for u in list(mapping):
        if u not in wanted:
            path = os.path.join(ROOT, mapping.pop(u))
            if os.path.exists(path):
                os.remove(path)
    for u in list(rejected):
        if u not in wanted:
            rejected.pop(u)

    out = {"maj": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "ok": mapping, "refus": rejected}
    with open(MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0, sort_keys=True)
    print(f"OK : {done} copiées, {refused} refusées ou injoignables ; total {len(mapping)} miniatures locales")
    for u, r in list(rejected.items())[:15]:
        print(f"  refus : {r['raison']} — {u}")


if __name__ == "__main__":
    sys.exit(main())
