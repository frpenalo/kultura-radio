# 🎙️ Conectarse EN VIVO a Kultura Radio

Cualquier DJ puede transmitir su show desde su casa/cabina — con su
computadora, su música y su programa de siempre. La radio IA se aparta sola
mientras el DJ está al aire y vuelve sola al desconectar.

## Programas compatibles
Cualquiera que transmita a **Icecast**: BUTT (gratis), Mixxx (gratis),
VirtualDJ, Serato, Traktor, OBS.

## Datos de conexión

| Campo        | Valor                    |
|--------------|--------------------------|
| Tipo/Server  | Icecast 2                |
| Host         | kulturaradio.com         |
| Puerto       | 8090                     |
| Mount        | live                     |
| Usuario      | source                   |
| Contraseña   | (la del `.env` LIVE_DJ_PASSWORD) |
| Códec        | MP3, 128 kbps, 44.1 kHz, estéreo |

Dale **Conectar** y en ~2 segundos estás al aire.

## Nombre del DJ en la app (opcional)
Para que la app muestre el nombre del show, escribe el nombre en el archivo
`state/live-dj-name.txt` del servidor antes del show:

```
echo "DJ Fulano" > /opt/subwave/state/live-dj-name.txt
```

Mientras el DJ está al aire, la app muestra un badge rojo **EN VIVO** y el
título que el programa del DJ envíe (metadata ICY). Al terminar, borra el
archivo (o déjalo; el default es "DJ en vivo").
