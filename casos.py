import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

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
