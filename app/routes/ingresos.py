from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user

from app.services.ingresos_service import validar_entrada
from app.utils.decorators import roles_required

ingresos_bp = Blueprint("ingresos", __name__, url_prefix="/ingresos")


@ingresos_bp.route("", methods=["GET"])
@roles_required("ADMIN", "INSPECTOR")
def index():
    return render_template("ingresos/index.html")


@ingresos_bp.route("/validar", methods=["POST"])
@roles_required("ADMIN", "INSPECTOR")
def validar():
    payload = request.get_json(silent=True) or {}
    identificador = request.form.get("codigo") or payload.get("codigo")
    if not isinstance(identificador, str):
        identificador = ""

    resultado = validar_entrada(identificador)

    if resultado["status"] in ("ALREADY_USED", "NOT_FOUND", "EXPIRED", "CANCELLED"):
        # repr() evita que un código con saltos de línea falsifique entradas del log.
        current_app.logger.warning(
            f"Validación {resultado['status']} — inspector={current_user.username} "
            f"código intentado={identificador[:80]!r}"
        )
    elif resultado["status"] == "VALID":
        current_app.logger.info(
            f"Entrada validada — inspector={current_user.username} "
            f"ticket={resultado['ticket']['ticket_code']}"
        )

    return jsonify(
        {
            "success": resultado["status"] == "VALID",
            "status": resultado["status"],
            "message": resultado["message"],
            "ticket": resultado["ticket"],
        }
    )
