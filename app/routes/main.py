from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.services import settings_service, talonarios_service

main_bp = Blueprint("main", __name__)


@main_bp.route("/", methods=["GET"])
@login_required
def index():
    alertas = []
    if (
        current_user.role in ("ADMIN", "SELLER")
        and settings_service.get_modo_venta() == settings_service.MODO_TALONARIO
    ):
        alertas = talonarios_service.alertas_talonarios()
    return render_template("main/index.html", alertas=alertas)
