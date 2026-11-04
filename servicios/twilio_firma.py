# -*- coding: utf-8 -*-
# Verificacion de X-Twilio-Signature (algoritmo oficial de Twilio para POST de
# formulario): URL publica exacta + cada parametro ordenado por nombre, con sus
# valores ordenados, concatenado nombre+valor; HMAC-SHA1 con el Auth Token
# principal; base64. Comparacion en tiempo constante.
import base64
import hashlib
import hmac


def calcular(token, url, form):
    """form: dict nombre -> lista de valores (como lo da urllib.parse.parse_qs)."""
    datos = url + "".join(k + v for k in sorted(form) for v in sorted(form[k]))
    return base64.b64encode(hmac.new(token.encode(), datos.encode("utf-8"), hashlib.sha1).digest()).decode()


def valida(token, url, form, firma):
    if not token or not firma:
        return False
    return hmac.compare_digest(calcular(token, url, form), firma)
