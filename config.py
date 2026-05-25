import json
import glob


def cargar_clientes():
    clientes = {}
    archivos = glob.glob("config_*.json")
    for archivo in archivos:
        with open(archivo, "r") as f:
            config = json.load(f)
            cliente_id = config["cliente_id"]
            clientes[cliente_id] = config
    return clientes


def obtener_cliente_activo():
    clientes = cargar_clientes()
    for cliente_id, config in clientes.items():
        if config.get("activo", False):
            return config
    return None


def cargar_whitelist(archivo_whitelist):
    try:
        with open(archivo_whitelist, "r") as f:
            data = json.load(f)
            return {e["numero"]: e for e in data["empleados"]}
    except:
        return {}


def obtener_empleado(whitelist, numero):
    return whitelist.get(numero, None)
