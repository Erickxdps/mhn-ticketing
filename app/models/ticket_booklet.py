from datetime import datetime

from app.extensions import db
from app.utils.money import formatear_numero_boleto

BOOKLET_STATUSES = ("ACTIVE", "CLOSED")


class TicketBooklet(db.Model):
    """Talonario físico de una categoría: un rango de números impresos
    (por ejemplo 00249 a 00500). `next_number` es el próximo boleto que
    se va a entregar; cuando supera `last_number` el talonario se agotó.
    Los números nunca se reutilizan."""

    __tablename__ = "ticket_booklets"

    id = db.Column(db.Integer, primary_key=True)
    ticket_category_id = db.Column(
        db.Integer, db.ForeignKey("ticket_categories.id"), nullable=False, index=True
    )
    first_number = db.Column(db.Integer, nullable=False)
    last_number = db.Column(db.Integer, nullable=False)
    next_number = db.Column(db.Integer, nullable=False)

    status = db.Column(
        db.String(10), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    notes = db.Column(db.String(200), nullable=True)

    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    closed_at = db.Column(db.DateTime, nullable=True)
    closed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    close_reason = db.Column(db.String(200), nullable=True)

    ticket_category = db.relationship("TicketCategory", back_populates="booklets")
    tickets = db.relationship("Ticket", back_populates="booklet", lazy="dynamic")
    voids = db.relationship(
        "BookletVoid", back_populates="booklet", order_by="BookletVoid.number"
    )
    creator = db.relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        db.CheckConstraint(
            "first_number >= 0 AND last_number >= first_number",
            name="ck_booklets_range",
        ),
        db.CheckConstraint(
            "next_number >= first_number AND next_number <= last_number + 1",
            name="ck_booklets_next_in_range",
        ),
        db.CheckConstraint("status IN ('ACTIVE', 'CLOSED')", name="ck_booklets_status"),
    )

    # --- cifras derivadas ------------------------------------------------
    @property
    def total(self):
        return self.last_number - self.first_number + 1

    @property
    def consumed(self):
        """Números ya entregados o anulados."""
        return self.next_number - self.first_number

    @property
    def remaining(self):
        """Boletos que todavía se pueden entregar (0 si está cerrado)."""
        if self.status != "ACTIVE":
            return 0
        return max(0, self.last_number - self.next_number + 1)

    @property
    def unused_when_closed(self):
        return max(0, self.last_number - self.next_number + 1) if self.status == "CLOSED" else 0

    @property
    def is_exhausted(self):
        return self.next_number > self.last_number

    @property
    def state_label(self):
        if self.status == "CLOSED":
            return "Cerrado"
        if self.is_exhausted:
            return "Agotado"
        return "En uso" if self.consumed else "Sin estrenar"

    @property
    def progress_percent(self):
        return round(100 * self.consumed / self.total) if self.total else 100

    @property
    def range_label(self):
        return f"{formatear_numero_boleto(self.first_number)} – {formatear_numero_boleto(self.last_number)}"

    def __repr__(self):
        return f"<TicketBooklet cat={self.ticket_category_id} {self.first_number}-{self.last_number} next={self.next_number}>"
