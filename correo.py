import os
import sendgrid
from dotenv import load_dotenv
from sendgrid.helpers.mail import Mail

load_dotenv()

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")


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
