# Importar todos los modelos aquí para que Flask-Migrate y create_all los
# detecten (Alembic y SQLAlchemy recorren los modelos registrados en db).

from app.models.user import User
from app.models.ticket_category import TicketCategory
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.ticket_booklet import TicketBooklet
from app.models.booklet_void import BookletVoid
from app.models.ticket import Ticket
from app.models.daily_closure import DailyClosure
from app.models.app_setting import AppSetting
from app.models.audit_log import AuditLog

__all__ = [
    "User",
    "TicketCategory",
    "Sale",
    "SaleItem",
    "TicketBooklet",
    "BookletVoid",
    "Ticket",
    "DailyClosure",
    "AppSetting",
    "AuditLog",
]
