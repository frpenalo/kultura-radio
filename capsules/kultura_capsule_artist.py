#!/usr/bin/env python3
# "Dato del Artista" — OCASIONAL (cron 2x/dia). El DJ cuenta un dato REAL del
# artista (de Wikipedia, cero invento) y ENSEGUIDA encola una cancion de ese
# artista (via /dj/queue-track, sin intro doble). Solo featurea artistas que SI
# estan en la biblioteca. Pool pre-generado (--gen). Gate de oyentes.
#   uso: kultura_capsule_artist.py [--gen] [--force] [--dry]
import json, urllib.request, urllib.parse, sys, base64, hashlib, random, unicodedata

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
AUTH = "Basic " + base64.b64encode(("admin:" + env("ADMIN_PASS")).encode()).decode()
BASE = "https://kulturaradio.com/api"
POOL = "/opt/subwave/state/capsule_artist.json"
NAV = "http://127.0.0.1:4533"; NUSER = "kultura"; NPW = env("SUBSONIC_PASS")

ARTISTS = [
    "Marc Anthony", "Gilberto Santa Rosa", "Víctor Manuelle", "Eddie Santiago",
    "Frankie Ruiz", "Tito Rojas", "El Gran Combo de Puerto Rico", "Willie Colón",
    "Héctor Lavoe", "Jerry Rivera", "Oscar D'León", "La India",
    "Romeo Santos", "Aventura", "Prince Royce", "Juan Luis Guerra",
    "Frank Reyes", "Antony Santos", "Zacarías Ferreira", "Raulín Rodríguez",
    "Joe Veras", "Luis Vargas", "Héctor Acosta", "Monchy & Alexandra",
    "Wilfrido Vargas", "Fernando Villalona", "Sergio Vargas", "Eddy Herrera",
    "Toño Rosario", "Elvis Crespo", "Olga Tañón", "Milly Quezada",
    "Los Hermanos Rosario", "El Alfa", "Juan Gabriel",
]

def fetch(url, auth=None, timeout=20):
    h = {"User-Agent": "KulturaRadio/1.0"}
    if auth:
        h["Authorization"] = auth
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout)

def norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if c.isalnum() or c == " ").strip()

def sub_qs(extra):
    salt = "%016x" % random.getrandbits(64); tok = hashlib.md5((NPW + salt).encode()).hexdigest()
    b = {"u": NUSER, "t": tok, "s": salt, "v": "1.16.1", "c": "kr-artist", "f": "json"}; b.update(extra)
    return urllib.parse.urlencode(b)

def find_song(artist):
    try:
        url = NAV + "/rest/search3?" + sub_qs({"query": artist, "songCount": 30, "artistCount": 0, "albumCount": 0})
        d = json.load(fetch(url))
        songs = d["subsonic-response"].get("searchResult3", {}).get("song", []) or []
        a = norm(artist)
        m = [s for s in songs if a and (a in norm(s.get("artist")) or norm(s.get("artist")) in a)]
        return random.choice(m) if m else None
    except Exception:
        return None

def _summary(title):
    try:
        url = "https://es.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_"))
        d = json.load(fetch(url))
        if d.get("type") == "disambiguation":
            return None
        return d.get("extract") or None
    except Exception:
        return None

def wiki_extract(artist):
    ex = _summary(artist)
    if ex and len(ex) >= 60:
        return ex
    # fallback: buscar el articulo correcto (desambiguaciones, titulos distintos)
    try:
        u = "https://es.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
            "action": "query", "list": "search", "srsearch": artist + " músico cantante",
            "srlimit": 1, "format": "json"})
        hits = json.load(fetch(u)).get("query", {}).get("search", [])
        if hits:
            return _summary(hits[0]["title"])
    except Exception:
        pass
    return None

def listeners():
    try:
        return json.load(fetch(BASE + "/listeners", auth=AUTH, timeout=30)).get("current", 0) or 0
    except Exception:
        return None

def claude(prompt):
    body = json.dumps({"model": "claude-haiku-4-5", "max_tokens": 350,
                       "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))["content"][0]["text"].strip()

def generate():
    items = []
    for a in ARTISTS:
        ex = wiki_extract(a)
        if not ex or len(ex) < 60:
            print("  (sin wiki, salto)", a); continue
        prompt = (
            "Eres el locutor de Kultura Radio (emisora latina del Triangle, Raleigh NC). "
            "Español caribeño dominicano, de TÚ. Con estos DATOS REALES de Wikipedia sobre %s, "
            "escribe un 'Dato del Artista' CORTO, MÁXIMO 300 caracteres (texto-a-voz). Usa SOLO "
            "datos del texto (nacionalidad, año, logros) — NO inventes. Tono cálido y orgulloso. "
            "Empieza mencionando al artista. NO cierres con despedida (va a sonar su canción "
            "enseguida). Tildes correctas, sin símbolos ni URLs.\n\nDATOS:\n%s" % (a, ex[:1500]))
        try:
            items.append({"artist": a, "text": claude(prompt).strip().strip('"')}); print("  OK", a)
        except Exception as e:
            print("  claude error", a, e)
    json.dump({"items": items, "recent": []}, open(POOL, "w"), ensure_ascii=False)
    print("pool generado: %d artistas" % len(items))

def main():
    if "--gen" in sys.argv:
        generate(); return
    try:
        pool = json.load(open(POOL))
    except Exception:
        print("no hay pool, corre con --gen primero"); return
    items = pool.get("items", [])
    if not items:
        print("pool vacío"); return
    if "--force" not in sys.argv and not listeners():
        print("sin oyentes, omito"); return
    recent = pool.get("recent", [])
    order = [i for i in range(len(items)) if i not in recent] or list(range(len(items)))
    # busca el primer artista (en orden de rotacion) que SI tenga cancion en la biblioteca
    chosen, song = None, None
    for idx in order:
        s = find_song(items[idx]["artist"])
        if s:
            chosen, song = idx, s; break
    if chosen is None:
        print("ningún artista del pool tiene canción en la biblioteca"); return
    entry = items[chosen]
    pool["recent"] = (recent + [chosen])[-(max(1, len(items) - 1)):]
    json.dump(pool, open(POOL, "w"), ensure_ascii=False)
    script = entry["text"].rstrip() + " Y aquí te va, en Kultura Radio."
    print("=== DATO: %s → cancion: %s (%d chars) ===" % (entry["artist"], song.get("title"), len(script)))
    print(script)
    if "--dry" in sys.argv:
        return
    # 1) airea el dato
    d1 = json.dumps({"text": script, "kind": "dj-speak", "mode": "raw"}).encode("utf-8")
    r1 = urllib.request.Request(BASE + "/dj/say", data=d1, headers={"Content-Type": "application/json", "Authorization": AUTH})
    print("dato aireado:", json.load(urllib.request.urlopen(r1, timeout=30)).get("ok"))
    # 2) encola la cancion del artista (sin intro doble)
    d2 = json.dumps(song).encode("utf-8")
    r2 = urllib.request.Request(BASE + "/dj/queue-track", data=d2, headers={"Content-Type": "application/json", "Authorization": AUTH})
    print("cancion encolada:", json.load(urllib.request.urlopen(r2, timeout=30)).get("ok"))

main()
