#!/usr/bin/env python3
# Capa central de PRONUNCIACION para Kultura Radio.
# Pasa cualquier texto que va a la voz (cápsulas) por Claude para: (1) reescribir
# CUALQUIER palabra/nombre en ingles a ortografia fonetica espanola (que suene como
# en ingles con voz espanola), y (2) corregir TODAS las tildes del espanol.
# Asi no hay que parchear palabra por palabra. Un solo lugar para la regla.
import json, urllib.request

def _key():
    try:
        for line in open("/opt/subwave/.env"):
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""

PROMPT = (
    "Eres un corrector para una voz de TEXTO-A-VOZ en ESPANOL (la voz solo sabe fonetica "
    "espanola). Te doy un texto que se leera en voz alta. Devuelve EXACTAMENTE el mismo texto, "
    "mismo sentido y mismo orden, pero corregido para que la voz lo diga bien:\n"
    "1) Cualquier palabra, sigla o nombre propio en INGLES (incluye nombres de CALLES, CARRETERAS, "
    "CONDADOS y CIUDADES): reescribelo en ortografia FONETICA espanola para que suene como en "
    "ingles. Ej: break->breik, Wake->Güeik, Peakway->Pikgüei, Raleigh->Rali, ICE->Ais, "
    "downtown->dauntaun, WhatsApp->Guasap, Facebook->Feisbuc, Orange->Órinch, Durham->Déram, "
    "Cary->Queri, Glenwood->Glénwud, Ligon Mill->Láigon Mil, Avenue->Avenu, Road->Roud.\n"
    "2) Numeros de autopista dilos en espanol: I-40->'la cuarenta', US-1->'la US uno'.\n"
    "3) Agrega TODAS las tildes correctas del espanol (tránsito, área, dirección, construcción, "
    "número, está, más).\n"
    "No agregues ni quites informacion. No expliques. Devuelve SOLO el texto corregido.\n\nTEXTO:\n")

def spanishify(text):
    key = _key()
    if not key or not text or not text.strip():
        return text
    body = json.dumps({"model": "claude-haiku-4-5", "max_tokens": 700,
                       "messages": [{"role": "user", "content": PROMPT + text}]}).encode("utf-8")
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        out = json.load(urllib.request.urlopen(req, timeout=60))["content"][0]["text"].strip()
        out = out.strip().strip('"').strip()
        return out or text
    except Exception:
        return text
