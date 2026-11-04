# -*- coding: utf-8 -*-
# Crea la plantilla de bienvenida con 3 botones (Content API, quick-reply) y
# guarda su SID en .env como KR_WA_MENU_SID. Los quick-reply dentro de la
# ventana de 24h de una conversacion no requieren aprobacion de Meta.
import base64, json, urllib.request

ENV = "/opt/subwave/.env"
E = dict(l.strip().split("=", 1) for l in open(ENV)
         if l.strip() and not l.startswith("#") and "=" in l)
auth = "Basic " + base64.b64encode(("%s:%s" % (E["TWILIO_SID"], E["TWILIO_TOKEN"])).encode()).decode()

cuerpo = ("¡Hola! \U0001F44B Bienvenido a Kultura Radio, la que nos une.\n"
          "Queremos escucharte. Toca una opción \U0001F447\n\n"
          "Al enviarnos un audio autorizas a Kultura Radio a reproducirlo, editarlo y "
          "difundirlo al aire. Si eres menor de edad, participa con un adulto.")
acciones = [
    {"title": "❤️ Lo que nos une", "id": "cat_unir"},
    {"title": "\U0001F399️ Tu saludo", "id": "cat_saludo"},
    {"title": "\U0001F4A1 Ideas y contacto", "id": "cat_ideas"},
]
for a in acciones:
    assert len(a["title"]) <= 20, a["title"]

body = json.dumps({
    "friendly_name": "kultura_bienvenida_botones",
    "language": "es",
    "types": {
        "twilio/quick-reply": {"body": cuerpo, "actions": acciones},
        "twilio/text": {"body": cuerpo},
    },
}).encode()
req = urllib.request.Request("https://content.twilio.com/v1/Content", data=body,
    headers={"Authorization": auth, "Content-Type": "application/json"})
try:
    r = json.load(urllib.request.urlopen(req, timeout=20))
except urllib.error.HTTPError as e:
    raise SystemExit("ERROR %s: %s" % (e.code, e.read().decode()[:300]))
sid = r["sid"]
print("plantilla creada:", sid)

lineas = [l for l in open(ENV).read().splitlines() if not l.startswith("KR_WA_MENU_SID=")]
lineas.append("KR_WA_MENU_SID=" + sid)
open(ENV, "w").write("\n".join(lineas) + "\n")
print("guardada en .env")
