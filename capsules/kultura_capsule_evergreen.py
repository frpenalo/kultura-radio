#!/usr/bin/env python3
# Capsulas "evergreen" para Kultura Radio: Minuto Kultural (curiosidades) y
# La Frase del Dia (motivacion). Genera un POOL con Claude UNA vez y lo guarda;
# en cada salida el cron solo ESCOGE y airea (sin costo de Claude por salida).
# Cuando se agota el pool, se regenera solo. Gate de oyentes. Cron.
#   uso: kultura_capsule_evergreen.py <cultural|frase> [--gen N] [--force] [--dry]
import json, urllib.request, sys, base64, os
from kultura_pron import spanishify

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
ADMIN = "admin:" + env("ADMIN_PASS")
AUTH = "Basic " + base64.b64encode(ADMIN.encode()).decode()
BASE = "https://kulturaradio.com/api"
STATE_DIR = "/opt/subwave/state"

KINDS = {
    "cultural": {
        "file": STATE_DIR + "/capsule_cultural.json",
        "n": 30,
        "prompt": (
            "Eres el locutor de Kultura Radio (emisora latina del Triangle, Raleigh NC). "
            "Espanol caribeno dominicano, de TU (jamas vos). Genera %d capsulas distintas "
            "tipo 'Minuto Kultural': cada una un dato curioso, historia, tradicion, palabra o "
            "costumbre del Caribe, Republica Dominicana o Latinoamerica. Cada capsula empieza "
            "EXACTO con 'Minuto Kultural.' y cierra con algo breve como 'Eso es cultura, en "
            "Kultura Radio.'. MAXIMO 430 caracteres cada una. Solo palabras pronunciables: "
            "nada de simbolos, URLs, siglas ni numeros con signos (cifras en palabras). "
            "Si usas palabras o nombres en INGLES, escribelos foneticamente para una voz en espanol "
            "para que suenen como en ingles (ej. Raleigh='Rali', break='breik'). "
            "Escribe con TILDES correctas en español (Día, está, más, número, qué). "
            "Responde SOLO un arreglo JSON de %d strings, sin texto extra."),
    },
    "frase": {
        "file": STATE_DIR + "/capsule_frase.json",
        "n": 30,
        "prompt": (
            "Eres el locutor de Kultura Radio (emisora latina del Triangle, Raleigh NC). "
            "Espanol caribeno dominicano, de TU (jamas vos). Genera %d capsulas distintas "
            "tipo 'La Frase del Dia': cada una una frase motivadora, inspiradora o de buena "
            "vibra, calida y con sabor caribeno. Cada una empieza EXACTO con 'La Frase del Dia.' "
            "y cierra con algo breve como 'Dale con todo, en Kultura Radio.'. MAXIMO 300 "
            "caracteres cada una. Solo palabras pronunciables: nada de simbolos, URLs ni siglas. "
            "Si usas palabras o nombres en INGLES, escribelos foneticamente para una voz en espanol "
            "para que suenen como en ingles (ej. Raleigh='Rali', break='breik'). "
            "Escribe con TILDES correctas en español (Día, está, más, número, qué). "
            "Responde SOLO un arreglo JSON de %d strings, sin texto extra."),
    },
}

def fetch(url, auth=False, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    if auth:
        req.add_header("Authorization", AUTH)
    return urllib.request.urlopen(req, timeout=timeout)

def listeners():
    try:
        return json.load(fetch(BASE + "/listeners", auth=True)).get("current", 0) or 0
    except Exception:
        return None

def claude(prompt, max_tokens=3500):
    body = json.dumps({"model": "claude-haiku-4-5", "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))["content"][0]["text"].strip()

def generate(kind, n):
    txt = claude(KINDS[kind]["prompt"] % (n, n))
    s = txt.strip()
    if s.startswith("```"):
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
    arr = json.loads(s)
    # Evergreen es puro español → NO pasar por spanishify (metía tildes de más,
    # ej. "Kulturáh"/"Rádio"). El prompt ya foneticiza el raro inglés al generar.
    return [x.strip() for x in arr if isinstance(x, str) and x.strip()]

def load_pool(kind):
    try:
        return json.load(open(KINDS[kind]["file"]))
    except Exception:
        return {"items": [], "recent": []}

def save_pool(kind, pool):
    json.dump(pool, open(KINDS[kind]["file"], "w"), ensure_ascii=False)

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in KINDS:
        print("uso: <cultural|frase> [--gen N] [--force] [--dry]")
        return
    kind = sys.argv[1]
    force = "--force" in sys.argv
    dry = "--dry" in sys.argv
    regen = "--gen" in sys.argv

    pool = load_pool(kind)
    if regen or not pool.get("items"):
        n = KINDS[kind]["n"]
        if regen:
            i = sys.argv.index("--gen")
            if i + 1 < len(sys.argv) and sys.argv[i + 1].isdigit():
                n = int(sys.argv[i + 1])
        pool = {"items": generate(kind, n), "recent": []}
        save_pool(kind, pool)
        print("pool regenerado: %d capsulas" % len(pool["items"]))
        if regen:
            return  # --gen solo genera, no airea

    if not force:
        m = listeners()
        if not m:
            print("sin oyentes (%s) — omito capsula" % m)
            return

    items = pool["items"]
    recent = pool.get("recent", [])
    avail = [i for i in range(len(items)) if i not in recent]
    if not avail:
        recent = []
        avail = list(range(len(items)))
    idx = avail[0]
    script = items[idx].strip().strip('"')
    recent = (recent + [idx])[-(max(1, len(items) - 1)):]
    pool["recent"] = recent
    save_pool(kind, pool)

    print("=== %s [%d/%d] (%d chars) ===" % (kind, idx + 1, len(items), len(script)))
    print(script)
    if dry:
        return
    data = json.dumps({"text": script, "kind": "dj-speak", "mode": "raw"}).encode("utf-8")
    req = urllib.request.Request(BASE + "/dj/say", data=data,
        headers={"Content-Type": "application/json", "Authorization": AUTH})
    print("aireado:", json.load(urllib.request.urlopen(req, timeout=30)).get("ok"))

main()
