import os
import anthropic
from flask import Flask, request
from dotenv import load_dotenv
import requests
import json

# Carga las variables del archivo .env
load_dotenv()

# ==========================================
# CONFIGURACIÓN GENERAL
# Modifica aquí los datos de conexión
# ==========================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

# ==========================================
# SECCIÓN: PERSONAL Y DERIVACIONES
# Modifica aquí cuando cambie el equipo
# ==========================================
ENCARGADOS = {
    "operaciones": {
        "nombre": "Carolina",
        "numero": "56912345678"
    },
    "administrativo": {
        "nombre": "Kathy",
        "numero": "56912345679"
    },
    "cumplimiento": {
        "nombre": "Nayarhet",
        "numero": "56912345680"
    }
}

# ==========================================
# SECCIÓN: PERSONALIDAD DE SIMÓN
# Modifica aquí cómo se presenta y responde
# ==========================================
SYSTEM_PROMPT = """Eres Simón, el asistente virtual del equipo de farmacias.
Tu rol es escuchar al colaborador, entender su consulta o inquietud,
y derivarla al encargado correcto.

Tipos de consulta y a quién derivar:
- Operaciones, turnos, inventario, sucursal → Carolina
- Temas administrativos, contratos, documentos → Kathy
- Denuncias, cumplimiento, Ley Karin → Nayarhet

Reglas:
- Saluda con calidez pero de forma breve
- Nunca menciones marcas ni franquicias
- Si no entiendes la consulta, pide que la reformule
- Confirma siempre a quién vas a derivar antes de hacerlo
- Sé empático pero conciso
"""

# ==========================================
# LISTA BLANCA DE NÚMEROS AUTORIZADOS
# El archivo numeros.txt es mantenido por Kathy
# ==========================================
def cargar_numeros_autorizados():
    try:
        with open("numeros.txt", "r") as f:
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
    numeros_autorizados = cargar_numeros_autorizados()

    if numero not in numeros_autorizados:
        return  # Número no autorizado, Simón no responde

    cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    respuesta = cliente.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": mensaje_usuario}
        ]
    )

    texto_respuesta = respuesta.content[0].text
    enviar_mensaje(numero, texto_respuesta)

# ==========================================
# SERVIDOR WEBHOOK (recibe mensajes de WhatsApp)
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
    app.run(port=5050, debug=True)