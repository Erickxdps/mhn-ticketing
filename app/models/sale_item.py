from app.extensions import db


class SaleItem(db.Model):
    __tablename__ = "sale_items"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(
        db.Integer, db.ForeignKey("sales.id"), nullable=False, index=True
    )
    ticket_category_id = db.Column(
        db.Integer, db.ForeignKey("ticket_categories.id"), nullable=False, index=True
    )
    quantity = db.Column(db.Integer, nullable=False)

    # unit_price y subtotal se congelan al momento de la venta para que un
    # cambio posterior en TicketCategory.price nunca altere ventas históricas.
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)

    sale = db.relationship("Sale", back_populates="sale_items")
    ticket_category = db.relationship("TicketCategory", back_populates="sale_items")
    tickets = db.relationship(
        "Ticket",
        back_populates="sale_item",
        cascade="all, delete-orphan",
        order_by="Ticket.id",
    )

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_sale_items_quantity_positive"),
    )

    def __repr__(self):
        return f"<SaleItem sale={self.sale_id} cat={self.ticket_category_id} qty={self.quantity}>"
