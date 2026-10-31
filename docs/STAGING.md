# Staging: configuración y operación

Esta rama configura únicamente staging. Producción no está preparada; el desarrollo
local y la publicación de imágenes pertenecen a los repositorios de API/UI.
Esta guía describe los archivos versionados, no acredita el estado actual del VPS.
Antes de operar, confirmar el destino SSH, hostname y contexto Docker.

```text
GitHub Actions → CI → imágenes GHCR → SSH → Docker Compose
Navegador → Nginx del host → Next.js → API → PostgreSQL / Redis
```

## Archivos y requisitos

| Archivo | Responsabilidad |
|---|---|
| [compose.yaml](../compose.yaml) | Servicios, puertos, recursos y montajes compartidos |
| [compose.staging.yaml](../compose.staging.yaml) | Perfil staging y nombres de volúmenes/red |
| [.env.staging.example](../.env.staging.example) | Plantilla pública de variables |
| [deploy-staging.sh](../scripts/deploy-staging.sh) | Instalación y actualización de la aplicación |
| [Nginx y Certbot](NGINX-STAGING.md) | Configuración del proxy, dominios y certificados |
| [S3](S3.md) | Almacenamiento opcional de archivos |

El host necesita Docker Engine, Compose con soporte para `!reset`, Bash, `make`
y `flock`; un checkout de `staging` en `/opt/bemol-infra` y acceso de lectura a
las imágenes GHCR. Usar una identidad con acceso a Docker y al archivo privado
`.env.staging`; no alternar usuarios para deploy y backup porque comparten un lock.

Crear `.env.staging` a partir de la plantilla sólo si no existe. Completar versiones,
credenciales, dominios y correo; no reemplazar secretos de una instalación existente.
El script exige que el archivo sea legible y no tenga permisos para grupo u otros:

```sh
chmod 600 /opt/bemol-infra/.env.staging
```

`UI_VERSION` y `API_VERSION` no tienen valor en la plantilla: deben referenciar
imágenes publicadas. `staging` sigue el último tag de esa rama; `sha-<commit>` fija
una publicación concreta. También se admite `staging@sha256:<digest>` como versión.
No copiar el nombre completo de la imagen en esas variables: el repositorio lo
aportan `UI_IMAGE` y `API_IMAGE`.

## Instalar o actualizar

Desde el checkout, con la identidad de despliegue:

```sh
cd /opt/bemol-infra
make deploy
```

`make` sin argumentos no hace nada; el despliegue requiere un objetivo explícito.

Es el mismo flujo para un VPS vacío y para actualizaciones. El script:

1. Toma `/tmp/bemol-infra-staging.lock` y valida `.env.staging` y el Compose combinado.
2. Descarga UI, API y `api-storage-init`.
3. Crea los cinco volúmenes y la red si faltan; reutiliza los existentes.
4. Lee `public/maintenance.html` de la imagen UI y actualiza atómicamente
   `.deploy/maintenance/maintenance.html`, antes de reemplazar la aplicación.
5. Ejecuta `up --detach --pull missing --wait --wait-timeout 900`.

El proyecto Compose es `bemol-staging`. PostgreSQL y Redis se descargan sólo si
sus imágenes no están disponibles localmente. `api-storage-init` prepara los
permisos del almacenamiento antes de iniciar la API.

La extracción ejecuta sólo `cat` en un contenedor temporal de UI, sin iniciar
Next.js, publicar puertos ni levantar dependencias. Si la imagen no incluye la
pantalla o la extracción falla, el script aborta antes de reemplazar la aplicación
y conserva la copia anterior. No borrar `.deploy/maintenance` mientras Nginx lo usa.

**El despliegue no ejecuta backups, no borra datos y no configura el host.** Nginx,
Certbot, DNS, usuarios y timers se preparan por separado. Crear un volumen vacío
no recupera datos de otro servidor: si deben conservarse, restaurarlos antes.

Si falla, revisar el error, corregir la causa y repetir el mismo comando. No hay
rollback automático. No borrar el lock ni ejecutar `down -v`, limpiezas globales
o eliminaciones de volúmenes para resolver un despliegue.

Editar `.env.staging` y hacer `restart` no actualiza el entorno de los contenedores:
volver a desplegar. Con tags móviles, ese deploy también puede actualizar ambas
aplicaciones; fijar versiones conocidas si el cambio debe ser sólo de configuración.

## Pantalla temporal y recuperación

La pantalla se genera durante `dev` y `build` con Tailwind y los tokens de
`globals.css`; el HTML resultante incluye CSS, fuente y logo, sin CDN ni recursos
externos. Es un único archivo autocontenido de UI: funciona desde Next.js cuando
la API no está lista y desde Nginx si el frontend no responde. Comprueba
`/api/health`, que verifica también readiness de la API, y vuelve a la dirección
original mediante una navegación GET; no reenvía formularios ni Server Actions.

El recambio de contenedores sigue siendo el habitual: no hay blue/green, no se
duplican servicios y el corte no desaparece. Nginx entrega la pantalla con `503`,
`Cache-Control: no-store` y `Retry-After: 5` sólo a navegación HTML segura; API,
RSC, assets y mutaciones no reciben HTML de mantenimiento.

Para activarla, publicar primero una imagen UI que contenga `maintenance.html`,
actualizar el checkout de infraestructura y ejecutar `make deploy`. Después
instalar los dos archivos de Nginx modificados, validar y recargar según
[NGINX-STAGING.md](NGINX-STAGING.md). No se aplican al host automáticamente.
Una caída de Nginx o del VPS queda fuera de esta pantalla.

## Entrega desde GitHub Actions

Los workflows `.github/workflows/deploy-staging.yaml` de API y UI reaccionan a
pushes a `staging`: primero CI, luego publicación en GHCR y finalmente SSH.
Ambos ejecutan:

```sh
cd /opt/bemol-infra && exec bash scripts/deploy-staging.sh
```

El environment `staging` de cada repositorio necesita `DEPLOY_HOST`, `DEPLOY_PORT`,
`DEPLOY_USER`, `DEPLOY_SSH_KEY` y `DEPLOY_SSH_KNOWN_HOSTS`. Usar una clave dedicada,
con `restrict` y el comando anterior forzado en `authorized_keys`; verificar la
clave del host por un canal confiable, sin aceptar automáticamente una de la red.

Estos workflows no actualizan el checkout de infraestructura ni sus archivos
privados. Un push a este repositorio tampoco aplica Nginx ni despliega por sí solo.

## Persistencia y red

| Volumen externo | Montaje en el contenedor |
|---|---|
| `bemol-api-postgres-data-staging` | `/var/lib/postgresql` — PostgreSQL 18 |
| `bemol-api-redis-data-staging` | `/data` — persistencia Redis |
| `bemol-api-enrollment-storage-staging` | `/app/storage` — archivos locales |
| `bemol-api-logs-staging` | `/app/logs` — logs de API |
| `bemol-ui-next-cache-staging` | `/app/.next/cache` — caché Next.js |

El Compose base declara los volúmenes externos; staging asigna sus nombres reales.
El script los crea fuera de Compose. La red externa es `bemol-network-staging`.

PostgreSQL crea `DB_NAME` si falta y reutiliza una base existente. Su healthcheck
exige una consulta SQL exitosa sobre esa base antes de iniciar la API. Un nombre
incorrecto puede crear una base vacía; no arrancar dos PostgreSQL sobre un volumen.

UI y API publican por defecto `127.0.0.1:3000` y `127.0.0.1:8080`, respectivamente.
PostgreSQL y Redis no publican puertos del host. Nginx utiliza el puerto de UI del
VPS; si cambia `UI_HOST_PORT`, ajustar también su upstream. Next.js llama a la API
por la red Docker, no por el puerto público de Nginx.

## Backups independientes

Backup manual:

```sh
cd /opt/bemol-infra
make backup-db
```

Comparte el lock con deploy: una operación espera a que termine la otra. El script
selecciona exactamente un PostgreSQL activo por volumen y label, genera un dump y
comprueba su índice con `pg_restore --list`; eso no prueba una restauración completa.

Por defecto usa `/var/backups/bemol/staging`, archivos `0600` y
`BACKUP_RETENTION_DAYS=7`. `BACKUP_DIR` cambia la raíz. La limpieza de dumps antiguos
ocurre sólo después de validar uno nuevo. Estos directorios no son necesarios para
desplegar; prepararlos con acceso exclusivo para la identidad de backup.

La programación es opcional: [las unidades systemd](../deploy/systemd/) se instalan
por separado. Usan usuario/grupo `staging`, que debe existir y tener acceso a Docker,
`.env.staging`, al lock y al directorio de backups. El timer `bemol-backup@staging.timer`
programa las 02:15 del reloj del servidor, hasta 15 minutos aleatorios después, y
recupera ejecuciones perdidas. No dejar dos programaciones para el mismo backup.

El dump no incluye adjuntos ni Redis. Un backup en el mismo VPS no cubre la pérdida
del servidor: conservar copias externas y comprobar restauraciones por separado.

## Rollback y comprobaciones

Para volver a una versión de aplicación, fijar imágenes inmutables compatibles y
usar `make deploy`. Cambiar de imagen **no revierte migraciones Flyway**. Restaurar
DB o archivos requiere un plan específico, pausar escrituras y preservar los datos
nuevos antes de reemplazarlos.

Después de un cambio, comprobar contenedores y healthchecks, imágenes y montajes
efectivos, HTTPS y la función afectada. La validación del proxy está en
[NGINX-STAGING.md](NGINX-STAGING.md). Un healthcheck no prueba login, correo, passkeys,
adjuntos ni recuperación de datos; verificar esos flujos cuando formen parte del cambio.

## Administración de plataforma: alta de llave y recuperación

La administración se publica en `https://admin.staging.bemol.com.ar`, DNS-only hacia
el VPS. No usa Cloudflare Access ni su WAF. Nginx lo atiende mediante la expresión
regular y los bloques HTTP/HTTPS compartidos con las instituciones, sin bloques
específicos para `admin`. Next.js y la API distinguen el dominio configurado en
`PLATFORM_PUBLIC_URL` y aplican la autenticación administrativa con passkey.
La administración se abre en la raíz del subdominio, sin el prefijo `/admin`:
`/` muestra el panel si hay sesión y, si no, lleva a `/auth/login`.
Los enlaces del panel usan rutas como `/institutions` y `/account/passkeys`.
Next.js las reescribe internamente a sus páginas `/admin/...`, sin cambiar la URL
visible. Los enlaces antiguos con `/admin` redirigen a la ruta pública equivalente;
sus mutaciones se rechazan, no se reenvían. Las rutas `/api/admin/*` no cambian.
Antes de activar, comprobar que el certificado `bemol-staging` cubra
`*.staging.bemol.com.ar`, validar `nginx -t` y verificar el destino DNS.
No añadir AAAA sin IPv6 operativo.

Configurar `PLATFORM_PUBLIC_URL=https://admin.staging.bemol.com.ar` en el entorno de
API/UI y recrear los contenedores mediante el despliegue existente. El dominio
institucional y sus variables WebAuthn no cambian. La migración de MFA cierra las
sesiones previas de plataforma; API y UI deben actualizarse coordinadamente.
No reutilizar el frontend anterior, que esperaba tokens después de la contraseña.

### Primera configuración o pérdida de todas las llaves

1. Verificar el host SSH, el contexto Docker y la identidad del administrador por
   un canal de confianza. El código no restablece su contraseña ni crea cuentas.
2. Obtener el UUID de `platform_accounts` correspondiente a la cuenta habilitada.
   Puede consultarse en su detalle desde otra sesión administrativa o mediante
   una consulta de solo lectura en PostgreSQL:

   ```sql
   SELECT platform_account_id, email FROM platform_accounts WHERE enabled ORDER BY email;
   ```

   No usar el UUID del usuario institucional.
3. Desde una terminal SSH interactiva, ejecutar:

   ```sh
   cd /opt/bemol-infra
   make platform-passkey-setup ACCOUNT_ID=UUID_DE_LA_CUENTA
   ```

4. Entregar el código mostrado por un canal privado. Expira en **15 minutos** y es
   de **un solo uso**. Emitir otro invalida el anterior. No guardarlo en tickets,
   chats, archivos, logs o capturas de pantalla; el comando rechaza stdout no interactivo.
5. El administrador ingresa email y contraseña en el nuevo dominio. Si ya tenía
   llaves, elige **Perdí mis llaves de acceso**. Presenta el código y registra una
   llave con su dispositivo compatible. Solo después obtiene una sesión.

El servidor conserva únicamente el hash del código en Redis, ligado a la cuenta.
La autorización por sí sola no permite acceder al panel ni registrar llaves en otra
cuenta. Al completar la recuperación, una transacción revoca las llaves anteriores,
registra la nueva y cierra las sesiones previas. La nueva sesión usa la nueva llave.
Un fallo o vencimiento puede requerir emitir otro código; nunca borrar credenciales
ni desactivar MFA manualmente para resolverlo. Si Redis pierde el código, emitir otro.

Con acceso normal, **Llaves de acceso** en el menú del administrador reutiliza el
gestor existente. Permite agregar una llave de respaldo, renombrar y eliminar.
Agregar o eliminar exige confirmar con una llave existente; no se permite borrar
la última. Eliminar otra cierra las sesiones, incluida la actual.

En desarrollo local, `http://admin.localhost:3000` permite ingresar solo con email y
contraseña por defecto. Para probar el flujo completo, iniciar la API con
`PLATFORM_PASSKEY_REQUIRED=true make dev` desde `bemol-api`, o definir esa variable
en `.env.dev`. No se configura en la UI: esta sigue la respuesta del backend.
Cerrar sesión y volver a ingresar para probar el cambio de modo.
Solo el perfil `dev` permite desactivar la exigencia; fuera de él, incluida cualquier
combinación con `staging`, `prod` o `production`, la API rechaza esa configuración
al iniciar. Staging y producción mantienen las passkeys obligatorias por defecto.

Con passkeys activadas en local se usa el mismo contrato Redis: la clave
`bemol:platform:setup:<uuid>` contiene el SHA-256 del código en Base64, con TTL de
900 segundos. Se puede emitir con los contenedores locales siguiendo la receta del
script; el comando de infraestructura selecciona exclusivamente el proyecto y los
volúmenes de staging para evitar operar otro entorno. No usar el modo solo contraseña
con datos reales ni en entornos compartidos o expuestos.

### Comprobación después de activar

Verificar con una cuenta de prueba: contraseña sola no abre sesión, alta con código,
login con llave, alta de respaldo y rescate. Confirmar que el host principal y los
institucionales rechazan mutaciones administrativas, que sus páginas antiguas
redirigen al nuevo dominio y que los accesos institucionales siguen funcionando.
No ejecutar `FLUSHALL`, `down -v` ni modificar contraseñas o datos institucionales.
