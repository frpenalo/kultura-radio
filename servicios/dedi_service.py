#!/usr/bin/env python3
# Servicio de DEDICATORIAS de Kultura Radio (corre en el HOST, como kultura-push).
# Recibe un audio corto del oyente, lo modera AUTOMATICAMENTE (transcripcion
# OpenAI + veredicto Anthropic) y, si esta limpio, lo saca al aire.
#
# TIMING ESTILO RADIO (v2, 16-oct): si el oyente pidio cancion, primero se pide
# la cancion al DJ, se espera a que ARRANQUE al aire, y el saludo suena ENCIMA
# de la entrada de esa cancion (canal say.txt: la musica se agacha). Sin
# cancion, el saludo sale de una vez. Si la cancion falla o tarda >8 min, el
# saludo sale solo para no perderse.
#
# Regla de oro: EN LA DUDA, NO SUENA. Cualquier fallo (API caida, transcripcion
# vacia, JSON raro) = rechazado. Los rechazados quedan en dedis/rechazadas/
# con su transcripcion en dedis.log.
#
#   POST /dedi {"name","song","audio" (base64),"ext"}   publico via Caddy /api/dedi
#   GET  /health                                        interno
#
# Escucha SOLO en 172.18.0.1 (gateway docker): invisible desde internet.
import base64, json, os, re, subprocess, threading, time, urllib.error, urllib.request, uuid

# GEO — licencias Live365 cubren US, Canada, Reino Unido y Mexico (oct 2026).
import importlib.util as _ilu
_spec_vw = _ilu.spec_from_file_location("voz_whatsapp", "/opt/subwave/push/voz_whatsapp.py")
vw = _ilu.module_from_spec(_spec_vw)
_spec_vw.loader.exec_module(vw)

GEO_PERMITIDOS = {"US", "CA", "GB", "MX"}

# CURADOR — curaduria manual de la biblioteca.
CUR_MUSICA = "/opt/subwave/music"
CUR_PAPELERA = "/opt/subwave/music-papelera"
CUR_GENEROS = ["Salsa", "Merengue", "Bachata", "Reggaeton", "Dembow", "Bolero", "Balada"]

def cur_nav_qs(extra):
    import hashlib as _h, random as _r, urllib.parse as _up
    pw = E.get("NAVIDROME_PASS", "")
    salt = "%016x" % _r.getrandbits(64)
    base = {"u": "kultura", "t": _h.md5((pw + salt).encode()).hexdigest(),
            "s": salt, "v": "1.16.1", "c": "curador", "f": "json"}
    base.update(extra)
    return _up.urlencode(base)

def cur_fila(x):
    rel = x.get("path") or ""
    return {"id": x.get("id"), "title": x.get("title", ""), "artist": x.get("artist", ""),
            "album": x.get("album", ""), "genre": x.get("genre", ""),
            "year": x.get("year"), "path": os.path.join(CUR_MUSICA, rel) if rel else ""}

CUR_NAV_DB = "/opt/subwave/state/navidrome/navidrome.db"

def cur_paths_por_id(ids):
    """ids subsonic -> ruta real en el host, via la base de Navidrome."""
    import sqlite3
    out = {}
    if not ids:
        return out
    con = sqlite3.connect("file:%s?mode=ro" % CUR_NAV_DB, uri=True, timeout=5)
    try:
        q = "SELECT id, path FROM media_file WHERE id IN (%s)" % ",".join("?" * len(ids))
        for sid, ruta in con.execute(q, list(ids)):
            # Navidrome guarda la ruta del contenedor (/music/...): mapear al host.
            if ruta.startswith("/music/"):
                ruta = CUR_MUSICA + ruta[len("/music"):]
            elif not ruta.startswith("/"):
                ruta = os.path.join(CUR_MUSICA, ruta)
            out[sid] = ruta
    finally:
        con.close()
    return out

def cur_path_ok(path):
    rp = os.path.realpath(path or "")
    return rp.startswith(CUR_MUSICA + os.sep) and os.path.isfile(rp)
GEO_DB = "/opt/subwave/state/geo/dbip-country-lite.mmdb"
_geo_reader = None
def geo_pais(ip):
    global _geo_reader
    try:
        if _geo_reader is None:
            import maxminddb
            _geo_reader = maxminddb.open_database(GEO_DB)
        r = _geo_reader.get(ip) or {}
        return (r.get("country") or {}).get("iso_code")
    except Exception:
        return None
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST, PORT = "172.18.0.1", 8098
STATE = "/opt/subwave/state"            # = /var/sub-wave dentro de los contenedores
DEDIS = STATE + "/dedis"                # aprobadas (el broadcast las lee de aqui)
RECH = DEDIS + "/rechazadas"
SAY = STATE + "/say.txt"                # canal de voz del DJ (lo sondea radio.liq)
NP = STATE + "/now-playing.json"        # lo escribe liquidsoap en cada cancion
ENV = "/opt/subwave/.env"
MAX_B64 = 3 * 1024 * 1024               # ~2MB de audio real
DUR_MIN, DUR_MAX = 1.5, 16.0
COOLDOWN_S = 10 * 60                    # por IP
LOCK = threading.Lock()
_np_cache = None
_np_hist = []          # [(ts, json del crudo)] ~3 min de instantaneas
_np_oyentes = None     # ultimo conteo de oyentes de la API de Live365

def _np_delay():
    try:
        cfg = json.load(open("/opt/subwave/state/stream-config.json"))
        return float(cfg.get("npDelay", 37))
    except Exception:
        return 37.0

def _hilo_np():
    global _np_oyentes
    tick = 0
    while True:
        try:
            raw = json.load(urllib.request.urlopen(
                "https://kulturaradio.com/api/now-playing-raw", timeout=6))
            if (raw.get("nowPlaying") or {}).get("title"):
                _np_hist.append((time.time(), raw))
                del _np_hist[:-50]
        except Exception:
            pass
        # Oyentes de Live365 cada ~32s (su API es lenta e inestable para
        # titulos, pero el conteo sirve).
        if tick % 8 == 0:
            try:
                lv = json.load(urllib.request.urlopen(
                    "https://api.live365.com/station/a21141", timeout=8))
                if isinstance(lv.get("listeners"), int):
                    _np_oyentes = lv["listeners"]
            except Exception:
                pass
        tick += 1
        time.sleep(4)

threading.Thread(target=_hilo_np, daemon=True).start()
_np_last_good = None
_art_cache = {}
last_by_ip = {}
_telem_ip = {}   # ip -> [timestamps] de reportes de vuelo

def env():
    d = {}
    for line in open(ENV):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d

E = env()
OPENAI_KEY = E.get("OPENAI_API_KEY", "")
ANTHROPIC_KEY = E.get("ANTHROPIC_API_KEY", "")

def log(msg):
    print(time.strftime("%H:%M:%S ") + msg, flush=True)

def ffprobe_dur(fp):
    try:
        out = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                              "format=duration", "-of", "csv=p=0", fp],
                             capture_output=True, text=True, timeout=15)
        return float(out.stdout.strip())
    except Exception:
        return 0.0

def transcribe(fp):
    """OpenAI whisper-1 via multipart manual (stdlib). '' si falla."""
    try:
        boundary = "----kultura" + uuid.uuid4().hex
        audio = open(fp, "rb").read()
        parts = []
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nwhisper-1\r\n" % boundary).encode())
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"dedi.mp3\"\r\nContent-Type: audio/mpeg\r\n\r\n" % boundary).encode())
        parts.append(audio)
        parts.append(("\r\n--%s--\r\n" % boundary).encode())
        body = b"".join(parts)
        req = urllib.request.Request("https://api.openai.com/v1/audio/transcriptions",
            data=body, headers={
                "Authorization": "Bearer " + OPENAI_KEY,
                "Content-Type": "multipart/form-data; boundary=" + boundary})
        resp = json.load(urllib.request.urlopen(req, timeout=45))
        return (resp.get("text") or "").strip()
    except Exception as e:
        log("transcribe error: %r" % e)
        return ""

MOD_PROMPT = """Eres el filtro de contenido de Kultura Radio, una emisora familiar latina. \
Un oyente grabo una dedicatoria de voz que sonara AL AIRE. Esta es la transcripcion:

\"%s\"

RECHAZA si contiene: groserias o vulgaridad (en cualquier idioma o disimulada), \
contenido sexual, violencia o amenazas, burlas o insultos a alguien, politica, \
odio o discriminacion, publicidad o promocion de negocios o redes sociales, \
numeros de telefono o direcciones, o si el texto no parece una dedicatoria o \
saludo coherente (puede ser ruido mal transcrito).

APRUEBA si es un saludo, dedicatoria, felicitacion o mensaje de carino normal, \
aunque mencione nombres de pila.

Responde SOLO este JSON, nada mas: {"ok": true o false, "motivo": "breve"}"""

def moderate(text):
    """Veredicto del LLM. (False, motivo) ante cualquier duda o fallo."""
    words = re.findall(r"\w+", text)
    if len(words) < 2:
        return False, "transcripcion vacia o inentendible"
    try:
        body = json.dumps({
            "model": "claude-haiku-5-5",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": MOD_PROMPT % text[:600]}],
        }).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages",
            data=body, headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"})
        resp = json.load(urllib.request.urlopen(req, timeout=30))
        # El modelo puede anteponer bloques de razonamiento: juntar SOLO texto.
        raw = "".join(b.get("text", "") for b in resp.get("content", []) if isinstance(b, dict))
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            log("moderate raw sin JSON: %r" % raw[:200])
            return False, "no se pudo verificar"
        v = json.loads(m.group(0))
        return bool(v.get("ok")), str(v.get("motivo", ""))[:120]
    except Exception as e:
        log("moderate error: %r" % e)
        return False, "no se pudo verificar"

try:
    vw.init(transcribe=transcribe, log=log, E=E)
except Exception as _e:
    log("voz init error: %r" % _e)

def play_on_air(container_path):
    """Escribe en say.txt cuando este libre (el DJ pudo haberlo usado hace nada)."""
    for _ in range(40):
        if not os.path.exists(SAY):
            open(SAY, "w").write(container_path)
            return True
        time.sleep(0.25)
    return False

def norm(s):
    return re.sub(r"\s+", " ", str(s or "").lower()).strip()

# --- PARRILLA NOMBRADA (Fase 4) ---------------------------------------------
# La programacion semanal vive en state/parrilla/parrilla.json (misma fuente
# que lee el picker del controller). Aqui se sirve en /programa y un hilo
# lanza el ident pregrabado del show cuando arranca (state/idents/<id>.mp3,
# visto por liquidsoap como /var/sub-wave/idents/<id>.mp3).
from zoneinfo import ZoneInfo
PARRILLA = STATE + "/parrilla/parrilla.json"
IDENTS = STATE + "/idents"
_parr_cache = (0.0, [])

def parrilla_shows():
    global _parr_cache
    try:
        mt = os.path.getmtime(PARRILLA)
        if mt != _parr_cache[0]:
            _parr_cache = (mt, json.load(open(PARRILLA, encoding="utf-8")).get("shows", []))
    except Exception as e:
        log("parrilla error: %r" % e)
    return _parr_cache[1]

def show_en_el_aire(dt=None):
    dt = dt or __import__("datetime").datetime.now(ZoneInfo("America/New_York"))
    h, wd = dt.hour, (dt.weekday() + 1) % 7   # 0=domingo, como en el JSON
    best = None
    for sh in parrilla_shows():
        wraps = sh["desde"] > sh["hasta"]
        en_hora = (h >= sh["desde"] or h < sh["hasta"]) if wraps else (sh["desde"] <= h < sh["hasta"])
        if not en_hora:
            continue
        dia = (wd + 6) % 7 if (wraps and h < sh["hasta"]) else wd
        if dia not in sh.get("dias", []):
            continue
        if best is None or sh.get("prio", 1) > best.get("prio", 1):
            best = sh
    return best

def ident_loop():
    """Al cambiar el show en el aire, suelta su ident pregrabado (si existe).
    Arranca sin disparar: el show vigente al bootear no se anuncia."""
    last = (show_en_el_aire() or {}).get("id")
    while True:
        time.sleep(30)
        try:
            sh = show_en_el_aire()
            sid = sh.get("id") if sh else None
            if sid and sid != last:
                f = IDENTS + "/" + sid + ".mp3"
                if os.path.exists(f):
                    if play_on_air("/var/sub-wave/idents/" + sid + ".mp3"):
                        log("ident al aire: " + sid)
                    else:
                        log("ident NO salio (say ocupado): " + sid)
            last = sid or last
        except Exception as e:
            log("ident_loop error: %r" % e)

def request_song(song, name):
    """Pide la cancion y espera la resolucion del DJ.
    Devuelve: dict track {'title','artist'} si quedo en cola, None si fallo."""
    for i in range(6):
        try:
            body = json.dumps({"text": song, "name": name}).encode()
            req = urllib.request.Request("https://kulturaradio.com/api/request",
                data=body, headers={"Content-Type": "application/json"})
            resp = json.load(urllib.request.urlopen(req, timeout=20))
            rid = resp.get("requestId")
            if rid:
                for _ in range(20):
                    time.sleep(2)
                    try:
                        st = json.load(urllib.request.urlopen(
                            "https://kulturaradio.com/api/request/" + rid, timeout=15))
                    except Exception:
                        continue
                    if st.get("status") == "resolved":
                        t = st.get("track") or {}
                        log("cancion en cola: %s - %s" % (t.get("title"), t.get("artist")))
                        return t
                    if st.get("status") == "failed":
                        log("cancion rechazada por el DJ: %s" % st.get("message"))
                        return None
                log("cancion sin resolucion en 40s")
                return {}
            log("cancion sin requestId (intento %d): %r" % (i + 1, resp))
        except Exception as e:
            log("request error (intento %d): %r" % (i + 1, e))
        time.sleep(20)
    return None

def now_playing_title():
    try:
        return norm(json.load(open(NP)).get("title"))
    except Exception:
        return ""

def dedi_with_song(cpath, song, name):
    """Timing estilo radio: espera a que la cancion pedida ARRANQUE al aire y
    suelta el saludo encima de su entrada. Fallbacks: sin cancion valida o
    timeout -> el saludo sale solo igual."""
    tr = request_song(song, name)
    if tr is None:
        log("sin cancion: saludo sale solo")
        play_on_air(cpath)
        return
    target = norm(tr.get("title"))
    if not target:
        time.sleep(10)
        play_on_air(cpath)
        return
    for _ in range(240):  # hasta 8 min esperando el turno de la cancion
        if now_playing_title() == target:
            time.sleep(2)  # que se oiga arrancar la musica primero
            ok = play_on_air(cpath)
            log("saludo sobre la entrada de '%s' (%s)" % (target, "OK" if ok else "say ocupado"))
            return
        time.sleep(2)
    log("timeout esperando '%s': saludo sale solo" % target)
    play_on_air(cpath)

class H(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/health":
            return self._json(200, {"ok": True})
        if self.path.split("?")[0] == "/salud":
            # Salud agregada para el monitor externo. "senal" prueba el camino
            # PUBLICO completo (Caddy -> liquidsoap, o el redirect a Live365
            # cuando este activo: un 3xx tambien cuenta como vivo).
            checks = {}
            try:
                class _NoRedir(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, *a, **k):
                        return None
                op = urllib.request.build_opener(_NoRedir)
                req = urllib.request.Request("https://kulturaradio.com/stream.mp3",
                                             headers={"User-Agent": "kultura-salud"})
                # Timeout holgado + un reintento: con un build de la app
                # exprimiendo el CPU, la sonda vencia a los 10s y el monitor
                # externo reportaba 503 con la radio perfectamente al aire
                # (falsas alarmas de 8:03 y 9:25 del 29-oct).
                checks["senal"] = False
                for _ in range(2):
                    try:
                        r = op.open(req, timeout=25)
                        checks["senal"] = bool(r.read(2048))
                        r.close()
                    except urllib.error.HTTPError as e:
                        checks["senal"] = 300 <= e.code < 400
                    except Exception:
                        pass
                    if checks["senal"]:
                        break
            except Exception:
                checks["senal"] = False
            try:
                checks["now_playing_fresco"] = (time.time() - os.path.getmtime(NP)) < 15 * 60
            except Exception:
                checks["now_playing_fresco"] = False
            try:
                import shutil
                checks["disco_gb_libres"] = round(shutil.disk_usage("/").free / 2**30, 1)
                checks["disco_ok"] = checks["disco_gb_libres"] > 2
            except Exception:
                checks["disco_ok"] = False
            ok = checks.get("senal") and checks.get("now_playing_fresco") and checks.get("disco_ok")
            return self._json(200 if ok else 503, {"ok": bool(ok), "checks": checks})
        if self.path.split("?")[0] == "/stream-config":
            try:
                body = open("/opt/subwave/state/stream-config.json", "rb").read()
            except Exception:
                body = b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split("?")[0] == "/geo":
            ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
            pais = geo_pais(ip)
            permitido = True if pais is None else (pais in GEO_PERMITIDOS)
            body = json.dumps({"pais": pais, "permitido": permitido}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split("?")[0] == "/programa":
            now = __import__("datetime").datetime.now(ZoneInfo("America/New_York"))
            sh = show_en_el_aire(now)
            hoy = (now.weekday() + 1) % 7
            dia_de = lambda s_: (s_["dias"][0] if len(s_.get("dias", [])) < 7 else None)
            semana = [{"id": x["id"], "nombre": x["nombre"], "desc": x.get("desc", ""),
                       "dias": x.get("dias", []), "desde": x["desde"], "hasta": x["hasta"]}
                      for x in parrilla_shows()]
            ahora = None
            if sh:
                ahora = {"id": sh["id"], "nombre": sh["nombre"], "desc": sh.get("desc", ""),
                         "hasta": "%02d:00" % sh["hasta"]}
            # Linea de tiempo de HOY ya resuelta (los especiales pisan al
            # show base), como dia radial: de 6am a 6am.
            import datetime as _dt
            start = now.replace(minute=0, second=0, microsecond=0, hour=6)
            if now.hour < 6:
                start -= _dt.timedelta(days=1)
            segs = []
            for i in range(24):
                t = start + _dt.timedelta(hours=i)
                x = show_en_el_aire(t)
                sid = x["id"] if x else None
                if segs and segs[-1]["id"] == sid:
                    segs[-1]["hasta"] = (t.hour + 1) % 24
                else:
                    segs.append({"id": sid, "nombre": x["nombre"] if x else "DJ Kultura",
                                 "desc": x.get("desc", "") if x else "",
                                 "desde": t.hour, "hasta": (t.hour + 1) % 24})
            return self._json(200, {"ahora": ahora, "hoy": hoy, "hoy_lista": segs, "semana": semana})
        if self.path.split("?")[0] == "/nowplaying":
            # "Ahora suena" SINCRONIZADO con lo que el oyente OYE: Live365
            # emite con buffer, asi que el titulo correcto es el de SU reloj
            # (su API publica current-track), no el del estudio. Si su API
            # falla, cae al dato de produccion sin drama. Cache 8s.
            global _np_cache
            now = time.time()
            if _np_cache and now - _np_cache[0] < 3:
                return self._json(200, _np_cache[1])
            # Reloj: el crudo de produccion con retraso fijo = lo que el
            # oyente OYE por Live365 (medido ~34s estable). En modo local
            # (desvio) no hay buffer: retraso 0.
            # Fuente de verdad del modo: el stream-config que obedecen los
            # reproductores (stream_mode.txt quedo obsoleto y desincronizado).
            try:
                cfg = json.load(open("/opt/subwave/state/stream-config.json"))
                modo = "live365" if "live365" in (cfg.get("primario") or "") else "local"
            except Exception:
                modo = "live365"
            objetivo = now - (_np_delay() if modo == "live365" else 0)
            raw = {}
            for ts, snap in reversed(_np_hist):
                if ts <= objetivo:
                    raw = json.loads(json.dumps(snap))
                    break
            if not raw and _np_hist:
                raw = json.loads(json.dumps(_np_hist[0][1]))
            if not raw:
                try:
                    raw = json.load(urllib.request.urlopen(
                        "https://kulturaradio.com/api/now-playing-raw", timeout=8))
                except Exception:
                    raw = {}
            if isinstance(_np_oyentes, int):
                raw.setdefault("listeners", {})["current"] = _np_oyentes
                ctx = raw.setdefault("context", {})
                ctx.setdefault("listeners", {})["count"] = _np_oyentes
            # Plan B de caratulas: si Live365 no dio arte, buscar directo en
            # iTunes Search (gratis, sin llave). Cache por cancion para no
            # repetir busquedas; None cacheado = ya se busco y no hay.
            np = raw.get("nowPlaying") or {}
            if np.get("title") and not np.get("art"):
                k = (np.get("title", "").lower(), (np.get("artist") or "").lower())
                if k in _art_cache:
                    if _art_cache[k]:
                        np["art"] = _art_cache[k]
                else:
                    try:
                        import urllib.parse as _up
                        q = _up.urlencode({"media": "music", "limit": 1,
                                           "term": "%s %s" % (np.get("artist") or "", np["title"])})
                        it = json.load(urllib.request.urlopen(
                            "https://itunes.apple.com/search?" + q, timeout=6))
                        res = (it.get("results") or [{}])[0]
                        art = (res.get("artworkUrl100") or "").replace("100x100", "512x512")
                        _art_cache[k] = art if "mzstatic.com" in art else None
                        if len(_art_cache) > 500:
                            _art_cache.clear()
                        if _art_cache[k]:
                            np["art"] = _art_cache[k]
                    except Exception as e2:
                        log("itunes art error: %r" % e2)
                        _art_cache[k] = None
            global _np_last_good
            if (raw.get("nowPlaying") or {}).get("title"):
                _np_last_good = raw
            elif _np_last_good:
                # Parpadeo de upstream: mejor el ultimo dato bueno que un vacio
                # que la app pinta como "Kultura Radio" pelado.
                raw = _np_last_good
            _np_cache = (now, raw)
            return self._json(200, raw)
        if self.path.startswith("/songs"):
            # Autocompletado del catalogo para la app: busqueda directa en
            # Navidrome (sin LLM). Publico via Caddy /api/songs.
            import urllib.parse as _up
            q = _up.parse_qs(_up.urlparse(self.path).query).get("q", [""])[0][:60].strip()
            if len(q) < 2:
                return self._json(200, {"songs": []})
            try:
                import hashlib as _h, random as _r
                pw = E.get("NAVIDROME_PASS", "")
                salt = "%016x" % _r.getrandbits(64)
                tok = _h.md5((pw + salt).encode()).hexdigest()
                qs = _up.urlencode({"u": "kultura", "t": tok, "s": salt, "v": "1.16.1",
                                    "c": "app-search", "f": "json", "query": q, "songCount": 8,
                                    "artistCount": 0, "albumCount": 0})
                d = json.load(urllib.request.urlopen(
                    "http://127.0.0.1:4533/rest/search3?" + qs, timeout=10))
                songs = d["subsonic-response"].get("searchResult3", {}).get("song", []) or []
                out, seen = [], set()
                for x in songs:
                    k = (x.get("title", "").lower(), x.get("artist", "").lower())
                    if k in seen: continue
                    seen.add(k)
                    out.append({"title": x.get("title", ""), "artist": x.get("artist", ""),
                                "genre": x.get("genre", "")})
                return self._json(200, {"songs": out})
            except Exception as e:
                log("songs search error: %r" % e)
                return self._json(200, {"songs": []})
        if self.path.startswith("/curador/voces/oir"):
            import urllib.parse as _up
            f = _up.parse_qs(_up.urlparse(self.path).query).get("f", [""])[0]
            rp = os.path.realpath(f)
            if rp.startswith(vw.DIR + os.sep) and os.path.isfile(rp):
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.end_headers()
                self.wfile.write(open(rp, "rb").read())
            else:
                self._json(404, {"error": "no"})
            return
        if self.path.startswith("/curador/voces"):
            import urllib.parse as _up
            qs = _up.parse_qs(_up.urlparse(self.path).query)
            return self._json(200, {"voces": vw.listar(
                cat=(qs.get("cat", [""])[0] or None),
                estado=(qs.get("estado", [""])[0] or None))})
        if self.path.startswith("/curador/lista"):
            import urllib.parse as _up
            qs = _up.parse_qs(_up.urlparse(self.path).query)
            q = (qs.get("q", [""])[0] or "").strip()[:60]
            genero = (qs.get("genero", [""])[0] or "").strip()
            offset = int(qs.get("offset", ["0"])[0] or 0)
            try:
                if q:
                    d = json.load(urllib.request.urlopen(
                        "http://127.0.0.1:4533/rest/search3?" + cur_nav_qs(
                            {"query": q, "songCount": 60, "artistCount": 0, "albumCount": 0}),
                        timeout=12))
                    songs = d["subsonic-response"].get("searchResult3", {}).get("song", []) or []
                elif genero:
                    d = json.load(urllib.request.urlopen(
                        "http://127.0.0.1:4533/rest/getSongsByGenre?" + cur_nav_qs(
                            {"genre": genero, "count": 100, "offset": offset}),
                        timeout=12))
                    songs = d["subsonic-response"].get("songsByGenre", {}).get("song", []) or []
                else:
                    songs = []
                filas = [cur_fila(x) for x in songs]
                reales = cur_paths_por_id([f["id"] for f in filas if f["id"]])
                for f in filas:
                    f["path"] = reales.get(f["id"], "")
                return self._json(200, {"songs": filas, "generos": CUR_GENEROS})
            except Exception as e:
                log("curador lista error: %r" % e)
                return self._json(500, {"error": str(e)})
        if self.path.startswith("/curador/oir"):
            import urllib.parse as _up
            sid = _up.parse_qs(_up.urlparse(self.path).query).get("id", [""])[0]
            if not sid:
                return self._json(400, {"error": "id"})
            try:
                r = urllib.request.urlopen(
                    "http://127.0.0.1:4533/rest/stream?" + cur_nav_qs({"id": sid, "format": "raw"}),
                    timeout=20)
                self.send_response(200)
                self.send_header("Content-Type", r.headers.get("Content-Type", "audio/mpeg"))
                self.end_headers()
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except Exception:
                pass
            return
        if self.path.startswith("/curador/papelera"):
            try:
                os.makedirs(CUR_PAPELERA, exist_ok=True)
                archivos = sorted(os.listdir(CUR_PAPELERA))
                return self._json(200, {"archivos": archivos, "total": len(archivos)})
            except Exception as e:
                return self._json(500, {"error": str(e)})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/telemetria":
            ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
            ahora = time.time()
            with LOCK:
                lst = [t for t in _telem_ip.get(ip, []) if ahora - t < 3600]
                if len(lst) >= 120:
                    _telem_ip[ip] = lst
                    self.send_response(429); self.end_headers(); return
                lst.append(ahora); _telem_ip[ip] = lst
                if len(_telem_ip) > 5000:
                    _telem_ip.clear()
            arch = "/opt/subwave/state/telemetria/%s.jsonl" % time.strftime("%Y-%m-%d")
            if os.path.exists(arch) and os.path.getsize(arch) > 20 * 1024 * 1024:
                self.send_response(204); self.end_headers(); return
            try:
                n = min(int(self.headers.get("Content-Length", 0)), 4000)
                d = json.loads(self.rfile.read(n) or b"{}")
                d = {k: (str(v)[:120] if not isinstance(v, (int, float, bool)) else v)
                     for k, v in list(d.items())[:15]}
                d["srv"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                os.makedirs("/opt/subwave/state/telemetria", exist_ok=True)
                with open("/opt/subwave/state/telemetria/%s.jsonl" % time.strftime("%Y-%m-%d"),
                          "a", encoding="utf-8") as f:
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")
            except Exception:
                pass
            self.send_response(204)
            self.end_headers()
            return
        if self.path in ("/voz-llamada", "/voz-llamada-fin", "/voz-llamada-grabacion"):
            import urllib.parse as _up
            n = int(self.headers.get("Content-Length", 0))
            form = _up.parse_qs(self.rfile.read(n).decode("utf-8", "ignore"))
            if self.path == "/voz-llamada-grabacion":
                threading.Thread(target=vw.llamada_grabacion, args=(form,), daemon=True).start()
                self.send_response(204)
                self.end_headers()
                return
            try:
                xml = vw.llamada_entrante(form) if self.path == "/voz-llamada" else vw.llamada_fin(form)
            except Exception as e:
                log("voz llamada twiml error: %r" % e)
                xml = b'<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'
            self.send_response(200)
            self.send_header("Content-Type", "text/xml")
            self.send_header("Content-Length", str(len(xml)))
            self.end_headers()
            self.wfile.write(xml)
            return
        if self.path == "/voz-whatsapp":
            import urllib.parse as _up
            n = int(self.headers.get("Content-Length", 0))
            form = _up.parse_qs(self.rfile.read(n).decode("utf-8", "ignore"))
            try:
                xml = vw.entrante(form)
            except Exception as e:
                log("voz entrante error: %r" % e)
                xml = b'<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
            self.send_response(200)
            self.send_header("Content-Type", "text/xml")
            self.send_header("Content-Length", str(len(xml)))
            self.end_headers()
            self.wfile.write(xml)
            return
        if self.path.startswith("/curador/") and \
                "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._json(415, {"error": "se requiere JSON"})
        if self.path.startswith("/curador/") and self.headers.get("Origin") and \
                self.headers.get("Origin") != "https://kulturaradio.com":
            return self._json(403, {"error": "origen no permitido"})
        if self.path == "/curador/voces/borrar":
            try:
                n = int(self.headers.get("Content-Length", 0))
                d = json.loads(self.rfile.read(n) or b"{}")
                return self._json(200, {"ok": vw.borrar(d.get("archivo", ""))})
            except Exception as e:
                return self._json(500, {"error": str(e)})
        if self.path == "/curador/editar":
            try:
                n = int(self.headers.get("Content-Length", 0))
                d = json.loads(self.rfile.read(n) or b"{}")
                path = cur_paths_por_id([d.get("id", "")]).get(d.get("id", ""), "")
                if not cur_path_ok(path):
                    return self._json(400, {"error": "ruta invalida"})
                from mutagen.easyid3 import EasyID3
                t = EasyID3(path)
                import csv as _csv
                w = _csv.writer(open("/opt/subwave/state/retag/cambios.csv", "a",
                                     newline="", encoding="utf-8"))
                for campo in ("genre", "artist", "title", "album"):
                    nuevo = (d.get(campo) or "").strip()
                    viejo = (t.get(campo) or [""])[0]
                    if nuevo and nuevo != viejo:
                        if campo == "genre" and nuevo not in CUR_GENEROS:
                            continue
                        t[campo] = nuevo
                        w.writerow([path, campo, viejo, nuevo + " (manual)"])
                t.save()
                log("curador edito: %s" % os.path.basename(path))
                return self._json(200, {"ok": True})
            except Exception as e:
                log("curador editar error: %r" % e)
                return self._json(500, {"error": str(e)})
        if self.path == "/curador/borrar":
            try:
                n = int(self.headers.get("Content-Length", 0))
                d = json.loads(self.rfile.read(n) or b"{}")
                path = cur_paths_por_id([d.get("id", "")]).get(d.get("id", ""), "")
                if not cur_path_ok(path):
                    return self._json(400, {"error": "ruta invalida"})
                os.makedirs(CUR_PAPELERA, exist_ok=True)
                destino = os.path.join(CUR_PAPELERA, os.path.basename(path))
                i = 1
                while os.path.exists(destino):
                    base, ext = os.path.splitext(os.path.basename(path))
                    destino = os.path.join(CUR_PAPELERA, "%s_%d%s" % (base, i, ext))
                    i += 1
                os.rename(path, destino)
                log("curador a papelera: %s" % os.path.basename(path))
                return self._json(200, {"ok": True})
            except Exception as e:
                return self._json(500, {"error": str(e)})
        if self.path == "/curador/vaciar":
            try:
                os.makedirs(CUR_PAPELERA, exist_ok=True)
                cuantos = 0
                for f in os.listdir(CUR_PAPELERA):
                    os.remove(os.path.join(CUR_PAPELERA, f))
                    cuantos += 1
                log("curador vacio papelera: %d" % cuantos)
                return self._json(200, {"ok": True, "borrados": cuantos})
            except Exception as e:
                return self._json(500, {"error": str(e)})
        if self.path == "/curador/rescan":
            def _rescan():
                try:
                    urllib.request.urlopen(
                        "http://127.0.0.1:4533/rest/startScan?" + cur_nav_qs({}), timeout=15)
                    time.sleep(25)
                    subprocess.run(["python3", "/opt/subwave/kultura_rotation.py"],
                                   capture_output=True, timeout=120)
                except Exception as e:
                    log("curador rescan error: %r" % e)
            threading.Thread(target=_rescan, daemon=True).start()
            return self._json(200, {"ok": True, "nota": "re-escaneo lanzado"})
        if self.path == "/anunciante":
            # Lead de la landing /anunciate. Sin backend de correo: queda en
            # anunciantes.log y Francisco lo revisa; cooldown suave por IP.
            ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
            now = time.time()
            with LOCK:
                if now - last_by_ip.get("ad:" + ip, 0) < 60:
                    return self._json(429, {"status": "error", "message": "Ya recibimos tu solicitud. Te contactamos pronto."})
                last_by_ip["ad:" + ip] = now
            try:
                n = int(self.headers.get("Content-Length", 0))
                if n > 4096:
                    return self._json(400, {"status": "error", "message": "Datos invalidos."})
                d = json.loads(self.rfile.read(n))
                lead = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "negocio": str(d.get("negocio", ""))[:120],
                        "contacto": str(d.get("contacto", ""))[:120],
                        "interes": str(d.get("interes", ""))[:60], "ip": ip}
                if not lead["negocio"] or not lead["contacto"]:
                    return self._json(400, {"status": "error", "message": "Falta el negocio o el contacto."})
                with open(STATE + "/anunciantes.log", "a", encoding="utf-8") as f:
                    f.write(json.dumps(lead, ensure_ascii=False) + "\n")
                log("ANUNCIANTE: %s / %s / %s" % (lead["negocio"], lead["contacto"], lead["interes"]))
                return self._json(200, {"status": "ok",
                    "message": "Recibido. Te contactamos en menos de 24 horas."})
            except Exception as e:
                log("anunciante error: %r" % e)
                return self._json(400, {"status": "error", "message": "Datos invalidos."})
        if self.path != "/dedi":
            return self._json(404, {"error": "not found"})
        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        now = time.time()
        with LOCK:
            if now - last_by_ip.get(ip, 0) < COOLDOWN_S:
                return self._json(429, {"status": "cooldown",
                    "message": "Ya mandaste una dedicatoria hace poquito, espera unos minutos."})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_B64 + 4096:
                return self._json(413, {"status": "rejected", "message": "Audio muy pesado."})
            data = json.loads(self.rfile.read(n))
            name = str(data.get("name") or "mi gente")[:24]
            song = str(data.get("song") or "")[:120]
            ext = str(data.get("ext") or "m4a").lower()
            if ext not in ("m4a", "mp3", "aac", "wav", "3gp", "caf"):
                ext = "m4a"
            audio = base64.b64decode(data["audio"])
        except Exception:
            return self._json(400, {"status": "rejected", "message": "Datos invalidos."})

        did = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        raw = "%s/raw-%s.%s" % (RECH, did, ext)
        mp3 = "%s/%s.mp3" % (DEDIS, did)
        open(raw, "wb").write(audio)

        dur = ffprobe_dur(raw)
        if not (DUR_MIN <= dur <= DUR_MAX):
            return self._json(200, {"status": "rejected",
                "message": "La grabacion debe durar entre 2 y 15 segundos."})

        # Normalizar volumen y convertir a mp3 (lo que sea que mande el telefono)
        conv = subprocess.run(["ffmpeg", "-y", "-i", raw, "-af",
                               "loudnorm=I=-16:TP=-1.5:LRA=11", "-ac", "1",
                               "-ar", "44100", "-b:a", "128k", mp3],
                              capture_output=True, timeout=60)
        if conv.returncode != 0 or not os.path.exists(mp3):
            log("ffmpeg fallo en %s" % did)
            return self._json(200, {"status": "rejected", "message": "No pude procesar el audio, intenta de nuevo."})

        text = transcribe(mp3)
        ok, motivo = moderate(text)
        log("dedi %s de '%s' (%.1fs) [%s] %s :: %s" % (did, name, dur, "OK" if ok else "RECHAZADA", motivo, text[:120]))
        with open(RECH + "/../dedis.log", "a") as f:
            f.write("%s\t-\t%s\t%s\t%s\t%s\n" % (did, name, "OK" if ok else "NO", motivo, text.replace("\t", " ")[:300]))

        if not ok:
            os.replace(mp3, "%s/%s.mp3" % (RECH, did))
            return self._json(200, {"status": "rejected",
                "message": "No pudimos poner tu dedicatoria esta vez. Intenta con otro mensaje."})

        os.remove(raw)
        with LOCK:
            last_by_ip[ip] = now
        cpath = "/var/sub-wave/dedis/%s.mp3" % did
        if song:
            threading.Thread(target=dedi_with_song, daemon=True, args=(cpath, song, name)).start()
            return self._json(200, {"status": "ok",
                "message": "¡Aprobada! Tu saludo sonará justo cuando arranque tu canción, en unos minutos. \U0001F399"})
        aired = play_on_air(cpath)
        return self._json(200, {"status": "ok",
            "message": "Tu dedicatoria va al aire en un momento. \U0001F399" if aired
                       else "Tu dedicatoria quedo en cola. \U0001F399"})

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    os.makedirs(RECH, exist_ok=True)
    if not OPENAI_KEY or not ANTHROPIC_KEY:
        log("FALTAN LLAVES en .env; el servicio rechazara todo")
    threading.Thread(target=ident_loop, daemon=True).start()
    log("dedi service en %s:%d" % (HOST, PORT))
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()
