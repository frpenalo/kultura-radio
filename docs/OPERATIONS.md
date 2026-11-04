# Kultura Radio · Operación

Guía para operar, desplegar, respaldar y recuperar la emisora. Todo corre en un
VPS (Ubuntu + Docker) bajo `/opt/subwave`. Ningún valor secreto aparece aquí:
las llaves viven solo en `/opt/subwave/.env` del servidor.

## Arquitectura en una página

```
Oyente (app Android / web)
   │
Caddy (HTTPS, rutas)  ── /api/*        → controller SUB/WAVE (contenedor)
   │                   ── /api/dedi, /api/geo, /api/health, /api/programa,
   │                      /api/now-playing, /api/curador/*, /api/voz-*,
   │                      /api/telemetria …  → kultura-dedi (172.18.0.1:8098)
   │                   ── /api/push/register → kultura-push (172.18.0.1:8099)
   │                   ── /stream.mp3        → broadcast (Liquidsoap/Icecast)
   │                   ── /                  → pwa/ (archivos estáticos)
Liquidsoap ──► Live365 (ingest, distribución con licencias)
   ▲  música: Navidrome (biblioteca) + kultura.m3u (rotación por bloques)
   ▲  voz: controller (DJ con Claude + TTS) y say.txt (dedicatorias, Minuto)
```

- **Contenedores** (docker compose, proyecto `subwave`): caddy, broadcast,
  controller, web, navidrome, ollama.
- **Servicios propios (systemd)**: `kultura-dedi` (dedicatorias, now-playing
  sincronizado, geo, curador, WhatsApp/buzón, telemetría, salud),
  `kultura-push` (tokens y envío de notificaciones), `kultura-minuto.timer`
  (El Minuto Kultura, cada 10 min decide si toca edición).
- **Cron** (`deploy/crontab.txt`): rotación cada 15 min, cápsulas (noticias,
  deportes, tránsito, frases, festivos, artista), limpieza de privacidad diaria
  (`limpieza_90d.py`, 9:15 UTC), refresco mensual de la base geo.

## Variables (`/opt/subwave/.env`, nunca en git)

| Variable | Para qué |
|---|---|
| ANTHROPIC_API_KEY | DJ, guiones, juez de contenido |
| OPENAI_API_KEY | Voces (ash/onyx), transcripción |
| ELEVENLABS_API_KEY | Voces de idents y tránsito |
| ADMIN_USER / ADMIN_PASS | Panel y API admin del controller |
| NAVIDROME_PASS / SUBSONIC_PASS | Biblioteca musical |
| DRIVENC_KEY | Tránsito (NCDOT) |
| TWILIO_ACCOUNT, TWILIO_SID, TWILIO_TOKEN | API Key "kultura" (descargar audios, enviar botones) |
| TWILIO_AUTH_TOKEN | Solo para verificar la firma de los webhooks |
| KR_WA_MENU_SID | Plantilla de botones de WhatsApp |

Cargar o rotar credenciales de Twilio sin que pasen por pantallas ni chats:
`ssh -t root@SERVIDOR /opt/subwave/poner-twilio.sh` (API Key) y
`/opt/subwave/poner-twilio-token.sh` (Auth Token).

## Desplegar cambios

| Qué cambió | Cómo aplicarlo | Corta el aire |
|---|---|---|
| Archivos de `controller-overrides/` (montados) | `docker restart sub-wave-controller` | No |
| Variables del controller en `.env` o compose | `docker compose -f docker-compose.yml -f docker-compose.navidrome.yml up -d controller` | No |
| `radio.liq` | validar `docker exec sub-wave-broadcast liquidsoap --check /etc/liquidsoap/radio.liq`, luego `docker restart sub-wave-broadcast` | Sí, ~20 s y reconexión con Live365 |
| `Caddyfile` | `docker exec sub-wave-caddy caddy validate …` y `caddy reload` | No (stream_close_delay protege a los oyentes) |
| Servicios propios | `systemctl restart kultura-dedi` o `kultura-push` | No (el stream no depende de ellos) |
| PWA | copiar a `/opt/subwave/pwa` y subir la versión de caché en `sw.js` | No |
| App Android | `deploy/build-local.sh` en `/opt/kultura-app` (horno, ~1 h) | No |

Regla: **siempre nombrar el servicio** en `docker compose up -d <servicio>`.
Un `up -d` sin nombre puede recrear `broadcast` y cortar el aire.

## Versiones de Docker fijas

Las imágenes están fijadas por digest en `deploy/docker-compose.navidrome.yml`
(no `:latest`). Los parches de `controller-overrides/` están hechos para esa
versión de SUB/WAVE. Para actualizar: bajar la imagen nueva, probar que los
parches siguen aplicando (el controller arranca y `/api/health` responde 200),
y recién ahí cambiar el digest. Rollback: volver al digest anterior y
`up -d <servicio>`.

## Salud y monitoreo

- `GET /api/health` (público, sin secretos): señal al aire, now-playing
  fresco, espacio en disco. UptimeRobot lo vigila cada 5 min.
- Reporte de vuelo de la app: `state/telemetria/AAAA-MM-DD.jsonl`.
- Logs: `journalctl -u kultura-dedi`, `docker logs sub-wave-controller`,
  `state/logs/radio.log` (Liquidsoap).

## Respaldo y restauración

Estado crítico a respaldar (fuera del servidor):

| Ruta | Contenido |
|---|---|
| `/opt/subwave/.env` | Llaves (respaldo cifrado, nunca en git) |
| `/opt/subwave/music/` | Biblioteca (copia maestra en el disco D: de Francisco) |
| `state/navidrome/` | Base de Navidrome (tags, ids) |
| `state/settings.json` | Configuración del DJ, prompts, personas |
| `state/parrilla/`, `state/skills/` | Programación y guiones del DJ |
| `push/tokens.json` | Teléfonos suscritos a notificaciones |
| `state/voz/`, `state/dedis/` | Audios de oyentes (respetar la política de privacidad) |
| `/opt/kultura-app` | Fábrica de la app con su historial git |

Restaurar: volver a copiar esas rutas, `docker compose … up -d` por servicio y
`systemctl restart kultura-dedi kultura-push`.

## Incidentes

**Se cayó el stream (silencio).** Mirar `/api/health`; si `senal` es false,
`docker logs sub-wave-broadcast --tail 50`; si Liquidsoap está colgado,
`docker restart sub-wave-broadcast` (~20 s). Si la biblioteca falla, Liquidsoap
entra solo a los mixes locales; si todo muere, suena la señal de emergencia.

**Se cayó Live365.** La app y la web alternan solas a la fuente de respaldo
definida en `state/stream-config.json`. Pendiente de licencias: confirmar con
Live365 si el respaldo propio está cubierto; si no lo está, el respaldo debe
mostrar un aviso en vez de música.

**Alguien tomó el aire por el puerto del DJ en vivo (8090).** Cambiar la
contraseña del harbor en `radio.liq` y reiniciar broadcast.

## Respaldo del código en GitHub

`bash /opt/subwave/armar_repo.sh` arma una copia sin secretos (reemplaza las
contraseñas por variables y verifica contra los valores reales del `.env`).
Esa copia es la que se sube a este repositorio.
