"""
Respaldo de la base de datos del museo.

Copia instance/museo.db a instance/backups/ con la fecha y hora en el
nombre, usando la API de respaldo de SQLite (sqlite3.Connection.backup),
que es segura aunque el servidor siga funcionando: no captura escrituras
a medio hacer (copiar el archivo a mano NO es seguro, porque con el modo
WAL parte de los datos puede estar todavía en el archivo museo.db-wal).

Después de copiar:
  1. Verifica la copia con PRAGMA integrity_check (un respaldo que no abre
     no sirve de nada).
  2. Si existe la variable BACKUP_EXTRA_DIR (por ejemplo la letra de un
     pendrive, E:\\respaldos, o una carpeta sincronizada con la nube),
     deja también una copia ahí: así un respaldo no vive en el mismo
     disco que la base de datos.
  3. Borra los respaldos con más de RETENCION_DIAS días.

Uso manual:
    python backup_db.py

Para que se ejecute solo todas las noches, ver programar_respaldo.bat.
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta

from config import Config, basedir

RETENCION_DIAS = 60
PATRON = ("museo_", "pre_actualizacion_")


class RespaldoError(Exception):
    pass


def ruta_base_datos(uri=None):
    """Ruta al archivo .db si la base es SQLite; None si es otro motor."""
    uri = uri or Config.SQLALCHEMY_DATABASE_URI
    prefijo = "sqlite:///"
    if not uri.startswith(prefijo):
        return None
    ruta = uri[len(prefijo):]
    if ruta in ("", ":memory:"):
        return None
    if not os.path.isabs(ruta):
        # Flask-SQLAlchemy interpreta las rutas relativas desde instance/
        ruta = os.path.join(basedir, "instance", ruta)
    return ruta


def _verificar(ruta):
    conexion = sqlite3.connect(ruta)
    try:
        resultado = conexion.execute("PRAGMA integrity_check").fetchone()
    finally:
        conexion.close()
    if not resultado or resultado[0] != "ok":
        raise RespaldoError(f"El respaldo {ruta} no pasó la verificación de integridad.")


def crear_respaldo(prefijo="museo", origen=None, carpeta=None, extra_dir=None):
    """Crea y verifica un respaldo. Devuelve la ruta del archivo creado."""
    origen = origen or ruta_base_datos()
    if origen is None:
        raise RespaldoError(
            "La base de datos configurada no es SQLite (probablemente PostgreSQL). "
            "Este script solo respalda SQLite; para PostgreSQL usa pg_dump."
        )
    if not os.path.exists(origen):
        raise RespaldoError(f"No se encontró la base de datos en: {origen}")

    carpeta = carpeta or os.path.join(basedir, "instance", "backups")
    os.makedirs(carpeta, exist_ok=True)

    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = os.path.join(carpeta, f"{prefijo}_{marca}.db")

    conexion_origen = sqlite3.connect(origen)
    conexion_destino = sqlite3.connect(destino)
    try:
        with conexion_destino:
            conexion_origen.backup(conexion_destino)
    finally:
        conexion_origen.close()
        conexion_destino.close()

    try:
        _verificar(destino)
    except RespaldoError:
        os.remove(destino)
        raise

    extra = extra_dir if extra_dir is not None else os.environ.get("BACKUP_EXTRA_DIR", "").strip()
    if extra:
        try:
            os.makedirs(extra, exist_ok=True)
            shutil.copy2(destino, os.path.join(extra, os.path.basename(destino)))
        except OSError as error:
            # El respaldo local ya existe; se avisa pero no se descarta.
            print(f"AVISO: no se pudo copiar a {extra}: {error}")

    _limpiar_antiguos(carpeta)
    return destino


def _limpiar_antiguos(carpeta):
    limite = datetime.now() - timedelta(days=RETENCION_DIAS)
    eliminados = 0
    for nombre in os.listdir(carpeta):
        if not (nombre.startswith(PATRON) and nombre.endswith(".db")):
            continue
        ruta = os.path.join(carpeta, nombre)
        if datetime.fromtimestamp(os.path.getmtime(ruta)) < limite:
            os.remove(ruta)
            eliminados += 1
    if eliminados:
        print(f"Se eliminaron {eliminados} respaldo(s) de más de {RETENCION_DIAS} días.")
    return eliminados


def main():
    try:
        destino = crear_respaldo()
    except RespaldoError as error:
        print(f"ERROR: {error}")
        sys.exit(1)
    print(f"Respaldo creado y verificado: {destino}")
    if os.environ.get("BACKUP_EXTRA_DIR", "").strip():
        print(f"Copia adicional en: {os.environ['BACKUP_EXTRA_DIR'].strip()}")
    else:
        print(
            "Consejo: define BACKUP_EXTRA_DIR en el archivo .env (por ejemplo un pendrive) "
            "para guardar también una copia fuera de este disco."
        )


if __name__ == "__main__":
    main()
