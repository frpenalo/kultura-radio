#!/usr/bin/env python3
# Filtro "limpio" para Kultura Radio (radio familiar/comunitaria).
# Lee toda la biblioteca de Navidrome, Claude clasifica (nivel BALANCEADO) y
# escribe /opt/subwave/state/blocklist.json con los IDs explicitos.
# La rotacion (kultura_rotation.py) salta esos IDs. Correr a mano cuando se
# agregue musica nueva:  python3 kultura_clean_filter.py
import json, urllib.request, urllib.parse, hashlib, random, os

NAV = "http://127.0.0.1:4533"
USER = "kultura"
PW = os.environ.get("SUBSONIC_PASS", "")
GENRES = ["Salsa", "Merengue", "Reggaeton", "Dembow", "Bachata"]
BLOCKLIST = "/opt/subwave/state/blocklist.json"
CHUNK = 80

def env(k):
    try:
        for line in open("/opt/subwave/.env"):
            if line.startswith(k + "="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""
KEY = env("ANTHROPIC_API_KEY")

def sub_qs(extra):
    salt = "%016x" % random.getrandbits(64)
    token = hashlib.md5((PW + salt).encode()).hexdigest()
    base = {"u": USER, "t": token, "s": salt, "v": "1.16.1", "c": "kultura-clean", "f": "json"}
    base.update(extra)
    return urllib.parse.urlencode(base)

def get_songs(genre, count=500):
    url = NAV + "/rest/getSongsByGenre?" + sub_qs({"genre": genre, "count": count})
    try:
        d = json.load(urllib.request.urlopen(url, timeout=30))
        return d["subsonic-response"].get("songsByGenre", {}).get("song", []) or []
    except Exception as e:
        print("fetch error", genre, e)
        return []

def claude(prompt):
    body = json.dumps({"model": "claude-haiku-4-5", "max_tokens": 1500,
                       "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=90))["content"][0]["text"].strip()

PROMPT_HEAD = (
    "Eres moderador de contenido de una radio latina FAMILIAR y comunitaria (Kultura Radio). "
    "Nivel BALANCEADO: marca una cancion como EXPLICITA solo si es CLARAMENTE inapropiada para "
    "radio abierta de dia: groserias fuertes, contenido sexual explicito, o apologia cruda de "
    "drogas o violencia/narco. NO marques lo meramente romantico, sugerente, fiestero o de doble "
    "sentido leve que ya suena normal en la radio comercial latina. Juzga por titulo, artista y "
    "album (un album tipo 'Bachata de Cabaret' sugiere doble sentido, pero marca explicito SOLO si "
    "el titulo lo confirma). Te doy una lista numerada. Responde SOLO un arreglo JSON con los "
    "numeros de las EXPLICITAS, sin texto extra. Si ninguna, responde [].\n\n")

def classify(items):
    flagged = set()
    for i in range(0, len(items), CHUNK):
        chunk = items[i:i + CHUNK]
        lines = []
        for j, s in enumerate(chunk):
            lines.append("%d) %s - %s [%s]" % (j, s.get("title", ""), s.get("artist", ""), s.get("album", "")))
        try:
            out = claude(PROMPT_HEAD + "\n".join(lines)).strip()
            if out.startswith("```"):
                out = out.split("```")[1]
                if out.startswith("json"):
                    out = out[4:]
            idxs = json.loads(out)
            for k in idxs:
                if isinstance(k, int) and 0 <= k < len(chunk):
                    flagged.add(chunk[k].get("id"))
        except Exception as e:
            print("classify error chunk", i, e)
    return flagged

def main():
    seen, songs = set(), []
    for g in GENRES:
        for s in get_songs(g):
            sid = s.get("id")
            if sid and sid not in seen:
                seen.add(sid)
                songs.append(s)
    print("biblioteca leida:", len(songs))
    flagged = classify(songs)
    out = {"ids": sorted(flagged), "count": len(flagged), "total": len(songs)}
    json.dump(out, open(BLOCKLIST, "w"))
    print("EXPLICITAS marcadas: %d de %d (%.1f%%)" % (len(flagged), len(songs), 100.0 * len(flagged) / max(1, len(songs))))
    # muestra unas cuantas para revision
    by_id = {s.get("id"): s for s in songs}
    for sid in list(flagged)[:25]:
        s = by_id.get(sid, {})
        print("  -", s.get("title"), "/", s.get("artist"), "[", s.get("album"), "]")

main()
