from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ_CHILE = ZoneInfo("America/Santiago")


def obtener_feriados_chile():
    anio = datetime.now().year
    return [
        datetime(anio, 1, 1),   # Año Nuevo
        datetime(anio, 4, 18),  # Viernes Santo (aproximado)
        datetime(anio, 4, 19),  # Sábado Santo
        datetime(anio, 5, 1),   # Día del Trabajo
        datetime(anio, 5, 21),  # Glorias Navales
        datetime(anio, 6, 20),  # Día de los Pueblos Indígenas
        datetime(anio, 6, 29),  # San Pedro y San Pablo
        datetime(anio, 7, 16),  # Virgen del Carmen
        datetime(anio, 8, 15),  # Asunción de la Virgen
        datetime(anio, 9, 18),  # Fiestas Patrias
        datetime(anio, 9, 19),  # Día de las Glorias del Ejército
        datetime(anio, 10, 12), # Día del Encuentro de Dos Mundos
        datetime(anio, 10, 31), # Día de las Iglesias Evangélicas
        datetime(anio, 11, 1),  # Día de Todos los Santos
        datetime(anio, 12, 8),  # Inmaculada Concepción
        datetime(anio, 12, 25), # Navidad
    ]


def es_dia_habil(fecha):
    feriados = obtener_feriados_chile()
    if fecha.weekday() == 6:  # domingo
        return False
    for feriado in feriados:
        if fecha.date() == feriado.date():
            return False
    return True


def calcular_dias_habiles(fecha_inicio_str):
    fecha_inicio = datetime.fromisoformat(fecha_inicio_str.replace("Z", ""))
    if fecha_inicio.tzinfo is None:
        fecha_inicio = fecha_inicio.replace(tzinfo=TZ_CHILE)
    fecha_actual = datetime.now(tz=TZ_CHILE)
    dias = 0
    fecha = fecha_inicio + timedelta(days=1)
    fecha = fecha.replace(hour=0, minute=0, second=0, microsecond=0)
    while fecha + timedelta(days=1) <= fecha_actual:
        if es_dia_habil(fecha):
            dias += 1
        fecha += timedelta(days=1)
    return dias
