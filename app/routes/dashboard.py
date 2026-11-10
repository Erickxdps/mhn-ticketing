from flask import Blueprint, render_template

from app.services import settings_service, talonarios_service
from app.services.cierres_service import dia_cerrado
from app.services.reportes_service import dashboard_hoy
from app.utils.decorators import roles_required
from app.utils.dates import hoy

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@dashboard_bp.route("", methods=["GET"])
@roles_required("ADMIN")
def index():
    resumen = dashboard_hoy()
    modo = settings_service.get_modo_venta()
    estado = talonarios_service.resumen_talonarios()
    alertas = talonarios_service.alertas_talonarios(estado) if modo == settings_service.MODO_TALONARIO else []
    return render_template(
        "dashboard/index.html",
        resumen=resumen,
        modo=modo,
        estado_talonarios=estado,
        alertas=alertas,
        cerrado=dia_cerrado(hoy()),
    )
