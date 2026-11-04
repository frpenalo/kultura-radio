#!/bin/bash
# Guarda las credenciales de Twilio de Kultura en /opt/subwave/.env sin
# mostrarlas en pantalla ni dejarlas en el historial.
set -e
ENV=/opt/subwave/.env
read -p  "Account SID (empieza con AC): " AC
read -p  "API Key SID (empieza con SK): " SK
read -sp "API Key Secret (no se ve al escribir): " SECRET; echo
case "$AC" in AC*) ;; *) echo "El Account SID debe empezar con AC"; exit 1;; esac
case "$SK" in SK*) ;; *) echo "El API Key SID debe empezar con SK"; exit 1;; esac
[ -n "$SECRET" ] || { echo "Falta el secret"; exit 1; }
cp "$ENV" "$ENV.bak-twilio"
grep -vE "^TWILIO_(SID|TOKEN|ACCOUNT)=" "$ENV.bak-twilio" > "$ENV"
printf "TWILIO_ACCOUNT=%s\nTWILIO_SID=%s\nTWILIO_TOKEN=%s\n" "$AC" "$SK" "$SECRET" >> "$ENV"
chmod 600 "$ENV"
systemctl restart kultura-dedi
echo "Listo: credenciales guardadas y servicio reiniciado. Avisale a Claude."
