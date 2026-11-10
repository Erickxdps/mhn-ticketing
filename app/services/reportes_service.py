"""Consultas agregadas para dashboard, reportes y cierre diario.

Todas las cifras salen de agregaciones en SQL (COUNT/SUM/GROUP BY) y
filtran por rangos de fecha (>= inicio y < fin) en vez de aplicar
func.date() a cada fila, para poder usar los índices.

Criterios:
- Una venta anulada no suma ni a la recaudación ni a los tickets
  vendidos; se informa aparte como "anulado".
- Los boletos de talonario nacen como utilizados (se rompen en la
  puerta), así que cuentan en "utilizados" desde el momento de la venta.
"""

import csv
import io
from datetime import date as date_cls
from decimal import Decimal

from flask import current_app
from sqlalchemy import and_, case, exists, func, select

from app.extensions import db
from app.models import (
    BookletVoid,
    Sale,
    SaleItem,
    Ticket,
    TicketBooklet,
    TicketCategory,
)
from app.utils.dates import limites_de_rango, limites_del_dia
from app.utils.money import a_decimal, formatear_numero_boleto


def _escalar(consulta, defecto=0):
    valor = db.session.scalar(consulta)
    return defecto if valor is None else valor


def resumen_por_fecha(fecha):
    """Resumen completo de un día. `fecha` es un objeto date."""
    ini, fin = limites_del_dia(fecha)

    ventas_del_dia = and_(Sale.created_at >= ini, Sale.created_at < fin)
    ventas_activas = and_(ventas_del_dia, Sale.status == "ACTIVE")
    ventas_anuladas = and_(ventas_del_dia, Sale.status == "VOIDED")

    total_ventas = _escalar(select(func.count(Sale.id)).where(ventas_activas))
    total_recaudado = a_decimal(
        _escalar(select(func.sum(Sale.total_amount)).where(ventas_activas))
    )

    # Recaudación por método de pago
    por_metodo = {"CASH": Decimal("0.00"), "QR": Decimal("0.00")}
    for metodo, monto in db.session.execute(
        select(Sale.payment_method, func.sum(Sale.total_amount))
        .where(ventas_activas)
        .group_by(Sale.payment_method)
    ):
        por_metodo[metodo] = a_decimal(monto)

    # Tickets vendidos / utilizados
    tickets_vendidos = _escalar(
        select(func.count(Ticket.id)).where(
            Ticket.sold_at >= ini, Ticket.sold_at < fin, Ticket.status != "CANCELLED"
        )
    )
    tickets_fisicos = _escalar(
        select(func.count(Ticket.id)).where(
            Ticket.sold_at >= ini,
            Ticket.sold_at < fin,
            Ticket.status != "CANCELLED",
            Ticket.booklet_id.is_not(None),
        )
    )
    tickets_utilizados = _escalar(
        select(func.count(Ticket.id)).where(
            Ticket.status == "USED", Ticket.used_at >= ini, Ticket.used_at < fin
        )
    )

    # Desglose por categoría (cantidad y dinero)
    filas = db.session.execute(
        select(
            TicketCategory.id,
            TicketCategory.name,
            func.sum(SaleItem.quantity),
            func.sum(SaleItem.subtotal),
        )
        .join(SaleItem, SaleItem.ticket_category_id == TicketCategory.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(ventas_activas)
        .group_by(TicketCategory.id, TicketCategory.name)
    ).all()
    vendido = {f[0]: (f[1], int(f[2] or 0), a_decimal(f[3])) for f in filas}

    desglose = []
    for categoria in db.session.execute(
        select(TicketCategory).order_by(TicketCategory.id)
    ).scalars():
        if categoria.id in vendido:
            _, cantidad, monto = vendido[categoria.id]
        elif categoria.is_active:
            cantidad, monto = 0, Decimal("0.00")
        else:
            continue  # categoría inactiva y sin ventas ese día: no aporta
        desglose.append(
            {
                "id": categoria.id,
                "nombre": categoria.name,
                "cantidad": cantidad,
                "monto": monto,
            }
        )

    # Anulaciones del día
    anuladas_cantidad = _escalar(select(func.count(Sale.id)).where(ventas_anuladas))
    anuladas_monto = a_decimal(
        _escalar(select(func.sum(Sale.total_amount)).where(ventas_anuladas))
    )
    tickets_anulados = _escalar(
        select(func.count(Ticket.id))
        .join(SaleItem, SaleItem.id == Ticket.sale_item_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(ventas_anuladas)
    )
    numeros_anulados = _escalar(
        select(func.count(BookletVoid.id)).where(
            BookletVoid.created_at >= ini, BookletVoid.created_at < fin
        )
    )

    return {
        "fecha": fecha,
        "total_ventas": total_ventas,
        "total_tickets_vendidos": tickets_vendidos,
        "total_tickets_utilizados": tickets_utilizados,
        "total_tickets_fisicos": tickets_fisicos,
        "total_tickets_qr": tickets_vendidos - tickets_fisicos,
        "total_recaudado": total_recaudado,
        "total_efectivo": por_metodo.get("CASH", Decimal("0.00")),
        "total_qr": por_metodo.get("QR", Decimal("0.00")),
        "desglose": desglose,
        # Compatibilidad: {nombre: cantidad}
        "desglose_categoria": {d["nombre"]: d["cantidad"] for d in desglose},
        "ventas_anuladas": anuladas_cantidad,
        "monto_anulado": anuladas_monto,
        "tickets_anulados": tickets_anulados,
        "numeros_anulados": numeros_anulados,
        "talonarios": rangos_talonario_del_dia(fecha),
    }


def rangos_talonario_del_dia(fecha):
    """Por talonario, qué números se consumieron ese día (vendidos,
    de ventas anuladas y dañados antes de venderse). Sirve para cuadrar
    el cierre con el talonario físico: «Mayores: 00249 a 00258»."""
    ini, fin = limites_del_dia(fecha)

    filas_tickets = db.session.execute(
        select(
            Ticket.booklet_id,
            func.min(Ticket.physical_number),
            func.max(Ticket.physical_number),
            func.sum(case((Ticket.status != "CANCELLED", 1), else_=0)),
            func.sum(case((Ticket.status == "CANCELLED", 1), else_=0)),
        )
        .where(
            Ticket.booklet_id.is_not(None), Ticket.sold_at >= ini, Ticket.sold_at < fin
        )
        .group_by(Ticket.booklet_id)
    ).all()

    filas_voids = db.session.execute(
        select(
            BookletVoid.booklet_id,
            func.min(BookletVoid.number),
            func.max(BookletVoid.number),
            func.count(BookletVoid.id),
        )
        .where(BookletVoid.created_at >= ini, BookletVoid.created_at < fin)
        .group_by(BookletVoid.booklet_id)
    ).all()

    datos = {}
    for bid, minimo, maximo, vendidos, cancelados in filas_tickets:
        datos[bid] = {
            "min": minimo,
            "max": maximo,
            "vendidos": int(vendidos or 0),
            "de_ventas_anuladas": int(cancelados or 0),
            "numeros_danados": 0,
        }
    for bid, minimo, maximo, cantidad in filas_voids:
        d = datos.setdefault(
            bid,
            {"min": minimo, "max": maximo, "vendidos": 0, "de_ventas_anuladas": 0, "numeros_danados": 0},
        )
        d["min"] = min(d["min"], minimo)
        d["max"] = max(d["max"], maximo)
        d["numeros_danados"] = int(cantidad)

    if not datos:
        return []

    talonarios = {
        t.id: t
        for t in db.session.execute(
            select(TicketBooklet).where(TicketBooklet.id.in_(list(datos)))
        ).scalars()
    }

    # Números dañados concretos, para listarlos
    danados = {}
    for bid, numero in db.session.execute(
        select(BookletVoid.booklet_id, BookletVoid.number)
        .where(BookletVoid.created_at >= ini, BookletVoid.created_at < fin)
        .order_by(BookletVoid.number)
    ):
        danados.setdefault(bid, []).append(numero)

    resultado = []
    for bid, d in datos.items():
        t = talonarios[bid]
        resultado.append(
            {
                "talonario_id": bid,
                "categoria": t.ticket_category.name,
                "desde": d["min"],
                "hasta": d["max"],
                "desde_txt": formatear_numero_boleto(d["min"]),
                "hasta_txt": formatear_numero_boleto(d["max"]),
                "vendidos": d["vendidos"],
                "de_ventas_anuladas": d["de_ventas_anuladas"],
                "numeros_danados": d["numeros_danados"],
                "lista_danados": [formatear_numero_boleto(n) for n in danados.get(bid, [])],
                "consumidos": d["vendidos"] + d["de_ventas_anuladas"] + d["numeros_danados"],
            }
        )
    resultado.sort(key=lambda r: (r["categoria"], r["desde"]))
    return resultado


def dashboard_hoy():
    return resumen_por_fecha(date_cls.today())


# --------------------------------------------------------------------------
# Listados filtrables (paginados)
# --------------------------------------------------------------------------

def _filtros_ventas(fecha_inicio, fecha_fin, category_id, user_id, metodo, estado):
    desde, hasta = limites_de_rango(fecha_inicio, fecha_fin)
    condiciones = []
    if desde:
        condiciones.append(Sale.created_at >= desde)
    if hasta:
        condiciones.append(Sale.created_at < hasta)
    if user_id:
        condiciones.append(Sale.user_id == user_id)
    if metodo:
        condiciones.append(Sale.payment_method == metodo)
    if estado:
        condiciones.append(Sale.status == estado)
    if category_id:
        condiciones.append(
            exists().where(
                SaleItem.sale_id == Sale.id, SaleItem.ticket_category_id == category_id
            )
        )
    return condiciones


def reporte_ventas(
    fecha_inicio=None,
    fecha_fin=None,
    category_id=None,
    user_id=None,
    metodo=None,
    estado=None,
    pagina=1,
    por_pagina=None,
):
    """Ventas filtradas y paginadas, más los totales de TODO el conjunto
    filtrado (no solo de la página visible). Devuelve (paginacion, totales)."""
    por_pagina = por_pagina or current_app.config.get("FILAS_POR_PAGINA", 50)
    condiciones = _filtros_ventas(fecha_inicio, fecha_fin, category_id, user_id, metodo, estado)

    consulta = select(Sale).where(*condiciones).order_by(Sale.created_at.desc(), Sale.id.desc())
    paginacion = db.paginate(consulta, page=pagina, per_page=por_pagina, error_out=False)

    activas = [*condiciones, Sale.status == "ACTIVE"]
    totales = {
        "cantidad": _escalar(select(func.count(Sale.id)).where(*condiciones)),
        "activas": _escalar(select(func.count(Sale.id)).where(*activas)),
        "monto": a_decimal(_escalar(select(func.sum(Sale.total_amount)).where(*activas))),
    }
    return paginacion, totales


def _filtros_entradas(fecha_inicio, fecha_fin, category_id, status, tipo):
    desde, hasta = limites_de_rango(fecha_inicio, fecha_fin)
    condiciones = []
    if desde:
        condiciones.append(Ticket.sold_at >= desde)
    if hasta:
        condiciones.append(Ticket.sold_at < hasta)
    if category_id:
        condiciones.append(SaleItem.ticket_category_id == category_id)
    if status:
        condiciones.append(Ticket.status == status)
    if tipo == "TALONARIO":
        condiciones.append(Ticket.booklet_id.is_not(None))
    elif tipo == "QR":
        condiciones.append(Ticket.booklet_id.is_(None))
    return condiciones


def reporte_entradas(
    fecha_inicio=None,
    fecha_fin=None,
    category_id=None,
    status=None,
    tipo=None,
    pagina=1,
    por_pagina=None,
):
    """Entradas filtradas y paginadas. Devuelve (paginacion, total)."""
    por_pagina = por_pagina or current_app.config.get("FILAS_POR_PAGINA", 50)
    condiciones = _filtros_entradas(fecha_inicio, fecha_fin, category_id, status, tipo)

    base = (
        select(Ticket)
        .join(SaleItem, SaleItem.id == Ticket.sale_item_id)
        .where(*condiciones)
        .order_by(Ticket.sold_at.desc(), Ticket.id.desc())
    )
    paginacion = db.paginate(base, page=pagina, per_page=por_pagina, error_out=False)
    total = _escalar(
        select(func.count(Ticket.id))
        .join(SaleItem, SaleItem.id == Ticket.sale_item_id)
        .where(*condiciones)
    )
    return paginacion, total


# --------------------------------------------------------------------------
# Exportación a CSV (se abre directo en Excel)
# --------------------------------------------------------------------------

def _csv(encabezados, filas):
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(encabezados)
    escritor.writerows(filas)
    # BOM para que Excel reconozca UTF-8 (tildes y ñ)
    return "﻿" + salida.getvalue()


def ventas_a_csv(fecha_inicio=None, fecha_fin=None, category_id=None, user_id=None,
                 metodo=None, estado=None):
    condiciones = _filtros_ventas(fecha_inicio, fecha_fin, category_id, user_id, metodo, estado)
    ventas = db.session.execute(
        select(Sale).where(*condiciones).order_by(Sale.created_at, Sale.id)
    ).scalars()
    filas = []
    for v in ventas:
        detalle = "; ".join(
            f"{i.ticket_category.name} x{i.quantity}" for i in v.sale_items
        )
        filas.append(
            [
                v.id,
                v.created_at.strftime("%d/%m/%Y %H:%M"),
                v.user.full_name,
                "Talonario" if v.is_booklet else "QR",
                "Efectivo" if v.payment_method == "CASH" else "QR",
                detalle,
                f"{a_decimal(v.total_amount):.2f}",
                "Anulada" if v.is_voided else "Activa",
                v.void_reason or "",
            ]
        )
    return _csv(
        ["N° venta", "Fecha", "Vendedor", "Tipo", "Pago", "Detalle", "Total (Bs)", "Estado", "Motivo de anulación"],
        filas,
    )


def entradas_a_csv(fecha_inicio=None, fecha_fin=None, category_id=None, status=None, tipo=None):
    condiciones = _filtros_entradas(fecha_inicio, fecha_fin, category_id, status, tipo)
    tickets = db.session.execute(
        select(Ticket)
        .join(SaleItem, SaleItem.id == Ticket.sale_item_id)
        .where(*condiciones)
        .order_by(Ticket.sold_at, Ticket.id)
    ).scalars()
    estados = {"UNUSED": "Sin usar", "USED": "Utilizada", "CANCELLED": "Anulada"}
    filas = []
    for t in tickets:
        filas.append(
            [
                t.ticket_code,
                "Talonario" if t.is_physical else "QR",
                t.display_number if t.is_physical else "",
                t.sale_item.ticket_category.name,
                estados.get(t.status, t.status),
                t.sold_at.strftime("%d/%m/%Y %H:%M"),
                t.used_at.strftime("%d/%m/%Y %H:%M") if t.used_at else "",
                t.sale_item.sale_id,
            ]
        )
    return _csv(
        ["Código", "Tipo", "N° talonario", "Categoría", "Estado", "Vendida", "Utilizada", "N° venta"],
        filas,
    )
