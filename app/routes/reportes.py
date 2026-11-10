from datetime import date, datetime

from flask import Blueprint, Response, abort, flash, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.models import TicketCategory
from app.models.ticket import TICKET_STATUSES
from app.services.reportes_service import (
    entradas_a_csv,
    reporte_entradas,
    reporte_ventas,
    resumen_por_fecha,
    ventas_a_csv,
)
from app.services.ventas_service import PAYMENT_METHOD_LABELS, PAYMENT_METHODS
from app.utils.decorators import roles_required

reportes_bp = Blueprint("reportes", __name__, url_prefix="/reportes")

ESTADOS_VENTA = {"ACTIVE": "Activas", "VOIDED": "Anuladas"}
TIPOS_ENTRADA = {"QR": "Con QR", "TALONARIO": "De talonario"}


def _parsear_fecha(valor, por_defecto=None):
    if not valor:
        return por_defecto
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        flash(f"Fecha inválida: '{valor}'. Se ignoró ese filtro.", "warning")
        return por_defecto


def _categorias():
    return db.session.execute(select(TicketCategory).order_by(TicketCategory.id)).scalars().all()


def _respuesta_csv(contenido, nombre):
    return Response(
        contenido,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}_{date.today():%Y%m%d}.csv"'},
    )


@reportes_bp.route("", methods=["GET"])
@roles_required("ADMIN")
def index():
    fecha = _parsear_fecha(request.args.get("fecha"), por_defecto=date.today())
    resumen = resumen_por_fecha(fecha)
    return render_template("reportes/index.html", resumen=resumen)


@reportes_bp.route("/ventas", methods=["GET"])
@roles_required("ADMIN", "SELLER")
def ventas():
    # ADMIN ve todas las ventas; SELLER solo las suyas (el filtro se aplica
    # en la consulta, no solo en la plantilla).
    fecha_inicio = _parsear_fecha(request.args.get("fecha_inicio"))
    fecha_fin = _parsear_fecha(request.args.get("fecha_fin"))
    category_id = request.args.get("category_id", type=int)
    metodo = request.args.get("metodo") or None
    if metodo and metodo not in PAYMENT_METHODS:
        metodo = None
    estado = request.args.get("estado") or None
    if estado and estado not in ESTADOS_VENTA:
        estado = None
    user_id = None if current_user.role == "ADMIN" else current_user.id
    filtros_consulta = dict(
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        category_id=category_id,
        user_id=user_id,
        metodo=metodo,
        estado=estado,
    )

    if request.args.get("formato") == "csv":
        return _respuesta_csv(ventas_a_csv(**filtros_consulta), "ventas")

    pagina = request.args.get("pagina", 1, type=int)
    paginacion, totales = reporte_ventas(pagina=pagina, **filtros_consulta)

    return render_template(
        "reportes/ventas.html",
        paginacion=paginacion,
        totales=totales,
        categorias=_categorias(),
        payment_method_labels=PAYMENT_METHOD_LABELS,
        estados=ESTADOS_VENTA,
        filtros={
            "fecha_inicio": request.args.get("fecha_inicio", ""),
            "fecha_fin": request.args.get("fecha_fin", ""),
            "category_id": category_id,
            "metodo": metodo or "",
            "estado": estado or "",
        },
        solo_propias=current_user.role == "SELLER",
    )


@reportes_bp.route("/entradas", methods=["GET"])
@roles_required("ADMIN")
def entradas():
    fecha_inicio = _parsear_fecha(request.args.get("fecha_inicio"))
    fecha_fin = _parsear_fecha(request.args.get("fecha_fin"))
    category_id = request.args.get("category_id", type=int)
    status = request.args.get("status") or None
    if status and status not in TICKET_STATUSES:
        flash(f"Estado inválido: '{status}'. Se ignoró el filtro de estado.", "warning")
        status = None
    tipo = request.args.get("tipo") or None
    if tipo and tipo not in TIPOS_ENTRADA:
        tipo = None
    filtros_consulta = dict(
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        category_id=category_id,
        status=status,
        tipo=tipo,
    )

    if request.args.get("formato") == "csv":
        return _respuesta_csv(entradas_a_csv(**filtros_consulta), "entradas")

    pagina = request.args.get("pagina", 1, type=int)
    paginacion, total = reporte_entradas(pagina=pagina, **filtros_consulta)

    return render_template(
        "reportes/entradas.html",
        paginacion=paginacion,
        total=total,
        categorias=_categorias(),
        estados=TICKET_STATUSES,
        tipos=TIPOS_ENTRADA,
        filtros={
            "fecha_inicio": request.args.get("fecha_inicio", ""),
            "fecha_fin": request.args.get("fecha_fin", ""),
            "category_id": category_id,
            "status": status or "",
            "tipo": tipo or "",
        },
    )
