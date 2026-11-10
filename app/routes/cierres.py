from datetime import date, datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from app.extensions import db
from app.models import DailyClosure
from app.services.cierres_service import (
    CierreError,
    crear_cierre,
    dia_cerrado,
    reabrir_cierre,
)
from app.services.reportes_service import resumen_por_fecha
from app.utils.decorators import roles_required

cierres_bp = Blueprint("cierres", __name__, url_prefix="/cierres")


def _fecha_o_none(valor):
    try:
        return datetime.strptime(valor or "", "%Y-%m-%d").date()
    except ValueError:
        return None


@cierres_bp.route("", methods=["GET"])
@roles_required("ADMIN")
def index():
    hoy = date.today()
    fecha = _fecha_o_none(request.args.get("fecha")) or hoy
    if fecha > hoy:
        flash("No se puede cerrar una fecha futura; se muestra la de hoy.", "warning")
        fecha = hoy

    pagina = request.args.get("pagina", 1, type=int)
    cierres = db.paginate(
        select(DailyClosure).order_by(DailyClosure.closure_date.desc()),
        page=pagina,
        per_page=current_app.config.get("FILAS_POR_PAGINA", 50),
        error_out=False,
    )
    return render_template(
        "cierres/index.html",
        cierres=cierres,
        hoy=hoy.isoformat(),
        fecha=fecha,
        vista_previa=resumen_por_fecha(fecha),
        ya_cerrado=dia_cerrado(fecha),
    )


@cierres_bp.route("", methods=["POST"])
@roles_required("ADMIN")
def crear():
    valor_fecha = request.form.get("closure_date", "")
    closure_date = _fecha_o_none(valor_fecha)
    if closure_date is None:
        flash(f"Fecha inválida: '{valor_fecha}'.", "danger")
        return redirect(url_for("cierres.index"))

    try:
        cierre = crear_cierre(
            closure_date,
            current_user,
            cash_counted=request.form.get("cash_counted"),
            notes=request.form.get("notes"),
        )
    except CierreError as error:
        flash(str(error), "danger")
        return redirect(url_for("cierres.index", fecha=closure_date.isoformat()))

    current_app.logger.info(
        f"Cierre diario del {cierre.closure_date} registrado por "
        f"{current_user.username} — tickets={cierre.total_tickets} "
        f"usados={cierre.total_used_tickets} monto={cierre.total_amount}"
    )
    flash(f"Cierre del {cierre.closure_date:%d/%m/%Y} registrado.", "success")
    return redirect(url_for("cierres.detalle", cierre_id=cierre.id))


@cierres_bp.route("/<int:cierre_id>", methods=["GET"])
@roles_required("ADMIN")
def detalle(cierre_id):
    cierre = db.get_or_404(DailyClosure, cierre_id)
    return render_template(
        "cierres/detail.html",
        cierre=cierre,
        resumen=resumen_por_fecha(cierre.closure_date),
    )


@cierres_bp.route("/<int:cierre_id>/reabrir", methods=["POST"])
@roles_required("ADMIN")
def reabrir(cierre_id):
    try:
        fecha = reabrir_cierre(cierre_id, request.form.get("motivo", ""), current_user)
    except CierreError as error:
        flash(str(error), "danger")
        return redirect(url_for("cierres.detalle", cierre_id=cierre_id))

    current_app.logger.warning(
        f"Cierre del {fecha} REABIERTO por {current_user.username}"
    )
    flash(
        f"El cierre del {fecha:%d/%m/%Y} se reabrió. Corrige lo necesario y vuelve a cerrar el día.",
        "success",
    )
    return redirect(url_for("cierres.index", fecha=fecha.isoformat()))
