from datetime import date, datetime, time, timedelta


def hoy():
    return date.today()


def ahora():
    return datetime.now()


def limites_del_dia(fecha):
    """(inicio, fin) del día como datetimes, con fin exclusivo.

    Filtrar por rango (>= inicio y < fin) en vez de func.date(columna)
    permite usar los índices de created_at / sold_at / used_at."""
    inicio = datetime.combine(fecha, time.min)
    return inicio, inicio + timedelta(days=1)


def limites_de_rango(fecha_inicio=None, fecha_fin=None):
    """(desde, hasta) para un rango de fechas inclusivo en ambos
    extremos; cualquiera puede ser None."""
    desde = datetime.combine(fecha_inicio, time.min) if fecha_inicio else None
    hasta = datetime.combine(fecha_fin, time.min) + timedelta(days=1) if fecha_fin else None
    return desde, hasta
