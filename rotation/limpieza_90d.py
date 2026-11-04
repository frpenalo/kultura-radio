#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Limpieza diaria que cumple la politica de privacidad (kulturaradio.com/privacidad):
# - 90 dias: audios APROBADOS (dedicatorias, WhatsApp, llamadas) y sus
#   transcripciones, porque son material de programacion; mensajes de la bandeja.
# - 30 dias: audios RECHAZADOS por el filtro y sus transcripciones, reportes
#   tecnicos (telemetria) y las copias que guarda Twilio (el servidor ya tiene
#   su propia copia procesada).
#
# Uso: limpieza_90d.py            borra
#      limpieza_90d.py --simular  solo cuenta lo que borraria
import base64, glob, json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

DIAS_APROBADO = 90
DIAS_CORTO = 30
ST = "/opt/subwave/state"
SIMULAR = "--simular" in sys.argv
cuenta = {}

def limite(dias):
    dt = datetime.now(timezone.utc) - timedelta(days=dias)
    return time.time() - dias * 86400, dt, dt.strftime("%Y%m%d")

C90, C90_DT, C90_ID = limite(DIAS_APROBADO)
C30, C30_DT, C30_ID = limite(DIAS_CORTO)

def anota(k, n=1):
    cuenta[k] = cuenta.get(k, 0) + n

def borrar(ruta, k):
    anota(k)
    if not SIMULAR:
        os.remove(ruta)

# --- archivos de audio --------------------------------------------------------
for patron, corte, k in ((ST + "/dedis/*.mp3", C90, "dedicatorias aprobadas"),
                         (ST + "/dedis/rechazadas/*", C30, "dedicatorias rechazadas"),
                         (ST + "/voz/*/aprobados/*.mp3", C90, "voz aprobados"),
                         (ST + "/voz/*/rechazados/*.mp3", C30, "voz rechazados")):
    for f in glob.glob(patron):
        if os.path.isfile(f) and os.path.getmtime(f) < corte:
            borrar(f, k)

# --- registros con transcripciones (se poda linea por linea) -------------------
def podar(ruta, es_vieja, k):
    if not os.path.exists(ruta):
        return
    lineas = open(ruta, encoding="utf-8").read().splitlines()
    quedan = [l for l in lineas if not es_vieja(l)]
    if len(quedan) != len(lineas):
        anota(k, len(lineas) - len(quedan))
        if not SIMULAR:
            open(ruta, "w", encoding="utf-8").write("\n".join(quedan) + ("\n" if quedan else ""))

def dedi_vieja(l):
    # dedis.log: id(AAAAMMDD-...) \t - \t nombre \t OK|NO \t motivo \t transcripcion
    c = l.split("\t")
    if not l[:8].isdigit():
        return False
    corte_id = C30_ID if len(c) > 3 and c[3] == "NO" else C90_ID
    return l[:8] < corte_id

def voz_vieja(l):
    try:
        d = json.loads(l)
    except Exception:
        return False
    corte_id = C30_ID if d.get("veredicto") == "rechazados" else C90_ID
    return str(d.get("ts", "99999999"))[:8] < corte_id

def bandeja_vieja(l):
    try:
        return str(json.loads(l).get("ts", "99999999"))[:8] < C90_ID
    except Exception:
        return False

podar(ST + "/dedis/dedis.log", dedi_vieja, "lineas dedis.log")
podar(ST + "/voz/indice.jsonl", voz_vieja, "lineas indice voz")
podar(ST + "/voz/bandeja.jsonl", bandeja_vieja, "lineas bandeja")
p = ST + "/voz/pendientes.jsonl"
if os.path.exists(p) and os.path.getmtime(p) < C30:
    borrar(p, "pendientes viejos")

# --- estados del bot (la categoria solo vale 24 h; no hay razon para guardarla) -
p = ST + "/voz/estados.json"
if os.path.exists(p):
    try:
        est = json.load(open(p))
        vivos = {k: v for k, v in est.items() if time.time() - v.get("ts", 0) < 86400}
        if len(vivos) != len(est):
            anota("estados vencidos", len(est) - len(vivos))
            if not SIMULAR:
                json.dump(vivos, open(p, "w"))
    except Exception:
        pass

# --- telemetria (un archivo por dia) --------------------------------------------
for f in glob.glob(ST + "/telemetria/*.jsonl"):
    if os.path.basename(f)[:10] < C30_DT.strftime("%Y-%m-%d"):
        borrar(f, "telemetria (dias)")

# --- copias en Twilio (30 dias) -------------------------------------------------
E = dict(l.strip().split("=", 1) for l in open("/opt/subwave/.env")
         if l.strip() and not l.startswith("#") and "=" in l)
if E.get("TWILIO_ACCOUNT") and E.get("TWILIO_SID"):
    AC = E["TWILIO_ACCOUNT"]
    auth = "Basic " + base64.b64encode(("%s:%s" % (E["TWILIO_SID"], E["TWILIO_TOKEN"])).encode()).decode()
    API = "https://api.twilio.com/2010-04-01/Accounts/" + AC

    def tw(url, metodo="GET"):
        req = urllib.request.Request(url, method=metodo, headers={"Authorization": auth})
        r = urllib.request.urlopen(req, timeout=30)
        return json.load(r) if metodo == "GET" else None

    try:
        antes = C30_DT.strftime("%Y-%m-%d")
        url = API + "/Recordings.json?" + urllib.parse.urlencode({"DateCreated<": antes, "PageSize": 100})
        for r in tw(url).get("recordings", []):
            anota("grabaciones Twilio")
            if not SIMULAR:
                tw(API + "/Recordings/%s.json" % r["sid"], "DELETE")
        url = API + "/Messages.json?" + urllib.parse.urlencode(
            {"To": "whatsapp:+19193430798", "DateSent<": antes, "PageSize": 100})
        for m in tw(url).get("messages", []):
            if int(m.get("num_media") or 0) == 0:
                continue
            for md in tw(API + "/Messages/%s/Media.json" % m["sid"]).get("media_list", []):
                anota("audios WhatsApp en Twilio")
                if not SIMULAR:
                    tw(API + "/Messages/%s/Media/%s.json" % (m["sid"], md["sid"]), "DELETE")
    except Exception as e:
        anota("error Twilio: %r" % (e,))

print(time.strftime("%Y-%m-%d %H:%M"), "SIMULACION" if SIMULAR else "BORRADO",
      "| cortes: aprobado", C90_DT.strftime("%Y-%m-%d"), "/ corto", C30_DT.strftime("%Y-%m-%d"),
      "|", cuenta or "nada que borrar", flush=True)
