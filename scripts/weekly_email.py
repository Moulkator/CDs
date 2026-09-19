#!/usr/bin/env python3
"""
Résumé hebdomadaire par e-mail (HTML, avec pochettes) :
  • sorties de la semaine, albums annoncés, mises à jour (depuis data/events-log.json)
  • albums ajoutés à la collection / à la liste de souhaits, retirés de la liste de souhaits
    (comparaison avec data/listes-prev.json, photo prise à chaque envoi)
  • à venir dans les 30 prochains jours

Variables d'environnement (secrets GitHub) :
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_TO   — obligatoires pour l'envoi
  MAIL_FROM (défaut : SMTP_USER), SITE_URL, DIGEST_DAYS (défaut 7)
Lancé par .github/workflows/weekly-digest.yml (dimanche) ou à la main.
"""
import json
import os
import re
import smtplib
import ssl
import sys
import unicodedata
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
LOG_FILE = os.path.join(DATA, "events-log.json")
SORTIES_FILE = os.path.join(DATA, "sorties.json")
COLL_FILE = os.path.join(DATA, "collection.json")
WISH_FILE = os.path.join(DATA, "wishlist.json")
SNAP_FILE = os.path.join(DATA, "listes-prev.json")
BADGES_FILE = os.path.join(DATA, "mes-badges.json")

SITE_URL = os.environ.get("SITE_URL", "https://moulkator.github.io/CDs/").rstrip("/") + "/"
DAYS = int(os.environ.get("DIGEST_DAYS", "7"))
TODAY = date.today()
SINCE = TODAY - timedelta(days=DAYS)
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
PH = SITE_URL + "assets/pochette-inconnue.png"


def norm(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def album_key(g, a):
    a = norm(a)
    a = re.sub(r"\b(deluxe|edition|bonus|remaster(ed)?|digipak|version)\b", "", a).strip()
    return norm(g) + "|" + a


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
    return "" if m <= 0 else (f"{m // 60} h {m % 60:02d}" if m >= 60 else f"{m} min")


def esc(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def cover_url(p):
    if not p:
        return ""
    return p if p.startswith("http") else SITE_URL + p.lstrip("/")


def artist_info(groupe, rows):
    out = {}
    for f in ("style", "pays", "langue"):
        cnt = {}
        for r in rows:
            if norm(r.get("groupe", "")) == norm(groupe) and (r.get(f) or "").strip():
                cnt[r[f].strip()] = cnt.get(r[f].strip(), 0) + 1
        if cnt:
            out[f] = max(cnt, key=cnt.get)
    return out


# ------------------------------------------------------------------ HTML

def card(it, rows, extra=""):
    g, a = it.get("groupe", ""), it.get("album", "")
    info = artist_info(g, rows)
    meta = [x for x in [
        fmt_date(it.get("date"), it.get("precision", "unknown")) if it.get("date") or it.get("precision") else (it.get("annee") or ""),
        "EP" if it.get("type") == "ep" else "",
        fmt_duree(it.get("duree")),
        it.get("style") or info.get("style", ""),
        it.get("pays") or info.get("pays", ""),
        it.get("langue") or info.get("langue", ""),
    ] if x]
    q = quote(f"{g} {a}")
    img = cover_url(it.get("pochette"))
    img_html = (f'<img src="{esc(img)}" width="96" height="96" style="width:96px;height:96px;object-fit:cover;border-radius:8px;display:block;background:#000">'
                if img else '<div style="width:96px;height:96px;border-radius:8px;background:#22242c;color:#6b6090;font-size:11px;text-align:center;line-height:96px">pas de pochette</div>')
    note = f'<div style="color:#9a93c4;font-size:12px;margin-top:4px">{esc(it.get("note"))}</div>' if it.get("note") else ""
    return f'''
<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;margin:0 0 12px;background:#15181e;border:1px solid #2a2f3a;border-radius:12px">
<tr><td style="padding:10px;width:96px;vertical-align:top">{img_html}</td>
<td style="padding:10px 10px 10px 0;vertical-align:top;font-family:Helvetica,Arial,sans-serif;color:#e8e4da">
<div style="color:#c9a227;font-weight:800;letter-spacing:1.4px;text-transform:uppercase;font-size:12px">{esc(g)}</div>
<div style="font-weight:700;font-size:16px;line-height:1.2;margin:2px 0 4px">{esc(a)}</div>
<div style="color:#9a93c4;font-size:12px">{esc(" · ".join(meta))}</div>{extra}{note}
<div style="margin-top:6px;font-size:12px"><a href="https://www.deezer.com/search/{q}" style="color:#79c6ff">Deezer</a> &nbsp;·&nbsp; <a href="https://bandcamp.com/search?q={q}" style="color:#79c6ff">Bandcamp</a> &nbsp;·&nbsp; <a href="https://www.metal-archives.com/search?searchString={quote(g)}&amp;type=band_name" style="color:#79c6ff">Metallum</a></div>
</td></tr></table>'''


def section(title, items_html, empty="Rien cette semaine."):
    body = "".join(items_html) if items_html else f'<div style="color:#9a93c4;font-family:Helvetica,Arial,sans-serif;font-size:13px;margin-bottom:12px">{empty}</div>'
    return f'<h2 style="font-family:Helvetica,Arial,sans-serif;color:#c9a227;font-size:15px;letter-spacing:1.5px;text-transform:uppercase;margin:22px 0 10px">{esc(title)}</h2>{body}'


def build_html(parts, period_txt):
    return f'''<!doctype html><html><body style="margin:0;padding:0;background:#0c0e11">
<div style="max-width:640px;margin:0 auto;padding:20px 14px 40px">
<h1 style="font-family:Helvetica,Arial,sans-serif;color:#e8e4da;font-size:22px;letter-spacing:2px;text-transform:uppercase;margin:0">Mes CD — <span style="color:#c9a227">résumé de la semaine</span></h1>
<div style="font-family:Helvetica,Arial,sans-serif;color:#9a93c4;font-size:13px;margin:4px 0 6px">{esc(period_txt)}</div>
{"".join(parts)}
<div style="font-family:Helvetica,Arial,sans-serif;color:#6b6090;font-size:12px;margin-top:26px"><a href="{SITE_URL}sorties.html#sorties" style="color:#79c6ff">Ouvrir le site</a> · envoyé automatiquement chaque dimanche</div>
</div></body></html>'''


# ------------------------------------------------------------------ main

def main():
    coll, wish = load_json(COLL_FILE, []), load_json(WISH_FILE, [])
    rows = coll + wish
    log = load_json(LOG_FILE, [])
    badges = load_json(BADGES_FILE, {})
    exclus = set(badges.get("sorties_exclues", []))
    ignores = set(badges.get("groupes_ignores", []))

    # 1. événements de la semaine (dédoublonnés : dernier état par album et par type)
    week = [e for e in log if e.get("jour", "") >= SINCE.isoformat()
            and album_key(e.get("groupe", ""), e.get("album", "")) not in exclus and norm(e.get("groupe", "")) not in ignores]
    by_kind = {"sorti": {}, "annonce": {}, "maj": {}}
    for e in week:
        by_kind.setdefault(e.get("kind", "maj"), {})[album_key(e["groupe"], e["album"])] = e
    sortis = sorted(by_kind["sorti"].values(), key=lambda e: e.get("date") or "")
    annonces = sorted(by_kind["annonce"].values(), key=lambda e: e.get("date") or "9999")
    majs = [e for k, e in by_kind["maj"].items() if k not in by_kind["annonce"] and k not in by_kind["sorti"]]

    # 2. changements dans tes listes depuis la dernière photo
    snap = load_json(SNAP_FILE, None)
    added_coll = added_wish = removed_wish = []
    if snap is not None:
        pc = {album_key(r.get("groupe", ""), r.get("album", "")) for r in snap.get("collection", [])}
        pw = {album_key(r.get("groupe", ""), r.get("album", "")): r for r in snap.get("wishlist", [])}
        cc = {album_key(r.get("groupe", ""), r.get("album", "")) for r in coll}
        cw = {album_key(r.get("groupe", ""), r.get("album", "")) for r in wish}
        added_coll = [r for r in coll if album_key(r.get("groupe", ""), r.get("album", "")) not in pc]
        added_wish = [r for r in wish if album_key(r.get("groupe", ""), r.get("album", "")) not in pw]
        removed_wish = [r for k, r in pw.items() if k not in cw]
    with open(SNAP_FILE, "w", encoding="utf-8") as f:
        json.dump({"date": TODAY.isoformat(), "collection": coll, "wishlist": wish}, f, ensure_ascii=False, indent=0)

    # 3. à venir sous 30 jours
    sorties = load_json(SORTIES_FILE, {}).get("items", [])
    upcoming = []
    for it in sorties:
        k = album_key(it["groupe"], it["album"])
        d = parse_date(it.get("date"))
        if k in exclus or norm(it["groupe"]) in ignores or not d:
            continue
        if TODAY < d <= TODAY + timedelta(days=30):
            upcoming.append(it)
    upcoming.sort(key=lambda i: i.get("date") or "")

    total = len(sortis) + len(annonces) + len(majs) + len(added_coll) + len(added_wish) + len(removed_wish)
    parts = [
        section("💿 Sortis cette semaine", [card(e, rows) for e in sortis]),
        section("🆕 Annoncés cette semaine", [card(e, rows) for e in annonces]),
        section("🔄 Mises à jour", [card(e, rows, extra=f'<div style="color:#79c6ff;font-size:12px;margin-top:4px">{esc(" · ".join(e.get("changes", [])).replace("**", ""))}</div>') for e in majs]),
        section("📀 Ajoutés à la collection", [card(r, rows) for r in added_coll], "Aucun ajout." if snap is not None else "Première semaine : photo de départ prise, les ajouts apparaîtront dimanche prochain."),
        section("🎁 Ajoutés à la liste de souhaits", [card(r, rows) for r in added_wish], "Aucun ajout."),
        section("✅ Retirés de la liste de souhaits", [card(r, rows) for r in removed_wish], "Aucun retrait."),
        section("📅 À venir dans les 30 jours", [card(i, rows) for i in upcoming], "Rien de programmé."),
    ]
    period = f"du {SINCE.day} {MOIS[SINCE.month - 1]} au {TODAY.day} {MOIS[TODAY.month - 1]} {TODAY.year} — {total} changement(s)"
    html = build_html(parts, period)
    text = f"Mes CD — résumé {period}\n" + "\n".join(
        f"- {t}: " + ", ".join(f"{i.get('groupe')} — {i.get('album')}" for i in lst)
        for t, lst in [("Sortis", sortis), ("Annoncés", annonces), ("Mis à jour", majs), ("Collection +", added_coll), ("Wishlist +", added_wish), ("Wishlist -", removed_wish), ("À venir", upcoming)] if lst
    ) + f"\n{SITE_URL}sorties.html"

    with open(os.path.join(DATA, "dernier-resume.html"), "w", encoding="utf-8") as f:
        f.write(html)

    host, user, pw, to = (os.environ.get(k, "").strip() for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "MAIL_TO"))
    port = int(os.environ.get("SMTP_PORT", "465") or 465)
    if not (host and user and pw and to):
        print("Secrets SMTP incomplets : aucun envoi. Aperçu écrit dans data/dernier-resume.html")
        print(text)
        return
    msg = EmailMessage()
    msg["Subject"] = f"Mes CD — résumé de la semaine ({total} changement{'s' if total > 1 else ''})"
    msg["From"] = os.environ.get("MAIL_FROM", "").strip() or user
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=60) as s:
                s.login(user, pw)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=60) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(user, pw)
                s.send_message(msg)
        print(f"E-mail envoyé à {to} ({total} changement(s)).")
    except Exception as e:
        print(f"! Échec de l'envoi : {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
