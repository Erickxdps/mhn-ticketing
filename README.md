# Museo de Historia Natural — Sistema de Entradas

Aplicación web para **vender entradas, controlar el ingreso y cuadrar la caja del día** en el Museo de Historia Natural.
Funciona en la red local del museo y **no necesita internet**: fuentes, iconos y librerías están incluidos.

**Tecnologías:** Python 3.11+, Flask, SQLite, Waitress. Diseño propio con HTML, CSS y JavaScript (sin dependencias externas).

---

## Características

- **Dos modos de venta**, que se cambian con un clic en *Ajustes*:
  - **Ticket con QR:** cada venta genera tickets imprimibles; se validan en la puerta con escáner o cámara.
  - **Talonario físico:** el sistema indica qué números del talonario entregar y lleva la cuenta de cada categoría.
- **Control de ingreso** por QR (escáner USB o cámara del celular).
- **Cierre diario** por categoría, con el rango de números consumidos para cuadrar con el talonario.
- **Reportes** con filtros, paginación y exportación a CSV (se abre en Excel).
- **Auditoría** de precios, anulaciones, talonarios, cierres, usuarios y ajustes.
- **Roles** con permisos distintos: administrador, vendedor e inspector.
- **Modo claro y oscuro**, adaptado a laptop y celular, con impresión para impresora térmica de 80 mm.

## Roles

| Rol | Puede |
|---|---|
| **ADMIN** | Todo: dashboard, reportes, cierres, categorías, talonarios, usuarios, ajustes y auditoría. |
| **SELLER** (vendedor) | Registrar ventas, ver sus propias ventas y anular números dañados. |
| **INSPECTOR** | Validar entradas QR. |

---

## Modo talonario físico

- Categorías y precios de ejemplo: **Mayores Bs 5, Menores Bs 3, Extranjeros Bs 12, Tercera edad Bs 2, Cortesía Bs 2** (editables en *Categorías*).
- Cada categoría tiene su propio talonario con un rango de números (por ejemplo, `00249` al `00500`). Se registra en **Talonarios → Registrar talonario o reposición**.
  - El **primer número** es el primer boleto que se va a entregar. Si el último vendido fue el 00249, empieza en 00250.
- Al vender, el sistema asigna los siguientes números en orden (por ejemplo, 9 Mayores desde el 00249 → `00249 – 00257`) y muestra qué boletos entregar. Si una venta cruza dos talonarios, indica los dos tramos.
- **Avisos de stock:** cuando quedan pocos boletos (por defecto 20, configurable) o no hay talonario, aparece una alerta con la **reposición sugerida**, continuando desde el último número registrado. Un administrador puede registrarla sin interrumpir las ventas.
- **Boleto dañado o saltado:** *Talonarios → Anular un número*. Queda registrado como anulado, no se vuelve a entregar y no suma a la caja.
- **Venta anulada** (solo ADMIN): sus números quedan anulados y nunca se reutilizan.
- Cada boleto de talonario se cuenta como **ingresado al venderse**; no se valida por QR.
- El **cierre diario** muestra, por categoría, el rango de números consumidos ese día.

---

## Instalación (Windows)

**Requisito:** Python 3.11 o superior.

1. En la carpeta del proyecto, crea el entorno e instala las dependencias:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Crea o actualiza la base de datos:
   ```
   flask --app run.py upgrade-db
   ```
3. Crea el primer administrador (siempre **después** del paso anterior):
   ```
   flask --app run.py create-admin
   ```
4. Inicia el sistema con **`iniciar_servidor.bat`** (doble clic).

El sistema arranca **minimizado** (la ventana negra queda en la barra de tareas; no la cierres mientras atiendes público) y abre solo el navegador en `http://localhost:8472`.

### Acceso directo en el Escritorio

Ejecuta una sola vez `crear_acceso_directo.bat`. Crea en el Escritorio, con el icono del museo:

- **Sistema de Entradas MHN** — equivale a `iniciar_servidor.bat`.
- **Sistema de Entradas MHN (HTTPS)** — equivale a `iniciar_https.bat` (para usar la cámara del celular).

Usa solo uno a la vez. Ambos inician minimizados y abren el navegador.

### Actualizar un sistema ya en uso

1. Apaga el sistema (cierra la ventana negra o pulsa `Ctrl+C`).
2. Copia los archivos nuevos sobre la carpeta del proyecto.
   **No borres ni reemplaces** `instance\` (base de datos, usuarios y respaldos) ni `venv\`.
3. Vuelve a abrir con `iniciar_servidor.bat`.

Al iniciar, el sistema revisa la base de datos **solo cuando cambió el sistema** (primera vez o tras actualizar); el resto de las veces arranca directo. La revisión (`flask upgrade-db`) guarda antes un respaldo `pre_actualizacion_*.db` en `instance\backups`, es segura de repetir y conserva todas las ventas. También puede ejecutarse a mano con `actualizar_bd.bat`.

---

## Acceder desde otros dispositivos

Funciona en la **misma red Wi-Fi o cable**; los datos móviles no sirven.

1. Permite el puerto en el firewall de Windows, una sola vez (PowerShell como administrador):
   ```
   netsh advfirewall firewall add rule name="MHN Entradas" dir=in action=allow protocol=TCP localport=8472
   ```
2. Averigua la IP de la computadora con `ipconfig`. Usa la **Dirección IPv4 del adaptador Wi-Fi o Ethernet**, no la de adaptadores virtuales (VirtualBox, WSL, Docker o VPN).
3. Desde el otro dispositivo, abre `http://IP-de-la-computadora:8472`.

**Recomendaciones:**
- Pide que el router reserve siempre la misma IP a esa computadora, para que la dirección no cambie.
- Los nombres tipo `equipo.local` dependen del dispositivo y fallan en muchos Android; usa la IP.
- No abras este puerto en el router hacia internet.

---

## HTTPS (necesario para usar la cámara en celulares)

Los navegadores móviles solo permiten la cámara en páginas **HTTPS**. Se logra con [Caddy](https://caddyserver.com/) delante del sistema.

**Preparación (una sola vez):**
1. Descarga Caddy para Windows (`Windows amd64`) desde https://caddyserver.com/download y copia `caddy.exe` a la carpeta del sistema.
2. Permite el puerto 443 en el firewall (PowerShell como administrador):
   ```
   netsh advfirewall firewall add rule name="MHN HTTPS" dir=in action=allow protocol=TCP localport=443
   ```

**Uso diario:** abre `iniciar_https.bat` en lugar de `iniciar_servidor.bat` (no uses los dos a la vez). Arranca minimizado, detecta la IP del Wi-Fi y abre `https://localhost`.
Desde el celular, entra a `https://IP-de-la-computadora` (**sin puerto**). Para apagar, cierra las dos ventanas de la barra de tareas (Caddy y Flask).

**Certificado:** Caddy genera uno propio, así que el navegador avisa "no es seguro" la primera vez: elige *Avanzado → Continuar*. Si aun así la cámara no se activa, instala el certificado en el celular:

1. Copia `%APPDATA%\Caddy\pki\authorities\local\root.crt` al celular.
2. Instálalo en *Ajustes → Seguridad → Cifrado y credenciales → Instalar un certificado → Certificado de CA*.
3. Cierra y vuelve a abrir el navegador.

---

## Respaldos

- `respaldar_bd.bat` crea una copia verificada en `instance\backups` (se conservan 60 días).
- `programar_respaldo.bat` programa un respaldo diario a las 18:30.
- Para una segunda copia automática en otro disco o carpeta, define `BACKUP_EXTRA_DIR` (ver `.env.example`).
- La base usa modo WAL: **no copies `museo.db` a mano con el sistema en marcha**; usa el script.

## Seguridad y reglas importantes

- Protección CSRF en todos los formularios y en la validación por AJAX.
- Contraseñas de mínimo 8 caracteres, sin claves comunes ni iguales al usuario. Tras 5 intentos fallidos, la cuenta se bloquea 15 minutos.
- La `SECRET_KEY` se genera sola en `instance\secret.key` si no se define.
- Un **día cerrado** no admite ventas ni anulaciones; un ADMIN puede reabrirlo y queda en la auditoría.
- Los tickets QR vencen según *Días de vigencia* (por defecto 1 = solo el día de la venta; 0 = no vencen).
- Pensado para uso en red local. No lo expongas directamente a internet.

---

## Pruebas

```
pip install -r requirements-dev.txt
python -m pytest
```

## Estructura del proyecto

| Ruta | Contenido |
|---|---|
| `app/` | Código de la aplicación (rutas, modelos, servicios, plantillas y archivos estáticos). |
| `instance/` | Datos locales: base de datos, respaldos y clave secreta. **No se sube a Git.** |
| `tests/` | Pruebas automáticas. |
| `*.bat` | Scripts de inicio, respaldo, actualización y acceso directo para Windows. |
