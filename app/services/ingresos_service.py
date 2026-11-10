from datetime import datetime, timedelta

from sqlalchemy import or_, update

from app.extensions import db
from app.models import Ticket
from app.services import settings_service

# Estados de respuesta de la validación.
STATUS_VALID = "VALID"
STATUS_NOT_FOUND = "NOT_FOUND"
STATUS_ALREADY_USED = "ALREADY_USED"
STATUS_CANCELLED = "CANCELLED"
STATUS_EXPIRED = "EXPIRED"
STATUS_PHYSICAL = "PHYSICAL"

MENSAJES = {
    STATUS_VALID: "Entrada válida.",
    STATUS_NOT_FOUND: "Entrada no encontrada.",
    STATUS_ALREADY_USED: "Entrada ya utilizada.",
    STATUS_CANCELLED: "Entrada anulada.",
    STATUS_EXPIRED: "Entrada vencida.",
    STATUS_PHYSICAL: "Boleto de talonario: se controla en la puerta, no se valida por sistema.",
}


def _serializar_ticket(ticket):
    return {
        "ticket_code": ticket.ticket_code,
        "category": ticket.sale_item.ticket_category.name,
        "sold_at": ticket.sold_at.isoformat() if ticket.sold_at else None,
        "used_at": ticket.used_at.isoformat() if ticket.used_at else None,
        "physical_number": ticket.display_number if ticket.is_physical else None,
    }


def _resultado(status, ticket=None, mensaje=None):
    return {
        "status": status,
        "message": mensaje or MENSAJES[status],
        "ticket": _serializar_ticket(ticket) if ticket is not None else None,
    }


def _vencida(ticket, ahora):
    """True si la entrada ya pasó su vigencia (ajuste «días de vigencia»,
    contando el día de la venta; 0 = no vence nunca)."""
    dias = settings_service.get_validez_dias()
    if dias <= 0:
        return False
    ultimo_dia_valido = ticket.sold_at.date() + timedelta(days=dias - 1)
    return ahora.date() > ultimo_dia_valido


def validar_entrada(identificador):
    """Valida una entrada a partir de su ticket_code o su qr_token.

    Devuelve {status, message, ticket} con status VALID, NOT_FOUND,
    ALREADY_USED, CANCELLED, EXPIRED o PHYSICAL.

    Si la entrada está UNUSED, marcarla como USED es atómico
    (UPDATE ... WHERE status = 'UNUSED'): dos inspectores escaneando el
    mismo QR casi a la vez no pueden validarla dos veces, sin depender
    de bloqueos de fila (funciona igual en SQLite y PostgreSQL).
    """
    identificador = (identificador or "").strip()
    if not identificador:
        return _resultado(STATUS_NOT_FOUND, mensaje="Debes indicar un código o escanear un QR.")
    if len(identificador) > 80:
        return _resultado(STATUS_NOT_FOUND)

    ticket = Ticket.query.filter(
        or_(
            Ticket.ticket_code == identificador,
            Ticket.ticket_code == identificador.upper(),
            Ticket.qr_token == identificador,
            Ticket.qr_token == identificador.lower(),
        )
    ).first()

    if ticket is None:
        return _resultado(STATUS_NOT_FOUND)

    if ticket.status == "CANCELLED":
        return _resultado(STATUS_CANCELLED, ticket=ticket)

    if ticket.is_physical:
        return _resultado(
            STATUS_PHYSICAL,
            ticket=ticket,
            mensaje=f"Boleto de talonario n.º {ticket.display_number}: se controla en la puerta, no se valida por sistema.",
        )

    if ticket.status == "USED":
        return _resultado(STATUS_ALREADY_USED, ticket=ticket)

    ahora = datetime.now()
    if _vencida(ticket, ahora):
        return _resultado(
            STATUS_EXPIRED,
            ticket=ticket,
            mensaje=f"Entrada vencida: se vendió el {ticket.sold_at:%d/%m/%Y}.",
        )

    resultado_update = db.session.execute(
        update(Ticket)
        .where(Ticket.id == ticket.id, Ticket.status == "UNUSED")
        .values(status="USED", used_at=ahora)
    )
    db.session.commit()

    if resultado_update.rowcount == 1:
        db.session.refresh(ticket)
        return _resultado(STATUS_VALID, ticket=ticket)

    # Otra solicitud la cambió entre la lectura y el UPDATE (doble escaneo
    # casi simultáneo): se informa el estado real sin volver a escribir.
    db.session.refresh(ticket)
    if ticket.status == "CANCELLED":
        return _resultado(STATUS_CANCELLED, ticket=ticket)
    return _resultado(STATUS_ALREADY_USED, ticket=ticket)
