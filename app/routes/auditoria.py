from datetime import datetime

from flask import Blueprint, current_app, render_template, request
from sqlalchemy import select

from app.extensions import db
from app.models import AuditLog
from app.utils.dates import limites_de_rango
from app.utils.decorators import roles_required

auditoria_bp = Blueprint("auditoria", __name__, url_prefix="/auditoria")

ETIQUETAS_ACCION = {
    "venta.crear": "Venta registrada",
    "venta.anular": "Venta anulada",
    "talonario.crear": "Talonario registrado",
    "talonario.cerrar": "Talonario cerrado",
    "talonario.anular_numero": "Número de talonario anulado",
    "cierre.crear": "Cierre diario",
    "cierre.reabrir": "Cierre reabierto",
    "categoria.crear": "Categoría creada",
    "categoria.editar": "Categoría modificada",
    "ajuste.cambiar": "Ajuste cambiado",
    "usuario.crear": "Usuario creado",
    "usuario.editar": "Usuario modificado",
    "usuario.cambiar_password_propia": "Cambio de contraseña propio",
    "login.bloqueo": "Bloqueo por intentos fallidos",
}


def _fecha(valor):
    try:
        return datetime.strptime(valor or "", "%Y-%m-%d").date()
    except ValueError:
        return None


@auditoria_bp.route("", methods=["GET"])
@roles_required("ADMIN")
def index():
    accion = request.args.get("accion") or None
    usuario = (request.args.get("usuario") or "").strip() or None
    fecha_inicio = _fecha(request.args.get("fecha_inicio"))
    fecha_fin = _fecha(request.args.get("fecha_fin"))
    desde, hasta = limites_de_rango(fecha_inicio, fecha_fin)

    consulta = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if accion:
        consulta = consulta.where(AuditLog.action == accion)
    if usuario:
        consulta = consulta.where(AuditLog.username == usuario)
    if desde:
        consulta = consulta.where(AuditLog.created_at >= desde)
    if hasta:
        consulta = consulta.where(AuditLog.created_at < hasta)

    pagina = request.args.get("pagina", 1, type=int)
    paginacion = db.paginate(
        consulta,
        page=pagina,
        per_page=current_app.config.get("FILAS_POR_PAGINA", 50),
        error_out=False,
    )
    return render_template(
        "auditoria/index.html",
        paginacion=paginacion,
        acciones=ETIQUETAS_ACCION,
        filtros={
            "accion": accion or "",
            "usuario": usuario or "",
            "fecha_inicio": request.args.get("fecha_inicio", ""),
            "fecha_fin": request.args.get("fecha_fin", ""),
        },
    )
