# 📻 Kultura Radio — la que nos une

**Emisora de radio online latina, 24/7, operada por un DJ de inteligencia artificial.**
Salsa, merengue, bachata, dembow y reggaetón para toda la comunidad latina del Triangle (Raleigh, NC) — sin bandera de ningún país.

> **English TL;DR:** Kultura Radio is a 24/7 AI-driven Latin internet radio station. An LLM DJ ("Diyei Kultura") announces tracks, reads local news/traffic/sports capsules, and takes listener requests — all in Caribbean Spanish. This repo contains the **Kultura layer**: the listener PWA, the genre-block rotation engine, the on-air content capsules, and the DJ brain overrides. It runs on top of [SUB/WAVE](https://github.com/perminder-klair/subwave) (MIT), a self-hosted AI radio platform. **No music is included** — you bring your own licensed library.

🔴 **En vivo:** [kulturaradio.com](https://kulturaradio.com)

---

## ¿Qué hace especial a esta emisora?

- 🎙️ **DJ de IA en español caribeño** — presenta canciones, hace *links* entre temas, saluda, y NUNCA inventa datos (género musical real de los tags, clima real de la API, sin "tormentas" imaginarias).
- 📰 **Cápsulas de contenido local**: noticias (Enlace Latino NC), tráfico en vivo (DriveNC/NCDOT), deportes, "Dato del Artista" (hechos reales de Wikipedia + canción del artista pegada), feriados.
- 🎶 **Rotación por bloques de género** estilo radio real: tandas de 5 canciones del mismo ritmo, repartidas parejo por franjas horarias (mañana merenguera, madrugada de baladas), con ventana anti-repetición.
- 📱 **PWA de oyente** con lock screen que se actualiza en vivo (la saga técnica de eso está abajo — vale la lectura).
- 📞 **Pedidos de oyentes** con matching difuso (typos, títulos parciales, "repite X") y respuesta del DJ al aire.
- 🛡️ **Resiliencia**: si la biblioteca musical (Navidrome) se cae, entran mixes locales curados; si todo muere, hay señal de emergencia. El DJ humano en vivo (Icecast harbor) siempre tiene prioridad.

## Arquitectura

```
Oyente (PWA / navegador)
   │
Caddy (HTTPS, routing)
   ├── /            → pwa/            (esta PWA estática)
   ├── /api/*       → SUB/WAVE controller (+ overrides de este repo)
   ├── /stream.mp3  → Liquidsoap → Icecast (radio.liq de este repo)
   └── /admin       → SUB/WAVE web (upstream)

Liquidsoap ← kultura.m3u ← rotation/kultura_rotation.py (cron)
     ↑ voz TTS ← controller ← capsules/*.py (cron) + LLM (Claude)
Navidrome (biblioteca musical, tags de género = la verdad)
```

**Base:** [SUB/WAVE](https://github.com/perminder-klair/subwave) de Parminder Klair (MIT) aporta el controller (DJ agent, TTS, colas), el broadcast (Liquidsoap/Icecast) y el panel admin. **Este repo es la capa Kultura** que lo convierte en una emisora latina real.

## Estructura del repo

| Carpeta | Qué es |
|---|---|
| `pwa/` | La app del oyente (HTML/JS vanilla, sin framework). Media Session API, service worker network-first, pedidos, instalable. |
| `rotation/` | `kultura_rotation.py`: motor de rotación por bloques/franjas. + filtro de canciones explícitas y guía de pronunciación del DJ. |
| `capsules/` | Cápsulas de contenido que salen al aire por cron: noticias, tráfico, deportes, artista, feriados, frases. |
| `controller-overrides/` | Archivos que se montan SOBRE el controller de SUB/WAVE (docker volume): el cerebro del DJ en español, anti-invento de géneros, TTS que no lee markdown, matcher de pedidos con Levenshtein. |
| `liquidsoap/` | `radio.liq` completo: crossfades, ducking de voz, jingles que no pisan al DJ, madrugada de baladas (0h–6h ET), fallback de bloques locales, DJ humano en vivo. |
| `deploy/` | Caddyfile (con las lecciones de caché aprendidas a sangre) y el compose de overrides. |

## Setup (resumen)

1. Despliega [SUB/WAVE](https://github.com/perminder-klair/subwave) con Docker + Navidrome apuntando a tu música (etiquetada por género — el tag ID3 es la fuente de verdad).
2. Monta los `controller-overrides/` sobre el controller (ver `deploy/docker-compose.navidrome.yml` como referencia del patrón).
3. Reemplaza el `radio.liq` del broadcast por el de `liquidsoap/`.
4. Sirve `pwa/` como raíz del dominio con el `deploy/Caddyfile`.
5. Programa `rotation/` y `capsules/` por cron (ver comentarios en cada script).
6. Copia `.env.example` → `.env` y llena tus credenciales.

### Variables de entorno

| Variable | Para qué |
|---|---|
| `ANTHROPIC_API_KEY` | El cerebro del DJ y las cápsulas (Claude) |
| `ELEVENLABS_API_KEY` | Voz cloud para cápsulas (opcional; hay fallback local) |
| `SUBSONIC_PASS` | Password del usuario de Navidrome que lee la biblioteca |
| `ADMIN_PASS` | Password admin del controller SUB/WAVE |
| `DRIVENC_KEY` | API key gratuita de DriveNC (NCDOT) para el tráfico |
| `LIVE_DJ_PASSWORD` | Password del harbor Icecast para DJ humano en vivo |

## Lecciones de guerra 🎖️ (léelas antes de pelear con iOS)

Cosas que esta emisora aprendió a golpes y que este código ya resuelve:

1. **iOS ignora `navigator.mediaSession.metadata = new MediaMetadata(...)` desde una página en segundo plano** (pantalla bloqueada). Pero **SÍ honra la mutación del objeto existente** (`metadata.title = ...`). La PWA hace ambas escrituras. En modo app instalada (standalone), iOS no repinta ni así — límite de Apple; la salida real es wrap nativo o HLS con metadata.
2. **Safari iOS cachea tu HTML por días** si no mandas `Cache-Control` (caché heurístico: 10% del tiempo desde `Last-Modified`). Tus oyentes quedan corriendo código viejo aunque recarguen. El Caddyfile manda `no-cache, must-revalidate` en el shell — siempre revalida (ETag → 304, barato).
3. **Service worker cache-first para el shell = deploys que nunca llegan.** El `sw.js` es network-first para `/`, `app.js` y manifest, con caché solo como fallback offline.
4. **El DJ LLM inventa géneros si no se los das**: pasa el género real del tag en CADA prompt (intro Y links) con la regla explícita de no inventar.
5. **El TTS lee los asteriscos de markdown en voz alta** ("asterisco asterisco"). Limpia el markdown en el chokepoint del TTS, no en cada generador.
6. **`getSongsByGenre` de Subsonic/Navidrome topa en 500 por request** — pagina con offset o tus conteos mienten.
7. **Detectar "placas" de DJ (voces incrustadas en mp3 piratas) con Whisper + keywords no funciona** — demasiados falsos positivos con letras de canciones. Ve reactivo: reporte humano + borrado.

## Lo que NO incluye este repo

- ❌ **Música.** Ni una canción. Consigue tu biblioteca y tus licencias de transmisión (SoundExchange/ASCAP/BMI/SESAC vía Live365, StreamLicensing o directo).
- ❌ Credenciales (todo por variables de entorno).
- ❌ El core de SUB/WAVE (instálalo del upstream; esto es la capa encima).

## Créditos y licencia

- **Kultura Radio** © 2026 Comandante Peñaló — [kulturaradio.com](https://kulturaradio.com). Código bajo licencia **MIT** (ver `LICENSE`).
- Construido sobre **[SUB/WAVE](https://github.com/perminder-klair/subwave)** © Parminder Klair, licencia MIT — gracias por la base espectacular. 🙏
- DJ con [Claude](https://claude.com) (Anthropic) · Voces [ElevenLabs](https://elevenlabs.io) + [Piper](https://github.com/rhasspy/piper) · Audio [Liquidsoap](https://www.liquidsoap.info) + [Icecast](https://icecast.org) · Biblioteca [Navidrome](https://www.navidrome.org).

---

*Hecho con 🎶 en Raleigh, NC — pa' toda mi gente latina.*
