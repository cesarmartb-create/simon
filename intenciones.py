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
