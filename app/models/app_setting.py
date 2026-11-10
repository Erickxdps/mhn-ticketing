from datetime import datetime

from app.extensions import db


class AppSetting(db.Model):
    """Ajuste del sistema que el administrador puede cambiar desde la
    interfaz (modo de venta, vigencia de las entradas, etc.)."""

    __tablename__ = "app_settings"

    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(255), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
