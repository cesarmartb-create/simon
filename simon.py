import os
import json
import glob
import anthropic
import sendgrid
from flask import Flask, request
from dotenv import load_dotenv
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ_CHILE = ZoneInfo("America/Santiago")
import requests
from sendgrid.helpers.mail import Mail
from upstash_redis import Redis

load_dotenv()

# ==========================================
# CONFIGURACIÓN DE CONEXIÓN
# ==========================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")

# ==========================================
# CONEXIÓN A REDIS
# ==========================================
redis = Redis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN)

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
# FERIADOS CHILENOS
# ==========================================
def obtener_feriados_chile():
    anio = datetime.now().year
    return [
        datetime(anio, 1, 1),   # Año Nuevo
        datetime(anio, 4, 18),  # Viernes Santo (aproximado)
        datetime(anio, 4, 19),  # Sábado Santo
        datetime(anio, 5, 1),   # Día del Trabajo
        datetime(anio, 5, 21),  # Glorias Navales
        datetime(anio, 6, 20),  # Día de los Pueblos Indígenas
        datetime(anio, 6, 29),  # San Pedro y San Pablo
        datetime(anio, 7, 16),  # Virgen del Carmen
        datetime(anio, 8, 15),  # Asunción de la Virgen
        datetime(anio, 9, 18),  # Fiestas Patrias
        datetime(anio, 9, 19),  # Día de las Glorias del Ejército
        datetime(anio, 10, 12), # Día del Encuentro de Dos Mundos
        datetime(anio, 10, 31), # Día de las Iglesias Evangélicas
        datetime(anio, 11, 1),  # Día de Todos los Santos
        datetime(anio, 12, 8),  # Inmaculada Concepción
        datetime(anio, 12, 25), # Navidad
    ]

def es_dia_habil(fecha):
    feriados = obtener_feriados_chile()
    if fecha.weekday() == 6:  # domingo
        return False
    for feriado in feriados:
        if fecha.date() == feriado.date():
            return False
    return True

# ==========================================
# MEMORIA DE CONVERSACIÓN EN REDIS
# ==========================================
DIAS_EXPIRACION = 5

def obtener_sesion(numero):
    try:
        data = redis.get(f"sesion:{numero}")
        if not data:
            return None
        return json.loads(data)
    except:
        return None

def guardar_sesion(numero, historial, pendiente_correo=False, notificar_a="", copia_a="", caso_derivado=False, fecha_derivacion="", escalamiento_nivel=0, mensaje_caso="", caso_sensible=False):
    try:
        sesion = {
            "historial": historial,
            "pendiente_correo": pendiente_correo,
            "notificar_a": notificar_a,
            "copia_a": copia_a,
            "caso_derivado": caso_derivado,
            "fecha_derivacion": fecha_derivacion,
            "escalamiento_nivel": escalamiento_nivel,
            "mensaje_caso": mensaje_caso,
            "caso_sensible": caso_sensible,
            "ultima_actividad": datetime.now(tz=TZ_CHILE).isoformat()
        }
        redis.set(f"sesion:{numero}", json.dumps(sesion, ensure_ascii=False), ex=DIAS_EXPIRACION * 24 * 3600)
    except Exception as e:
        print(f"Error guardando sesion en Redis: {e}")

def cerrar_sesion(numero):
    try:
        redis.delete(f"sesion:{numero}")
    except Exception as e:
        print(f"Error cerrando sesion en Redis: {e}")

# ==========================================
# FUNCIÓN DE CORREO
# ==========================================
def formatear_cargo(cargo):
    return cargo.replace("_", " ").title()

def enviar_correo(destinatario, copia, nombre_empleado, cargo, mensaje_original, numero_empleado="", asunto_extra="", nivel_escalamiento=0):
    cargo_fmt = formatear_cargo(cargo)
    remitente = "simon@grupobaco.cl"

    if nivel_escalamiento == 0:
        asunto = f"Simón — Consulta de {nombre_empleado} ({cargo_fmt})"
        titulo_correo = "Simón — Nueva Consulta"
        alerta_html = ""
    elif nivel_escalamiento == 1:
        asunto = f"⚠️ Simón — Recordatorio: Consulta de {nombre_empleado} sin respuesta"
        titulo_correo = "Simón — Recordatorio de Consulta"
        alerta_html = "<p style='color:#E67E22; font-weight:bold;'>⚠️ Esta consulta lleva 1 día hábil sin respuesta.</p>"
    else:
        asunto = f"🚨 Simón — Escalamiento: Consulta de {nombre_empleado} sin respuesta"
        titulo_correo = "Simón — Caso Escalado"
        alerta_html = f"<p style='color:#E74C3C; font-weight:bold;'>🚨 Esta consulta lleva {nivel_escalamiento} días hábiles sin respuesta y ha sido escalada.</p>"

    cuerpo_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #2C3E50; padding: 20px; border-radius: 8px 8px 0 0;">
            <h2 style="color: white; margin: 0;">{titulo_correo}</h2>
            <p style="color: #BDC3C7; margin: 5px 0 0 0;">Grupo Baco</p>
        </div>
        <div style="background-color: #F8F9FA; padding: 25px; border-radius: 0 0 8px 8px; border: 1px solid #E0E0E0;">
            {alerta_html}
            <p style="color: #555;">Hola, tienes una consulta que requiere tu atención:</p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr style="background-color: #EAF2FF;">
                    <td style="padding: 10px; font-weight: bold; color: #2C3E50; width: 30%;">Colaborador</td>
                    <td style="padding: 10px; color: #555;">{nombre_empleado}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; font-weight: bold; color: #2C3E50;">Cargo</td>
                    <td style="padding: 10px; color: #555;">{cargo_fmt}</td>
                </tr>
                <tr style="background-color: #EAF2FF;">
                    <td style="padding: 10px; font-weight: bold; color: #2C3E50;">Teléfono</td>
                    <td style="padding: 10px; color: #555;">+{numero_empleado}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; font-weight: bold; color: #2C3E50;">Consulta</td>
                    <td style="padding: 10px; color: #555;">{mensaje_original}</td>
                </tr>
            </table>
            <p style="color: #888; font-size: 12px; margin-top: 30px; border-top: 1px solid #E0E0E0; padding-top: 15px;">
                Este mensaje fue generado automáticamente por Simón · Grupo Baco
            </p>
        </div>
    </div>
    """
    mensaje = Mail(
        from_email=remitente,
        to_emails=destinatario,
        subject=asunto,
        html_content=cuerpo_html
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
# DETECTAR INTENCIONES
# ==========================================
def es_confirmacion(texto):
    texto = texto.lower().strip()
    palabras = ["si", "sí", "ok", "dale", "ya", "confirmo", "adelante", "por favor", "porfa", "claro", "bueno"]
    return any(p in texto for p in palabras)

def es_rechazo(texto):
    texto = texto.lower().strip()
    # Solo cierra si el mensaje es corto y claramente un rechazo
    # No interceptar frases largas que contengan "no"
    if len(texto) > 15:
        return False
    palabras = ["no", "nope", "cancel", "cancela", "olvida", "no gracias"]
    return any(p == texto or texto.startswith(p + " ") for p in palabras)

def es_sin_respuesta(texto):
    texto = texto.lower().strip()
    frases = ["no me han respondido", "no me respondieron", "sigo esperando", "nadie me ha contactado",
              "no he tenido respuesta", "todavía nada", "sin respuesta", "no me llamaron",
              "no me escribieron", "no me contactaron", "siguen sin responderme"]
    return any(f in texto for f in frases)

def calcular_dias_habiles(fecha_inicio_str):
    fecha_inicio = datetime.fromisoformat(fecha_inicio_str.replace("Z", ""))
    if fecha_inicio.tzinfo is None:
        fecha_inicio = fecha_inicio.replace(tzinfo=TZ_CHILE)
    fecha_actual = datetime.now(tz=TZ_CHILE)
    dias = 0
    fecha = fecha_inicio + timedelta(days=1)
    fecha = fecha.replace(hour=0, minute=0, second=0, microsecond=0)
    while fecha + timedelta(days=1) <= fecha_actual:
        if es_dia_habil(fecha):
            dias += 1
        fecha += timedelta(days=1)
    return dias

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

    # Verificar si pasaron más de 3 minutos de inactividad
    if sesion and sesion.get("ultima_actividad"):
        try:
            ultima = datetime.fromisoformat(sesion["ultima_actividad"])
            if ultima.tzinfo is None:
                ultima = ultima.replace(tzinfo=TZ_CHILE)
            ahora = datetime.now(tz=TZ_CHILE)
            minutos_transcurridos = (ahora - ultima).total_seconds() / 60
            if minutos_transcurridos > 3:
                # Sesión expirada: enviar despedida y empezar conversación nueva
                enviar_mensaje(numero, f"Veo que ya no tienes más consultas {nombre}. Cualquier cosa me escribes. ¡Hasta pronto! 👋")
                cerrar_sesion(numero)
                sesion = None
        except Exception as e:
            print(f"Error verificando timeout: {e}")

    # Caso 1: esperando confirmación para derivar
    if sesion and sesion.get("pendiente_correo"):
        if es_confirmacion(mensaje_usuario):
            # Buscar la consulta real: el último mensaje del usuario ANTES de la confirmación
            # Recorremos el historial al revés saltándonos el último (que es la confirmación)
            primer_mensaje = mensaje_usuario
            historial_usr = [m for m in sesion["historial"] if m.get("role") == "user"]
            if len(historial_usr) >= 2:
                # El penúltimo mensaje del usuario es la consulta real
                primer_mensaje = historial_usr[-2]["content"]
                # Si ese mensaje también es muy corto (tipo "si", "ok"), buscar más atrás
                for msg in reversed(historial_usr[:-1]):
                    if len(msg["content"]) > 10:
                        primer_mensaje = msg["content"]
                        break
            elif len(historial_usr) == 1:
                primer_mensaje = historial_usr[0]["content"]
            enviar_correo(notificar_a, copia_a, nombre, cargo, primer_mensaje, numero)
            # Mantener historial para que Claude recuerde el contexto (nombre, local)
            historial_actual = sesion.get("historial", [])
            guardar_sesion(
                numero,
                historial=historial_actual,
                pendiente_correo=False,
                notificar_a=notificar_a,
                copia_a=copia_a,
                caso_derivado=True,
                fecha_derivacion=datetime.now(tz=TZ_CHILE).isoformat(),
                escalamiento_nivel=0,
                mensaje_caso=primer_mensaje
            )
            if sesion.get("caso_sensible", False):
                enviar_mensaje(numero, f"Cuídate mucho {nombre}. Hiciste lo correcto al comunicarlo 🙏\n\n¿Necesitas ayuda con algo más?")
            else:
                enviar_mensaje(numero, f"Listo {nombre}, ya notifiqué al encargado. Te debiera contactar pronto. 👍\n\n¿Necesitas ayuda con algo más?")
            return
        elif es_rechazo(mensaje_usuario):
            cerrar_sesion(numero)
            enviar_mensaje(numero, f"Entendido {nombre}, quedamos atentos si necesitas algo más.")
            return

    # Caso 2: caso ya derivado y empleado reporta sin respuesta
    if sesion and sesion.get("caso_derivado") and es_sin_respuesta(mensaje_usuario):
        fecha_derivacion = sesion.get("fecha_derivacion", "")
        dias_habiles = calcular_dias_habiles(fecha_derivacion) if fecha_derivacion else 0
        nivel_actual = sesion.get("escalamiento_nivel", 0)

        print(f"Dias habiles transcurridos: {dias_habiles}, nivel actual: {nivel_actual}")

        if dias_habiles < 1:
            enviar_mensaje(numero, f"Entiendo tu inquietud {nombre}, pero el plazo para que te contacten aún no ha vencido. Si mañana sigues sin respuesta, escríbeme y escalo tu caso de inmediato.")
            return
        nivel = sesion.get("escalamiento_nivel", 0) + 1
        mensaje_caso = sesion.get("mensaje_caso", "consulta anterior")

        if nivel == 1:
            # Escala a María Andrea
            correo_escalamiento = config.get("correo_escalamiento_1", copia_a)
            enviar_correo(correo_escalamiento, "cesar.martinez@grupobaco.cl", nombre, cargo, mensaje_caso, numero, nivel_escalamiento=nivel)
            guardar_sesion(numero, [], False, notificar_a, copia_a, True, sesion.get("fecha_derivacion"), nivel, mensaje_caso)
            enviar_mensaje(numero, f"Entendido {nombre}. Escalé tu caso a la siguiente persona responsable e incluí el historial completo. Te contactarán durante el próximo día hábil.")
        else:
            # Escala a César
            enviar_correo("cesar.martinez@grupobaco.cl", "", nombre, cargo, mensaje_caso, numero, nivel_escalamiento=nivel)
            cerrar_sesion(numero)
            enviar_mensaje(numero, f"Entendido {nombre}. Tu caso fue escalado a la Gerencia Comercial con el historial completo. Te contactarán a la brevedad.")
        return

    # Caso 3: conversación normal
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
    sensible_detectado = any(p in texto_respuesta.lower() for p in ["ley karin", "qr", "denuncia@grupobaco", "confidencial", "hostigamiento", "acoso"])

    guardar_sesion(
        numero,
        historial,
        pendiente_correo=derivacion_detectada,
        notificar_a=notificar_a,
        copia_a=copia_a,
        caso_sensible=sensible_detectado
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
