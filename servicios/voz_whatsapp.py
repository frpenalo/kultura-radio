# -*- coding: utf-8 -*-
# TU VOZ EN KULTURA — canal de participacion comunitaria por WhatsApp (Twilio).
# Lo importa dedi_service.py, que le inyecta sus helpers (transcribe, log, env)
# via init(). El bot responde con TwiML (sin credenciales para contestar; las
# credenciales TWILIO_SID/TWILIO_TOKEN solo hacen falta para DESCARGAR audios).
#
# Flujo: bienvenida con menu 1-4 -> categoria pegajosa por telefono (24h) ->
# audio: descargar -> mp3 -> transcribir -> juez LLM por categoria -> aprobado/
# rechazado (saludos aprobados quedan listos para el aire; historias y "lo que
# nos une" alimentan el pool de capsulas). Textos de sugerencias/contacto van
# a la bandeja. NADA espera aprobacion manual: el Curador (pestana Voces) es
# historial y pesca de joyas, no aduana.
import json, os, re, subprocess, time, urllib.request
from xml.sax.saxutils import escape

DIR = "/opt/subwave/state/voz"
ESTADOS = DIR + "/estados.json"
INDICE = DIR + "/indice.jsonl"
BANDEJA = DIR + "/bandeja.jsonl"
CATS = {"1": "lo-que-nos-une", "2": "saludos", "3": "sugerencias", "4": "contacto"}
DUR_MIN, DUR_MAX = 2.0, 90.0

_h = {}  # helpers inyectados: transcribe(fp), log(msg), E (env dict)
import threading
PROCESO_AUDIO = threading.BoundedSemaphore(2)   # audios procesandose a la vez (global)

def init(transcribe, log, E):
    _h.update(transcribe=transcribe, log=log, E=E)
    for c in CATS.values():
        for sub in ("aprobados", "rechazados"):
            os.makedirs(os.path.join(DIR, c, sub), exist_ok=True)

BIENVENIDA = (
    "¡Hola! \U0001F44B Bienvenido a Kultura Radio, la que nos une.\n"
    "Queremos escucharte. ¿Cómo deseas participar?\n\n"
    "1. ❤️ Lo que nos une\n"
    "2. \U0001F399️ Saludos e historias\n"
    "3. \U0001F4A1 Sugerencias\n"
    "4. \U0001F4AC Contacto general\n\n"
    "Responde con el número de tu opción.\n\n"
    "Al enviarnos un audio autorizas a Kultura Radio a reproducirlo, editarlo y "
    "difundirlo al aire. Si eres menor de edad, participa con un adulto.")

# Botones de la bienvenida (plantilla quick-reply KR_WA_MENU_SID): el toque
# llega con ButtonPayload = id. "Ideas y contacto" junta sugerencias y
# contacto, que por dentro ya iban igual (bandeja, sin juez ni aire).
BOTONES = {"cat_unir": "lo-que-nos-une", "cat_saludo": "saludos", "cat_ideas": "sugerencias"}

def _enviar_botones(desde, a):
    """Manda la bienvenida con botones por REST. False si no se pudo (el
    llamador cae al menu de texto)."""
    import base64, urllib.parse
    E = _h["E"]
    csid = E.get("KR_WA_MENU_SID", "")
    if not (csid and E.get("TWILIO_ACCOUNT") and desde and a):
        return False
    auth = base64.b64encode(("%s:%s" % (E["TWILIO_SID"], E["TWILIO_TOKEN"])).encode()).decode()
    data = urllib.parse.urlencode({"From": desde, "To": a, "ContentSid": csid}).encode()
    req = urllib.request.Request(
        "https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json" % E["TWILIO_ACCOUNT"],
        data=data, headers={"Authorization": "Basic " + auth})
    try:
        urllib.request.urlopen(req, timeout=15).read()
        return True
    except Exception as e:
        _h["log"]("voz botones error: %r" % e)
        return False

RESPUESTA_CAT = {
    "lo-que-nos-une": ("❤️ ¡Eso! Mandanos un AUDIO de 10 a 15 segundos "
        "respondiendo la pregunta de la semana o contando esa tradición, frase o "
        "sabor que te conecta con tu tierra."),
    "saludos": ("\U0001F399️ ¡Dale! Mandanos tu AUDIO con tu saludo o tu "
        "historia (10 a 30 segundos). Dinos tu nombre y de qué país eres."),
    "sugerencias": ("\U0001F4A1 Te leemos: escribe tu idea, sugerencia o lo que "
        "necesites de Kultura Radio (o mándalo en audio) y te respondemos pronto."),
    "contacto": ("\U0001F4AC Cuéntanos en qué te podemos ayudar y te "
        "respondemos pronto."),
}

JUEZ = """Eres el filtro de contenido de Kultura Radio, una emisora familiar latina. \
Un oyente mando por WhatsApp un audio de la categoria "%s" que podria sonar AL AIRE. \
Transcripcion:

\"%s\"

RECHAZA si contiene: groserias o vulgaridad (en cualquier idioma o disimulada), \
contenido sexual, violencia o amenazas, burlas o insultos a alguien, politica, odio \
o discriminacion, publicidad o promocion de negocios o redes, numeros de telefono o \
direcciones, o si no parece un aporte coherente (puede ser ruido mal transcrito).

APRUEBA si es un saludo, historia, anecdota, tradicion, frase tipica o respuesta \
cultural normal y de buena fe, aunque mencione nombres de pila o paises.

Responde SOLO este JSON, nada mas: {"ok": true o false, "motivo": "breve"}"""

def _estados():
    try:
        return json.load(open(ESTADOS))
    except Exception:
        return {}

def _guardar_estado(d):
    os.makedirs(DIR, exist_ok=True)
    json.dump(d, open(ESTADOS, "w"))

def _twiml_vacio():
    return b'<?xml version="1.0" encoding="UTF-8"?><Response></Response>'

def _twiml(texto):
    return ('<?xml version="1.0" encoding="UTF-8"?><Response><Message>'
            + escape(texto) + "</Message></Response>").encode("utf-8")

def _anon(tel):
    t = re.sub(r"\D", "", tel or "")
    return "..." + t[-4:] if len(t) >= 4 else "?"

def _indice(fila):
    with open(INDICE, "a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")

def _juzgar(cat, texto):
    import urllib.request as _ur
    if len(re.findall(r"\w+", texto)) < 2:
        return False, "transcripcion vacia o inentendible"
    try:
        body = json.dumps({"model": "claude-haiku-5-5", "max_tokens": 1000,
            "messages": [{"role": "user", "content": JUEZ % (cat, texto[:700])}]}).encode()
        req = _ur.Request("https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": _h["E"].get("ANTHROPIC_API_KEY", ""),
                     "anthropic-version": "2023-06-01", "Content-Type": "application/json"})
        resp = json.load(_ur.urlopen(req, timeout=30))
        raw = "".join(b.get("text", "") for b in resp.get("content", []) if isinstance(b, dict))
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return False, "sin veredicto"
        v = json.loads(m.group(0))
        return bool(v.get("ok")), str(v.get("motivo", ""))[:120]
    except Exception as e:
        _h["log"]("voz juez error: %r" % e)
        return False, "no se pudo verificar"

def _es_twilio(url):
    from urllib.parse import urlparse
    u = urlparse(url or "")
    h = (u.hostname or "").lower()
    return u.scheme == "https" and (h == "twilio.com" or h.endswith(".twilio.com"))

def _descargar_audio(url):
    # La URL llega en el POST del webhook, que cualquiera puede falsificar: solo
    # se descarga de Twilio, y la llave va como header "unredirected" para que
    # no viaje al servidor de almacenamiento al que Twilio redirige el audio.
    import base64
    if not _es_twilio(url):
        raise ValueError("media fuera de Twilio rechazada")
    sid = _h["E"].get("TWILIO_SID", "")
    tok = _h["E"].get("TWILIO_TOKEN", "")
    req = urllib.request.Request(url)
    if sid and tok:
        req.add_unredirected_header("Authorization",
                       "Basic " + base64.b64encode(("%s:%s" % (sid, tok)).encode()).decode())
    return urllib.request.urlopen(req, timeout=30).read()

def procesar_audio(cat, tel, crudo_bytes, origen="whatsapp"):
    """Pipeline completo: bytes de audio -> mp3 -> transcripcion -> veredicto.
    Devuelve (ok, respuesta_al_oyente)."""
    ts = time.strftime("%Y%m%d-%H%M%S")
    base = "%s_%s" % (ts, _anon(tel).strip("."))
    tmp = "/tmp/voz-%s" % base
    open(tmp, "wb").write(crudo_bytes)
    mp3tmp = tmp + ".mp3"
    r = subprocess.run(["ffmpeg", "-y", "-i", tmp, "-af",
                        "loudnorm=I=-15:TP=-1.5:LRA=7", "-c:a", "libmp3lame",
                        "-b:a", "96k", mp3tmp], capture_output=True)
    os.remove(tmp)
    if r.returncode != 0:
        return False, "No pude leer ese audio \U0001F648 ¿Lo intentas de nuevo?"
    dur = float(subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                                "format=duration", "-of", "csv=p=0", mp3tmp],
                               capture_output=True, text=True).stdout.strip() or 0)
    if not (DUR_MIN <= dur <= DUR_MAX):
        os.remove(mp3tmp)
        return False, ("Tu audio dura %.0f segundos; buscamos entre %d y %d. "
                       "¿Lo regrabas? \U0001F399️" % (dur, DUR_MIN, DUR_MAX))
    if not PROCESO_AUDIO.acquire(timeout=60):
        os.remove(mp3tmp)
        return False, "Estamos recibiendo muchos audios \U0001F605 Intenta de nuevo en un ratito."
    try:
        texto = _h["transcribe"](mp3tmp)
        juicio = None if cat in ("sugerencias", "contacto") else _juzgar(cat, texto)
    finally:
        PROCESO_AUDIO.release()
    if cat in ("sugerencias", "contacto"):
        destino = os.path.join(DIR, cat, "aprobados", base + ".mp3")
        os.rename(mp3tmp, destino)
        _indice({"ts": ts, "tel": _anon(tel), "cat": cat, "archivo": destino,
                 "transcript": texto, "veredicto": "bandeja", "dur": round(dur, 1)})
        with open(BANDEJA, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": ts, "tel": _anon(tel), "cat": cat,
                                "texto": texto, "audio": destino}, ensure_ascii=False) + "\n")
        return True, "¡Recibido! Gracias por escribirnos \U0001F64F"
    ok, motivo = juicio
    sub = "aprobados" if ok else "rechazados"
    destino = os.path.join(DIR, cat, sub, base + ".mp3")
    os.rename(mp3tmp, destino)
    _indice({"ts": ts, "tel": _anon(tel), "cat": cat, "archivo": destino,
             "transcript": texto, "veredicto": sub, "motivo": motivo,
             "dur": round(dur, 1)})
    _h["log"]("voz %s [%s] %.1fs" % (sub, cat, dur))
    if ok:
        return True, ("¡Buenísimo! ❤️ Tu voz ya es parte de Kultura. "
                      "Mantente pendiente del aire \U0001F4FB")
    return False, ("Gracias por participar \U0001F64F Ese audio no lo podemos usar al "
                   "aire, pero puedes intentar con otro (recuerda: radio familiar).")

_por_numero = {}   # telefono -> [timestamps]; tope anti-spam del webhook

def entrante(form):
    """Maneja un POST del webhook de Twilio. Devuelve bytes TwiML."""
    tel = form.get("From", [""])[0]
    ahora_rl = time.time()
    lst = [t for t in _por_numero.get(tel, []) if ahora_rl - t < 3600]
    if len(lst) >= 30:
        _por_numero[tel] = lst
        return _twiml_vacio()
    lst.append(ahora_rl)
    _por_numero[tel] = lst
    if len(_por_numero) > 5000:
        _por_numero.clear()
    body = (form.get("Body", [""])[0] or "").strip().lower()
    nmedia = int(form.get("NumMedia", ["0"])[0] or 0)
    estados = _estados()
    ahora = time.time()
    est = estados.get(tel) or {}
    if est and ahora - est.get("ts", 0) > 24 * 3600:
        est = {}
    cat = est.get("cat")

    def bienvenida():
        if _enviar_botones(form.get("To", [""])[0], tel):
            return _twiml_vacio()
        return _twiml(BIENVENIDA)

    payload = (form.get("ButtonPayload", [""])[0] or "").strip()
    if payload in BOTONES:
        cat = BOTONES[payload]
        estados[tel] = {"cat": cat, "ts": ahora}
        _guardar_estado(estados)
        return _twiml(RESPUESTA_CAT[cat])

    if nmedia > 0:
        ctype = form.get("MediaContentType0", [""])[0]
        if not ctype.startswith("audio"):
            return _twiml("Por ahora solo recibimos audios y mensajes de texto \U0001F399️")
        if not cat:
            return bienvenida()
        try:
            crudo = _descargar_audio(form.get("MediaUrl0", [""])[0])
        except Exception as e:
            _h["log"]("voz descarga error: %r" % e)
            return _twiml("Se nos enredó el cable \U0001F648 Intenta de nuevo en un rato.")
        _ok, resp = procesar_audio(cat, tel, crudo)
        return _twiml(resp)

    if body in CATS:
        cat = CATS[body]
        estados[tel] = {"cat": cat, "ts": ahora}
        _guardar_estado(estados)
        return _twiml(RESPUESTA_CAT[cat])

    if cat in ("sugerencias", "contacto") and body and body not in ("menu", "menú", "hola"):
        with open(BANDEJA, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y%m%d-%H%M%S"), "tel": _anon(tel),
                                "cat": cat, "texto": form.get("Body", [""])[0]},
                               ensure_ascii=False) + "\n")
        return _twiml("¡Recibido! Gracias por escribirnos \U0001F64F")

    return bienvenida()

# ---------------------------------------------------------------------------
# LLAMADAS: mismo numero que WhatsApp. Mientras no exista el programa
# interactivo, la llamada cae en un buzon: saludo de ash -> tono -> graba hasta
# 60s -> la grabacion pasa por el MISMO pipeline (transcribe + juez) como
# categoria "saludos". El oyente no recibe respuesta (no hay SMS registrado);
# el veredicto queda en la pestana Voces.
# ---------------------------------------------------------------------------
SALUDO_LLAMADA = "https://kulturaradio.com/voz/saludo-llamada.mp3"
BASE_API = "https://kulturaradio.com/api"

def _twiml_voz(cuerpo):
    return ('<?xml version="1.0" encoding="UTF-8"?><Response>' + cuerpo
            + "</Response>").encode("utf-8")

_llamadas = {}   # CallSid -> From (el callback de grabacion no trae el From)

def llamada_entrante(form):
    sid = form.get("CallSid", [""])[0]
    if sid:
        _llamadas[sid] = form.get("From", [""])[0]
        if len(_llamadas) > 500:
            _llamadas.clear()
    return _twiml_voz(
        "<Play>%s</Play>" % SALUDO_LLAMADA
        + '<Record maxLength="60" playBeep="true" timeout="5" trim="trim-silence"'
        + ' action="%s/voz-llamada-fin"' % BASE_API
        + ' recordingStatusCallback="%s/voz-llamada-grabacion"' % BASE_API
        + ' recordingStatusCallbackEvent="completed"/>')

def llamada_fin(form):
    return _twiml_voz(
        '<Say language="es-MX" voice="Polly.Mia">¡Gracias! Tu voz ya es parte de Kultura.</Say>'
        "<Hangup/>")

def llamada_grabacion(form):
    """Callback de Twilio con la grabacion lista: se procesa en el pipeline."""
    if (form.get("RecordingStatus", [""])[0] or "") != "completed":
        return
    url = form.get("RecordingUrl", [""])[0]
    if not url:
        return
    if not url.endswith(".mp3"):
        url += ".mp3"
    sid = form.get("CallSid", [""])[0]
    tel = _llamadas.pop(sid, "") or sid or "llamada"
    try:
        crudo = _descargar_audio(url)
        ok, _resp = procesar_audio("saludos", "llamada:" + tel, crudo, origen="llamada")
        _h["log"]("voz llamada procesada: ok=%s" % ok)
    except Exception as e:
        _h["log"]("voz llamada error: %r" % e)
        # Se guarda para reintentar (p.ej. faltaban credenciales).
        with open(os.path.join(DIR, "pendientes.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"url": url, "tel": tel}) + chr(10))

def listar(cat=None, estado=None, limite=100):
    filas = []
    try:
        for l in open(INDICE, encoding="utf-8"):
            try:
                d = json.loads(l)
            except Exception:
                continue
            if cat and d.get("cat") != cat:
                continue
            if estado and d.get("veredicto") != estado:
                continue
            filas.append(d)
    except FileNotFoundError:
        pass
    return filas[-limite:][::-1]

def borrar(archivo):
    rp = os.path.realpath(archivo or "")
    if not rp.startswith(DIR + os.sep) or not os.path.isfile(rp):
        return False
    os.remove(rp)
    return True
