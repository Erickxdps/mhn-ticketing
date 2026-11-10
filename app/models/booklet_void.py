from datetime import datetime

from app.extensions import db


class BookletVoid(db.Model):
    """Número de talonario que salió dañado, se saltó o se anuló antes de
    venderse. Cuenta como número consumido (no se reutiliza) pero no suma
    a la caja; queda registrado para que el cierre cuadre con el
    talonario físico."""

    __tablename__ = "booklet_voids"

    id = db.Column(db.Integer, primary_key=True)
    booklet_id = db.Column(
        db.Integer, db.ForeignKey("ticket_booklets.id"), nullable=False, index=True
    )
    number = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(200), nullable=False)
    voided_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.now, index=True
    )

    booklet = db.relationship("TicketBooklet", back_populates="voids")
    user = db.relationship("User", foreign_keys=[voided_by])

    __table_args__ = (
        db.UniqueConstraint("booklet_id", "number", name="uq_booklet_voids_number"),
    )
