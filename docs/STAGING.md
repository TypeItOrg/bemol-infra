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
4. Ejecuta `up --detach --pull missing --wait --wait-timeout 900`.

El proyecto Compose es `bemol-staging`. PostgreSQL y Redis se descargan sólo si
sus imágenes no están disponibles localmente. `api-storage-init` prepara los
permisos del almacenamiento antes de iniciar la API.

**El despliegue no ejecuta backups, no borra datos y no configura el host.** Nginx,
Certbot, DNS, usuarios y timers se preparan por separado. Crear un volumen vacío
no recupera datos de otro servidor: si deben conservarse, restaurarlos antes.

Si falla, revisar el error, corregir la causa y repetir el mismo comando. No hay
rollback automático. No borrar el lock ni ejecutar `down -v`, limpiezas globales
o eliminaciones de volúmenes para resolver un despliegue.

Editar `.env.staging` y hacer `restart` no actualiza el entorno de los contenedores:
volver a desplegar. Con tags móviles, ese deploy también puede actualizar ambas
aplicaciones; fijar versiones conocidas si el cambio debe ser sólo de configuración.

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
