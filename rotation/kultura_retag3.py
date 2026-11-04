#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Tercera pasada: los huerfanos donde el catalogo no confirmo la propuesta.
# Causa tipica: alias de credito (Claude dice "Marco Antonio Solis", el
# catalogo acredita "Los Bukis"). Cierre: busqueda por TITULO solo -> lista de
# versiones REALES del catalogo -> Claude elige cual es la de una coleccion de
# DJ dominicano (o ninguna). El artista siempre sale del catalogo: cero
# inventos. Cambios al mismo cambios.csv.
import csv, json, os, re, sys, time, urllib.parse, urllib.request
from mutagen.easyid3 import EasyID3

sys.path.insert(0, "/opt/subwave")
from kultura_retag import E, http_json, log, sim

DIR = "/opt/subwave/state/retag"
IDENT = DIR + "/identificados.jsonl"
SALIDA = DIR + "/reconfirmados.jsonl"
CAMBIOS = DIR + "/cambios.csv"
LOTE = 18

def candidatos_titulo(titulo):
    out = []
    term = urllib.parse.quote_plus(titulo)
    try:
        d = http_json("https://itunes.apple.com/search?media=music&limit=12&term=" + term)
        for r in d.get("results", []):
            if sim(titulo, r.get("trackName")) >= 0.7:
                out.append({"titulo": r.get("trackName"), "artista": r.get("artistName"),
                            "album": r.get("collectionName"),
                            "ano": (r.get("releaseDate") or "")[:4],
                            "sello": None, "fuente": "itunes"})
    except Exception:
        time.sleep(12)
    if len(out) < 3:
        try:
            d = http_json("https://api.deezer.com/search?q=" + term + "&limit=10")
            for r in d.get("data", []):
                if sim(titulo, r.get("title")) >= 0.7:
                    out.append({"titulo": r.get("title"),
                                "artista": (r.get("artist") or {}).get("name"),
                                "album": (r.get("album") or {}).get("title"),
                                "ano": "", "sello": None, "fuente": "deezer"})
        except Exception:
            pass
    # dedupe por artista (la primera version de cada artista basta)
    vistos, dedup = set(), []
    for c in out:
        k = (c["artista"] or "").lower()
        if k and k not in vistos:
            vistos.add(k)
            dedup.append(c)
    return dedup[:8]

def elegir(lote):
    bloques = []
    for i, (c, cands) in enumerate(lote):
        ops = "; ".join("%d=%s" % (j, x["artista"]) for j, x in enumerate(cands))
        bloques.append('%d. "%s" [genero: %s] versiones: %s'
                       % (i, c["clue"], c.get("genero") or "?", ops))
    prompt = (
        "Coleccion de un DJ dominicano (merengue, salsa, bachata, bolero, balada). Para "
        "cada titulo, elige CUAL de las versiones listadas (artistas reales de catalogo) "
        "es la que casi seguro tiene esta coleccion, guiandote por el genero del tag y "
        "por cual version es la clasica/popular en el publico latino. Si ninguna encaja "
        "o no conoces el tema, elige null.\n\n" + "\n".join(bloques) + "\n\n"
        'Devuelve SOLO JSON array: [{"i":0,"v":2},{"i":1,"v":null},...]')
    body = json.dumps({"model": "claude-sonnet-5-5", "max_tokens": 4000,
                       "thinking": {"type": "between_tools"},
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": E["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                 "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=180))
    texto = "".join(b.get("text", "") for b in d.get("content", []))
    m = re.search(r"\[.*\]", texto, re.S)
    return json.loads(m.group(0)) if m else []

def main():
    pend = []
    for l in open(IDENT, encoding="utf-8"):
        try:
            d = json.loads(l)
        except Exception:
            continue
        if d.get("estado") in ("catalogo-no-confirmo", "sin-identificar"):
            pend.append(d)
    hechas = set()
    if os.path.exists(SALIDA):
        for l in open(SALIDA, encoding="utf-8"):
            try:
                hechas.add(json.loads(l)["path"])
            except Exception:
                pass
    pend = [d for d in pend if d["path"] not in hechas]
    log("reconfirmacion: %d pendientes" % len(pend))
    reg = open(SALIDA, "a", encoding="utf-8")
    w = csv.writer(open(CAMBIOS, "a", newline="", encoding="utf-8"))
    resueltos = 0
    for i in range(0, len(pend), LOTE):
        lote = []
        for c in pend[i:i + LOTE]:
            # el genero del tag orienta la eleccion de version
            try:
                c["genero"] = (EasyID3(c["path"]).get("genre") or [""])[0]
            except Exception:
                c["genero"] = ""
            cands = candidatos_titulo(c["clue"])
            time.sleep(0.6)
            lote.append((c, cands))
        con_cands = [(c, k) for c, k in lote if k]
        res = {}
        if con_cands:
            try:
                res = {r.get("i"): r.get("v") for r in elegir(con_cands) if isinstance(r, dict)}
            except Exception as e:
                log("lote %d LLM ERROR %r" % (i // LOTE, e))
        idx = 0
        for c, cands in lote:
            estado = "sin-candidatos"
            if cands:
                v = res.get(idx)
                idx += 1
                if isinstance(v, int) and 0 <= v < len(cands):
                    el = cands[v]
                    try:
                        t = EasyID3(c["path"])
                        def pon(campo, nuevo):
                            viejo = (t.get(campo) or [""])[0]
                            if nuevo and str(nuevo).strip() not in ("", "?") and viejo != nuevo:
                                t[campo] = str(nuevo)
                                w.writerow([c["path"], campo, viejo, nuevo])
                        pon("artist", el["artista"])
                        pon("title", el["titulo"])
                        pon("album", el["album"])
                        if (el.get("ano") or "").isdigit():
                            pon("date", el["ano"])
                        t.save()
                        estado = "resuelto:" + el["fuente"]
                        resueltos += 1
                    except Exception:
                        estado = "error-tag"
                else:
                    estado = "llm-ninguna"
            reg.write(json.dumps({"path": c["path"], "clue": c["clue"], "estado": estado},
                                 ensure_ascii=False) + "\n")
        reg.flush()
        log("lote %d/%d (resueltos %d)" % (i // LOTE + 1, (len(pend) + LOTE - 1) // LOTE, resueltos))
    log("fin: %d resueltos de %d" % (resueltos, len(pend)))

if __name__ == "__main__":
    main()
