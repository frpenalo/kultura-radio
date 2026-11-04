# -*- coding: utf-8 -*-
# Diagnostico: mensajes entrantes al WhatsApp de Kultura + alertas recientes.
import base64, json, urllib.parse, urllib.request

E = dict(l.strip().split("=", 1) for l in open("/opt/subwave/.env")
         if l.strip() and not l.startswith("#") and "=" in l)
AC = E["TWILIO_ACCOUNT"]
auth = "Basic " + base64.b64encode(("%s:%s" % (E["TWILIO_SID"], E["TWILIO_TOKEN"])).encode()).decode()

def api(url):
    req = urllib.request.Request(url, headers={"Authorization": auth})
    try:
        return json.load(urllib.request.urlopen(req, timeout=20))
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:300]}

q = urllib.parse.urlencode({"To": "whatsapp:+19193430798", "PageSize": 5})
d = api("https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json?%s" % (AC, q))
msgs = d.get("messages", [])
print("mensajes ENTRANTES a Kultura:", len(msgs), d.get("_error", ""), d.get("_body", ""))
for m in msgs:
    print(" -", m.get("date_created"), "| de", m.get("from"), "| estado", m.get("status"),
          "| err", m.get("error_code"), "| texto:", (m.get("body") or "")[:40],
          "| msg_service:", m.get("messaging_service_sid"))

q2 = urllib.parse.urlencode({"From": "whatsapp:+19193430798", "PageSize": 5})
d2 = api("https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json?%s" % (AC, q2))
print("mensajes SALIENTES de Kultura:", len(d2.get("messages", [])))
for m in d2.get("messages", []):
    print(" -", m.get("date_created"), "| a", m.get("to"), "| estado", m.get("status"), "| err", m.get("error_code"))

al = api("https://monitor.twilio.com/v1/Alerts?PageSize=5")
print("alertas recientes:")
for a in al.get("alerts", []):
    print(" -", a.get("date_created"), "| codigo", a.get("error_code"), "|", (a.get("alert_text") or "")[:160])

pn = api("https://api.twilio.com/2010-04-01/Accounts/%s/IncomingPhoneNumbers.json?PhoneNumber=%%2B19193430798" % AC)
for n in pn.get("incoming_phone_numbers", []):
    print("numero: sms_url=", n.get("sms_url"), "| voice_url=", n.get("voice_url"))
