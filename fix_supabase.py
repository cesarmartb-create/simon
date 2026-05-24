with open("simon.py", "r", encoding="utf-8") as f:
    contenido = f.read()

cambios_ok = 0
cambios_total = 3

# ── CAMBIO 1: Agregar import y cliente Supabase al inicio ────────────────

viejo_1 = "from upstash_redis import Redis"

nuevo_1 = (
    "from upstash_redis import Redis\n"
    "from supabase import create_client, Client"
)

if viejo_1 in contenido and "from supabase import" not in contenido:
    contenido = contenido.replace(viejo_1, nuevo_1, 1)
    cambios_ok += 1
    print("✅ Cambio 1: import de Supabase agregado")
else:
    print("⚠️  Cambio 1 ya aplicado o NO encontrado")
    cambios_ok += 1

# ── CAMBIO 2: Crear el cliente Supabase + función registrar_caso ─────────

# Lo insertamos justo antes de "def enviar_correo"
marcador = "def enviar_correo("

bloque_nuevo = (
    "# ==========================================\n"
    "# SUPABASE - Registro de casos\n"
    "# ==========================================\n"
    "SUPABASE_URL = os.environ.get(\"SUPABASE_URL\", \"\")\n"
    "SUPABASE_KEY = os.environ.get(\"SUPABASE_KEY\", \"\")\n"
    "\n"
    "supabase_client: Client = None\n"
    "if SUPABASE_URL and SUPABASE_KEY:\n"
    "    try:\n"
    "        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)\n"
    "        print(\"✅ Conectado a Supabase\")\n"
    "    except Exception as e:\n"
    "        print(f\"⚠️  Error conectando a Supabase: {e}\")\n"
    "        supabase_client = None\n"
    "else:\n"
    "    print(\"⚠️  SUPABASE_URL o SUPABASE_KEY no configuradas\")\n"
    "\n"
    "def registrar_caso(cliente_id, nombre, numero, cargo, local, consulta, categoria, responsable):\n"
    "    \"\"\"Registra un caso nuevo en Supabase. No bloquea si falla.\"\"\"\n"
    "    if not supabase_client:\n"
    "        print(\"Supabase no disponible, caso no registrado\")\n"
    "        return None\n"
    "    try:\n"
    "        data = {\n"
    "            \"cliente_id\": cliente_id,\n"
    "            \"colaborador_nombre\": nombre,\n"
    "            \"colaborador_numero\": numero,\n"
    "            \"colaborador_cargo\": cargo,\n"
    "            \"local\": local,\n"
    "            \"consulta\": consulta,\n"
    "            \"categoria\": categoria,\n"
    "            \"responsable\": responsable,\n"
    "            \"estado\": \"abierto\"\n"
    "        }\n"
    "        result = supabase_client.table(\"casos\").insert(data).execute()\n"
    "        caso_id = result.data[0][\"id\"] if result.data else None\n"
    "        print(f\"✅ Caso registrado en Supabase: {caso_id}\")\n"
    "        # Registrar evento de creación\n"
    "        if caso_id:\n"
    "            supabase_client.table(\"eventos\").insert({\n"
    "                \"caso_id\": caso_id,\n"
    "                \"tipo\": \"creado\",\n"
    "                \"detalle\": f\"Caso derivado a {responsable}\",\n"
    "                \"actor\": \"simon\"\n"
    "            }).execute()\n"
    "        return caso_id\n"
    "    except Exception as e:\n"
    "        print(f\"⚠️  Error registrando caso en Supabase: {e}\")\n"
    "        return None\n"
    "\n"
)

if "def registrar_caso(" not in contenido:
    contenido = contenido.replace(marcador, bloque_nuevo + marcador, 1)
    cambios_ok += 1
    print("✅ Cambio 2: función registrar_caso agregada")
else:
    print("⚠️  Cambio 2 ya aplicado")
    cambios_ok += 1

# ── CAMBIO 3: Llamar a registrar_caso después de enviar_correo (línea 349)

viejo_3 = "            enviar_correo(notificar_a, copia_a, nombre, cargo, primer_mensaje, numero)"

nuevo_3 = (
    "            enviar_correo(notificar_a, copia_a, nombre, cargo, primer_mensaje, numero)\n"
    "            # Registrar caso en Supabase (no bloqueante)\n"
    "            categoria_caso = \"sensible\" if sesion.get(\"caso_sensible\") else \"operacional\"\n"
    "            registrar_caso(\n"
    "                cliente_id=config.get(\"cliente_id\", \"grupobaco\"),\n"
    "                nombre=nombre,\n"
    "                numero=numero,\n"
    "                cargo=cargo,\n"
    "                local=sesion.get(\"local\", \"\"),\n"
    "                consulta=primer_mensaje,\n"
    "                categoria=categoria_caso,\n"
    "                responsable=notificar_a\n"
    "            )"
)

if viejo_3 in contenido and "registrar_caso(" not in contenido[contenido.index(viejo_3):contenido.index(viejo_3)+500]:
    contenido = contenido.replace(viejo_3, nuevo_3, 1)
    cambios_ok += 1
    print("✅ Cambio 3: llamada a registrar_caso agregada")
else:
    print("⚠️  Cambio 3 NO encontrado o ya aplicado")

with open("simon.py", "w", encoding="utf-8") as f:
    f.write(contenido)

print(f"\n✅ Resultado: {cambios_ok}/{cambios_total} cambios aplicados")
