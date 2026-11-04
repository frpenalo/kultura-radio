# -*- coding: utf-8 -*-
# Estado del remitente WhatsApp de Kultura en Twilio (Senders API v2).
# Uso: wa_sender.py            -> muestra estado
#      wa_sender.py --webhook  -> apunta los mensajes entrantes al bot
import base64, json, sys, urllib.request

E = dict(l.strip().split("=", 1) for l in open("/opt/subwave/.env")
         if l.strip() and not l.startswith("#") and "=" in l)
auth = "Basic " + base64.b64encode(("%s:%s" % (E["TWILIO_SID"], E["TWILIO_TOKEN"])).encode()).decode()
NUM = "whatsapp:+19193430798"
HOOK = "https://kulturaradio.com/api/voz-whatsapp"

def api(url, body=None, method="GET"):
    req = urllib.request.Request(url, data=body, method=method,
        headers={"Authorization": auth, "Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=20))
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:400]}

d = api("https://messaging.twilio.com/v2/Channels/Senders?Channel=whatsapp&PageSize=20")
if "_error" in d:
    print("ERROR listando:", d); sys.exit(1)
senders = d.get("senders", [])
print("remitentes WhatsApp en la cuenta:", len(senders))
k = None
for s in senders:
    marca = "  <== KULTURA" if s.get("sender_id") == NUM else ""
    print(" -", s.get("sender_id"), "| estado:", s.get("status"),
          "| nombre:", (s.get("profile") or {}).get("name"),
          "| webhook:", (s.get("webhook") or {}).get("callback_url"), marca)
    if s.get("sender_id") == NUM:
        k = s

if k and "--webhook" in sys.argv:
    r = api("https://messaging.twilio.com/v2/Channels/Senders/%s" % k["sid"],
            json.dumps({"webhook": {"callback_url": HOOK, "callback_method": "POST"}}).encode(),
            method="POST")
    print("webhook ->", (r.get("webhook") or {}).get("callback_url") if "_error" not in r else r)
