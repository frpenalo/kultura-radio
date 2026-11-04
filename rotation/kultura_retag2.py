#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Segunda pasada del re-tagueador: los HUERFANOS que la v2 salto por prudencia
# (artista "Desconocido"/vacio, sin titulo, o sin album). Flujo: Claude
# identifica el tema por el titulo/nombre de archivo (propone interprete y
# titulo canonico) -> el catalogo (iTunes/Deezer) CONFIRMA -> solo se adopta
# con match fuerte contra lo propuesto. Identificar sin confirmar NO escribe:
# cero inventos. Cambios al mismo state/retag/cambios.csv.
import csv, json, os, re, sys, time, urllib.request
from mutagen.easyid3 import EasyID3

sys.path.insert(0, "/opt/subwave")
from kultura_retag import (E, GENEROS, MATCH_ARTISTA, MATCH_TITULO, buscar_deezer,
                           buscar_itunes, log, norm)

MUSICA = "/opt/subwave/music"
DIR = "/opt/subwave/state/retag"
IDENT = DIR + "/identificados.jsonl"
CAMBIOS = DIR + "/cambios.csv"
LOTE = 40

def pista(path, t):
    tit = (t.get("title") or [""])[0].strip()
    if tit:
        return tit
    base = os.path.splitext(os.path.basename(path))[0]
    base = re.sub(r"^\d+[\s_.-]*", "", base)          # prefijos 001_
    return re.sub(r"[_]+", " ", base).strip()

def huerfanos():
    out = []
    for root, _, files in os.walk(MUSICA):
        for f in sorted(files):
            if not f.lower().endswith(".mp3"):
                continue
            fp = os.path.join(root, f)
            try:
                t = EasyID3(fp)
            except Exception:
                continue
            art = (t.get("artist") or [""])[0].strip()
            alb = (t.get("album") or [""])[0].strip()
            tit = (t.get("title") or [""])[0].strip()
            if art.lower() in ("", "desconocido") or not alb or not tit:
                if "Bloque" in f:                      # mixes de madrugada: no son canciones
                    continue
                out.append({"path": fp, "clue": pista(fp, t),
                            "genero": (t.get("genre") or [""])[0]})
    return out

def identificar(lote):
    filas = "\n".join('%d. "%s"  [genero del tag: %s]' % (i, c["clue"], c["genero"] or "?")
                      for i, c in enumerate(lote))
    prompt = (
        "Eres el curador musical de una radio tropical dominicana/caribena. Estos son "
        "titulos (o nombres de archivo) de canciones de una coleccion de DJ dominicano "
        "SIN el interprete en el tag. Identifica cada tema REAL y su interprete mas "
        "conocido en esa version (merengue/salsa/bachata/bolero clasicos sobre todo).\n\n"
        + filas + "\n\n"
        "Reglas: conf alta solo si reconoces el tema con seguridad; media si es tu mejor "
        "candidato razonable; baja si no lo reconoces (artista null). NO inventes nombres "
        "de artistas que no existen. El genero del tag te orienta la version (ej. el mismo "
        "tema existe en salsa y en bolero).\n"
        'Devuelve SOLO JSON array: [{"i":0,"artista":"...","titulo":"...","conf":"alta|media|baja"}]')
    body = json.dumps({"model": "claude-sonnet-5-5", "max_tokens": 6000,
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
    os.makedirs(DIR, exist_ok=True)
    hechos = set()
    if os.path.exists(IDENT):
        for l in open(IDENT, encoding="utf-8"):
            try:
                hechos.add(json.loads(l)["path"])
            except Exception:
                pass
    pend = [c for c in huerfanos() if c["path"] not in hechos]
    log("huerfanos pendientes: %d (ya procesados %d)" % (len(pend), len(hechos)))
    reg = open(IDENT, "a", encoding="utf-8")
    w = csv.writer(open(CAMBIOS, "a", newline="", encoding="utf-8"))
    resueltos = 0
    for i in range(0, len(pend), LOTE):
        lote = pend[i:i + LOTE]
        try:
            res = identificar(lote)
        except Exception as e:
            log("lote %d ERROR %r" % (i // LOTE, e))
            time.sleep(5)
            continue
        por_i = {r.get("i"): r for r in res if isinstance(r, dict)}
        for j, c in enumerate(lote):
            r = por_i.get(j) or {}
            art, tit, conf = r.get("artista"), r.get("titulo") or c["clue"], r.get("conf")
            estado = "sin-identificar"
            if art:
                m = None
                try:
                    m = buscar_itunes(art, tit)
                except Exception:
                    time.sleep(15)
                if not m or m["st"] < MATCH_TITULO or m["sa"] < MATCH_ARTISTA:
                    try:
                        m2 = buscar_deezer(art, tit)
                        if m2 and (not m or m2["st"] + m2["sa"] > m["st"] + m["sa"]):
                            m = m2
                    except Exception:
                        pass
                # El match se mide contra lo PROPUESTO por Claude: catalogo y
                # modelo tienen que estar de acuerdo para escribir.
                if m and m["st"] >= MATCH_TITULO and m["sa"] >= MATCH_ARTISTA:
                    try:
                        t = EasyID3(c["path"])
                        def pon(campo, nuevo):
                            viejo = (t.get(campo) or [""])[0]
                            if nuevo and str(nuevo).strip() not in ("", "?") and viejo != nuevo:
                                t[campo] = str(nuevo)
                                w.writerow([c["path"], campo, viejo, nuevo])
                        pon("artist", m.get("artista"))
                        pon("title", m.get("titulo"))
                        pon("album", m.get("album"))
                        if (m.get("ano") or "").isdigit():
                            pon("date", m["ano"])
                        pon("organization", m.get("sello"))
                        t.save()
                        estado = "resuelto:" + m["fuente"]
                        resueltos += 1
                    except Exception:
                        estado = "error-tag"
                else:
                    estado = "catalogo-no-confirmo"
                time.sleep(0.6)
            reg.write(json.dumps({"path": c["path"], "clue": c["clue"],
                                  "propuesta": art, "conf": conf, "estado": estado},
                                 ensure_ascii=False) + "\n")
        reg.flush()
        log("lote %d/%d (resueltos %d)" % (i // LOTE + 1, (len(pend) + LOTE - 1) // LOTE, resueltos))
    log("fin: %d resueltos de %d huerfanos" % (resueltos, len(pend)))

if __name__ == "__main__":
    main()
