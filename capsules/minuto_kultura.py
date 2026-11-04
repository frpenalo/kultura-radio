#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# EL MINUTO KULTURA (ampliado) — noticiero de 3-4 minutos para Kultura Radio.
# Corre por timer cada 10 min; produce y saca al aire una edicion cuando toca
# (7:50am / 12:50pm / 5:50pm ET). Flujo: RSS Enlace Latino -> guion (Claude,
# reglas editoriales: Triangle primero, fuente citada, sin editorializar) ->
# TTS OpenAI onyx por parrafos -> concat + loudnorm -> say.txt (ducking).
#
# Uso: minuto_kultura.py            (modo timer: solo si toca una edicion)
#      minuto_kultura.py --ahora    (produce y saca una edicion YA, para probar)
import json, os, re, subprocess, sys, time, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from xml.etree import ElementTree

STATE = "/opt/subwave/state"
DIR = STATE + "/minuto"                  # /var/sub-wave/minuto en los contenedores
SAY = STATE + "/say.txt"
SEEN = DIR + "/vistas.json"              # noticias ya leidas al aire
MARCA = DIR + "/ultima_edicion.txt"      # "YYYY-MM-DD HH" de la ultima edicion
FEED = "https://enlacelatinonc.org/feed/"
FEED_TECH = "https://www.xataka.com/feedburner.xml"
EDICIONES = (7, 12, 17)                  # horas ET; ventana :50-:59
VOICE_INSTRUCTIONS = ("Dominican bilingual radio news presenter from Santo Domingo. "
                      "Warm, clear, engaging Caribbean Spanish, steady news pace. "
                      "Pronounce English place names like Raleigh, Durham, Cary and "
                      "Triangle naturally in English.")

E = dict(l.strip().split("=", 1) for l in open("/opt/subwave/.env")
         if l.strip() and not l.startswith("#") and "=" in l)

def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S ") + msg, flush=True)

def ahora_et():
    return datetime.now(ZoneInfo("America/New_York"))

def toca_edicion(dt):
    if dt.hour in EDICIONES and dt.minute >= 50:
        marca = dt.strftime("%Y-%m-%d ") + str(dt.hour)
        try:
            if open(MARCA).read().strip() == marca:
                return None
        except FileNotFoundError:
            pass
        return marca
    return None

def sane(s):
    s = re.sub(r"<[^>]+>", " ", str(s or ""))
    s = s.replace("&amp;", "&").replace("&quot;", '"').replace("&#8217;", "'")
    s = s.replace("&#8220;", '"').replace("&#8221;", '"').replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", s).strip()

def _items_feed(url, vistas, n, maxdet=400):
    req = urllib.request.Request(url, headers={"User-Agent": "KulturaRadio/1.0"})
    xml = urllib.request.urlopen(req, timeout=20).read()
    root = ElementTree.fromstring(xml)
    items = []
    for it in root.iter("item"):
        t = sane(it.findtext("title"))
        d = sane(it.findtext("description"))[:maxdet]
        if not t or t in vistas:
            continue
        items.append({"titulo": t, "detalle": d})
        if len(items) >= n:
            break
    return items

def noticias_frescas(n=2):
    try:
        vistas = set(json.load(open(SEEN)))
    except Exception:
        vistas = set()
    items = _items_feed(FEED, vistas, n)
    # Una nota de tecnologia fresca (Xataka) para la mencion de cierre; si el
    # feed falla, el Minuto sale igual sin tech.
    tech = []
    try:
        tech = _items_feed(FEED_TECH, vistas, 1, maxdet=250)
    except Exception:
        pass
    return items, tech, vistas

def clima():
    try:
        d = json.load(urllib.request.urlopen(
            "https://api.open-meteo.com/v1/forecast?latitude=35.78&longitude=-78.64"
            "&current=temperature_2m,weather_code&temperature_unit=fahrenheit", timeout=10))
        return round(d["current"]["temperature_2m"])
    except Exception:
        return None

def escribir_guion(items, tech, temp, dt):
    franja = "Buenos días" if dt.hour < 12 else ("Buenas tardes" if dt.hour < 19 else "Buenas noches")
    notas = "\n".join("- %s: %s" % (i["titulo"], i["detalle"]) for i in items)
    temp_linea = ("La temperatura actual en Raleigh es de %d grados Fahrenheit." % temp) if temp else ""
    prompt = (
        "Escribe el guion de EL MINUTO KULTURA, la pausa informativa BREVE de Kultura "
        "Radio, emisora de musica tropical para la comunidad latina del Triangle "
        "(Raleigh, Durham, Cary, Chapel Hill, North Carolina).\n\n"
        "NOTICIAS DISPONIBLES (fuente: Enlace Latino NC):\n" + notas + "\n\n"
        "NOTICIA DE TECNOLOGIA (fuente: Xataka): " + (("- %s: %s" % (tech[0]["titulo"], tech[0]["detalle"])) if tech else "no hay, omitela") + "\n"
        "DATO DEL CLIMA: " + (temp_linea or "no disponible, omitelo") + "\n"
        "HORA LOCAL: " + dt.strftime("%H:%M") + " (saludo: " + franja + ")\n\n"
        "REGLAS DURAS:\n"
        "- Es UN MINUTO de radio entre canciones: entre 150 y 190 palabras TOTALES. "
        "Ni una mas: la musica es la protagonista y esto es una pausa, no un programa.\n"
        "- Desarrolla UNA sola noticia, la primera de la lista: que se entienda el "
        "contexto y por que le importa a la comunidad latina del Triangle (eso es "
        "ampliar el tema: profundidad, no duracion).\n"
        "- Si hay segunda noticia, menciona su titular en UNA frase al final (\'y "
        "ademas...\'); si no, omitela.\n"
        "- Cita la fuente UNA vez de forma natural (\'segun reporta Enlace Latino\').\n"
        "- CERO opinion, CERO editorializar, CERO alarmismo.\n"
        "- Espanol latino neutro con calidez caribena; de tu, nunca vos.\n"
        "- Palabras en ingles con su ortografia real (Raleigh, Durham, Triangle); "
        "la voz es bilingue. Tildes correctas SIEMPRE.\n"
        "- Si hay noticia de tecnologia, UNA sola frase antes del clima (\'Y en "
        "tecnologia...\'); sin detalles tecnicos pesados, que se entienda de oido.\n"
        "- Clima: solo si hay dato, en media frase del cierre.\n"
        "- Abre con: \'Este es El Minuto Kultura.\' y cierra con: \'Kultura Radio, la "
        "que nos une.\' (el cierre largo con la pagina web NO va: esto es rapido).\n"
        "- Devuelve SOLO el guion hablado, sin titulos ni notas. Parrafos con linea "
        "en blanco entre si.\n")
    body = json.dumps({"model": "claude-sonnet-5-5", "max_tokens": 6000,
                       "thinking": {"type": "between_tools"},
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": E["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=120))
    texto = "".join(b.get("text", "") for b in d.get("content", [])).strip()
    if len(texto.split()) < 90:
        raise RuntimeError("guion corto; stop=%s tipos=%s texto=%r" % (d.get("stop_reason"), [b.get("type") for b in d.get("content", [])], texto[:80]))
    return texto

def tts_parrafo(texto, out):
    body = json.dumps({"model": "gpt-4o-mini-tts", "voice": "onyx", "input": texto,
                       "speed": 1.15, "instructions": VOICE_INSTRUCTIONS}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=body,
        headers={"Authorization": "Bearer " + E["OPENAI_API_KEY"],
                 "Content-Type": "application/json"})
    open(out, "wb").write(urllib.request.urlopen(req, timeout=120).read())

def producir(guion):
    os.makedirs(DIR, exist_ok=True)
    # TTS por bloques (el API limita el largo por llamada) y concat sin cortes
    bloques, actual = [], ""
    for p in [p.strip() for p in guion.split("\n\n") if p.strip()]:
        if len(actual) + len(p) > 1800 and actual:
            bloques.append(actual)
            actual = p
        else:
            actual = (actual + "\n\n" + p).strip()
    if actual:
        bloques.append(actual)
    partes = []
    for i, b in enumerate(bloques):
        f = "%s/parte%d.mp3" % (DIR, i)
        tts_parrafo(b, f)
        partes.append(f)
    lista = DIR + "/partes.txt"
    open(lista, "w").write("\n".join("file '%s'" % p for p in partes))
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lista,
                    "-af", "loudnorm=I=-15:TP=-1.5:LRA=7",
                    "-c:a", "libmp3lame", "-b:a", "128k", DIR + "/minuto-actual.mp3"],
                   capture_output=True, check=True)
    for p in partes:
        os.remove(p)
    os.remove(lista)
    dur = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                          "-of", "csv=p=0", DIR + "/minuto-actual.mp3"],
                         capture_output=True, text=True).stdout.strip()
    return float(dur)

def autolink(on):
    """Apaga/enciende los links automaticos del DJ (para que ash no hable
    encima del Minuto). Mejor-esfuerzo: si falla, el Minuto sale igual."""
    try:
        snippet = (
            "const a=Buffer.from(process.env.U+\":\"+process.env.P).toString(\"base64\");"
            "fetch(\"http://localhost:7701/dj/auto-link\",{method:\"POST\","
            "headers:{\"Content-Type\":\"application/json\",\"Authorization\":\"Basic \"+a},"
            "body:JSON.stringify({on:%s})}).then(r=>r.json()).then(d=>console.log(JSON.stringify(d)));"
            % ("true" if on else "false"))
        subprocess.run(["docker", "exec", "-e", "U=" + E.get("ADMIN_USER", ""),
                        "-e", "P=" + E.get("ADMIN_PASS", ""), "sub-wave-controller",
                        "node", "-e", snippet], capture_output=True, timeout=20)
    except Exception as e:
        log("autolink(%s) fallo: %r" % (on, e))

def al_aire():
    for _ in range(120):
        if not os.path.exists(SAY):
            open(SAY, "w").write("/var/sub-wave/minuto/minuto-actual.mp3")
            return True
        time.sleep(1)
    return False

def main():
    forzar = "--ahora" in sys.argv
    dt = ahora_et()
    marca = toca_edicion(dt) if not forzar else dt.strftime("%Y-%m-%d %H:%M-manual")
    if not marca:
        return
    os.makedirs(DIR, exist_ok=True)
    items, tech, vistas = noticias_frescas()
    if len(items) < 1:
        log("edicion saltada: sin noticias frescas")
        if not forzar:
            open(MARCA, "w").write(marca)   # no reintentar la misma hora
        return
    guion = escribir_guion(items, tech, clima(), dt)
    dur = producir(guion)
    open(DIR + "/ultimo-guion.txt", "w", encoding="utf-8").write(guion)
    vistas.update(i["titulo"] for i in items + tech)
    json.dump(sorted(vistas)[-120:], open(SEEN, "w"))
    open(MARCA, "w").write(marca)
    autolink(False)
    try:
        ok = al_aire()
        if ok:
            time.sleep(dur + 25)   # el DJ no mete links mientras dura el Minuto
    finally:
        autolink(True)
    log("edicion %s: %d noticias, %.0fs de audio, al aire=%s" % (marca, len(items), dur, ok))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("ERROR: %r" % e)
        sys.exit(1)
