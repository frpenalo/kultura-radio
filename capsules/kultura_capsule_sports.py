#!/usr/bin/env python3
# "Deportes Kultura" — capsula de resultados deportivos para Kultura Radio.
# Combina marcadores reales de MLB (statsapi, gratis) + Diario Libre Deportes RSS
# (angulo dominicano + Mundial). Claude lo arma en espanol caribeno (voz del DJ)
# y lo airea via /dj/say. Gate de oyentes: sin nadie, no genera (no gasta). Cron.
import json, urllib.request, sys, base64, re, html
from kultura_pron import spanishify
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/New_York")
except Exception:
    TZ = None

ENV = "/opt/subwave/.env"
def env(k):
    try:
        for line in open(ENV):
            if line.startswith(k + "="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""

KEY = env("ANTHROPIC_API_KEY")
ADMIN = "admin:" + env("ADMIN_PASS")
AUTH = "Basic " + base64.b64encode(ADMIN.encode()).decode()
BASE = "https://kulturaradio.com/api"
RSS = [("Deportes RD", "https://www.diariolibre.com/rss/deportes.xml")]

def fetch(url, auth=False, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    if auth:
        req.add_header("Authorization", AUTH)
    return urllib.request.urlopen(req, timeout=timeout)

def listeners():
    try:
        return json.load(fetch(BASE + "/listeners", auth=True)).get("current", 0) or 0
    except Exception:
        return None

def mlb_scores():
    now = datetime.now(TZ) if TZ else datetime.now()
    day = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    url = ("https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=%s"
           "&hydrate=linescore,team" % day)
    out = []
    try:
        d = json.load(fetch(url))
        for date in d.get("dates", []):
            for g in date.get("games", []):
                st = (g.get("status", {}) or {}).get("abstractGameState", "")
                if st != "Final":
                    continue
                t = g.get("teams", {})
                a, h = t.get("away", {}), t.get("home", {})
                an = a.get("team", {}).get("name", "")
                hn = h.get("team", {}).get("name", "")
                asc, hsc = a.get("score"), h.get("score")
                if an and hn and asc is not None and hsc is not None:
                    out.append("%s %s, %s %s" % (an, asc, hn, hsc))
    except Exception as e:
        print("mlb error", e)
    return out[:10]

def headlines():
    out = []
    for label, url in RSS:
        try:
            raw = fetch(url).read().decode("utf-8", "ignore")
            items = re.findall(r"<item[ >].*?</item>", raw, re.DOTALL | re.IGNORECASE)
            n = 0
            for it in items:
                m = re.search(r"<title>(.*?)</title>", it, re.DOTALL | re.IGNORECASE)
                if not m:
                    continue
                t = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", m.group(1), flags=re.DOTALL)
                t = html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
                if t:
                    out.append((label, t))
                    n += 1
                    if n >= 5:
                        break
        except Exception as e:
            print("feed error", label, e)
    return out

def claude(prompt):
    body = json.dumps({"model": "claude-haiku-4-5", "max_tokens": 400,
                       "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))["content"][0]["text"].strip()

def main():
    force = "--force" in sys.argv
    dry = "--dry" in sys.argv
    if not force:
        n = listeners()
        if not n:
            print("sin oyentes (%s) — omito capsula" % n)
            return
    scores = mlb_scores()
    hl = headlines()
    if not scores and not hl:
        print("sin datos deportivos")
        return
    ctx = ""
    if scores:
        ctx += "Resultados de las Grandes Ligas (anoche):\n" + "\n".join("- " + s for s in scores) + "\n\n"
    if hl:
        ctx += "Titulares deportivos:\n" + "\n".join("- %s" % t for _, t in hl) + "\n"
    prompt = (
        "Eres el locutor de Kultura Radio, emisora latina del Triangle (Raleigh, NC). "
        "Hablas en espanol caribeno dominicano, de TU (jamas vos ni voseo). "
        "Escribe una capsula deportiva CORTA para radio, MAXIMO 430 caracteres "
        "(es para texto-a-voz, se leera en voz alta). Empieza EXACTO con 'Deportes Kultura.' "
        "y cierra con algo breve como 'Asi se juega en Kultura Radio.'. "
        "Prioriza lo que le importa al fanatico dominicano y latino: peloteros dominicanos en "
        "las Grandes Ligas y el Mundial de futbol. Menciona 2 o 3 resultados o notas relevantes "
        "con TUS PALABRAS (no copies textual). "
        "Solo palabras pronunciables: nada de simbolos, URLs, siglas raras ni numeros con signos "
        "(escribe las cifras en palabras). "
        "Si mencionas palabras o nombres en INGLES (equipos, lugares de EE.UU., siglas como NBA, MLB), "
        "escribelos FONETICAMENTE para una voz en espanol para que suenen como en ingles "
        "(ej. Raleigh='Rali', NBA='ene-bi-ei', break='breik'). "
        "Tono calido, vibrante y deportivo.\n\n" + ctx)
    script = claude(prompt).strip().strip('"')
    script = spanishify(script)
    if len(script) > 490:
        cut = script[:490]
        script = cut[:cut.rfind(".") + 1] or cut
    print("=== CAPSULA (%d chars) ===" % len(script))
    print(script)
    if dry:
        return
    data = json.dumps({"text": script, "kind": "dj-speak", "mode": "raw"}).encode("utf-8")
    req = urllib.request.Request(BASE + "/dj/say", data=data,
        headers={"Content-Type": "application/json", "Authorization": AUTH})
    print("aireado:", json.load(urllib.request.urlopen(req, timeout=30)).get("ok"))

main()
