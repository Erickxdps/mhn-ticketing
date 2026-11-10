"""Registro y anulación de ventas.

Una venta puede entregarse de dos formas (ajuste global del sistema):

- QR: cada unidad genera un ticket con código MHN-AAAAMMDD-000001 y un
  QR que se imprime y se valida al ingresar.
- BOOKLET (talonario): cada unidad usa el siguiente número del talonario
  físico de su categoría; el sistema no imprime nada.

En ambos casos todo ocurre en una sola transacción: si algo falla no
queda ninguna venta, ítem, ticket ni número de talonario a medio usar.
"""

import uuid
from datetime import datetime

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Sale, SaleItem, Ticket, TicketCategory
from app.services import audit_service, settings_service, talonarios_service
from app.services.cierres_service import dia_cerrado
from app.utils.money import a_decimal, formatear_numero_boleto

# Métodos de pago soportados a nivel interno.
PAYMENT_METHODS = ("CASH", "QR")
PAYMENT_METHOD_LABELS = {"CASH": "Efectivo", "QR": "QR"}

MAX_REINTENTOS_CODIGO = 3
MAX_UNIDADES_POR_CATEGORIA = 1000


class VentaError(Exception):
    """Error de validación o de negocio al registrar o anular una venta.
    El mensaje es apto para mostrar al usuario."""


def _siguiente_secuencia(prefix):
    """Siguiente número secuencial del día para el prefijo MHN-AAAAMMDD-."""
    ultimo = (
        Ticket.query.filter(Ticket.ticket_code.like(f"{prefix}%"))
        .order_by(Ticket.ticket_code.desc())
        .first()
    )
    if ultimo:
        return int(ultimo.ticket_code.rsplit("-", 1)[-1]) + 1
    return 1


def _validar_lineas(items):
    """Valida las líneas y devuelve [(categoria, cantidad), ...]."""
    maximo_venta = current_app.config.get("MAX_TICKETS_POR_VENTA", 300)
    lineas = []
    total = 0
    vistas = set()
    for item in items or []:
        cantidad = item.get("quantity", 0)
        if not isinstance(cantidad, int) or isinstance(cantidad, bool):
            raise VentaError("Las cantidades deben ser números enteros.")
        if cantidad <= 0:
            continue
        if cantidad > MAX_UNIDADES_POR_CATEGORIA:
            raise VentaError(
                f"No se pueden vender más de {MAX_UNIDADES_POR_CATEGORIA} entradas de una categoría en una venta."
            )

        categoria_id = item.get("ticket_category_id")
        if categoria_id in vistas:
            raise VentaError("Una categoría aparece repetida en la venta.")
        vistas.add(categoria_id)

        categoria = db.session.get(TicketCategory, categoria_id)
        if not categoria or not categoria.is_active:
            raise VentaError("Una de las categorías elegidas no existe o está inactiva.")

        total += cantidad
        lineas.append((categoria, cantidad))

    if not lineas:
        raise VentaError("Indica una cantidad mayor a 0 en al menos una categoría.")
    if total > maximo_venta:
        raise VentaError(
            f"Una venta no puede superar {maximo_venta} entradas (pediste {total}). "
            "Si es un grupo grande, divídelo en varias ventas."
        )
    return lineas


def _intentar_crear_venta(user, payment_method, lineas, modo):
    sold_at = datetime.now()
    es_talonario = modo == settings_service.MODO_TALONARIO

    prefix = f"MHN-{sold_at.strftime('%Y%m%d')}-"
    siguiente_seq = None if es_talonario else _siguiente_secuencia(prefix)

    total_amount = a_decimal(0)
    calculadas = []
    for categoria, cantidad in lineas:
        unit_price = a_decimal(categoria.price)
        subtotal = (unit_price * cantidad).quantize(unit_price)
        total_amount += subtotal
        calculadas.append((categoria, cantidad, unit_price, subtotal))

    sale = Sale(
        user_id=user.id,
        total_amount=total_amount,
        payment_method=payment_method,
        created_at=sold_at,
        sales_mode=modo,
        status="ACTIVE",
    )
    db.session.add(sale)
    db.session.flush()

    for categoria, cantidad, unit_price, subtotal in calculadas:
        sale_item = SaleItem(
            sale_id=sale.id,
            ticket_category_id=categoria.id,
            quantity=cantidad,
            unit_price=unit_price,
            subtotal=subtotal,
        )
        db.session.add(sale_item)
        db.session.flush()

        if es_talonario:
            for talonario, numero in talonarios_service.reservar_numeros(categoria, cantidad):
                db.session.add(
                    Ticket(
                        sale_item_id=sale_item.id,
                        ticket_code=f"TAL-{categoria.id:02d}-{numero:05d}",
                        qr_token=uuid.uuid4().hex,
                        # El boleto de talonario se rompe en la puerta: no se
                        # escanea, así que nace como utilizado.
                        status="USED",
                        sold_at=sold_at,
                        used_at=sold_at,
                        booklet_id=talonario.id,
                        physical_number=numero,
                    )
                )
        else:
            for _ in range(cantidad):
                db.session.add(
                    Ticket(
                        sale_item_id=sale_item.id,
                        ticket_code=f"{prefix}{siguiente_seq:06d}",
                        qr_token=uuid.uuid4().hex,
                        status="UNUSED",
                        sold_at=sold_at,
                    )
                )
                siguiente_seq += 1

    audit_service.registrar(
        "venta.crear",
        entidad="sale",
        entidad_id=sale.id,
        detalle=(
            f"{'talonario' if es_talonario else 'QR'}; "
            f"{sum(c for _, c, _, _ in calculadas)} entradas; Bs {total_amount}; pago {payment_method}"
        ),
        usuario=user,
    )
    db.session.commit()
    return sale


def crear_venta(user, payment_method, items, modo=None):
    """Registra una venta completa.

    `items`: lista de {"ticket_category_id": int, "quantity": int}.
    `modo`: "QR" o "BOOKLET"; si no se indica se usa el ajuste global.

    Ante una colisión de código de ticket (dos ventas simultáneas) se
    reintenta unas pocas veces recalculando la secuencia.
    """
    if payment_method not in PAYMENT_METHODS:
        raise VentaError("Método de pago inválido.")

    modo = modo or settings_service.get_modo_venta()
    if modo not in settings_service.MODOS_VENTA:
        raise VentaError("Modo de venta inválido.")

    if dia_cerrado(datetime.now().date()):
        raise VentaError(
            "El día de hoy ya está cerrado: no se pueden registrar más ventas. "
            "Un administrador puede reabrir el cierre desde Cierre diario."
        )

    lineas = _validar_lineas(items)

    intentos = 0
    while True:
        intentos += 1
        try:
            return _intentar_crear_venta(user, payment_method, lineas, modo)
        except IntegrityError:
            db.session.rollback()
            if modo == settings_service.MODO_TALONARIO or intentos >= MAX_REINTENTOS_CODIGO:
                current_app.logger.exception("Venta: conflicto de unicidad al guardar")
                raise VentaError(
                    "No se pudo guardar la venta por un conflicto de numeración. "
                    "Vuelve a intentarla."
                )
        except talonarios_service.TalonarioError as error:
            db.session.rollback()
            raise VentaError(str(error))
        except VentaError:
            db.session.rollback()
            raise
        except Exception:
            db.session.rollback()
            # El detalle técnico va al archivo de registro, no a la pantalla.
            current_app.logger.exception("Venta: error inesperado al registrar")
            raise VentaError(
                "No se pudo registrar la venta. Inténtalo de nuevo; si el problema "
                "continúa, avisa a un administrador."
            )


def anular_venta(sale_id, motivo, usuario):
    """Anula una venta completa (error de cobro, devolución).

    - La venta no se borra: queda como ANULADA con motivo y responsable.
    - Sus tickets pasan a CANCELLED; una entrada con QR anulada ya no se
      puede validar.
    - Los números de talonario de una venta anulada NO se reutilizan: el
      boleto físico se conserva y se marca como anulado.
    - No se anula si alguna entrada con QR ya fue utilizada, ni si el día
      de la venta ya está cerrado.
    """
    venta = db.session.get(Sale, sale_id)
    if venta is None:
        raise VentaError("La venta no existe.")
    if venta.is_voided:
        raise VentaError("Esa venta ya está anulada.")

    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        raise VentaError("Escribe el motivo de la anulación (mínimo 5 caracteres).")

    if dia_cerrado(venta.created_at.date()):
        raise VentaError(
            f"El día {venta.created_at:%d/%m/%Y} ya está cerrado. "
            "Reabre el cierre antes de anular ventas de ese día."
        )

    tickets = [t for item in venta.sale_items for t in item.tickets]
    usados_qr = [t for t in tickets if not t.is_physical and t.status == "USED"]
    if usados_qr:
        raise VentaError(
            f"No se puede anular: {len(usados_qr)} entrada(s) con QR de esta venta ya fueron utilizadas."
        )

    ahora = datetime.now()
    for ticket in tickets:
        ticket.status = "CANCELLED"
        ticket.void_reason = motivo[:200]
        ticket.voided_at = ahora
        ticket.voided_by = usuario.id

    venta.status = "VOIDED"
    venta.voided_at = ahora
    venta.voided_by = usuario.id
    venta.void_reason = motivo[:200]

    numeros = ""
    if venta.is_booklet:
        numeros = "; números: " + ", ".join(
            f"{formatear_numero_boleto(t.physical_number)}" for t in tickets if t.is_physical
        )
    audit_service.registrar(
        "venta.anular",
        entidad="sale",
        entidad_id=venta.id,
        detalle=f"Bs {a_decimal(venta.total_amount)}; {len(tickets)} entradas{numeros}; motivo: {motivo}",
        usuario=usuario,
    )
    db.session.commit()
    return venta
