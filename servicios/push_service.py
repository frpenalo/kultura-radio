#!/usr/bin/env python3
# Servicio de notificaciones push de Kultura Radio (corre en el HOST, no en docker).
# Escucha SOLO en el gateway de la red docker (172.18.0.1): los contenedores
# (Caddy, Liquidsoap) y el host llegan; desde internet no existe.
#
#   POST /register {"token":"ExponentPushToken[...]"}  publico via Caddy (/api/push/register)
#   POST /live     {"dj":"Nombre"}                     interno: Liquidsoap al conectar DJ en vivo
#   POST /send     {"title":"...","body":"..."}        interno: anuncios manuales (curl desde el host)
#   GET  /count                                        interno: cuantos dispositivos registrados
#
# Envia por el push service de Expo (gratis). Tokens en /opt/subwave/push/tokens.json;
# los que Expo reporta DeviceNotRegistered (app desinstalada) se eliminan solos.
import json, os, re, threading, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST, PORT = "172.18.0.1", 8099
DB = "/opt/subwave/push/tokens.json"
EXPO = "https://exp.host/--/api/v2/push/send"
TOK_RX = re.compile(r"^Expo(nent)?PushToken\[[A-Za-z0-9_\-]{10,60}\]$")
LOCK = threading.Lock()
_altas_ip = {}   # ip -> [timestamps] de tokens nuevos (tope diario)
MAX_TOKENS = 50000

def load():
    try:
        return json.load(open(DB))
    except Exception:
        return []

def save(toks):
    tmp = DB + ".tmp"
    json.dump(toks, open(tmp, "w"))
    os.replace(tmp, DB)

def send_all(title, body):
    toks = load()
    bad = set()
    for i in range(0, len(toks), 100):
        chunk = toks[i:i + 100]
        msgs = [{"to": t, "title": title, "body": body, "sound": "default",
                 "priority": "high"} for t in chunk]
        try:
            req = urllib.request.Request(EXPO, data=json.dumps(msgs).encode(),
                                         headers={"Content-Type": "application/json"})
            resp = json.load(urllib.request.urlopen(req, timeout=20))
            for t, tick in zip(chunk, resp.get("data", [])):
                det = tick.get("details", {}) if isinstance(tick, dict) else {}
                if det.get("error") == "DeviceNotRegistered":
                    bad.add(t)
        except Exception as e:
            print("expo send error:", e, flush=True)
    if bad:
        with LOCK:
            save([t for t in load() if t not in bad])
    print("push enviado a %d dispositivos (%d dados de baja)" % (len(toks) - len(bad), len(bad)), flush=True)

class H(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/count":
            return self._json(200, {"tokens": len(load())})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 4096)
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._json(400, {"error": "bad json"})
        if self.path == "/register":
            t = str(data.get("token", ""))
            if not TOK_RX.match(t):
                return self._json(400, {"error": "bad token"})
            import time as _t
            ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
            with LOCK:
                toks = load()
                if t not in toks:
                    ahora = _t.time()
                    altas = [x for x in _altas_ip.get(ip, []) if ahora - x < 86400]
                    if len(altas) >= 10:
                        return self._json(429, {"error": "limite"})
                    if len(toks) >= MAX_TOKENS:
                        return self._json(429, {"error": "full"})
                    altas.append(ahora)
                    _altas_ip[ip] = altas
                    if len(_altas_ip) > 20000:
                        _altas_ip.clear()
                    toks.append(t)
                    save(toks)
            return self._json(200, {"ok": True})
        if self.path == "/live":
            dj = str(data.get("dj") or "El DJ")[:40]
            # Async: Liquidsoap no debe esperar a que Expo responda.
            threading.Thread(target=send_all, daemon=True, args=(
                "\U0001F534 EN VIVO en Kultura Radio",
                dj + " está al aire. ¡Dale play!")).start()
            return self._json(200, {"queued": len(load())})
        if self.path == "/send":
            title = str(data.get("title") or "")[:80]
            body = str(data.get("body") or "")[:180]
            if not title or not body:
                return self._json(400, {"error": "title y body requeridos"})
            threading.Thread(target=send_all, daemon=True, args=(title, body)).start()
            return self._json(200, {"queued": len(load())})
        self._json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        print("%s %s" % (self.address_string(), fmt % args), flush=True)

if __name__ == "__main__":
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    print("push service en %s:%d" % (HOST, PORT), flush=True)
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
