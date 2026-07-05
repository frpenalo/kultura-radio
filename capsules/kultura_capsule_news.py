#!/usr/bin/env python3
# "Minuto Kultura Noticias" — cápsula de noticias corta para Kultura Radio.
# Lee RSS en español (Diario Libre RD + La Opinión EEUU), Claude resume/parafrasea
# 3-4 titulares en español caribeño (voz del DJ), y la airea via /dj/say (duck).
# Gate de oyentes: si no hay nadie, no genera (no gasta). Corre por cron.
import json, urllib.request, sys, base64, re, html
from kultura_pron import spanishify

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
FEEDS = [
    ("Caribe/RD", "https://www.diariolibre.com/rss/portada.xml"),
    ("Comunidad EEUU", "https://laopinion.com/feed/"),
    ("Local NC/Triangle", "https://enlacelatinonc.org/feed/"),  # solo contenido; NO nombrar la fuente hasta tener autorizacion
]

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

def headlines():
    out = []
    for label, url in FEEDS:
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
                    if n >= 4:
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
            print("sin oyentes (%s) — omito cápsula" % n)
            return
    hl = headlines()
    if not hl:
        print("sin titulares")
        return
    lines = "\n".join("- [%s] %s" % (s, t) for s, t in hl)
    prompt = (
        "Eres el locutor de Kultura Radio, emisora latina del Triangle (Raleigh, NC). "
        "Hablas en espanol caribeno dominicano, de TU (jamas vos ni voseo). "
        "Escribe una capsula de noticias CORTA para radio, MAXIMO 430 caracteres "
        "(es para texto-a-voz, se leera en voz alta). Empieza EXACTO con 'Minuto Kultura Noticias.' "
        "y cierra con algo breve como 'Seguimos contigo en Kultura Radio.'. "
        "Resume con TUS PALABRAS 3 o 4 de estos titulares (NO los copies textual), mezclando "
        "algo del Caribe, algo de la comunidad latina en EE.UU., algo de actualidad y, si hay, "
        "algo LOCAL de Carolina del Norte o el Triangle (priorizalo, es lo que mas le importa al "
        "oyente). IMPORTANTE: NO menciones el nombre de ningun medio ni fuente, solo cuenta el hecho. "
        "Solo palabras pronunciables: nada de simbolos, URLs, siglas raras ni numeros con signos "
        "(escribe las cifras en palabras). "
        "Si mencionas palabras, siglas o nombres en INGLES (la migra ICE, lugares de EE.UU. como "
        "Raleigh), escribelos FONETICAMENTE para una voz en espanol, para que suenen como en ingles: "
        "ICE='Ais' (nunca 'i-ce-e'), Raleigh='Rali', North Carolina='Nort Carolaina', break='breik'. "
        "Tono calido y agil.\n\nTitulares:\n" + lines)
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
