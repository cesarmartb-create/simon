with open("simon.py", "r", encoding="utf-8") as f:
    contenido = f.read()

cambios_ok = 0
cambios_total = 2

# ── CAMBIO 1: Agregar diccionario de locales + función de detección ──────

# Lo insertamos justo antes de la función registrar_caso
marcador = "def registrar_caso("

bloque_locales = (
    "# ==========================================\n"
    "# DETECCIÓN DE LOCAL DESDE HISTORIAL\n"
    "# ==========================================\n"
    "LOCALES_GRUPOBACO = {\n"
    "    1:  \"F0006 — Maipú 1\",\n"
    "    2:  \"F0024 — Chillán 1\",\n"
    "    3:  \"F0090 — Castro 1\",\n"
    "    4:  \"F0160 — Talagante\",\n"
    "    5:  \"F0171 — Pedro Aguirre Cerda\",\n"
    "    6:  \"F0234 — Franklin\",\n"
    "    7:  \"F0287 — Chillán 3\",\n"
    "    8:  \"F0313 — Maipú 3\",\n"
    "    9:  \"F0383 — Rancagua 8\",\n"
    "    10: \"F0437 — Talagante 2\",\n"
    "    11: \"F0521 — Maipú Chacabuco\",\n"
    "    12: \"F0544 — Chillán 6\",\n"
    "    13: \"F0578 — Castro 2\"\n"
    "}\n"
    "\n"
    "def detectar_local(historial):\n"
    "    \"\"\"Busca el primer mensaje del usuario que sea un número 1-13 y devuelve el local.\"\"\"\n"
    "    if not historial:\n"
    "        return \"\"\n"
    "    for msg in historial:\n"
    "        if msg.get(\"role\") != \"user\":\n"
    "            continue\n"
    "        texto = msg.get(\"content\", \"\").strip()\n"
    "        if texto.isdigit():\n"
    "            numero = int(texto)\n"
    "            if 1 <= numero <= 13:\n"
    "                return LOCALES_GRUPOBACO[numero]\n"
    "    return \"\"\n"
    "\n"
)

if "def detectar_local(" not in contenido:
    contenido = contenido.replace(marcador, bloque_locales + marcador, 1)
    cambios_ok += 1
    print("✅ Cambio 1: función detectar_local agregada")
else:
    print("⚠️  Cambio 1 ya aplicado")
    cambios_ok += 1

# ── CAMBIO 2: Usar detectar_local en la llamada a registrar_caso ─────────

viejo_2 = 'local=sesion.get("local", ""),'
nuevo_2 = 'local=detectar_local(sesion.get("historial", [])),'

if viejo_2 in contenido:
    contenido = contenido.replace(viejo_2, nuevo_2, 1)
    cambios_ok += 1
    print("✅ Cambio 2: registrar_caso ahora usa detectar_local")
else:
    print("⚠️  Cambio 2 NO encontrado")

with open("simon.py", "w", encoding="utf-8") as f:
    f.write(contenido)

print(f"\n✅ Resultado: {cambios_ok}/{cambios_total} cambios aplicados")
