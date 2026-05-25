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
