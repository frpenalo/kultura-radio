#!/usr/bin/env python3
# Motor de rotacion por BLOQUES para Kultura Radio.
# Arma auto.m3u en bloques ordenados: N canciones del mismo ritmo seguidas,
# luego cambia de ritmo. Liquidsoap lo reproduce EN ORDEN (mode=normal).
# Solo reescribe cuando cambia la franja (para no reiniciar la lista a cada rato).
# Corre por cron cada 15 min (revisa; reescribe solo si cambio la franja).
import json, urllib.request, urllib.parse, hashlib, random, os, sys
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/New_York")
except Exception:
    TZ = None

NAV_QUERY = "http://127.0.0.1:4533"
NAV_STREAM = "http://navidrome:4533"
USER = "kultura"
PW = os.environ.get("SUBSONIC_PASS", "")
AUTO = "/opt/subwave/state/kultura.m3u"  # propio: el controller pisa auto.m3u cada hora
STATE = "/opt/subwave/state/kultura_rotation_state.json"
BLOCKLIST = "/opt/subwave/state/blocklist.json"  # filtro "limpio" (IDs explicitos)
BLOCK_SIZE = 5       # canciones por bloque/tanda (mismo ritmo seguidas, ~18 min)
BUFFER = 140         # total de canciones en la lista (cubre la franja mas larga)
RECENT_KEEP = 300   # ventana de no-repetir (mas alto = tardan mas en volver)

def daypart(now):
    wd = now.weekday()
    h = now.hour
    # CONCEPTO (ago 2026): Kultura = musica TROPICAL. Salsa/merengue/bachata
    # dominan TODO el dia sin urbano. El reggaeton/dembow queda rezagado a UN
    # solo bloque nocturno: Zona Urbana, 7-8pm — fieles al concepto.
    if h == 19:
        return ("Zona Urbana", {"Reggaeton": 55, "Dembow": 45})
    if wd in (4, 5) and 20 <= h < 23:
        # Fiesta tropical de fin de semana — energia alta, cero urbano.
        return ("Reventon", {"Merengue": 45, "Salsa": 35, "Bachata": 20})
    if 6 <= h < 10:
        return ("Kultura Despierta", {"Merengue": 40, "Salsa": 40, "Bachata": 20})
    if 10 <= h < 15:
        return ("Kultura Mix", {"Salsa": 35, "Merengue": 35, "Bachata": 30})
    if 15 <= h < 19:
        return ("La Ruta", {"Merengue": 35, "Salsa": 30, "Bachata": 35})
    if 20 <= h < 23:
        return ("Sabor / Noche", {"Salsa": 40, "Merengue": 30, "Bachata": 30})
    return ("Kultura Nights", {"Bachata": 45, "Salsa": 45, "Merengue": 10})

def sub_qs(extra):
    salt = "%016x" % random.getrandbits(64)
    token = hashlib.md5((PW + salt).encode()).hexdigest()
    base = {"u": USER, "t": token, "s": salt, "v": "1.16.1", "c": "sub-wave", "f": "json"}
    base.update(extra)
    return urllib.parse.urlencode(base)

def get_songs(genre, count=500):
    url = NAV_QUERY + "/rest/getSongsByGenre?" + sub_qs({"genre": genre, "count": count})
    try:
        d = json.load(urllib.request.urlopen(url, timeout=30))
        return d["subsonic-response"].get("songsByGenre", {}).get("song", []) or []
    except Exception as e:
        print("genre fetch error", genre, e)
        return []

def esc(s):
    return (s or "").replace('"', "").replace("\n", " ").replace(":", " ").strip()

def stream_uri(sid):
    return "subhttp:" + NAV_STREAM + "/rest/stream?" + sub_qs({"id": sid, "format": "raw"})

def annotate(s):
    f = ['title="%s"' % esc(s.get("title")), 'artist="%s"' % esc(s.get("artist")),
         'album="%s"' % esc(s.get("album")), 'subsonic_id="%s"' % s.get("id"),
         'genre="%s"' % esc(s.get("genre"))]
    return "annotate:" + ",".join(f) + ":" + stream_uri(s.get("id"))

def main():
    now = datetime.now(TZ) if TZ else datetime.now()
    name, weights = daypart(now)
    try:
        st = json.load(open(STATE))
    except Exception:
        st = {"daypart": None, "recent": []}
    recent = st.get("recent", [])
    recent_set = set(recent)

    force = ("--force" in sys.argv) or (not os.path.exists(AUTO)) or (st.get("daypart") != name)
    if not force:
        print("misma franja (%s), no reescribo" % name)
        return

    try:
        block_ids = set(json.load(open(BLOCKLIST)).get("ids", []))
    except Exception:
        block_ids = set()

    pools = {}
    for g in weights:
        p = [s for s in get_songs(g) if s.get("id") not in block_ids]
        random.shuffle(p)
        pools[g] = p

    def take_block(pool):
        block = []
        for s in list(pool):
            sid = s.get("id")
            if sid and sid not in seq_ids and sid not in recent_set:
                block.append(s); seq_ids.add(sid); pool.remove(s)
                if len(block) >= BLOCK_SIZE: break
        if len(block) < BLOCK_SIZE:  # sin frescas, completa con lo que haya
            for s in list(pool):
                sid = s.get("id")
                if sid and sid not in seq_ids:
                    block.append(s); seq_ids.add(sid); pool.remove(s)
                    if len(block) >= BLOCK_SIZE: break
        return block

    # Reparte BLOQUES por genero segun peso, lo mas espaciados posible (sin
    # ping-pong): cada genero hace su tanda y se recorren todos antes de repetir.
    seq, seq_ids = [], set()
    genres = list(weights)
    n_blocks = max(len(genres), BUFFER // BLOCK_SIZE)
    total_w = sum(weights.values()) or 1
    counts = {g: max(1, round(n_blocks * weights[g] / total_w)) for g in genres}

    # orden de tandas: INTERCALADO PAREJO. Antes ponia los generos pesados al
    # frente (front-loaded) y los livianos al final; como una franja solo alcanza
    # a reproducir ~la mitad de la lista, la cola casi nunca sonaba y se oia puro
    # salsa/merengue. Ahora reparto cada genero a lo largo de TODA la lista:
    # en cada paso elijo el genero mas "atrasado" respecto a su cuota (menor
    # placed/target), evitando repetir el anterior. Asi cualquier tramo que suene
    # trae la mezcla con los pesos correctos.
    order, placed, last_g = [], {g: 0 for g in genres}, None
    total_blocks = sum(counts.values())
    for _ in range(total_blocks):
        cand = [g for g in genres if placed[g] < counts[g]]
        if not cand:
            break
        pool_g = [g for g in cand if g != last_g] or cand
        g = min(pool_g, key=lambda x: (placed[x] / counts[x], -weights[x]))
        order.append(g); placed[g] += 1; last_g = g

    last_g = None
    for g in order:
        if len(seq) >= BUFFER:
            break
        block = take_block(pools[g])
        if not block:  # genero agotado: usa otro con stock, sin repetir el anterior
            alt = next((x for x in genres if x != last_g and pools[x]), None)
            if not alt:
                if all(len(p) == 0 for p in pools.values()):
                    break
                continue
            block = take_block(pools[alt]); g = alt
        if block:
            seq.extend(block)
            last_g = g

    lines = ["#EXTM3U"] + [annotate(s) for s in seq]
    open(AUTO, "w").write("\n".join(lines) + "\n")

    recent = (recent + [s.get("id") for s in seq])[-RECENT_KEEP:]
    json.dump({"daypart": name, "recent": recent}, open(STATE, "w"))
    print("[%s] %d canciones en bloques de %d (ritmos: %s)" % (name, len(seq), BLOCK_SIZE, list(weights)))

main()
