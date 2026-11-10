from app.extensions import db
from app.utils.money import formatear_numero_boleto

# Estados oficiales del ticket.
TICKET_STATUSES = ("UNUSED", "USED", "CANCELLED")


class Ticket(db.Model):
    """Una entrada individual.

    Hay dos clases:
    - Con QR (booklet_id es NULL): se imprime y se valida al ingresar.
    - De talonario (booklet_id y physical_number con valor): es el boleto
      físico numerado del talonario del museo. No se escanea: nace como
      USED porque se rompe en la puerta.
    """

    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)
    sale_item_id = db.Column(
        db.Integer, db.ForeignKey("sale_items.id"), nullable=False, index=True
    )

    ticket_code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    qr_token = db.Column(db.String(64), unique=True, nullable=False, index=True)

    status = db.Column(
        db.Enum(*TICKET_STATUSES, name="ticket_status", validate_strings=True),
        nullable=False,
        default="UNUSED",
    )

    sold_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)

    # Talonario físico
    booklet_id = db.Column(
        db.Integer, db.ForeignKey("ticket_booklets.id"), nullable=True
    )
    physical_number = db.Column(db.Integer, nullable=True)

    # Anulación
    void_reason = db.Column(db.String(200), nullable=True)
    voided_at = db.Column(db.DateTime, nullable=True)
    voided_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    sale_item = db.relationship("SaleItem", back_populates="tickets")
    booklet = db.relationship("TicketBooklet", back_populates="tickets")

    __table_args__ = (
        # Un mismo número no puede entregarse dos veces dentro de un talonario.
        db.Index("uq_tickets_booklet_number", "booklet_id", "physical_number", unique=True),
        db.Index("ix_tickets_sold_at", "sold_at"),
        db.Index("ix_tickets_used_at", "used_at"),
    )

    @property
    def is_physical(self):
        return self.booklet_id is not None

    @property
    def display_number(self):
        return formatear_numero_boleto(self.physical_number)

    def __repr__(self):
        return f"<Ticket {self.ticket_code} ({self.status})>"
