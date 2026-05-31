import os
import re
import anthropic
from datetime import datetime
from dotenv import load_dotenv

from config import obtener_cliente_activo, cargar_whitelist, obtener_empleado
from sesion import obtener_sesion, guardar_sesion, cerrar_sesion
from feriados import TZ_CHILE, calcular_dias_habiles
from locales import detectar_local
from whatsapp import enviar_mensaje, enviar_botones_si_no
from correo import enviar_correo
from casos import registrar_caso, obtener_responsable
from intenciones import es_confirmacion, es_rechazo, es_sin_respuesta, es_emergencia

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


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
            # Categoría que Claude clasificó (PASO 9), con fallback a operacional
            categoria_caso = sesion.get("categoria", "") or "operacional"
            # Casos sensibles: NO transportar el contenido de la denuncia por correo ni Supabase.
            # Solo un aviso al responsable de área. El canal formal (QR Ley Karin / denuncia@...)
            # es el único registro válido del contenido. Aplica también a la sesión, para que
            # un escalamiento posterior (Caso 2) tampoco filtre el contenido real.
            if categoria_caso == "sensible":
                consulta_a_enviar = "Caso sensible reportado — contenido reservado por confidencialidad. Gestionar por el canal formal (Ley Karin / denuncia@grupobaco.cl)."
            else:
                consulta_a_enviar = primer_mensaje
            # Routing por categoría: buscar responsable en areas_derivacion. Si no hay match,
            # caemos al notificar_a del whitelist para no perder la derivación.
            resp = obtener_responsable(config.get("cliente_id", "grupobaco"), categoria_caso)
            correo_destino = resp["correo"] if resp and resp.get("correo") else notificar_a
            enviar_correo(correo_destino, copia_a, nombre, cargo, consulta_a_enviar, numero)
            # Registrar caso en Supabase (no bloqueante)
            registrar_caso(
                cliente_id=config.get("cliente_id", "grupobaco"),
                nombre=nombre,
                numero=numero,
                cargo=cargo,
                local=detectar_local(sesion.get("historial", [])),
                consulta=consulta_a_enviar,
                categoria=categoria_caso,
                responsable=correo_destino
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
                mensaje_caso=consulta_a_enviar,
                esperando_continuacion=True,
                mensajes_derivados=len([m for m in historial_actual if m.get("role") == "user"])
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

    texto_respuesta_raw = respuesta.content[0].text

    # Extrae [[CATEGORIA: x]] y deja el texto visible sin la etiqueta. Por ahora solo se
    # calcula categoria_detectada para logs; el routing por categoría se conecta en Pieza 3.
    match_categoria = re.search(r"\[\[\s*CATEGORIA\s*:\s*([a-z_]+)\s*\]\]", texto_respuesta_raw, re.IGNORECASE)
    categoria_detectada = match_categoria.group(1).lower() if match_categoria else None
    # Reemplaza la etiqueta por un espacio (no por vacío) para no pegar palabras si quedó a
    # mitad del texto. Luego colapsa solo whitespace horizontal (espacios y tabs), preservando
    # los \n que Simón usa entre puntos del mensaje.
    texto_respuesta = re.sub(r"\[\[\s*CATEGORIA\s*:\s*[a-z_]+\s*\]\]", " ", texto_respuesta_raw, flags=re.IGNORECASE)
    texto_respuesta = re.sub(r"[ \t]+", " ", texto_respuesta).strip()
    print(f"Categoria detectada: {categoria_detectada}")

    historial.append({"role": "assistant", "content": texto_respuesta})

    derivacion_detectada = any(p in texto_respuesta.lower() for p in ["maría andrea", "kathy", "nayarhet", "derivar", "derivarte", "notificar"])
    sensible_detectado = any(p in texto_respuesta.lower() for p in ["ley karin", "qr", "denuncia@grupobaco", "confidencial", "hostigamiento", "acoso"])
    emergencia_detectada = es_emergencia(mensaje_usuario)

    # Guardar mensaje original cuando se detecta derivación nueva o emergencia
    # Construir consulta completa: todos los mensajes del usuario excepto identificación del local
    if derivacion_detectada or emergencia_detectada:
        # Solo considerar mensajes posteriores a la última derivación, para que un caso
        # nuevo no arrastre la consulta de un caso ya derivado. El contador se actualiza
        # en Caso 1 al confirmar la derivación (ver sub-paso 3).
        ya_derivados = sesion.get("mensajes_derivados", 0) if sesion else 0
        msgs_usuario = [m["content"] for m in historial if m.get("role") == "user"][ya_derivados:]
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

    # Emergencia: notificar a Nayarhet AHORA, sin pedir confirmación ni botones
    if emergencia_detectada:
        # TEMPORAL Fase 1: routing por categoria se migrara a Supabase.
        correo_emergencia = config.get("encargados", {}).get("cumplimiento", {}).get("email", "") or notificar_a
        enviar_correo(correo_emergencia, copia_a, nombre, cargo, mensaje_caso_a_guardar, numero)
        registrar_caso(
            cliente_id=config.get("cliente_id", "grupobaco"),
            nombre=nombre,
            numero=numero,
            cargo=cargo,
            local=detectar_local(historial),
            consulta=mensaje_caso_a_guardar,
            categoria="accidente",
            responsable=correo_emergencia
        )
        cerrar_sesion(numero)
        enviar_mensaje(numero, texto_respuesta)
        return

    guardar_sesion(
        numero,
        historial,
        pendiente_correo=derivacion_detectada,
        notificar_a=notificar_a,
        copia_a=copia_a,
        caso_sensible=sensible_detectado,
        mensaje_caso=mensaje_caso_a_guardar,
        categoria=categoria_detectada
    )

    if derivacion_detectada:
        enviar_botones_si_no(numero, texto_respuesta)
    else:
        enviar_mensaje(numero, texto_respuesta)
