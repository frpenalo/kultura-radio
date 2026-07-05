#!/usr/bin/env python3
# "Saludo del Día" — si HOY es una fecha festiva/especial para la comunidad,
# el DJ da un saludo cálido. Corre por cron a diario; si no es festivo, no hace
# nada. Gate de oyentes. Fechas pensadas para el público caribeño/dominicano +
# EE.UU. + orgullo latino.
import json, urllib.request, sys, base64, calendar
from datetime import date
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

# Fechas FIJAS (mes, dia) -> (nombre, contexto para el saludo)
FIXED = {
    (1, 1):   ("Año Nuevo", "comienzo de año, esperanza y nuevos sueños"),
    (1, 6):   ("Día de Reyes", "la llegada de los Reyes Magos, tradición muy caribeña y dominicana, regalos e ilusión de los niños"),
    (2, 14):  ("Día del Amor y la Amistad", "San Valentín, amor y amistad"),
    (2, 27):  ("Día de la Independencia Dominicana", "orgullo dominicano, la libertad de República Dominicana"),
    (5, 5):   ("Cinco de Mayo", "celebración de la cultura mexicana"),
    (7, 4):   ("Día de la Independencia de Estados Unidos", "la fiesta del país que hoy es nuestra casa"),
    (9, 15):  ("inicio del Mes de la Herencia Hispana", "orgullo latino, nuestra herencia y cultura; también arrancan las independencias de Centroamérica"),
    (9, 16):  ("Día de la Independencia de México", "orgullo mexicano"),
    (10, 12): ("Día de la Hispanidad", "nuestra raza y herencia hispana, lo que nos une"),
    (10, 31): ("Halloween", "noche de disfraces, en familia y con cuidado"),
    (11, 2):  ("Día de los Muertos", "recordar con cariño a los que ya partieron, hermosa tradición latina"),
    (12, 24): ("Nochebuena", "la cena en familia, la unión y el cariño"),
    (12, 25): ("Navidad", "paz, familia y alegría"),
    (12, 31): ("Fin de Año", "despedir el año con gratitud y buenos deseos"),
}

def nth_dow(y, m, dow, n):  # dow: lun=0..dom=6 ; n>=1 o -1 (ultimo)
    days = [w[dow] for w in calendar.monthcalendar(y, m) if w[dow] != 0]
    return days[n - 1] if n > 0 else days[-1]

def floating(d):
    y = d.year
    rules = [
        (date(y, 1, nth_dow(y, 1, 0, 3)),  ("Día de Martin Luther King", "justicia, igualdad y respeto para todos")),
        (date(y, 5, nth_dow(y, 5, 6, 2)),  ("Día de las Madres", "homenaje a todas las madres; un abrazo enorme a las que están lejos de sus hijos")),
        (date(y, 5, nth_dow(y, 5, 0, -1)), ("Memorial Day", "recordar a los caídos; fin de semana en familia")),
        (date(y, 6, nth_dow(y, 6, 6, 3)),  ("Día del Padre", "homenaje a todos los papás; un saludo especial a los que trabajan duro lejos de su familia")),
        (date(y, 7, nth_dow(y, 7, 6, -1)), ("Día de los Padres en República Dominicana", "homenaje a los papás dominicanos")),
        (date(y, 9, nth_dow(y, 9, 0, 1)),  ("Día del Trabajo", "homenaje a todos los trabajadores latinos que echan pa'lante")),
        (date(y, 11, nth_dow(y, 11, 3, 4)),("Día de Acción de Gracias", "gratitud, familia y bendiciones")),
    ]
    for dd, info in rules:
        if dd == d:
            return info
    return None

def holiday_today(d):
    if (d.month, d.day) in FIXED:
        return FIXED[(d.month, d.day)]
    return floating(d)

def listeners():
    try:
        r = urllib.request.Request(BASE + "/listeners", headers={"Authorization": AUTH})
        return json.load(urllib.request.urlopen(r, timeout=30)).get("current", 0) or 0
    except Exception:
        return None

def claude(prompt):
    body = json.dumps({"model": "claude-haiku-4-5", "max_tokens": 350,
                       "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))["content"][0]["text"].strip()

def main():
    force = "--force" in sys.argv
    dry = "--dry" in sys.argv
    today = (date.today() if TZ is None else __import__("datetime").datetime.now(TZ).date())
    hol = holiday_today(today)
    # permite forzar una fecha de prueba: --date=MM-DD
    for a in sys.argv:
        if a.startswith("--date="):
            mm, dd = a.split("=")[1].split("-"); hol = holiday_today(date(today.year, int(mm), int(dd)))
    if not hol:
        print("hoy no es festivo, no hago nada"); return
    name, ctx = hol
    if not force:
        n = listeners()
        if not n:
            print("festivo (%s) pero sin oyentes, omito" % name); return
    prompt = (
        "Eres el locutor de Kultura Radio, emisora latina del Triangle (Raleigh, NC). "
        "Español caribeño dominicano, de TÚ (jamás vos). Hoy es %s. Escribe un SALUDO breve y "
        "cálido para radio, MÁXIMO 320 caracteres (texto-a-voz). Conecta con la comunidad latina "
        "del Triangle (muchos lejos de su país y su familia). Contexto del día: %s. Cierra con algo "
        "como 'Feliz día, de parte de Kultura Radio.'. Solo palabras pronunciables: nada de símbolos "
        "ni URLs. Tildes correctas en español." % (name, ctx))
    script = claude(prompt).strip().strip('"')
    if len(script) > 480:
        script = script[:480]; script = script[:script.rfind(".") + 1] or script
    print("=== SALUDO (%s, %d chars) ===" % (name, len(script)))
    print(script)
    if dry:
        return
    data = json.dumps({"text": script, "kind": "dj-speak", "mode": "raw"}).encode("utf-8")
    req = urllib.request.Request(BASE + "/dj/say", data=data,
        headers={"Content-Type": "application/json", "Authorization": AUTH})
    print("aireado:", json.load(urllib.request.urlopen(req, timeout=30)).get("ok"))

main()
