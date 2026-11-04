# -*- coding: utf-8 -*-
import os, json, shutil
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.id3 import ID3NoHeaderError

STAGE = "/opt/subwave/music_stage"
DEST = "/opt/subwave/music"
BAD = set(['/', '\\', ':', '*', '?', '"', '<', '>', '|'])

manifest = json.load(open(os.path.join(STAGE, "manifest.json"), encoding="utf-8"))
ok = 0
for m in manifest:
    src = os.path.join(STAGE, m["file"])
    if not os.path.exists(src):
        continue
    try:
        try:
            audio = EasyID3(src)
        except ID3NoHeaderError:
            mp = MP3(src)
            mp.add_tags()
            mp.save()
            audio = EasyID3(src)
        audio["artist"] = m["artist"]
        audio["title"] = m["title"]
        audio["album"] = m.get("album", "")
        audio["genre"] = m.get("genre", "")
        audio.save()
        genre_dir = os.path.join(DEST, m.get("genre", "Otros"))
        os.makedirs(genre_dir, exist_ok=True)
        base = m["artist"] + " - " + m["title"]
        safe = "".join(c for c in base if c not in BAD)[:120]
        shutil.move(src, os.path.join(genre_dir, safe + ".mp3"))
        ok += 1
    except Exception as ex:
        print("err", m["file"], repr(ex))
print("tagged + moved:", ok, "/", len(manifest))
