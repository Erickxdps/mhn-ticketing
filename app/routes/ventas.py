from datetime import date

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.models import Sale, TicketCategory
from app.services import settings_service, talonarios_service
from app.services.cierres_service import dia_cerrado
from app.services.ventas_service import (
    PAYMENT_METHOD_LABELS,
    PAYMENT_METHODS,
    VentaError,
    anular_venta,
    crear_venta,
)
from app.utils.decorators import roles_required
from app.utils.money import ErrorValidacion, parsear_entero

ventas_bp = Blueprint("ventas", __name__, url_prefix="/ventas")


def _categorias_activas():
    return (
        db.session.execute(
            select(TicketCategory)
            .where(TicketCategory.is_active.is_(True))
            .order_by(TicketCategory.id)
        )
        .scalars()
        .all()
    )


def _venta_visible_o_404(sale_id):
    """ADMIN ve cualquier venta; SELLER solo las suyas. Para el resto (o
    una venta ajena) responde 404, sin confirmar que existe."""
    venta = db.session.get(Sale, sale_id)
    if venta is None:
        abort(404)
    if current_user.role == "ADMIN":
        return venta
    if current_user.role == "SELLER" and venta.user_id == current_user.id:
        return venta
    abort(404)


@ventas_bp.route("", methods=["GET"])
@roles_required("ADMIN", "SELLER")
def index():
    modo = settings_service.get_modo_venta()
    categorias = _categorias_activas()

    estado_talonarios = {}
    alertas = []
    if modo == settings_service.MODO_TALONARIO:
        resumen = talonarios_service.resumen_talonarios()
        estado_talonarios = {fila["categoria"].id: fila for fila in resumen}
        alertas = talonarios_service.alertas_talonarios(resumen)

    consulta = select(Sale).order_by(Sale.created_at.desc(), Sale.id.desc()).limit(12)
    if current_user.role != "ADMIN":
        consulta = consulta.where(Sale.user_id == current_user.id)
    ventas_recientes = db.session.execute(consulta).scalars().all()

    return render_template(
        "ventas/form.html",
        categorias=categorias,
        modo=modo,
        estado_talonarios=estado_talonarios,
        alertas=alertas,
        payment_methods=PAYMENT_METHODS,
        payment_method_labels=PAYMENT_METHOD_LABELS,
        ventas_recientes=ventas_recientes,
        dia_cerrado=dia_cerrado(date.today()),
    )


@ventas_bp.route("", methods=["POST"])
@roles_required("ADMIN", "SELLER")
def crear():
    categorias = _categorias_activas()
    payment_method = request.form.get("payment_method", "")

    items = []
    try:
        for categoria in categorias:
            cantidad = parsear_entero(
                request.form.get(f"quantity_{categoria.id}", "0") or "0",
                f"La cantidad de {categoria.name}",
                0,
                1000,
            )
            if cantidad > 0:
                items.append({"ticket_category_id": categoria.id, "quantity": cantidad})
    except ErrorValidacion as error:
        flash(str(error), "danger")
        return redirect(url_for("ventas.index"))

    try:
        sale = crear_venta(current_user, payment_method, items)
    except VentaError as error:
        flash(str(error), "danger")
        return redirect(url_for("ventas.index"))

    current_app.logger.info(
        f"Venta #{sale.id} creada — vendedor={current_user.username} "
        f"modo={sale.sales_mode} monto={sale.total_amount} tickets={sale.total_tickets} "
        f"pago={sale.payment_method}"
    )
    if sale.is_booklet:
        flash(
            f"Venta #{sale.id} registrada. Entrega los boletos del talonario indicados abajo.",
            "success",
        )
    else:
        flash(
            f"Venta #{sale.id} registrada correctamente. Se generaron {sale.total_tickets} tickets.",
            "success",
        )
    return redirect(url_for("ventas.detalle", sale_id=sale.id))


@ventas_bp.route("/<int:sale_id>", methods=["GET"])
@login_required
def detalle(sale_id):
    sale = _venta_visible_o_404(sale_id)

    # Números entregados por categoría (solo ventas de talonario)
    rangos = []
    if sale.is_booklet:
        for item in sale.sale_items:
            numeros = sorted(t.physical_number for t in item.tickets if t.physical_number is not None)
            rangos.append(
                {
                    "categoria": item.ticket_category.name,
                    "cantidad": item.quantity,
                    "numeros": numeros,
                    "tramos": _tramos(numeros),
                }
            )

    puede_anular = (
        current_user.role == "ADMIN"
        and not sale.is_voided
        and not dia_cerrado(sale.created_at.date())
    )
    return render_template(
        "ventas/detail.html",
        sale=sale,
        rangos=rangos,
        puede_anular=puede_anular,
        payment_method_labels=PAYMENT_METHOD_LABELS,
    )


def _tramos(numeros):
    """[249,250,251,300] -> [(249, 251), (300, 300)]"""
    tramos = []
    for n in numeros:
        if tramos and n == tramos[-1][1] + 1:
            tramos[-1] = (tramos[-1][0], n)
        else:
            tramos.append((n, n))
    return tramos


@ventas_bp.route("/<int:sale_id>/anular", methods=["POST"])
@roles_required("ADMIN")
def anular(sale_id):
    try:
        anular_venta(sale_id, request.form.get("motivo", ""), current_user)
    except VentaError as error:
        flash(str(error), "danger")
    else:
        current_app.logger.warning(f"Venta #{sale_id} ANULADA por {current_user.username}")
        flash(f"La venta #{sale_id} fue anulada.", "success")
    return redirect(url_for("ventas.detalle", sale_id=sale_id))
