#!/usr/bin/env python3
# "Transito Kultura" — reporte de transito del Triangle para Kultura Radio.
# Fuente: DriveNC (NCDOT) API oficial gratis. Filtra Wake/Durham/Orange,
# prioriza accidentes + cierres totales + autopistas, Claude arma un reporte
# corto en espanol caribeno y lo airea via /dj/say. Gate de oyentes. Cron.
# Patrocinable: pon el nombre del anunciante en SPONSOR.
import json, urllib.request, sys, base64, re
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
DNC = env("DRIVENC_KEY")
ADMIN = "admin:" + env("ADMIN_PASS")
AUTH = "Basic " + base64.b64encode(ADMIN.encode()).decode()
BASE = "https://kulturaradio.com/api"
COUNTIES = {"Wake", "Durham", "Orange"}
SPONSOR = ""  # ej. "presentado por Seguros La Familia" — dejar "" si no hay patrocinador

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

def score(e):
    s = 0
    if e.get("EventType") == "accidentsAndIncidents":
        s += 100
    if e.get("IsFullClosure"):
        s += 40
    rn = e.get("RoadwayName") or ""
    if re.match(r"^(I-|US-|NC-|I\s?\d)", rn) or "Interstate" in rn:
        s += 30
    if (e.get("Severity") or "").lower() in ("major", "severe"):
        s += 25
    if e.get("MajorEvent"):
        s += 25
    return s

def events():
    if not DNC:
        print("falta DRIVENC_KEY en .env")
        return []
    url = "https://www.drivenc.gov/api/v2/get/event?key=%s&format=json" % DNC
    try:
        data = json.load(fetch(url))
        ev = data if isinstance(data, list) else (data.get("events") or [])
        ev = [e for e in ev if (e.get("County") in COUNTIES)]
        ev.sort(key=score, reverse=True)
        return ev
    except Exception as e:
        print("drivenc error", e)
        return []

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
    ev = events()
    top = ev[:10]
    lines = []
    for e in top:
        lines.append("- [%s] %s (%s): %s" % (
            e.get("County"), e.get("RoadwayName"), e.get("EventType"),
            (e.get("Description") or "").strip()[:160]))
    ctx = "\n".join(lines) if lines else "(sin incidentes reportados ahora mismo)"
    intro = "El tránsito de Kultura Radio" + ((" " + SPONSOR) if SPONSOR else "")
    prompt = (
        "Eres el locutor de Kultura Radio (emisora latina del Triangle, Raleigh NC). "
        "Espanol caribeno dominicano, de TU (jamas vos). Escribe un REPORTE DE TRANSITO CORTO "
        "para radio, MAXIMO 430 caracteres (texto-a-voz, se leera en voz alta). "
        "Empieza EXACTO con '" + intro + ".' y cierra con algo MUY breve SIN repetir el nombre de la "
        "emisora (ej. 'Maneja con cuidado.' o 'Cuídate en la vía.'); 'Kultura Radio' ya va en el "
        "saludo inicial, NO lo repitas al final. De la lista, menciona con TUS PALABRAS solo lo MAS relevante para quien "
        "maneja (2 a 4): prioriza accidentes, cierres totales y AUTOPISTAS. "
        "REGLA DE CALLES: el oyente necesita saber EN CUAL vía está el problema para evitarla, "
        "así que SIEMPRE di el nombre real de la calle o carretera afectada, con su zona (en "
        "Raleigh, en Durham, en el condado de Orange). Di los nombres de calles, ciudades y "
        "condados en INGLÉS tal como vienen (Apex Peakway, New Hope Church Road, Raleigh, Wake) — "
        "la voz es bilingüe y los pronuncia bien. Las autopistas dilas en español: I-40='la "
        "cuarenta', I-440='la cuatrocientos cuarenta', I-540='la quinientos cuarenta', US-1='la US "
        "uno', US-70='la US setenta'. Menciona los 2 a 4 incidentes más relevantes con su ubicación "
        "concreta. Si todo es obra menor o no hay nada, di que el tránsito está fluido. Escribe con "
        "tildes correctas en español (tránsito, área, dirección). Nada de símbolos ni siglas raras."
        "\n\nIncidentes:\n" + ctx)
    script = claude(prompt).strip().strip('"')
    # Voz ElevenLabs (Sandra) es bilingüe → dice inglés bien, NO foneticear.
    if len(script) > 490:
        cut = script[:490]
        script = cut[:cut.rfind(".") + 1] or cut
    print("=== TRANSITO (%d chars, %d eventos Triangle) ===" % (len(script), len(ev)))
    print(script)
    if dry:
        return
    data = json.dumps({"text": script, "kind": "capsule", "mode": "raw"}).encode("utf-8")
    req = urllib.request.Request(BASE + "/dj/say", data=data,
        headers={"Content-Type": "application/json", "Authorization": AUTH})
    print("aireado:", json.load(urllib.request.urlopen(req, timeout=30)).get("ok"))

main()
