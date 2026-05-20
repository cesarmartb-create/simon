import os
import json
import glob
import anthropic
from flask import Flask, request
from dotenv import load_dotenv
import requests

# Carga las variables del archivo .env
load_dotenv()

# ==========================================
# CONFIGURACIÓN DE CONEXIÓN
# ==========================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

# ==========================================
# CARGA DE CLIENTES
# Lee todos los archivos config_*.json
# ==========================================
def cargar_clientes():
    clientes = {}
    archivos = glob.glob("config_*.json")
    for archivo in archivos:
        with open(archivo, "r") as f:
            config = json.load(f)
            cliente_id = config["cliente_id"]
            clientes[cliente_id] = config
    return clientes

def obtener_cliente_activo():
    clientes = cargar_clientes()
    for cliente_id, config in clientes.items():
        if config.get("activo", False):
            return config
    return None

# ==========================================
# WHITELIST POR CLIENTE
# ==========================================
def cargar_numeros_autorizados(archivo_whitelist):
    try:
        with open(archivo_whitelist, "r") as f:
            return [line.strip() for line in f if line.strip()]
    except:
        return []

# ==========================================
# FUNCIONES DE WHATSAPP
# ==========================================
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

# ==========================================
# FUNCIÓN PRINCIPAL: PROCESAR MENSAJE
# ==========================================
def procesar_mensaje(numero, mensaje_usuario):
    config = obtener_cliente_activo()

    if not config:
        print("No hay cliente activo configurado")
        return

    numeros_autorizados = cargar_numeros_autorizados(config["archivo_whitelist"])

    if numero not in numeros_autorizados:
        return

    cliente_api = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    respuesta = cliente_api.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        system=config["system_prompt"],
        messages=[
            {"role": "user", "content": mensaje_usuario}
        ]
    )

    texto_respuesta = respuesta.content[0].text
    enviar_mensaje(numero, texto_respuesta)

# ==========================================
# SERVIDOR WEBHOOK
# ==========================================
app = Flask(__name__)

@app.route("/webhook", methods=["GET"])
def verificar_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        return challenge, 200
    return "Token inválido", 403

@app.route("/webhook", methods=["POST"])
def recibir_mensaje():
    data = request.json

    try:
        entry = data["entry"][0]
        cambio = entry["changes"][0]
        valor = cambio["value"]

        if "messages" in valor:
            mensaje = valor["messages"][0]
            numero = mensaje["from"]
            texto = mensaje["text"]["body"]
            procesar_mensaje(numero, texto)

    except Exception as e:
        print(f"Error procesando mensaje: {e}")

    return "OK", 200

# ==========================================
# INICIO DEL SERVIDOR
# ==========================================
if __name__ == "__main__":
    clientes = cargar_clientes()
    print(f"Clientes cargados: {list(clientes.keys())}")
    app.run(port=5050, debug=True)
