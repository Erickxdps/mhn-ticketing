from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db

# Roles oficiales. validate_strings hace que SQLAlchemy rechace un valor
# fuera de la lista antes de llegar a la base de datos.
USER_ROLES = ("ADMIN", "SELLER", "INSPECTOR")


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(
        db.Enum(*USER_ROLES, name="user_role", validate_strings=True), nullable=False
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    # Relaciones. Sale tiene dos claves hacia users (vendedor y quien
    # anuló), por eso se indica cuál usa cada relación.
    sales = db.relationship(
        "Sale", back_populates="user", lazy="dynamic", foreign_keys="Sale.user_id"
    )
    daily_closures = db.relationship(
        "DailyClosure", back_populates="closed_by_user", lazy="dynamic"
    )

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    # UserMixin.is_authenticated devuelve is_active: un usuario desactivado
    # pierde el acceso de inmediato, incluso con la sesión ya abierta.

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"
