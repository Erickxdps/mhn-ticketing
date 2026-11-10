from datetime import datetime

from app.extensions import db


class TicketCategory(db.Model):
    __tablename__ = "ticket_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    sale_items = db.relationship(
        "SaleItem", back_populates="ticket_category", lazy="dynamic"
    )
    booklets = db.relationship(
        "TicketBooklet", back_populates="ticket_category", lazy="dynamic"
    )

    def __repr__(self):
        return f"<TicketCategory {self.name} - {self.price}>"
