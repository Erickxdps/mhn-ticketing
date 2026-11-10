from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import select

from app.extensions import db
from app.models import TicketCategory
from app.services import audit_service, settings_service, talonarios_service
from app.utils.decorators import roles_required
from app.utils.money import ErrorValidacion, a_decimal, parsear_precio
from flask import current_app

configuracion_bp = Blueprint("configuracion", __name__, url_prefix="/configuracion")


def _nombre_valido(crudo, excluir_id=None):
    nombre = " ".join((crudo or "").split())
    if len(nombre) < 2 or len(nombre) > 50:
        raise ErrorValidacion("El nombre debe tener entre 2 y 50 caracteres.")
    consulta = select(TicketCategory).where(
        db.func.lower(TicketCategory.name) == nombre.lower()
    )
    if excluir_id is not None:
        consulta = consulta.where(TicketCategory.id != excluir_id)
    if db.session.scalar(consulta) is not None:
        raise ErrorValidacion(f"Ya existe una categoría llamada '{nombre}'.")
    return nombre


@configuracion_bp.route("/categorias", methods=["GET"])
@roles_required("ADMIN")
def categorias():
    todas = db.session.execute(select(TicketCategory).order_by(TicketCategory.id)).scalars().all()
    modo = settings_service.get_modo_venta()
    sin_talonario = set()
    if modo == settings_service.MODO_TALONARIO:
        sin_talonario = {
            f["categoria"].id
            for f in talonarios_service.resumen_talonarios()
            if f["nivel"] in ("sin", "agotado")
        }
    return render_template(
        "configuracion/categorias.html",
        categorias=todas,
        modo=modo,
        sin_talonario=sin_talonario,
    )


@configuracion_bp.route("/categorias", methods=["POST"])
@roles_required("ADMIN")
def categorias_crear():
    """Alta de una categoría nueva."""
    try:
        nombre = _nombre_valido(request.form.get("name"))
        precio = parsear_precio(request.form.get("price"), current_app.config["PRECIO_MAXIMO"])
    except ErrorValidacion as error:
        flash(str(error), "danger")
        return redirect(url_for("configuracion.categorias"))

    nueva = TicketCategory(name=nombre, price=precio, is_active=True)
    db.session.add(nueva)
    db.session.flush()
    audit_service.registrar(
        "categoria.crear",
        entidad="ticket_category",
        entidad_id=nueva.id,
        detalle=f"{nombre}: Bs {precio}",
    )
    db.session.commit()

    flash(f"Categoría '{nombre}' creada correctamente.", "success")
    return redirect(url_for("configuracion.categorias"))


@configuracion_bp.route("/categorias/<int:category_id>", methods=["POST"])
@roles_required("ADMIN")
def categorias_editar(category_id):
    """Actualiza nombre, precio y estado de una categoría.

    Ninguna categoría se elimina: si ya no debe venderse se desactiva.
    Las ventas históricas no se ven afectadas porque SaleItem guarda su
    propio unit_price/subtotal, y renombrar solo cambia la etiqueta.
    """
    categoria = db.get_or_404(TicketCategory, category_id)
    is_active = request.form.get("is_active") == "on"

    try:
        nombre = _nombre_valido(request.form.get("name", categoria.name), excluir_id=categoria.id)
        precio = parsear_precio(request.form.get("price"), current_app.config["PRECIO_MAXIMO"])
    except ErrorValidacion as error:
        flash(str(error), "danger")
        return redirect(url_for("configuracion.categorias"))

    cambios = []
    if categoria.name != nombre:
        cambios.append(f"nombre: '{categoria.name}' -> '{nombre}'")
    if a_decimal(categoria.price) != precio:
        cambios.append(f"precio: Bs {a_decimal(categoria.price)} -> Bs {precio}")
    if categoria.is_active != is_active:
        cambios.append(f"activa: {categoria.is_active} -> {is_active}")

    categoria.name = nombre
    categoria.price = precio
    categoria.is_active = is_active
    if cambios:
        audit_service.registrar(
            "categoria.editar",
            entidad="ticket_category",
            entidad_id=categoria.id,
            detalle="; ".join(cambios),
        )
    db.session.commit()

    flash(f"Categoría '{nombre}' actualizada correctamente.", "success")
    return redirect(url_for("configuracion.categorias"))


@configuracion_bp.route("/ajustes", methods=["GET"])
@roles_required("ADMIN")
def ajustes():
    return render_template(
        "configuracion/ajustes.html",
        modo=settings_service.get_modo_venta(),
        validez_dias=settings_service.get_validez_dias(),
        umbral=settings_service.get_umbral_aviso(),
        etiquetas_modo=settings_service.ETIQUETAS_MODO,
    )


@configuracion_bp.route("/ajustes", methods=["POST"])
@roles_required("ADMIN")
def ajustes_guardar():
    try:
        cambio_modo = settings_service.set_setting(
            "sales_mode", request.form.get("sales_mode", ""), current_user
        )
        settings_service.set_setting(
            "ticket_validity_days", request.form.get("ticket_validity_days", ""), current_user
        )
        settings_service.set_setting(
            "booklet_low_threshold", request.form.get("booklet_low_threshold", ""), current_user
        )
    except settings_service.AjusteError as error:
        db.session.rollback()
        flash(str(error), "danger")
        return redirect(url_for("configuracion.ajustes"))

    db.session.commit()
    if cambio_modo:
        modo = settings_service.get_modo_venta()
        current_app.logger.warning(
            f"Modo de venta cambiado a {modo} por {current_user.username}"
        )
        flash(
            f"Modo de venta cambiado a «{settings_service.ETIQUETAS_MODO[modo]}». "
            "Las próximas ventas ya usan este modo.",
            "success",
        )
    else:
        flash("Ajustes guardados.", "success")
    return redirect(url_for("configuracion.ajustes"))
