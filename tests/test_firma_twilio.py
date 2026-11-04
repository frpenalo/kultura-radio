# -*- coding: utf-8 -*-
# Prueba de servicios/twilio_firma.py. El vector esperado se genero con la
# libreria oficial de Twilio (twilio.request_validator.RequestValidator).
import importlib.util
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("tf", os.path.join(RAIZ, "servicios", "twilio_firma.py"))
tf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tf)

TOKEN = "12345"
URL = "https://kulturaradio.com/api/voz-whatsapp"
FORM = {"Body": ["hola"], "From": ["whatsapp:+15550000000"]}
OFICIAL = "69mewmm5K1OKjwFW0dkosE/d2eU="

fallos = 0
def chequear(nombre, ok):
    global fallos
    print(("PASA  " if ok else "FALLA ") + nombre)
    fallos += 0 if ok else 1

chequear("calcula igual que la libreria oficial", tf.calcular(TOKEN, URL, FORM) == OFICIAL)
chequear("acepta la firma correcta", tf.valida(TOKEN, URL, FORM, OFICIAL))
chequear("rechaza firma alterada", not tf.valida(TOKEN, URL, FORM, OFICIAL[:-2] + "xx"))
chequear("rechaza otro cuerpo", not tf.valida(TOKEN, URL, {"Body": ["chao"], "From": FORM["From"]}, OFICIAL))
chequear("rechaza otra URL", not tf.valida(TOKEN, URL + "x", FORM, OFICIAL))
chequear("rechaza sin token configurado", not tf.valida("", URL, FORM, OFICIAL))
chequear("rechaza sin firma", not tf.valida(TOKEN, URL, FORM, ""))
sys.exit(1 if fallos else 0)
