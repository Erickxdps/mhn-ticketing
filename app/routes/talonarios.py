from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from app.extensions import db
from app.models import TicketBooklet, TicketCategory
from app.services import settings_service, talonarios_service
from app.services.talonarios_service import TalonarioError
from app.utils.decorators import roles_required
from app.utils.money import formatear_numero_boleto

talonarios_bp = Blueprint("talonarios", __name__, url_prefix="/talonarios")


@talonarios_bp.route("", methods=["GET"])
@roles_required("ADMIN", "SELLER")
def index():
    resumen = talonarios_service.resumen_talonarios()
    alertas = talonarios_service.alertas_talonarios(resumen)

    talonarios = (
        db.session.execute(
            select(TicketBooklet)
            .join(TicketCategory, TicketCategory.id == TicketBooklet.ticket_category_id)
            .order_by(TicketCategory.id, TicketBooklet.first_number.desc())
        )
        .scalars()
        .all()
    )
    categorias = [f["categoria"] for f in resumen]
    return render_template(
        "talonarios/index.html",
        resumen=resumen,
        alertas=alertas,
        talonarios=talonarios,
        categorias=categorias,
        modo=settings_service.get_modo_venta(),
        sugeridos={f["categoria"].id: f["sugerido_inicio"] for f in resumen},
    )


@talonarios_bp.route("/nuevo", methods=["POST"])
@roles_required("ADMIN")
def nuevo():
    try:
        talonario = talonarios_service.registrar_talonario(
            request.form.get("category_id", type=int),
            request.form.get("first_number"),
            request.form.get("last_number"),
            current_user,
            notas=request.form.get("notes"),
        )
    except TalonarioError as error:
        flash(str(error), "danger")
        return redirect(url_for("talonarios.index"))

    current_app.logger.info(
        f"Talonario registrado — usuario={current_user.username} "
        f"cat={talonario.ticket_category_id} rango={talonario.first_number}-{talonario.last_number}"
    )
    flash(
        f"Talonario de {talonario.ticket_category.name} registrado: {talonario.range_label} "
        f"({talonario.total} boletos).",
        "success",
    )
    return redirect(url_for("talonarios.index"))


@talonarios_bp.route("/<int:booklet_id>", methods=["GET"])
@roles_required("ADMIN", "SELLER")
def detalle(booklet_id):
    talonario = db.get_or_404(TicketBooklet, booklet_id)
    return render_template(
        "talonarios/detail.html",
        t=talonario,
        ventas=talonarios_service.ventas_del_talonario(talonario.id),
    )


@talonarios_bp.route("/<int:booklet_id>/cerrar", methods=["POST"])
@roles_required("ADMIN")
def cerrar(booklet_id):
    try:
        talonario = talonarios_service.cerrar_talonario(
            booklet_id, request.form.get("motivo", ""), current_user
        )
    except TalonarioError as error:
        flash(str(error), "danger")
    else:
        flash(f"Talonario {talonario.range_label} de {talonario.ticket_category.name} cerrado.", "success")
    return redirect(url_for("talonarios.detalle", booklet_id=booklet_id))


@talonarios_bp.route("/anular-numero", methods=["POST"])
@roles_required("ADMIN", "SELLER")
def anular_numero():
    try:
        reservados = talonarios_service.anular_numeros(
            request.form.get("category_id", type=int),
            request.form.get("cantidad", "1"),
            request.form.get("motivo", ""),
            current_user,
        )
    except TalonarioError as error:
        flash(str(error), "danger")
    else:
        numeros = ", ".join(formatear_numero_boleto(n) for _, n in reservados)
        current_app.logger.warning(
            f"Números de talonario anulados — usuario={current_user.username} números={numeros}"
        )
        flash(
            f"Número{'s' if len(reservados) != 1 else ''} anulado{'s' if len(reservados) != 1 else ''}: "
            f"{numeros}. Conserva el boleto físico y márcalo como ANULADO.",
            "success",
        )
    return redirect(url_for("talonarios.index"))
