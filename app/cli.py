import click
from flask.cli import with_appcontext

from app.extensions import db
from app.models import User
from app.security import validar_password


@click.command("create-admin")
@click.option("--username", prompt=True)
@click.option("--full-name", prompt="Nombre completo")
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
)
@with_appcontext
def create_admin_command(username, full_name, password):
    """Crea el usuario administrador inicial (rol ADMIN).

    Uso:
        flask create-admin
    """
    username = username.strip()
    if User.query.filter(db.func.lower(User.username) == username.lower()).first():
        click.echo(f"Ya existe un usuario con username '{username}'. No se creó nada.")
        return

    error = validar_password(password, username)
    if error:
        raise click.ClickException(error)

    admin = User(
        username=username,
        full_name=full_name.strip(),
        role="ADMIN",
        is_active=True,
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()

    click.echo(f"Usuario administrador '{username}' creado correctamente.")


@click.command("reset-password")
@click.option("--username", prompt=True)
@click.option(
    "--password",
    prompt="Nueva contraseña",
    hide_input=True,
    confirmation_prompt=True,
)
@with_appcontext
def reset_password_command(username, password):
    """Restablece la contraseña de un usuario (por ejemplo si el único
    administrador la olvidó) y lo reactiva si estaba inactivo.

    Uso:
        flask reset-password
    """
    from app.security import limitador_login
    from app.services import audit_service

    usuario = User.query.filter(db.func.lower(User.username) == username.strip().lower()).first()
    if usuario is None:
        raise click.ClickException(f"No existe el usuario '{username}'.")
    error = validar_password(password, usuario.username)
    if error:
        raise click.ClickException(error)

    usuario.set_password(password)
    usuario.is_active = True
    audit_service.registrar(
        "usuario.restablecer_password_consola",
        entidad="user",
        entidad_id=usuario.id,
        detalle=f"{usuario.username}: contraseña restablecida desde la consola",
        usuario=usuario,
    )
    db.session.commit()
    limitador_login.reiniciar()
    click.echo(f"Contraseña de '{usuario.username}' restablecida.")


@click.command("upgrade-db")
@click.option("--sin-respaldo", is_flag=True, help="No crear respaldo previo (no recomendado).")
@with_appcontext
def upgrade_db_command(sin_respaldo):
    """Crea o actualiza la base de datos (idempotente, con respaldo previo).

    Úsalo tanto en una instalación nueva como después de actualizar el
    sistema. Si ya está al día no hace nada.

    Uso:
        flask upgrade-db
    """
    from app.db_upgrade import actualizar_base_de_datos

    acciones = actualizar_base_de_datos(respaldo=not sin_respaldo)
    if not acciones:
        click.echo("La base de datos ya está al día. No hubo cambios.")
        return
    click.echo("Base de datos actualizada:")
    for accion in acciones:
        click.echo(f"  - {accion}")


def register_cli(app):
    app.cli.add_command(create_admin_command)
    app.cli.add_command(reset_password_command)
    app.cli.add_command(upgrade_db_command)
