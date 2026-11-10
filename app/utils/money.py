"""Lectura y formato seguros de dinero y cantidades que llegan desde
formularios."""

import re
from decimal import Decimal, InvalidOperation

CENTAVO = Decimal("0.01")


class ErrorValidacion(ValueError):
    """Dato de formulario inválido; el mensaje es apto para mostrar."""


def parsear_precio(crudo, maximo=Decimal("9999.99")):
    """Convierte "12", "12.5" o "12,50" en Decimal con 2 decimales.

    Rechaza vacío, texto, NaN, Infinity, negativos, más de 2 decimales y
    valores por encima de `maximo`. (Antes se aceptaba "Infinity", "1e30"
    o "10.999", que dejaban precios imposibles guardados.)
    """
    texto = (crudo or "").strip().replace(",", ".")
    if not texto:
        raise ErrorValidacion("El precio es obligatorio.")
    if len(texto) > 12:
        raise ErrorValidacion("El precio no es válido.")
    try:
        valor = Decimal(texto)
    except InvalidOperation:
        raise ErrorValidacion("El precio debe ser un número válido (por ejemplo 5 o 5.50).")
    if not valor.is_finite():
        raise ErrorValidacion("El precio debe ser un número válido (por ejemplo 5 o 5.50).")
    if valor < 0:
        raise ErrorValidacion("El precio no puede ser negativo.")
    if valor != valor.quantize(CENTAVO):
        raise ErrorValidacion("El precio admite como máximo 2 decimales.")
    valor = valor.quantize(CENTAVO)
    if valor > maximo:
        raise ErrorValidacion(f"El precio no puede superar Bs {maximo}.")
    return valor


def parsear_entero(crudo, nombre="El valor", minimo=0, maximo=10**9):
    """Entero acotado. `nombre` se usa en el mensaje de error."""
    texto = str(crudo).strip() if crudo is not None else ""
    if not texto:
        raise ErrorValidacion(f"{nombre} es obligatorio.")
    if len(texto) > 12 or not re.fullmatch(r"[+-]?\d+", texto):
        raise ErrorValidacion(f"{nombre} debe ser un número entero.")
    valor = int(texto)
    if valor < minimo:
        raise ErrorValidacion(f"{nombre} no puede ser menor que {minimo}.")
    if valor > maximo:
        raise ErrorValidacion(f"{nombre} no puede ser mayor que {maximo}.")
    return valor


def a_decimal(valor):
    """Normaliza lo que devuelve la base de datos (float en SQLite) a
    Decimal con 2 decimales."""
    if valor is None:
        return Decimal("0.00")
    if isinstance(valor, Decimal):
        return valor.quantize(CENTAVO)
    return Decimal(str(round(float(valor), 2))).quantize(CENTAVO)


def formatear_bs(valor):
    return f"{a_decimal(valor):.2f}"


def formatear_numero_boleto(numero):
    """Número de boleto de talonario con ceros a la izquierda: 249 -> 00249."""
    if numero is None:
        return "—"
    return f"{int(numero):05d}"
