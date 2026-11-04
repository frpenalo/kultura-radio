#!/usr/bin/env python3
# Detector de PLACAS (voces de DJ) en el audio. Extrae el inicio de cada
# cancion, lo transcribe con Whisper, y marca las que tienen senales de placa
# (nombres de DJ, "exclusivo", saludos, telefonos RD, etc.). NO borra nada:
# escribe una lista de sospechosas para revisar.
#   uso: /opt/whisper-venv/bin/python placa_detect.py [--limit N] [--secs S]
import os, subprocess, json, re, sys, unicodedata
from faster_whisper import WhisperModel

MUSIC = "/opt/subwave/music"
OUT = "/opt/subwave/state/placas_review.json"
SECS = 25
LIMIT = None
for i, a in enumerate(sys.argv):
    if a == "--limit": LIMIT = int(sys.argv[i + 1])
    if a == "--secs": SECS = int(sys.argv[i + 1])

# Senales de placa de DJ (texto hablado al inicio). Normalizado sin acentos.
KW = ["exclusiv", "konklase", "kon klase", "el que manda", "el que pega",
      "lo mas nuevo", "lo nuevo de", "para mi gente", "para to mi gente",
      "saludos a", "saludo a", "saludando", "vacilon", "mp3teca", "el lider",
      "arroba", "instagram", "siguem", "sigueme en", "dale dale", "dale que dale",
      "wepa", "klok", "discplay", "la planta", "version dj", "dj exclusiv",
      "el bueno de", "lo mato", "subelo", "aqui les traigo", "les presento",
      "directamente desde", "el imperio", "la mafia musical", "play music"]

def norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if not unicodedata.combining(c))

print("cargando modelo whisper (base, int8)...", flush=True)
model = WhisperModel("base", device="cpu", compute_type="int8")

def transcribe(path):
    tmp = "/tmp/_placa_clip.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-t", str(SECS), "-i", path,
                    "-ar", "16000", "-ac", "1", tmp], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    segs, _ = model.transcribe(tmp, language="es", beam_size=1)
    return " ".join(s.text for s in segs).strip()

files = []
for root, _, fs in os.walk(MUSIC):
    for f in fs:
        if f.lower().endswith(".mp3"):
            files.append(os.path.join(root, f))
files.sort()
if LIMIT:
    files = files[:LIMIT]

flagged = []
for i, p in enumerate(files):
    try:
        txt = transcribe(p)
    except Exception as e:
        print("  error", os.path.basename(p), e, flush=True); continue
    n = norm(txt)
    hits = [k for k in KW if k in n]
    if re.search(r"\b8(09|29|49)\b", n):
        hits.append("telefono-RD")
    if hits:
        flagged.append({"file": p, "hits": hits, "text": txt[:200]})
    if i % 25 == 0:
        print("%d/%d  sospechosas=%d" % (i, len(files), len(flagged)), flush=True)

json.dump(flagged, open(OUT, "w"), ensure_ascii=False, indent=1)
print("LISTO: %d canciones escaneadas, %d sospechosas -> %s" % (len(files), len(flagged), OUT), flush=True)
