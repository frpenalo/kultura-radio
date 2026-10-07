#!/usr/bin/env python3
# Limpiador de metadata para Kultura Radio: quita la basura de pools piratas
# de TODOS los frames ID3, no solo del titulo. Los pools estampan su sitio web
# en ~18 frames (COMM, TIT3 subtitulo, TPE2 album-artist, USLT letra, TBPM,
# TPUB, W***...) y Navidrome anexa el subtitulo al titulo en el API Subsonic,
# por eso se veia "(WwW.Sitio.CoM)" al aire con el TIT2 limpio.
# Es parte del PIPELINE de subida (toda tanda nueva pasa por aqui al taguear)
# y sirve para barrer la biblioteca completa. Live365 exige metadata limpia.
#
#   uso: python3 kultura_tag_clean.py [ruta]            (dry-run: muestra cambios)
#        python3 kultura_tag_clean.py --apply [ruta]    (escribe los cambios)
#   ruta por defecto: /opt/subwave/music
#
# Importable: from kultura_tag_clean import clean_text
import os, re, sys

JUNK = [
    # (WwW.Sitio.CoM) / [sitio.net] con cualquier texto alrededor
    re.compile(r"[(\[{][^)\]}]*\.(?:com|net|org|info|biz|fm|tv)[^)\]}]*[)\]}]", re.I),
    # www.sitio.com suelto, con o sin http
    re.compile(r"(?:https?://)?w{2,3}\s*\.\s*\S+?\.(?:com|net|org|info|biz|fm|tv)\S*", re.I),
    # marcas de calidad de los pools
    re.compile(r"\(\s*bien\s*\)", re.I),
]
# Un frame cuyo texto ES basura (sitio web, con o sin www) se elimina completo.
JUNK_FULL = re.compile(r"(?:https?://|w{2,3}\s*\.)?\b[a-z0-9][a-z0-9-]*\.(?:com|net|org|info|biz|fm|tv)\b", re.I)
# Frames que NUNCA se tocan (binarios o rating de volumen).
SKIP_PREFIX = ("APIC", "RVA2", "PRIV", "MCDI", "GEOB")

def clean_text(s):
    if not s:
        return s
    t = s
    for rx in JUNK:
        t = rx.sub(" ", t)
    t = re.sub(r"[(\[{]\s*[)\]}]", " ", t)       # parentesis que quedaron vacios
    t = re.sub(r"\s*[/\\|@]+\s*$", "", t)        # separadores colgando al final
    t = re.sub(r"\s{2,}", " ", t).strip(" -_/|,;:")
    t = t.strip()
    return t if t else s                          # nunca dejar un tag vacio

def frame_text(frame):
    # texto representativo del frame: text para T*/COMM/USLT, url para W*
    v = getattr(frame, "url", None)
    if v:
        return str(v)
    v = getattr(frame, "text", None)
    if v is not None:
        try:
            return " ".join(str(x) for x in v)
        except TypeError:
            return str(v)
    return ""

def clean_file(fp, apply):
    """Devuelve lista de cambios [(frame, antes, despues|None)]; escribe si apply."""
    from mutagen.id3 import ID3
    try:
        tags = ID3(fp)
    except Exception:
        return None  # sin tag v2 o corrupto; se reporta como error arriba
    cambios = []
    for key in list(tags.keys()):
        if key.startswith(SKIP_PREFIX):
            continue
        txt = frame_text(tags[key])
        probe = key + " " + txt
        if JUNK_FULL.search(probe) and key.split(":")[0] not in ("TIT2", "TPE1", "TALB", "TCON"):
            # frame prescindible contaminado -> fuera completo
            cambios.append((key, txt[:60], None))
            if apply:
                tags.delall(key)
            continue
        if key.split(":")[0] in ("TIT2", "TPE1", "TALB"):
            new = clean_text(txt)
            if key.split(":")[0] == "TALB" and (new == txt) and JUNK_FULL.fullmatch(txt.strip()):
                # album que ES un sitio web completo: mejor sin album
                cambios.append((key, txt[:60], None))
                if apply:
                    tags.delall(key)
                continue
            if new != txt:
                cambios.append((key, txt[:60], new[:60]))
                if apply:
                    tags[key].text = [new]
    if apply and cambios:
        tags.save()
    return cambios

def main():
    apply = "--apply" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--apply"]
    root = args[0] if args else "/opt/subwave/music"

    tocados, frames, errores, mostrados = 0, 0, 0, 0
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if not fn.lower().endswith(".mp3"):
                continue
            fp = os.path.join(dirpath, fn)
            try:
                cambios = clean_file(fp, apply)
            except Exception:
                errores += 1
                continue
            if cambios is None:
                errores += 1
                continue
            if not cambios:
                continue
            tocados += 1
            frames += len(cambios)
            if mostrados < 12:
                mostrados += 1
                print("  %s" % os.path.relpath(fp, root))
                for key, old, new in cambios[:6]:
                    print("     %s: %s -> %s" % (key, old, "[ELIMINADO]" if new is None else new))
                if len(cambios) > 6:
                    print("     ... y %d frames mas" % (len(cambios) - 6))
    modo = "APLICADOS" if apply else "pendientes (dry-run, usa --apply)"
    print("\narchivos con cambios %s: %d | frames afectados: %d | errores: %d" % (modo, tocados, frames, errores))

if __name__ == "__main__":
    main()
