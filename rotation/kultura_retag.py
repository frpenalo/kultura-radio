#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Re-tagueador v2 de la biblioteca: busca cada cancion en catalogos de internet
# (iTunes primero, Deezer de respaldo), adopta los metadatos canonicos (titulo,
# artista, album, ano, y sello cuando Deezer lo da) y Claude Sonnet decide el
# genero de PARRILLA (Salsa/Merengue/Bachata/...) viendo el hallazgo. Live365
# reporta titulo/artista/album: con esto queda completo. El tagueo original fue
# por carpeta de origen y miente (bachatas tagueadas Merengue, etc).
#
# Prudencia: el catalogo solo se adopta con match fuerte (titulo Y artista
# coinciden); el genero solo cambia con confianza alta (media solo rellena tags
# vacios/invalidos). Todo cambio queda en state/retag/cambios.csv
# (path,campo,viejo,nuevo) para revertir facil. Corridas reanudables (caches
# jsonl por archivo).
#
# Uso: kultura_retag.py            corrida completa (buscar -> decidir -> aplicar)
#      kultura_retag.py --aplicar  solo re-aplica decisiones ya tomadas
import csv, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from mutagen.easyid3 import EasyID3

MUSICA = "/opt/subwave/music"
DIR = "/opt/subwave/state/retag"
BUSQUEDAS = DIR + "/busquedas.jsonl"
DECISIONES = DIR + "/decisiones.jsonl"
CAMBIOS = DIR + "/cambios.csv"
GENEROS = ["Salsa", "Merengue", "Bachata", "Reggaeton", "Dembow", "Bolero", "Balada"]
LOTE = 50
MATCH_TITULO, MATCH_ARTISTA = 0.6, 0.5   # umbral para adoptar el catalogo

E = dict(l.strip().split("=", 1) for l in open("/opt/subwave/.env")
         if l.strip() and not l.startswith("#") and "=" in l)

def log(m):
    print(time.strftime("%H:%M:%S ") + m, flush=True)

def norm(s):
    s = unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[\(\[].*?[\)\]]", " ", s.lower())          # parentesis/corchetes
    s = re.sub(r"www\.\S+|\S+\.(com|net|org)\S*", " ", s)   # basura de sitios
    return re.sub(r"[^a-z0-9 ]+", " ", s)

def toks(s):
    return set(norm(s).split())

def sim(a, b):
    A, B = toks(a), toks(b)
    if not A or not B:
        return 0.0
    return len(A & B) / min(len(A), len(B))

def artista_principal(a):
    return re.split(r"\b(feat\.?|ft\.?|featuring|con|x)\b|,|&", a or "", 1,
                    re.IGNORECASE)[0].strip()

def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "KulturaRadio/1.0"})
    return json.load(urllib.request.urlopen(req, timeout=20))

def buscar_itunes(artista, titulo):
    term = urllib.parse.quote_plus((artista + " " + titulo).strip())
    d = http_json("https://itunes.apple.com/search?media=music&limit=8&term=" + term)
    mejor = None
    for r in d.get("results", []):
        st, sa = sim(titulo, r.get("trackName")), sim(artista, r.get("artistName"))
        if mejor is None or st + sa > mejor[0] + mejor[1]:
            mejor = (st, sa, r)
    if not mejor:
        return None
    st, sa, r = mejor
    return {"fuente": "itunes", "st": round(st, 2), "sa": round(sa, 2),
            "titulo": r.get("trackName"), "artista": r.get("artistName"),
            "album": r.get("collectionName"),
            "ano": (r.get("releaseDate") or "")[:4],
            "genero_tienda": r.get("primaryGenreName"), "sello": None}

def buscar_deezer(artista, titulo):
    q = urllib.parse.quote_plus((artista + " " + titulo).strip())
    d = http_json("https://api.deezer.com/search?q=" + q + "&limit=8")
    mejor = None
    for r in d.get("data", []):
        st = sim(titulo, r.get("title"))
        sa = sim(artista, (r.get("artist") or {}).get("name"))
        if mejor is None or st + sa > mejor[0] + mejor[1]:
            mejor = (st, sa, r)
    if not mejor:
        return None
    st, sa, r = mejor
    out = {"fuente": "deezer", "st": round(st, 2), "sa": round(sa, 2),
           "titulo": r.get("title"), "artista": (r.get("artist") or {}).get("name"),
           "album": (r.get("album") or {}).get("title"), "ano": "",
           "genero_tienda": None, "sello": None}
    try:
        alb = http_json("https://api.deezer.com/album/%s" % (r.get("album") or {}).get("id"))
        out["ano"] = (alb.get("release_date") or "")[:4]
        out["sello"] = alb.get("label")
        gd = ((alb.get("genres") or {}).get("data") or [])
        if gd:
            out["genero_tienda"] = gd[0].get("name")
    except Exception:
        pass
    return out

def biblioteca():
    out = []
    for root, _, files in os.walk(MUSICA):
        for f in sorted(files):
            if not f.lower().endswith(".mp3"):
                continue
            fp = os.path.join(root, f)
            try:
                t = EasyID3(fp)
                out.append({"path": fp,
                            "artist": (t.get("artist") or [""])[0],
                            "title": (t.get("title") or [""])[0],
                            "genero": (t.get("genre") or [""])[0]})
            except Exception:
                pass  # headers rotos: se quedan como estan
    return out

def cache_paths(archivo):
    done = set()
    if os.path.exists(archivo):
        for l in open(archivo, encoding="utf-8"):
            try:
                done.add(json.loads(l)["path"])
            except Exception:
                pass
    return done

def buscar():
    hechas = cache_paths(BUSQUEDAS)
    todas = [c for c in biblioteca() if c["path"] not in hechas]
    log("busqueda: pendientes %d (ya buscadas %d)" % (len(todas), len(hechas)))
    out = open(BUSQUEDAS, "a", encoding="utf-8")
    for i, c in enumerate(todas):
        art, tit = artista_principal(c["artist"]), c["title"]
        m = None
        if tit and art and art.lower() != "desconocido":
            try:
                m = buscar_itunes(art, tit)
            except Exception:
                time.sleep(20)
            if not m or m["st"] < MATCH_TITULO or m["sa"] < MATCH_ARTISTA:
                try:
                    m2 = buscar_deezer(art, tit)
                    if m2 and (not m or m2["st"] + m2["sa"] > m["st"] + m["sa"]):
                        m = m2
                except Exception:
                    pass
        out.write(json.dumps({"path": c["path"], "match": m}, ensure_ascii=False) + "\n")
        if i % 25 == 0:
            out.flush()
            log("busqueda %d/%d" % (i, len(todas)))
        time.sleep(0.55)   # respeto de rate limit (iTunes es el delicado)
    out.close()

def clasificar(lote):
    filas = []
    for i, c in enumerate(lote):
        extra = ""
        m = c.get("match")
        if m and m["st"] >= MATCH_TITULO and m["sa"] >= MATCH_ARTISTA:
            extra = "  [catalogo: genero=%s, album=%s, ano=%s]" % (
                m.get("genero_tienda") or "?", m.get("album") or "?", m.get("ano") or "?")
        filas.append('%d. "%s" — %s  [tag actual: %s]%s' % (
            i, c["title"] or "?", c["artist"] or "?", c["genero"] or "sin genero", extra))
    prompt = (
        "Eres el curador musical de una radio tropical dominicana/caribena. Para cada "
        "cancion, determina el genero REAL de la grabacion. Tienes el tag actual (puede "
        "estar MAL: se tagueo por carpeta) y, cuando hubo match, lo que dice el catalogo "
        "de la tienda (su genero es grueso, p.ej. 'Latin'; usalo como pista, no como ley).\n\n"
        + "\n".join(filas) + "\n\n"
        "Generos validos (exactos): " + ", ".join(GENEROS) + ".\n"
        "Reglas:\n"
        "- Merengue tipico/perico ripiao cuenta como Merengue.\n"
        "- Salsa romantica/erotica cuenta como Salsa (NO Bolero ni Balada).\n"
        "- Bolero = bolero clasico; Balada = balada pop romantica no bailable.\n"
        "- conf alta: conoces ESA cancion, o el artista es inequivoco de UN genero, o el "
        "catalogo lo deja claro. Con artistas de varios generos (Alex Bueno, Antony "
        "Santos, Juan Luis Guerra...) solo alta si conoces el tema especifico.\n"
        "- conf media: probable, no seguro. conf baja: no se. En media/baja, si el tag "
        "actual es valido, respetalo en tu respuesta.\n\n"
        "Devuelve SOLO un JSON array, sin texto extra: "
        '[{"i": 0, "genero": "Salsa", "conf": "alta"}, ...] con TODAS las filas.')
    body = json.dumps({
        "model": "claude-sonnet-5-5", "max_tokens": 6000,
        "thinking": {"type": "between_tools"},
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": E["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=180))
    texto = "".join(b.get("text", "") for b in d.get("content", []))
    m = re.search(r"\[.*\]", texto, re.S)
    return json.loads(m.group(0)) if m else []

def decidir():
    matches = {}
    for l in open(BUSQUEDAS, encoding="utf-8"):
        try:
            d = json.loads(l)
            matches[d["path"]] = d.get("match")
        except Exception:
            pass
    hechas = cache_paths(DECISIONES)
    todas = [dict(c, match=matches.get(c["path"]))
             for c in biblioteca() if c["path"] not in hechas]
    log("decision: pendientes %d (ya decididas %d)" % (len(todas), len(hechas)))
    out = open(DECISIONES, "a", encoding="utf-8")
    for i in range(0, len(todas), LOTE):
        lote = todas[i:i + LOTE]
        try:
            res = clasificar(lote)
        except Exception as e:
            log("lote %d ERROR %r — sigo con el proximo" % (i // LOTE, e))
            time.sleep(5)
            continue
        por_i = {r.get("i"): r for r in res if isinstance(r, dict)}
        for j, c in enumerate(lote):
            r = por_i.get(j) or {}
            g = r.get("genero") if r.get("genero") in GENEROS else None
            out.write(json.dumps({"path": c["path"], "artist": c["artist"],
                                  "title": c["title"], "viejo": c["genero"],
                                  "genero": g, "conf": r.get("conf", "baja")},
                                 ensure_ascii=False) + "\n")
        out.flush()
        log("decision lote %d/%d" % (i // LOTE + 1, (len(todas) + LOTE - 1) // LOTE))
        time.sleep(1)
    out.close()

def aplicar():
    matches = {}
    for l in open(BUSQUEDAS, encoding="utf-8"):
        try:
            d = json.loads(l)
            matches[d["path"]] = d.get("match")
        except Exception:
            pass
    cambios, errores = 0, 0
    nuevo_csv = not os.path.exists(CAMBIOS)
    w = csv.writer(open(CAMBIOS, "a", newline="", encoding="utf-8"))
    if nuevo_csv:
        w.writerow(["path", "campo", "viejo", "nuevo"])

    def pon(t, path, campo, nuevo):
        nonlocal cambios
        viejo = (t.get(campo) or [""])[0]
        if not nuevo or str(nuevo).strip() in ("", "?") or viejo == nuevo:
            return
        t[campo] = str(nuevo)
        w.writerow([path, campo, viejo, nuevo])
        cambios += 1

    for l in open(DECISIONES, encoding="utf-8"):
        try:
            d = json.loads(l)
        except Exception:
            continue
        path = d["path"]
        try:
            t = EasyID3(path)
        except Exception:
            errores += 1
            continue
        m = matches.get(path)
        if m and m["st"] >= MATCH_TITULO and m["sa"] >= MATCH_ARTISTA:
            pon(t, path, "title", m.get("titulo"))
            pon(t, path, "artist", m.get("artista"))
            pon(t, path, "album", m.get("album"))
            if (m.get("ano") or "").isdigit():
                pon(t, path, "date", m["ano"])
            pon(t, path, "organization", m.get("sello"))
        g, viejo, conf = d.get("genero"), d.get("viejo") or "", d.get("conf")
        # Solo confianza alta cambia un genero existente; media rellena invalidos.
        if g and g != viejo and (conf == "alta" or (viejo not in GENEROS and conf == "media")):
            pon(t, path, "genre", g)
        try:
            t.save()
        except Exception:
            errores += 1
    log("aplicados %d cambios de campo (%d archivos con error)" % (cambios, errores))

if __name__ == "__main__":
    os.makedirs(DIR, exist_ok=True)
    if "--aplicar" not in sys.argv:
        buscar()
        decidir()
    aplicar()
