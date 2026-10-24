# Bemol / staging: Compose, SSH, Nginx y Certbot

Nginx + Certbot son el proxy y gestor TLS de staging;
[configuración y operación](NGINX-STAGING.md).

`staging` es la rama principal y versiona la infraestructura de este VPS.
Producción no está configurada; `main` se creará cuando se prepare ese entorno.
Para operar el VPS, usar un checkout de `staging`.

Staging es el único ambiente compartido configurado en esta rama. El
despliegue usa Docker Compose por SSH, sin Dokploy. Desarrollo local, Dockerfiles
y publicación de imágenes pertenecen a los repositorios de API/UI.

Esta guía describe el contrato operativo; no acredita por sí sola el estado vivo
del VPS. Antes de modificarlo, comprobar el destino de `ssh home-server`, el
hostname real, contenedores, mounts, versiones y salud. No usar estas instrucciones
para producción ni crear otro ambiente sin autorización.

## Responsabilidades y archivos

```text
Actions → CI del mismo commit → imágenes GHCR → SSH → deploy-staging.sh
Navegador → Cloudflare (general) o directo (institucional) → Nginx → UI → API → PostgreSQL / Redis
```

| Recurso | Fuente / ubicación operativa |
|---|---|
| Checkout del VPS | `/opt/bemol-infra`, checkout operativo para staging |
| Aplicación | `compose.yaml` + `compose.staging.yaml`, proyecto `bemol-staging` |
| Variables privadas de aplicación | `/opt/bemol-infra/.env.staging`, permisos `0600` |
| Plantilla pública de aplicación | `.env.staging.example` |
| Proxy del host | `nginx.service`, principal `/etc/nginx/nginx.conf` |
| Configuración por responsabilidad | `deploy/nginx/` → `/etc/bemol/nginx/` |
| Certificado general + wildcard | `/etc/letsencrypt/live/bemol-staging/` |
| Credenciales DNS privadas | `/etc/letsencrypt/cloudflare.ini`, root y `0600` |
| Renovación | `certbot.timer` y hook `deploy/certbot/reload-nginx.sh` |

Los workflows de API/UI publican imágenes de sus ramas `staging` y solicitan el
mismo comando remoto. Leer sus `.github/workflows/deploy-staging.yaml` para los
triggers, nombres de secrets y permisos efectivos. El host necesita acceso de
lectura a GHCR; no colocar credenciales de registro en Compose ni en Git.
Un push a infraestructura no sincroniza por sí solo los archivos privados del VPS.

## Primera instalación en un VPS nuevo

Este procedimiento crea una base **vacía**; no migra ni restaura otro staging.
Confirmar el host y contexto Docker antes de iniciarlo. No usarlo si corresponde
conservar datos de una instalación anterior.

Requisitos del host:

- Docker Engine y Compose con soporte para `!reset`, `make`, Bash y `flock`.
- Checkout de `staging` en `/opt/bemol-infra` y acceso de lectura a las imágenes GHCR.
- Una identidad de despliegue con acceso a Docker y lectura de `.env.staging`.
  Los despliegues siguientes y el timer deben usar esa misma identidad.
- `.env.staging` completo, con permiso `0600`, versiones publicadas y secretos
  nuevos para esta instalación; no reemplazar credenciales de otra instalación.
- Los cinco volúmenes y la red de staging enumerados abajo no deben existir,
  ni debe haber contenedores del proyecto `bemol-staging`.

Desde el checkout, con la identidad de despliegue:

```sh
cd /opt/bemol-infra
make init
```

Equivale a `bash scripts/deploy-staging.sh --init`. El mismo lock de despliegue
protege la operación completa. Primero valida la configuración y rechaza recursos
existentes; después descarga las imágenes y crea los volúmenes y la red externos.
Luego arranca el stack con la misma configuración del despliegue habitual.
PostgreSQL crea la base configurada si falta y reutiliza una existente sin borrarla
ni reemplazarla. Su healthcheck exige una consulta SQL exitosa sobre esa base por
TCP antes de permitir el arranque de API. No modifica `.env.staging` ni ejecuta backups.

El modo inicial no se utiliza en actualizaciones ni en los workflows.
Nginx, Certbot, DNS, el usuario de despliegue y el timer de backup se preparan por
separado; `make init` instala el stack de aplicación, no configura el host.

Si falla tras crear recursos, se conservan los volúmenes, contenedores y sus datos;
no se eliminan recursos ni se restaura nada automáticamente. No repetir `make init`
ni borrar volúmenes para forzarlo: inspeccionar el estado, corregir la causa y
continuar con `make deploy`. En un fallo posterior a las migraciones, preservar
también los nuevos datos antes de decidir una recuperación.

## Desplegar una instalación existente

Desde el checkout operativo de la rama `staging`, el entrypoint de actualización es:

```sh
cd /opt/bemol-infra
./scripts/deploy-staging.sh
```

Por SSH, ejecutar ese mismo comando fijo desde la identidad de despliegue
configurada; no conceder root genérico al job de Actions. El script no recibe
argumentos ni código de shell procedente del workflow.

Actions utiliza una clave SSH dedicada, compartida sólo por los environments
`staging` de API/UI; no la clave personal del operador. Su entrada en
`authorized_keys` combina `restrict` con el comando fijo
`cd /opt/bemol-infra && exec bash scripts/deploy-staging.sh`. Los cinco secrets
`DEPLOY_*` permanecen en GitHub; el host se valida con sus claves ya confiadas,
sin aceptar automáticamente una clave obtenida de la red.

Deploy y backup programado usan el usuario `staging`, miembro de `docker`.
No alternar con root: el lock compartido en `/tmp` y los archivos privados deben
seguir siendo accesibles por esa identidad. Los permisos de backup se preparan
por separado y no son un requisito para desplegar.

El script toma `/tmp/bemol-infra-staging.lock`, comprueba el Compose y descarga
únicamente UI, API y el auxiliar `api-storage-init`. Aplica el stack con
`up --wait`, hasta 900
segundos, y `--pull never`: no actualiza PostgreSQL/Redis como efecto secundario de
publicar una aplicación. No ejecuta backups ni exige un PostgreSQL ya arrancado
para respaldarlo antes del despliegue. No borrar el archivo de lock para forzar un deploy.

Un exit code exitoso exige healthchecks del stack; completar además la comprobación
HTTPS y la función afectada. Un fallo deja visible el error, sin restauración ni
rollback automático. No lanzar dos despliegues o tareas de mantenimiento en
paralelo fuera del lock compartido.

### Versiones y cambios de variables

- `UI_VERSION=staging` y `API_VERSION=staging` siguen los tags publicados por
  Actions. Cambian con cada publicación; el siguiente deploy puede actualizar ambas.
- Para una versión inmutable usar tags `sha-<commit>` publicados y comprobados, o
  un pin de manifest como `staging@sha256:<digest>`. Compose antepone el repositorio
  de `UI_IMAGE` / `API_IMAGE`; no copiar una referencia completa en `*_VERSION`.
- El primer corte conserva las imágenes en ejecución mediante sus digests. No
  reconstruirlas ni aprovechar la migración para actualizar PostgreSQL/Redis.
- Editar sólo las variables necesarias en `.env.staging`, conservando credenciales
  DB, JWT, refresh, SMTP, passkeys, storage y la política actual de auto-login.
- Una variable nueva necesita consumidor, paso explícito por Compose y plantilla
  pública actualizada. Editar el archivo o hacer `restart` no actualiza el entorno:
  se requiere el deploy autorizado. Las variables compiladas de UI requieren imagen.

Para un cambio exclusivamente de configuración, fijar primero ambas imágenes
conocidas; no usar tags móviles si no se desea actualizar código.

## Datos persistentes y redes

| Volumen externo existente | Contenido |
|---|---|
| `bemol-api-postgres-data-staging` | PostgreSQL 18, `/var/lib/postgresql` |
| `bemol-api-redis-data-staging` | Redis, `/data`; incluye persistencia ligada a sesiones |
| `bemol-api-enrollment-storage-staging` | Archivos locales, `/app/storage` |
| `bemol-api-logs-staging` | Logs de API, `/app/logs` |
| `bemol-ui-next-cache-staging` | Caché Next, `/app/.next/cache` |

En actualizaciones, si falta un volumen, detenerse; no crear una base vacía.
Sólo `make init` crea recursos para una primera instalación autorizada.
PostgreSQL crea `DB_NAME` si falta y conserva una base existente; no comprueba que
contenga datos. Un nombre incorrecto puede crear otra base vacía. El entrypoint
versionado de `docker/` se monta en sólo lectura.
No ejecutar dos PostgreSQL sobre el mismo volumen. `api-storage-init` prepara los
permisos de archivos antes de iniciar API; su éxito no prueba una carga/descarga.

`bemol-network-staging` conecta los servicios de aplicación. UI publica sólo
`127.0.0.1:3000`, que utiliza el upstream del Nginx instalado en el host.
API permanece en `127.0.0.1:8080` para mantenimiento y en la red interna para
Next.js; PostgreSQL/Redis no publican puertos. Nginx en el host es quien escucha en `80` y `443`.

## Proxy y HTTPS

El acceso general es **`staging.bemol.com.ar`**, proxied por Cloudflare en modo
Full (strict). Nginx exige un peer Cloudflare; no alcanza con falsificar
`CF-Connecting-IP` o `X-Forwarded-For`. Los rangos confiables se mantienen en
`conf.d/cloudflare.conf`, tanto para restaurar la IP real como para comprobar el
peer original. No cambiar la política de toda la zona por iniciativa.

Los hosts `<institucion>.staging.bemol.com.ar` usan wildcard **DNS-only** hacia el
VPS, sin TLS, WAF ni límites del edge de Cloudflare. Nginx los admite directamente
con certificado wildcard; valida un único nivel de slug DNS. No añadir AAAA sin
IPv6 operativo, aliases ni `www` para resolver un problema del acceso general.

### Archivos separados por responsabilidad

`deploy/nginx/nginx.conf` se instala en `/etc/nginx/nginx.conf`; el árbol completo
se copia a `/etc/bemol/nginx/`. No se cargan además los viejos includes de
`/etc/nginx/sites-enabled` y `/etc/nginx/conf.d`. El principal sólo reúne proceso,
eventos, logs e includes; no contiene toda la política de la aplicación.

- `conf.d/`: upstream UI, Cloudflare, gzip, política de caché y zonas de límites.
- `snippets/`: TLS, headers de seguridad, transporte al upstream y rutas privadas.
- `sites/staging.conf`: hosts general/institucional, redirecciones y rechazos.

Nginx envía `/api/*` a Next.js, que maneja la sesión y llama internamente a
Spring. `/api/v1`, `/api/v1/*` y `/actuator*` públicos devuelven `403`. No hay
upstream público de API. Se conserva `Host` y se reconstruyen los headers de IP
antes de enviarlos al upstream; no se concatenan headers arbitrarios del cliente.

Los límites generales son 20 solicitudes/s, burst 100; autenticación 30/min,
burst 20; concurrencia 50 por cliente y 200 por host, cuerpo máximo 32 MiB.
El dominio general cuenta por IP. En los institucionales IPv4 cuenta por IP e
IPv6 por red `/64`, incluidos autenticación y concurrencia. Las zonas Nginx se
comparten entre workers/rutas; no son contadores separados por router como antes.

Las respuestas siguen sin buffering para streaming. La compresión usa gzip.
No hay caché HTTP compartida en Nginx: Next.js conserva sus propios headers de
caché, incluidos los de assets versionados. No agregar `expires` global ni caché
de documentos privados. La caché de sesiones TLS no almacena respuestas HTTP.
No agregar `add_header` en un `location` sin conservar los headers heredados.

Tras copiar una modificación autorizada de configuración, analizarla antes de
recargar. Un `nginx -t` fallido debe detener la operación:

```sh
sudo nginx -t && sudo systemctl reload nginx
```

### Certificados y renovación

Certbot DNS-01 con el plugin Cloudflare gestiona un certificado llamado
`bemol-staging`, con `staging.bemol.com.ar` y `*.staging.bemol.com.ar`. El token DNS
existente permanece limitado a la zona; no se guarda en Git ni en `.env.staging`.
Su INI privado es root y `0600`. No usar `certbot --nginx`: el instalador puede
reescribir la configuración separada. La emisión inicial se documenta en la guía
de Nginx; no repetirla en cada deploy.

`certbot.timer` ejecuta la renovación. El hook instalado en
`/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh` analiza y recarga Nginx sólo
si está activo. Para una
comprobación de renovación **autorizada**, que escribe TXT temporales:

```sh
sudo certbot renew --cert-name bemol-staging --dry-run --run-deploy-hooks
```

Verificar timer, resultado de Certbot, recarga y certificado efectivamente
servido. Logs sin errores no prueban renovación. No borrar TXT ajenos ni resetear
almacenes ACME. Nginx no publica un dashboard; no modificar DNS ajeno
como efecto secundario de una actualización.

## Backups y rollback limitado

Los backups son independientes del despliegue y del proxy. `make backup-db` permite
solicitar uno manualmente. El timer `bemol-backup@staging.timer` ejecuta
`make backup-db ENV=staging` en `/opt/bemol-infra`, a las 02:15 del reloj del servidor,
con hasta 15 minutos aleatorios y recuperación de ejecuciones perdidas.
El helper selecciona exactamente un PostgreSQL vivo por volumen y label de servicio;
no depende de nombres efímeros de contenedor.

El timer instala `User=staging` y `Group=staging`; para usar backups, mantener
`/var/backups/bemol` con grupo `staging` y permiso `0710`, y su subdirectorio
`staging` propiedad de ese usuario, permiso `0700`. Estos directorios no son
necesarios para `make init` ni `make deploy`.

Los dumps quedan por defecto en `/var/backups/bemol/staging`, permisos `0600`,
retención de siete días. `BACKUP_DIR` y `BACKUP_RETENTION_DAYS` permiten cambiar esos
valores. La rotación ocurre sólo tras validar un dump nuevo con `pg_restore --list`;
esa validación **no** es un ensayo de restauración. Revisar el timer y
`Result`/`ExecMainStatus` del oneshot; `inactive/dead` después de éxito es normal.

PostgreSQL no respalda los adjuntos. Antes de un corte destructivo, preservar y
validar también los archivos locales o el destino S3 activo, según corresponda.
Ni `make init` ni `make deploy` crean un dump ni un punto de recuperación previo
a cada cambio. Mantener una copia fuera del host cuando se requieran backups:
el backup en el mismo disco no cubre pérdida del VPS.

Por decisión del usuario no se conserva configuración histórica de Dokploy ni un
rollback al panel. Se conservan los datos y las imágenes conocidas. Para volver a
una versión, fijar ambos tags/digests compatibles y ejecutar el mismo script.
No se revierten migraciones Flyway. Una restauración de DB/archivos requiere otro
plan aprobado, pausar escrituras y preservar datos nuevos antes de reemplazarlos.
No usar `down -v`, `docker system prune`, ni borrar volúmenes para arreglar un deploy.

## Comprobaciones y aceptación funcional pendiente

Tras un cambio autorizado, comprobar estado y healthchecks de Compose, mounts,
imágenes efectivas, HTTPS general y login de plataforma, redirección HTTP, denegación
de rutas privadas y origen directo y logs. Revisar backup/timer cuando sean parte
del cambio solicitado. Si cambia almacenamiento,
comprobar carga/descarga autorizadas con datos descartables. No afirmar pruebas de
registro, login, correo, adjuntos o restauración si sólo se revisaron healthchecks.

API/UI construyen `<institucion>.staging.bemol.com.ar`. La configuración versionada
incluye el wildcard DNS-only, el certificado wildcard de Certbot y los hosts de
Nginx. Routing, TLS y páginas de acceso se verificaron en el corte; eso no prueba
los flujos completos de login, refresh, passkeys o adjuntos. El tráfico
institucional evita Cloudflare y no hereda WAF ni límites de edge. El RP
actual es `staging.bemol.com.ar`; las passkeys del dominio retirado necesitan
registro nuevo. Se conserva el remitente SMTP existente según la decisión del
usuario; no se acredita un remitente nuevo por actualizar el dominio general.

El [registro de renombre](RENOMBRE-BEMOL.md) documenta una operación pasada,
no instrucciones para reinstalar componentes retirados ni borrar datos. Este
repositorio no contiene suites de tests ni harnesses de aceptación; los tests de
aplicación permanecen en API/UI. No ejecutar seeds, restauraciones o despliegues
adicionales por iniciativa al consultar esta guía.

## Corte verificado: 2026-10-22

- Destino comprobado por SSH: `cristinet`. Aplicación en `bemol-staging` y proxy en
  `bemol-proxy-staging`, saludables; cinco volúmenes existentes conservados.
- El primer arranque mantuvo los IDs exactos de imágenes de API/UI y las imágenes
  locales de PostgreSQL/Redis. Coincidieron los conteos de las 115 tablas públicas y
  los hashes de los dos archivos almacenados antes y después del corte.
- Se creó y validó el dump `bemol-staging-20261022T183957Z.dump` y los archivos
  `bemol-staging-files-20261022T183959Z.tar` y
  `bemol-staging-redis-20261022T183959Z.tar`, bajo `/var/backups/bemol/staging`.
  No se realizó un ensayo de restauración ni una copia fuera del host.
- HTTPS general `303`, login general/plataforma `200`, HTTP→HTTPS `301`, rutas
  privadas y origen directo `403`; TLS de origen validado sin excepciones. El
  hostname retirado del panel devuelve `404`; su DNS no se modificó.
- Se retiraron servicios, contenedores, red, volúmenes de metadatos, imagen y
  directorio de Dokploy, sin respaldar su configuración anterior.
- El comando fijo SSH se ejecutó correctamente como `staging`, con backup y salud
  completos, sin reiniciar PostgreSQL/Redis. El timer sigue activo y el servicio
  de backup finalizó con `Result=success`; ambos usan la identidad `staging`.
  La retención sólo examina dumps en el directorio principal, sin recorrer
  respaldos históricos privados. Las versiones privadas quedan en `staging` para
  las siguientes publicaciones; eso no cambió las imágenes en ejecución.
- Las ramas remotas todavía usaban Dokploy al terminar ese primer corte. La
  promoción posterior de workflows y los secrets SSH se verificaron como se
  registra en la sección siguiente.
- Se validaron sintaxis, Compose efectivo, salud, HTTPS y persistencia; no suites
  de tests ni flujos completos de registro, correo, passkeys o adjuntos.
  La aceptación funcional completa sigue pendiente.

## Workflows SSH verificados: 2026-10-22

- Promoción aislada a `staging`, sin cambios de aplicación ni merges de `develop`:
  API `2c32ecea527f870b897d7fe8a7cf1e12631076a4` y UI
  `8c51d329157f7cf13237537f823daae931da13e7`. Cada commit modifica únicamente su
  workflow y documentación, con un padre y mensaje subject-only; push sin force.
- Los cinco secrets `DEPLOY_*` se configuraron en ambos environments `staging`
  con una clave nueva restringida al script. Se conservan las claves anteriores;
  la copia privada temporal local se eliminó después de verificar SSH y CI.
- [API Actions](https://github.com/TypeItOrg/bemol-api/actions/runs/39837329100) y
  [UI Actions](https://github.com/TypeItOrg/bemol-ui/actions/runs/39836939921): CI,
  publicación y despliegue SSH finalizaron correctamente. Los manifests
  `linux/amd64` de los tags SHA publicados coinciden con los contenedores vivos.
  Un índice OCI puede cambiar por su procedencia sin cambiar el manifest de la
  plataforma; no forzar una recreación sólo porque difiera el ID del índice.
- Configuración pública y guía aplicadas en el VPS y versionadas en la rama
  `staging` de este repositorio. No se cambió el modo SSL de toda la zona
  Cloudflare ni se ejecutaron suites locales adicionales.
