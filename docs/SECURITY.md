# Kultura Radio · Seguridad

## Superficie pública

| Ruta | Quién la usa | Protección |
|---|---|---|
| `/stream.mp3` | Respaldo del reproductor | Pública (ver pendiente de licencias en OPERATIONS) |
| `/api/now-playing`, `/api/programa`, `/api/geo`, `/api/health`, `/api/stream-config` | App y web | Solo lectura, sin datos personales |
| `/api/request` (controller) | Pedidos de canciones | 1 cada 20 s y 8 por hora por IP |
| `/api/dedi` | Dedicatorias de voz | 6 intentos/hora y 1 aprobada cada 10 min por IP; tope de tamaño y duración; se revisa antes de procesar |
| `/api/push/register` | Notificaciones | Formato de token validado; 10 altas por día por IP; tope global 50 000 |
| `/api/anunciante` | Formulario de anunciantes | 1 por minuto por IP; máximo 4 KB |
| `/api/telemetria` | Reporte de vuelo de la app | 120 por hora por IP; archivo diario máximo 20 MB |
| `/api/voz-whatsapp`, `/api/voz-llamada*` | Webhooks de Twilio | Firma X-Twilio-Signature obligatoria; 64 KB; 30 mensajes/hora por número |
| `/api/curador/*`, `/curador` | Curaduría (Francisco) | Contraseña (basic auth) + solo JSON + origen kulturaradio.com |
| `/api/*` resto del controller | Admin SUB/WAVE | `requireAdmin` (basic auth) en todo lo que modifica |
| Puerto 8090 | DJ en vivo | Contraseña del harbor (no se publica en ninguna página) |

Los servicios propios escuchan solo en la red interna `172.18.0.1`; desde
internet únicamente se llega a ellos a través de Caddy, que fija la IP real del
cliente en `X-Forwarded-For`.

Procesamiento de audio: como máximo 2 audios a la vez (dedicatorias, WhatsApp
y buzón comparten el límite), para no saturar el servidor.

## Datos que se guardan

Detalle público en https://kulturaradio.com/privacidad.

| Dato | Dónde | Retención |
|---|---|---|
| Audios aprobados y sus transcripciones | `state/dedis/`, `state/voz/*/aprobados` | 90 días |
| Audios rechazados y sus transcripciones | `state/dedis/rechazadas`, `state/voz/*/rechazados` | 30 días |
| Telemetría de la app | `state/telemetria/` | 30 días |
| Copias en Twilio (grabaciones, audios de WhatsApp) | Twilio | 30 días (las borra la limpieza) |
| Tokens de notificaciones | `push/tokens.json` | Hasta que el teléfono desinstala la app |
| Contactos de anunciantes | `state/anunciantes.log` | Para responderles |

No se guardan IPs asociadas a dedicatorias. Los logs del sistema no incluyen
transcripciones ni nombres de oyentes. La limpieza diaria es
`rotation/limpieza_90d.py` (con `--simular` para ver qué borraría).

## Secretos

- Solo en `/opt/subwave/.env` (permisos 600). Nunca en el repositorio, la app
  ni la web.
- La copia que se sube a GitHub pasa por `armar_repo.sh`, que verifica contra
  los valores reales antes de subir.
- La descarga de audios solo acepta direcciones `https://*.twilio.com`, y la
  llave no viaja en redirecciones.

## Si encuentras un problema de seguridad

Escribe a hola@kulturaradio.com con el detalle. Proceso: confirmar el
problema, corregir, probar, y si hubo credenciales expuestas, rotarlas
(ver "Variables" en OPERATIONS.md).
