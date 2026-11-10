from datetime import datetime

from app.extensions import db

SALE_MODES = ("QR", "BOOKLET")      # QR impreso / talonario físico
SALE_STATUSES = ("ACTIVE", "VOIDED")


class Sale(db.Model):
    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(30), nullable=False)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.now, index=True
    )

    # Modo en que se entregaron las entradas: QR (ticket impreso) o
    # BOOKLET (boleto físico de talonario). Las ventas anteriores a esta
    # versión quedan como QR.
    sales_mode = db.Column(
        db.String(10), nullable=False, default="QR", server_default="QR"
    )

    # Una venta no se borra: se anula, con motivo y responsable.
    status = db.Column(
        db.String(10), nullable=False, default="ACTIVE", server_default="ACTIVE"
    )
    voided_at = db.Column(db.DateTime, nullable=True)
    voided_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    void_reason = db.Column(db.String(200), nullable=True)

    user = db.relationship("User", back_populates="sales", foreign_keys=[user_id])
    voided_by_user = db.relationship("User", foreign_keys=[voided_by])
    sale_items = db.relationship(
        "SaleItem",
        back_populates="sale",
        cascade="all, delete-orphan",
        order_by="SaleItem.id",
    )

    __table_args__ = (
        db.CheckConstraint("sales_mode IN ('QR', 'BOOKLET')", name="ck_sales_mode"),
        db.CheckConstraint("status IN ('ACTIVE', 'VOIDED')", name="ck_sales_status"),
        db.CheckConstraint("total_amount >= 0", name="ck_sales_total_non_negative"),
    )

    @property
    def is_voided(self):
        return self.status == "VOIDED"

    @property
    def is_booklet(self):
        return self.sales_mode == "BOOKLET"

    @property
    def total_tickets(self):
        return sum(item.quantity for item in self.sale_items)

    def __repr__(self):
        return f"<Sale #{self.id} - {self.total_amount}>"
