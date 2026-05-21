import os
import json
import glob
import anthropic
import sendgrid
from flask import Flask, request
from dotenv import load_dotenv
from datetime import datetime, timedelta
import requests
from sendgrid.helpers.mail import Mail

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
# MEMORIA DE CONVERSACIÓN
# ==========================================
ARCHIVO_CONVERSACIONES = "conversaciones_grupobaco.json"
HORAS_EXPIRACION = 24

def cargar_conversaciones():
    try:
        with open(ARCHIVO_CONVERSACIONES, "r") as f:
            return json.load(f)
    except:
        return {}

def guardar_conversaciones(conversaciones):
    with open(ARCHIVO_CONVERSACIONES, "w") as f:
        json.dump(conversaciones, f, ensure_ascii=False, indent=2)

def obtener_sesion(numero):
    conversaciones = cargar_conversaciones()
    sesion = conversaciones.get(numero)
    if not sesion:
        return None
    ultima = datetime.fromisoformat(sesion["ultima_actividad"])
    if datetime.now() - ultima > timedelta(hours=HORAS_EXPIRACION):
        return None
    return sesion

def guardar_sesion(numero, historial, pendiente_correo=False, notificar_a="", copia_a=""):
    conversaciones = cargar_conversaciones()
    conversaciones[numero] = {
        "historial": historial,
        "pendiente_correo": pendiente_correo,
        "notificar_a": notificar_a,
        "copia_a": copia_a,
        "ultima_actividad": datetime.now().isoformat()
    }
    guardar_conversaciones(conversaciones)

def cerrar_sesion(numero):
    conversaciones = cargar_conversaciones()
    if numero in conversaciones:
        del conversaciones[numero]
        guardar_conversaciones(conversaciones)

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
        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
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
# DETECTAR CONFIRMACIÓN
# ==========================================
def es_confirmacion(texto):
    texto = texto.lower().strip()
    palabras = ["si", "sí", "ok", "dale", "ya", "confirmo", "adelante", "por favor", "porfa", "claro", "bueno"]
    return any(p in texto for p in palabras)

def es_rechazo(texto):
    texto = texto.lower().strip()
    palabras = ["no", "nope", "cancel", "cancela", "olvida", "no gracias"]
    return any(p in texto for p in palabras)

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

    sesion = obtener_sesion(numero)

    if sesion and sesion.get("pendiente_correo"):
        if es_confirmacion(mensaje_usuario):
            primer_mensaje = sesion["historial"][0]["content"] if sesion["historial"] else mensaje_usuario
            enviar_correo(sesion["notificar_a"], sesion["copia_a"], nombre, cargo, primer_mensaje)
            cerrar_sesion(numero)
            enviar_mensaje(numero, f"Listo {nombre}, ya notifiqué al encargado. Te contactará a la brevedad.")
            return
        elif es_rechazo(mensaje_usuario):
            cerrar_sesion(numero)
            enviar_mensaje(numero, f"Entendido {nombre}, quedamos atentos si necesitas algo más.")
            return

    historial = sesion["historial"] if sesion else []
    historial.append({"role": "user", "content": mensaje_usuario})

    system_prompt_personalizado = (
        config["system_prompt"] +
        f"\n\nEl colaborador que escribe se llama {nombre} y su cargo es {cargo}. "
        f"Salúdalo por su nombre solo en el primer mensaje. "
        f"Si su consulta requiere derivación, pregúntale si confirma y dile que se notificará por correo."
    )

    cliente_api = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    respuesta = cliente_api.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        system=system_prompt_personalizado,
        messages=historial
    )

    texto_respuesta = respuesta.content[0].text
    historial.append({"role": "assistant", "content": texto_respuesta})

    derivacion_detectada = any(p in texto_respuesta.lower() for p in ["maría andrea", "kathy", "nayarhet", "derivar", "derivarte", "notificar"])

    guardar_sesion(
        numero,
        historial,
        pendiente_correo=derivacion_detectada,
        notificar_a=notificar_a,
        copia_a=copia_a
    )

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
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
