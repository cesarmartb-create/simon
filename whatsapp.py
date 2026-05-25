import os
import requests
from dotenv import load_dotenv

load_dotenv()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")


def enviar_mensaje(numero, mensaje):
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": mensaje}
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()


def enviar_botones_si_no(numero, mensaje):
    """Envía un mensaje con botones Sí/No al estilo Abastible"""
    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": mensaje[:1024]},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": "btn_si", "title": "Sí"}},
                    {"type": "reply", "reply": {"id": "btn_no", "title": "No"}}
                ]
            }
        }
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        resultado = response.json()
        print(f"Respuesta botones: {resultado}")
        # Si falla, mandar como texto normal
        if "error" in resultado:
            print(f"Error enviando botones, enviando como texto: {resultado.get('error')}")
            enviar_mensaje(numero, mensaje)
        return resultado
    except Exception as e:
        print(f"Excepción enviando botones: {e}")
        enviar_mensaje(numero, mensaje)
        return None
