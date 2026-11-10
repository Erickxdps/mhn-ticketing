import io

import qrcode
from flask import Blueprint, abort, render_template, send_file
from flask_login import current_user

from app.extensions import db
from app.models import Ticket
from app.utils.decorators import roles_required

entradas_bp = Blueprint("entradas", __name__, url_prefix="/entradas")


def _ticket_visible_o_404(ticket_id):
    """ADMIN ve cualquier entrada; SELLER solo las de sus ventas."""
    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None:
        abort(404)
    if current_user.role == "ADMIN":
        return ticket
    if current_user.role == "SELLER" and ticket.sale_item.sale.user_id == current_user.id:
        return ticket
    abort(404)


@entradas_bp.route("/<int:ticket_id>", methods=["GET"])
@roles_required("ADMIN", "SELLER")
def detalle(ticket_id):
    ticket = _ticket_visible_o_404(ticket_id)
    return render_template("entradas/detail.html", ticket=ticket)


@entradas_bp.route("/<int:ticket_id>/qr.png", methods=["GET"])
@roles_required("ADMIN", "SELLER")
def qr_png(ticket_id):
    """Genera el QR de forma dinámica a partir de qr_token, sin guardar
    ninguna imagen. Los boletos de talonario no tienen QR."""
    ticket = _ticket_visible_o_404(ticket_id)
    if ticket.is_physical:
        abort(404)

    imagen = qrcode.make(ticket.qr_token)
    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG")
    buffer.seek(0)

    return send_file(buffer, mimetype="image/png", max_age=0)
