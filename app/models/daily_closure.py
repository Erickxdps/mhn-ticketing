from datetime import datetime

from app.extensions import db


def _dinero():
    return db.Column(
        db.Numeric(10, 2), nullable=False, default=0, server_default=db.text("0")
    )


def _entero():
    return db.Column(
        db.Integer, nullable=False, default=0, server_default=db.text("0")
    )


class DailyClosure(db.Model):
    """Cierre de un día. Es una foto de los totales al momento de cerrar.
    Un día cerrado no admite nuevas ventas ni anulaciones; para corregirlo
    un ADMIN debe reabrirlo (queda en la auditoría)."""

    __tablename__ = "daily_closures"

    id = db.Column(db.Integer, primary_key=True)
    closed_by = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    closure_date = db.Column(db.Date, nullable=False)

    total_tickets = db.Column(db.Integer, nullable=False)
    total_used_tickets = db.Column(db.Integer, nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)

    # Desglose para cuadrar la caja
    total_cash = _dinero()
    total_qr = _dinero()
    total_physical_tickets = _entero()
    total_voided_tickets = _entero()
    total_voided_amount = _dinero()
    cash_counted = db.Column(db.Numeric(10, 2), nullable=True)
    notes = db.Column(db.String(300), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    closed_by_user = db.relationship("User", back_populates="daily_closures")

    __table_args__ = (
        # Evita múltiples cierres accidentales para la misma fecha.
        db.UniqueConstraint("closure_date", name="uq_daily_closures_closure_date"),
    )

    @property
    def cash_difference(self):
        """Efectivo contado menos efectivo esperado (None si no se contó)."""
        if self.cash_counted is None:
            return None
        return self.cash_counted - self.total_cash

    def __repr__(self):
        return f"<DailyClosure {self.closure_date} - {self.total_amount}>"
