import os
from flask import Flask, request
from dotenv import load_dotenv

from sesion import obtener_sesion
from conversacion import procesar_mensaje
from whatsapp import enviar_mensaje

load_dotenv()

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
LIMPIADOR_SECRET = os.getenv("LIMPIADOR_SECRET")

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
            # Detectar si es un texto normal o una respuesta de botón
            if mensaje.get("type") == "interactive":
                interactive = mensaje.get("interactive", {})
                if interactive.get("type") == "button_reply":
                    texto = interactive["button_reply"]["title"]
                    # Ignorar botones tardíos si no hay sesión activa
                    if not obtener_sesion(numero):
                        print(f"Botón tardío ignorado de {numero}: {texto}")
                        return "OK", 200
                else:
                    texto = mensaje.get("text", {}).get("body", "")
            else:
                texto = mensaje["text"]["body"]
            procesar_mensaje(numero, texto)
    except Exception as e:
        print(f"Error procesando mensaje: {e}")
    return "OK", 200


@app.route("/limpiar-sesiones", methods=["POST"])
def limpiar_sesiones_endpoint():
    secret_recibido = request.headers.get("X-Secret", "")
    if secret_recibido != LIMPIADOR_SECRET:
        return "Unauthorized", 401

    try:
        from limpiador_sesiones import limpiar_sesiones
        limpiar_sesiones()
        return {"status": "ok"}, 200
    except Exception as e:
        print(f"Error en limpieza: {e}")
        return {"status": "error", "message": str(e)}, 500


@app.route("/notificar-colaborador", methods=["POST"])
def notificar_colaborador_endpoint():
    secret_recibido = request.headers.get("X-Secret", "")
    if secret_recibido != LIMPIADOR_SECRET:
        return "Unauthorized", 401

    try:
        data = request.json or {}
        numero = data.get("numero", "")
        nombre = data.get("nombre", "")
        estado = data.get("estado", "")

        mensajes = {
            "en_gestion": f"Hola {nombre}, te informamos que tu consulta está siendo atendida. No es necesario que respondas este mensaje.",
            "cerrado": f"Hola {nombre}, tu consulta ha sido resuelta. Si tienes una nueva consulta, puedes escribirme cuando quieras.",
            "escalado": f"Hola {nombre}, tu consulta ha sido derivada a un nivel superior para asegurar que reciba la atención que corresponde. Te contactarán a la brevedad. No es necesario que respondas este mensaje.",
        }

        mensaje = mensajes.get(estado)
        if not mensaje:
            return {"status": "ok", "notificado": False}, 200

        enviar_mensaje(numero, mensaje)
        return {"status": "ok", "notificado": True}, 200
    except Exception as e:
        print(f"Error notificando colaborador: {e}")
        return {"status": "error", "message": str(e)}, 500


if __name__ == "__main__":
    from config import cargar_clientes
    clientes = cargar_clientes()
    print(f"Clientes cargados: {list(clientes.keys())}")
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
