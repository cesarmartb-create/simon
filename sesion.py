import os
import json
from datetime import datetime
from dotenv import load_dotenv
from upstash_redis import Redis

from feriados import TZ_CHILE

load_dotenv()

UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")

redis = Redis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN)

DIAS_EXPIRACION = 5


def obtener_sesion(numero):
    try:
        data = redis.get(f"sesion:{numero}")
        if not data:
            return None
        return json.loads(data)
    except:
        return None


def guardar_sesion(numero, historial=None, pendiente_correo=None, notificar_a=None, copia_a=None, caso_derivado=None, fecha_derivacion=None, escalamiento_nivel=None, mensaje_caso=None, caso_sensible=None, esperando_continuacion=None, categoria=None, mensajes_derivados=None, canal_sensible=None):
    try:
        # Partir de la sesion existente (si la hay) para no borrar campos
        anterior = obtener_sesion(numero) or {}

        defaults = {
            "historial": [],
            "pendiente_correo": False,
            "notificar_a": "",
            "copia_a": "",
            "caso_derivado": False,
            "fecha_derivacion": "",
            "escalamiento_nivel": 0,
            "mensaje_caso": "",
            "caso_sensible": False,
            "esperando_continuacion": False,
            "categoria": "",
            "mensajes_derivados": 0,
            "canal_sensible": "",
        }

        nuevos = {
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
            "categoria": categoria,
            "mensajes_derivados": mensajes_derivados,
            "canal_sensible": canal_sensible,
        }

        sesion = {}
        for campo, default in defaults.items():
            if nuevos[campo] is not None:
                sesion[campo] = nuevos[campo]          # valor enviado explicitamente
            elif campo in anterior:
                sesion[campo] = anterior[campo]         # conservar valor previo
            else:
                sesion[campo] = default                 # primera vez

        sesion["ultima_actividad"] = datetime.now(tz=TZ_CHILE).isoformat()

        redis.set(f"sesion:{numero}", json.dumps(sesion, ensure_ascii=False), ex=DIAS_EXPIRACION * 24 * 3600)
    except Exception as e:
        print(f"Error guardando sesion en Redis: {e}")


def cerrar_sesion(numero):
    try:
        redis.delete(f"sesion:{numero}")
    except Exception as e:
        print(f"Error cerrando sesion en Redis: {e}")
