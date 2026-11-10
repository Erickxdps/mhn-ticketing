from datetime import datetime

from app.extensions import db


class AuditLog(db.Model):
    """Bitácora de acciones sensibles: cambios de precio, usuarios,
    anulaciones, talonarios, cierres y reaperturas, cambio de modo de
    venta. Solo se agrega; nunca se edita ni se borra desde la app."""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    username = db.Column(db.String(80), nullable=True)   # copia, por si el usuario cambia
    action = db.Column(db.String(60), nullable=False, index=True)
    entity = db.Column(db.String(40), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    detail = db.Column(db.Text, nullable=True)
    ip = db.Column(db.String(45), nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.now, index=True
    )
