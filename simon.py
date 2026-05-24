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
from supabase import create_client, Client

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

def guardar_sesion(numero, historial, pendiente_correo=False, notificar_a="", copia_a="", caso_derivado=False, fecha_derivacion="", escalamiento_nivel=0, mensaje_caso="", caso_sensible=False, esperando_continuacion=False):
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
            "esperando_continuacion": esperando_continuacion,
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

# ==========================================
# SUPABASE - Registro de casos
# ==========================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

supabase_client: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Conectado a Supabase")
    except Exception as e:
        print(f"⚠️  Error conectando a Supabase: {e}")
        supabase_client = None
else:
    print("⚠️  SUPABASE_URL o SUPABASE_KEY no configuradas")

# ==========================================
# DETECCIÓN DE LOCAL DESDE HISTORIAL
# ==========================================
LOCALES_GRUPOBACO = {
    1:  "F0006 — Maipú 1",
    2:  "F0024 — Chillán 1",
    3:  "F0090 — Castro 1",
    4:  "F0160 — Talagante",
    5:  "F0171 — Pedro Aguirre Cerda",
    6:  "F0234 — Franklin",
    7:  "F0287 — Chillán 3",
    8:  "F0313 — Maipú 3",
    9:  "F0383 — Rancagua 8",
    10: "F0437 — Talagante 2",
    11: "F0521 — Maipú Chacabuco",
    12: "F0544 — Chillán 6",
    13: "F0578 — Castro 2"
}

def detectar_local(historial):
    """Busca el primer mensaje del usuario que sea un número 1-13 y devuelve el local."""
    if not historial:
        return ""
    for msg in historial:
        if msg.get("role") != "user":
            continue
        texto = msg.get("content", "").strip()
        if texto.isdigit():
            numero = int(texto)
            if 1 <= numero <= 13:
                return LOCALES_GRUPOBACO[numero]
    return ""

def registrar_caso(cliente_id, nombre, numero, cargo, local, consulta, categoria, responsable):
    """Registra un caso nuevo en Supabase. No bloquea si falla."""
    if not supabase_client:
        print("Supabase no disponible, caso no registrado")
        return None
    try:
        data = {
            "cliente_id": cliente_id,
            "colaborador_nombre": nombre,
            "colaborador_numero": numero,
            "colaborador_cargo": cargo,
            "local": local,
            "consulta": consulta,
            "categoria": categoria,
            "responsable": responsable,
            "estado": "abierto"
        }
        result = supabase_client.table("casos").insert(data).execute()
        caso_id = result.data[0]["id"] if result.data else None
        print(f"✅ Caso registrado en Supabase: {caso_id}")
        # Registrar evento de creación
        if caso_id:
            supabase_client.table("eventos").insert({
                "caso_id": caso_id,
                "tipo": "creado",
                "detalle": f"Caso derivado a {responsable}",
                "actor": "simon"
            }).execute()
        return caso_id
    except Exception as e:
        print(f"⚠️  Error registrando caso en Supabase: {e}")
        return None

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

    # Caso 0: esperando respuesta a "¿Necesitas ayuda con algo más?"
    if sesion and sesion.get("esperando_continuacion"):
        if es_rechazo(mensaje_usuario):
            cerrar_sesion(numero)
            enviar_mensaje(numero, f"Perfecto {nombre}, quedo atento. ¡Hasta pronto! 👋")
            return
        # "Sí" o cualquier otra cosa → limpiar caso anterior y continuar conversación
        guardar_sesion(
            numero,
            historial=sesion.get("historial", []),
            notificar_a=notificar_a,
            copia_a=copia_a,
            esperando_continuacion=False
        )
        if es_confirmacion(mensaje_usuario):
            enviar_mensaje(numero, f"Cuéntame {nombre}, ¿en qué más puedo ayudarte?")
            return
        # Si escribió directamente una consulta nueva (no "sí" ni "no"), procesarla
        sesion = obtener_sesion(numero)

    # Caso 1: esperando confirmación para derivar
    if sesion and sesion.get("pendiente_correo"):
        if es_confirmacion(mensaje_usuario):
            # Usar el mensaje_caso guardado cuando se detectó la derivación
            primer_mensaje = sesion.get("mensaje_caso", "") or mensaje_usuario
            enviar_correo(notificar_a, copia_a, nombre, cargo, primer_mensaje, numero)
            # Registrar caso en Supabase (no bloqueante)
            categoria_caso = "sensible" if sesion.get("caso_sensible") else "operacional"
            registrar_caso(
                cliente_id=config.get("cliente_id", "grupobaco"),
                nombre=nombre,
                numero=numero,
                cargo=cargo,
                local=detectar_local(sesion.get("historial", [])),
                consulta=primer_mensaje,
                categoria=categoria_caso,
                responsable=notificar_a
            )
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
                mensaje_caso=primer_mensaje,
                esperando_continuacion=True
            )
            if sesion.get("caso_sensible", False):
                enviar_botones_si_no(numero, f"Cuídate mucho {nombre}. Hiciste lo correcto al comunicarlo 🙏\n\n¿Necesitas ayuda con algo más?")
            else:
                enviar_botones_si_no(numero, f"Listo {nombre}, ya notifiqué al encargado. Te debiera contactar pronto. 👍\n\n¿Necesitas ayuda con algo más?")
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

    # Si no hay sesión y el mensaje es una confirmación suelta corta → ignorar
    if not sesion and es_confirmacion(mensaje_usuario) and len(mensaje_usuario.strip()) <= 5:
        print(f"Confirmación suelta ignorada de {numero}: {mensaje_usuario}")
        return

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

    # Guardar mensaje original solo cuando se detecta derivación nueva
    # Construir consulta completa: todos los mensajes del usuario excepto identificación del local
    if derivacion_detectada:
        msgs_usuario = [m["content"] for m in historial if m.get("role") == "user"]
        # Excluir mensajes de identificación de local (números del 1 al 13)
        msgs_filtrados = [m for m in msgs_usuario if not (m.strip().isdigit() and 1 <= int(m.strip()) <= 13)]
        # Excluir saludos cortos y confirmaciones
        msgs_filtrados = [m for m in msgs_filtrados if m.strip().lower() not in ["hola", "buenas", "buenos días", "buenas tardes", "buenas noches", "si", "sí", "ok", "no"]]
        if len(msgs_filtrados) > 1:
            mensaje_caso_a_guardar = "\n• " + "\n• ".join(msgs_filtrados)
        elif len(msgs_filtrados) == 1:
            mensaje_caso_a_guardar = msgs_filtrados[0]
        else:
            mensaje_caso_a_guardar = mensaje_usuario
    else:
        mensaje_caso_a_guardar = sesion.get("mensaje_caso", "") if sesion else ""

    guardar_sesion(
        numero,
        historial,
        pendiente_correo=derivacion_detectada,
        notificar_a=notificar_a,
        copia_a=copia_a,
        caso_sensible=sensible_detectado,
        mensaje_caso=mensaje_caso_a_guardar
    )

    if derivacion_detectada:
        enviar_botones_si_no(numero, texto_respuesta)
    else:
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

# ==========================================
# ENDPOINT DE LIMPIEZA AUTOMÁTICA
# ==========================================
LIMPIADOR_SECRET = os.getenv("LIMPIADOR_SECRET")

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

# ==========================================
# INICIO DEL SERVIDOR
# ==========================================
if __name__ == "__main__":
    clientes = cargar_clientes()
    print(f"Clientes cargados: {list(clientes.keys())}")
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
