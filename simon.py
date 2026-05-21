import os
import json
import glob
import anthropic
from flask import Flask, request
from dotenv import load_dotenv
import requests
from sendgrid import SendGridAPIClient
from sendgrid.mail import Mail

load_dotenv()

# ==========================================
# CONFIGURACIÓN DE CONEXIÓN
# ==========================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")

# ==========================================
# CARGA DE CLIENTES
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
def cargar_whitelist(archivo_whitelist):
    try:
        with open(archivo_whitelist, "r") as f:
            data = json.load(f)
            return {e["numero"]: e for e in data["empleados"]}
    except:
        return {}

def obtener_empleado(whitelist, numero):
    return whitelist.get(numero, None)

# ==========================================
# FUNCIÓN DE CORREO
# ==========================================
def enviar_correo(destinatario, copia, nombre_empleado, cargo, mensaje_original):
    remitente = "cesarmartb@gmail.com"
    asunto = f"Simón — Consulta de {nombre_empleado} ({cargo})"
    cuerpo = f"""Hola,

El siguiente colaborador tiene una consulta que requiere tu atención:

Nombre: {nombre_empleado}
Cargo: {cargo}
Mensaje: {mensaje_original}

Por favor responde directamente al colaborador.

Este mensaje fue generado automáticamente por Simón.
"""
    mensaje = Mail(
        from_email=remitente,
        to_emails=destinatario,
        subject=asunto,
        plain_text_content=cuerpo
    )
    if copia:
        mensaje.add_cc(copia)
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        sg.send(mensaje)
        print(f"Correo enviado a {destinatario}")
    except Exception as e:
        print(f"Error enviando correo: {e}")

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

    whitelist = cargar_whitelist(config["archivo_whitelist"])
    empleado = obtener_empleado(whitelist, numero)

    if not empleado:
        return

    nombre = empleado.get("nombre", "colaborador")
    cargo = empleado.get("cargo", "")
    notificar_a = empleado.get("notificar_a", "")
    copia_a = empleado.get("copia_a", "")

    system_prompt_personalizado = (
        config["system_prompt"] +
        f"\n\nEl colaborador que escribe se llama {nombre} y su cargo es {cargo}. "
        f"Salúdalo por su nombre. "
        f"Si su consulta requiere derivación, el responsable será notificado por correo."
    )

    cliente_api = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    respuesta = cliente_api.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        system=system_prompt_personalizado,
        messages=[
            {"role": "user", "content": mensaje_usuario}
        ]
    )

    texto_respuesta = respuesta.content[0].text
    enviar_mensaje(numero, texto_respuesta)

    if notificar_a:
        enviar_correo(notificar_a, copia_a, nombre, cargo, mensaje_usuario)

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
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
