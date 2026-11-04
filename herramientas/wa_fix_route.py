# -*- coding: utf-8 -*-
# Amarra la ruta de entrada del WhatsApp de Kultura por los dos lados:
# (1) webhook del sender (Senders v2) y (2) Messaging URL del numero, que es
# la ruta que Twilio usa para WhatsApp en numeros propios de Twilio.
import base64, json, urllib.parse, urllib.request

E = dict(l.strip().split("=", 1) for l in open("/opt/subwave/.env")
         if l.strip() and not l.startswith("#") and "=" in l)
AC = E["TWILIO_ACCOUNT"]
auth = "Basic " + base64.b64encode(("%s:%s" % (E["TWILIO_SID"], E["TWILIO_TOKEN"])).encode()).decode()
HOOK = "https://kulturaradio.com/api/voz-whatsapp"

def api(url, data=None, ctype="application/x-www-form-urlencoded"):
    req = urllib.request.Request(url, data=data,
        headers={"Authorization": auth, "Content-Type": ctype})
    try:
        return json.load(urllib.request.urlopen(req, timeout=20))
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:300]}

# (1) sender
d = api("https://messaging.twilio.com/v2/Channels/Senders?Channel=whatsapp&PageSize=20")
for s in d.get("senders", []):
    if s.get("sender_id") == "whatsapp:+19193430798":
        print("sender estado:", s.get("status"), "| webhook actual:", s.get("webhook"))

# (2) numero
pn = api("https://api.twilio.com/2010-04-01/Accounts/%s/IncomingPhoneNumbers.json?PhoneNumber=%%2B19193430798" % AC)
n = pn["incoming_phone_numbers"][0]
r = api("https://api.twilio.com/2010-04-01/Accounts/%s/IncomingPhoneNumbers/%s.json" % (AC, n["sid"]),
        urllib.parse.urlencode({"SmsUrl": HOOK, "SmsMethod": "POST"}).encode())
print("numero sms_url ->", r.get("sms_url", r))
