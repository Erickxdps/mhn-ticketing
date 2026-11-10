from flask import has_request_context, request
from flask_login import current_user

from app.extensions import db
from app.models import AuditLog


def registrar(accion, entidad=None, entidad_id=None, detalle="", usuario=None, commit=False):
    """Agrega una fila a la bitácora.

    Por defecto NO hace commit: la fila se guarda junto con el cambio que
    describe, en la misma transacción (si el cambio falla, tampoco queda
    en la bitácora). Usar commit=True solo para eventos sueltos como un
    bloqueo de login.
    """
    if usuario is None and has_request_context() and current_user.is_authenticated:
        usuario = current_user
    ip = request.remote_addr if has_request_context() else None

    fila = AuditLog(
        user_id=getattr(usuario, "id", None),
        username=getattr(usuario, "username", None),
        action=accion,
        entity=entidad,
        entity_id=entidad_id,
        detail=(detalle or "")[:2000] or None,
        ip=ip,
    )
    db.session.add(fila)
    if commit:
        db.session.commit()
    return fila
