import os
import json
from datetime import datetime
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic()

# Lista blanca de números autorizados
def cargar_numeros_autorizados():
    try:
        with open('numeros.txt', 'r') as f:
            numeros = [line.strip() for line in f if line.strip()]
        return numeros
    except:
        print("Advertencia: no se encontró numeros.txt")
        return []

NUMEROS_AUTORIZADOS = cargar_numeros_autorizados()

# Base de datos simple en memoria
conversaciones = {}
casos_abiertos = {}

SYSTEM_PROMPT = """Eres Simón, el asistente virtual interno de tu equipo.
Tu rol es recibir consultas e inquietudes del equipo, orientarlos y derivarlos al área correcta.

REGLA ABSOLUTA DE IDENTIDAD: Al presentarte usa ÚNICAMENTE "Simón, el asistente virtual de tu equipo". PROHIBIDO mencionar cualquier nombre de empresa, marca o dominio en tus saludos o presentaciones.

REGLAS IMPORTANTES:
1. Saluda cordialmente e identifica al trabajador preguntando su nombre y de qué local es.
2. Clasifica cada consulta en una de estas categorías:
   - OPERATIVO: turnos, stock, procesos, equipos (deriva a Carolina)
   - ADMINISTRATIVO: RRHH, clima laboral, permisos (deriva a Kathy)
   - PREVENCION: accidentes, seguridad laboral, riesgos (deriva a Nayarhet)
   - CONSULTA_COMPLIANCE: dudas sobre cumplimiento normativo (deriva a Nayarhet)
   - DENUNCIA_COMPLIANCE: denuncia formal (indica correo denuncia@grupobaco.cl)
   - CONSULTA_KARIN: consultas sobre Ley Karin (deriva a Nayarhet)
   - DENUNCIA_KARIN: denuncia Ley Karin (indica usar portal QR en sucursal)
   - SIMPLE: consulta que puedes responder tú directamente

3. Cuando derives, informa al trabajador a quién va su caso y que recibirá respuesta en máximo 1 día hábil.
4. Para denuncias formales, sé empático y claro con los canales correctos.
5. Al cerrar la conversación pregunta si hay algo más en que puedas ayudar.
6. Sé siempre cordial, claro y conciso. Usa lenguaje simple.

CANALES FORMALES:
- Denuncia compliance: denuncia@grupobaco.cl
- Denuncia Ley Karin: Portal QR presente en cada sucursal

Al finalizar cada conversación genera internamente un resumen con:
- Nombre del trabajador
- Local
- Categoría del problema
- Descripción breve
- Derivación realizada
- Estado: ABIERTO o RESUELTO"""


def numero_autorizado(numero):
    return numero in NUMEROS_AUTORIZADOS


def procesar_mensaje(numero, mensaje):
    if not numero_autorizado(numero):
        return "Este canal es de uso interno de tu equipo. Si eres parte del equipo, contacta a tu jefatura para registrar tu número."

    if numero not in conversaciones:
        conversaciones[numero] = []

    conversaciones[numero].append({
        "role": "user",
        "content": mensaje
    })

    respuesta = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=conversaciones[numero]
    )

    texto_respuesta = respuesta.content[0].text

    conversaciones[numero].append({
        "role": "assistant",
        "content": texto_respuesta
    })

    return texto_respuesta


def generar_informe(numero):
    if numero not in conversaciones:
        return None

    historial = conversaciones[numero]

    informe_prompt = """Basándote en esta conversación, genera un informe estructurado en formato JSON con estos campos exactos:
    {
        "nombre": "nombre del trabajador",
        "local": "local o sucursal",
        "categoria": "categoría del problema",
        "descripcion": "descripción breve del problema",
        "derivacion": "a quién se derivó",
        "estado": "ABIERTO o RESUELTO",
        "fecha": "fecha de hoy",
        "plazo_respuesta": "plazo indicado si existe"
    }
    Responde SOLO con el JSON, sin texto adicional."""

    informe_respuesta = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=512,
        system="Eres un asistente que genera informes estructurados en JSON.",
        messages=historial + [{"role": "user", "content": informe_prompt}]
    )

    try:
        texto = informe_respuesta.content[0].text.strip()
        if texto.startswith("```"):
            texto = texto.split("```")[1]
            if texto.startswith("json"):
                texto = texto[4:]
        informe = json.loads(texto.strip())
        informe["fecha"] = datetime.now().strftime("%d/%m/%Y %H:%M")
        return informe
    except Exception as e:
        print(f"Error al parsear informe: {e}")
        print(f"Respuesta recibida: {informe_respuesta.content[0].text}")
        return None


# Modo de prueba por terminal
if __name__ == "__main__":
    print("=== SIMÓN - Modo de prueba ===")
    print("Escribe 'salir' para terminar la conversación")
    print("Escribe 'informe' para ver el informe generado")
    print("================================\n")

    numero_prueba = "+56993434939"

    while True:
        mensaje = input("Tú: ").strip()

        if mensaje.lower() == "salir":
            print("\nGenerando informe final...")
            informe = generar_informe(numero_prueba)
            if informe:
                print("\n=== INFORME FINAL ===")
                print(json.dumps(informe, ensure_ascii=False, indent=2))
            else:
                print("No se pudo generar el informe. Conversación muy corta o sin datos suficientes.")
            break

        if mensaje.lower() == "informe":
            informe = generar_informe(numero_prueba)
            if informe:
                print("\n=== INFORME ACTUAL ===")
                print(json.dumps(informe, ensure_ascii=False, indent=2))
            continue

        if mensaje:
            respuesta = procesar_mensaje(numero_prueba, mensaje)
            print(f"\nSimón: {respuesta}\n")