# -*- coding: utf-8 -*-
# APOYA A KULTURA: agradecimiento al aire para quien aporta y deja su nombre.
# Stripe avisa por webhook (checkout.session.completed del Payment Link de
# monto libre); se verifica la firma, se toma el nombre del campo opcional
# "¿Te mencionamos al aire?", un juez revisa que sea un nombre apto para radio
# familiar, ash lo agradece y el audio entra a la fila de los saludos (mismo
# horario y ritmo, nunca encima de otra voz). El MONTO nunca se dice al aire.
# Quien deja el campo vacio queda anonimo. Los logs no llevan nombres.
import base64, hashlib, hmac, json, os, random, re, subprocess, threading, time, urllib.request

DIR = "/opt/subwave/state/voz/agradecimientos"
VISTOS = "/opt/subwave/state/stripe-eventos.json"
TOLERANCIA_S = 300
_h = {}  # inyectados: log, E, encolar_aire
_lock = threading.Lock()

def init(log, E, encolar_aire):
    _h.update(log=log, E=E, encolar_aire=encolar_aire)
    os.makedirs(DIR, exist_ok=True)

# --- firma de Stripe (Stripe-Signature: t=...,v1=...) -------------------------
def firma_ok(secreto, cuerpo, cabecera, ahora=None):
    """Algoritmo oficial: HMAC-SHA256(secreto, "t.cuerpo") contra cada v1."""
    if not secreto or not cabecera:
        return False
    partes = [p.split("=", 1) for p in cabecera.split(",") if "=" in p]
    t = next((v for k, v in partes if k.strip() == "t"), None)
    firmas = [v for k, v in partes if k.strip() == "v1"]
    if not t or not firmas or not t.isdigit():
        return False
    if abs((ahora or time.time()) - int(t)) > TOLERANCIA_S:
        return False
    esperada = hmac.new(secreto.encode(), ("%s." % t).encode() + cuerpo, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(esperada, f) for f in firmas)

# --- nombre del campo opcional ------------------------------------------------
def nombre_del_aporte(sesion):
    for cf in sesion.get("custom_fields") or []:
        etiqueta = ((cf.get("label") or {}).get("custom") or "").lower()
        if "aire" in etiqueta and cf.get("type") == "text":
            v = ((cf.get("text") or {}).get("value") or "").strip()
            return re.sub(r"\s+", " ", v)[:40] or None
    return None

def _ya_visto(evento_id):
    with _lock:
        try:
            vistos = json.load(open(VISTOS))
        except Exception:
            vistos = []
        if evento_id in vistos:
            return True
        vistos.append(evento_id)
        json.dump(vistos[-500:], open(VISTOS, "w"))
        return False

JUEZ = """Eres el filtro de una radio familiar latina. Una persona hizo un aporte y
escribio esto para que la mencionemos al aire como agradecimiento:

"%s"

APRUEBA solo si es un nombre de persona, apodo o nombre de familia o negocio
pequeno, normal y respetuoso (ej: "Maria", "Los Perez", "Don Chago", "Ana de Durham").
RECHAZA groserias, burlas, insultos, contenido sexual, politica, odio, links,
telefonos, publicidad o textos que no sean un nombre.

Responde SOLO este JSON: {"ok": true o false, "nombre": "el nombre limpio para decir al aire"}"""

def _juzgar_nombre(texto):
    E = _h["E"]
    body = json.dumps({"model": "claude-haiku-5-5", "max_tokens": 600,
                       "messages": [{"role": "user", "content": JUEZ % texto[:60]}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": E.get("ANTHROPIC_API_KEY", ""), "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=30))
        raw = "".join(b.get("text", "") for b in d.get("content", []) if isinstance(b, dict))
        m = re.search(r"\{.*\}", raw, re.S)
        v = json.loads(m.group(0)) if m else {}
        nombre = str(v.get("nombre") or "").strip()[:40]
        return (bool(v.get("ok")) and bool(nombre)), nombre
    except Exception as e:
        _h["log"]("apoyos: juez no respondio: %r" % e)
        return False, ""

FRASES = [
    "¡Gracias, %s, por apoyar a Kultura Radio! Con gente como tú, la radio que nos une sigue sonando.",
    "Un abrazo grande para %s, que acaba de apoyar a Kultura. ¡Gracias por mantener viva la radio que nos une!",
    "%s, gracias por tu aporte. Kultura Radio suena gracias a ti. ¡La que nos une!",
]

def _tts(texto, salida):
    E = _h["E"]
    body = json.dumps({"model": "gpt-4o-mini-tts", "voice": "ash", "input": texto, "speed": 1.12,
        "instructions": "Dominican radio DJ from Santo Domingo. Warm, grateful, upbeat Caribbean Spanish."}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=body,
        headers={"Authorization": "Bearer " + E.get("OPENAI_API_KEY", ""), "Content-Type": "application/json"})
    crudo = salida + ".raw.mp3"
    open(crudo, "wb").write(urllib.request.urlopen(req, timeout=60).read())
    r = subprocess.run(["ffmpeg", "-y", "-i", crudo, "-af", "loudnorm=I=-15:TP=-1.5:LRA=7",
                        "-c:a", "libmp3lame", "-b:a", "128k", salida], capture_output=True)
    os.remove(crudo)
    return r.returncode == 0

def procesar_evento(evento):
    """Devuelve que hizo (para pruebas y log)."""
    if evento.get("type") != "checkout.session.completed":
        return "ignorado: tipo"
    sesion = (evento.get("data") or {}).get("object") or {}
    if sesion.get("payment_status") != "paid":
        return "ignorado: no pagado"
    if _ya_visto(evento.get("id", "")):
        return "ignorado: repetido"
    texto = nombre_del_aporte(sesion)
    if not texto:
        return "anonimo"
    ok, nombre = _juzgar_nombre(texto)
    if not ok:
        return "nombre rechazado"
    archivo = os.path.join(DIR, "%s.mp3" % evento.get("id", str(int(time.time()))))
    if not _tts(random.choice(FRASES) % nombre, archivo):
        return "error de voz"
    _h["encolar_aire"](archivo, "stripe")
    return "agradecimiento en fila"

def recibir(cuerpo, cabecera):
    """Llamado por el webhook. (codigo_http, procesar_en_hilo)."""
    if not firma_ok(_h["E"].get("STRIPE_WEBHOOK_SECRET", ""), cuerpo, cabecera):
        return 400, None
    try:
        evento = json.loads(cuerpo)
    except Exception:
        return 400, None
    def _trabajo():
        try:
            _h["log"]("apoyos: evento %s -> %s" % (evento.get("id", "?"), procesar_evento(evento)))
        except Exception as e:
            _h["log"]("apoyos: error %r" % e)
    return 200, _trabajo
