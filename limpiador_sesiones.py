"""
Script de limpieza automática de sesiones inactivas.
Se ejecuta cada minuto vía Cron Job en Render.
Revisa todas las sesiones activas y:
- Si pasaron más de 3 minutos sin actividad Y tiene caso pendiente → envía despedida + cierra sesión
- Si pasaron más de 3 minutos sin actividad sin pendientes → solo cierra sesión
"""

import json
from datetime import datetime

from sesion import redis
from feriados import TZ_CHILE
from whatsapp import enviar_mensaje
from config import cargar_clientes, cargar_whitelist

MINUTOS_TIMEOUT = 1


def cargar_whitelist_global():
    """Carga las whitelists de todos los clientes activos."""
    whitelist = {}
    for config in cargar_clientes().values():
        if config.get("activo"):
            try:
                whitelist.update(cargar_whitelist(config["archivo_whitelist"]))
            except Exception as e:
                print(f"Error cargando whitelist {config['archivo_whitelist']}: {e}")
    return whitelist


def limpiar_sesiones():
    """Recorre todas las sesiones y cierra las que pasaron el timeout."""
    whitelist = cargar_whitelist_global()
    cursor = 0
    total_revisadas = 0
    total_cerradas = 0
    total_despedidas = 0

    while True:
        result = redis.scan(cursor, match="sesion:*", count=100)
        cursor = result[0]
        claves = result[1]

        for clave in claves:
            total_revisadas += 1
            try:
                data = redis.get(clave)
                if not data:
                    continue
                sesion = json.loads(data)
                ultima_str = sesion.get("ultima_actividad")
                if not ultima_str:
                    continue

                ultima = datetime.fromisoformat(ultima_str)
                if ultima.tzinfo is None:
                    ultima = ultima.replace(tzinfo=TZ_CHILE)
                ahora = datetime.now(tz=TZ_CHILE)
                minutos = (ahora - ultima).total_seconds() / 60

                if minutos > MINUTOS_TIMEOUT:
                    numero = clave.replace("sesion:", "")
                    tiene_pendientes = sesion.get("caso_derivado") or sesion.get("pendiente_correo")

                    if tiene_pendientes:
                        empleado = whitelist.get(numero, {})
                        nombre = empleado.get("nombre", "")
                        if nombre:
                            mensaje = f"Veo que ya no tienes más consultas {nombre}. Cualquier cosa me escribes. ¡Hasta pronto! 👋"
                        else:
                            mensaje = "Veo que ya no tienes más consultas. Cualquier cosa me escribes. ¡Hasta pronto! 👋"
                        enviar_mensaje(numero, mensaje)
                        total_despedidas += 1
                        print(f"Despedida enviada a {numero} (inactivo {minutos:.1f} min)")

                    redis.delete(clave)
                    total_cerradas += 1
                    print(f"Sesión cerrada: {numero}")

            except Exception as e:
                print(f"Error procesando {clave}: {e}")

        if cursor == 0:
            break

    print(f"\nResumen: revisadas={total_revisadas}, cerradas={total_cerradas}, despedidas={total_despedidas}")


if __name__ == "__main__":
    print(f"=== Limpieza de sesiones — {datetime.now(tz=TZ_CHILE).isoformat()} ===")
    limpiar_sesiones()
