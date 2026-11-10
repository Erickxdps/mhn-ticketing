"""
Datos iniciales.

Crea las tablas que falten, los ajustes por defecto y las cinco
categorías vigentes del museo (Mayores Bs 5, Menores Bs 3, Extranjeros
Bs 12, Tercera edad Bs 2, Cortesía Bs 2). Es idempotente: se puede
ejecutar varias veces sin duplicar nada. Si la base viene de la versión
anterior, renombra Adulto/Niño/Extranjero conservando su historial.

Es lo mismo que:  flask --app run.py upgrade-db

Uso:
    python seed.py
"""

from app import create_app
from app.db_upgrade import actualizar_base_de_datos


def seed():
    app = create_app()
    with app.app_context():
        acciones = actualizar_base_de_datos()
        if not acciones:
            print("Todo estaba al día. No hubo cambios.")
        for accion in acciones:
            print(f"- {accion}")


if __name__ == "__main__":
    seed()
