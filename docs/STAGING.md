# Bemol / staging: Compose, SSH y Traefik

La rama `main` corresponde a producción y `staging` a la infraestructura de este
VPS. Esta actualización no aprovisiona ni despliega producción. Para operar el
VPS, usar un checkout de `staging`, nunca `main`.

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
Navegador → Cloudflare → Traefik → UI → API → PostgreSQL / Redis
```

| Recurso | Fuente / ubicación operativa |
|---|---|
| Checkout del VPS | `/opt/bemol-infra`, checkout operativo para staging |
| Aplicación | `compose.yaml` + `compose.staging.yaml`, proyecto `bemol-staging` |
| Variables privadas de aplicación | `/opt/bemol-infra/.env.staging`, permisos `0600` |
| Plantilla pública de aplicación | `.env.staging.example` |
| Proxy independiente | `compose.proxy.yaml`, proyecto `bemol-proxy-staging` |
| Configuración estática privada | `/etc/bemol/traefik/traefik.yml` |
| Reglas dinámicas | `/etc/bemol/traefik/dynamic/traefik-staging.yaml` |
| Entorno privado de Traefik | `/etc/bemol/traefik/traefik.env` |

Los workflows de API/UI publican imágenes de sus ramas `staging` y solicitan el
mismo comando remoto. Leer sus `.github/workflows/deploy-staging.yaml` para los
triggers, nombres de secrets y permisos efectivos. El host necesita acceso de
lectura a GHCR; no colocar credenciales de registro en Compose ni en Git.
Un push a infraestructura no sincroniza por sí solo los archivos privados del VPS.

## Desplegar la aplicación

Desde el checkout operativo de la rama `staging`, el único entrypoint de deploy es:

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
seguir siendo accesibles por esa identidad. El timer instala `User=staging` y
`Group=staging`; mantener `/var/backups/bemol` con grupo `staging` y permiso `0710`,
y su subdirectorio `staging` propiedad de ese usuario, permiso `0700`.

El script toma `/tmp/bemol-infra-staging.lock`, comprueba el Compose y descarga
únicamente UI, API y el auxiliar `api-storage-init`. Crea un dump PostgreSQL
validado antes de aplicar el stack con `up --wait`, hasta 900
segundos, y `--pull never`: no actualiza PostgreSQL/Redis como efecto secundario de
publicar una aplicación. No borrar el archivo de lock para forzar un deploy.

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

Si falta un volumen, detenerse; no crear una base vacía. PostgreSQL exige que
`DB_NAME` ya exista y monta el entrypoint versionado de `docker/` en sólo lectura.
No ejecutar dos PostgreSQL sobre el mismo volumen. `api-storage-init` prepara los
permisos de archivos antes de iniciar API; su éxito no prueba una carga/descarga.

`bemol-network-staging` conecta los servicios de aplicación. Sólo UI entra además
a `bemol-proxy-staging` con alias `bemol-ui-staging`; API, DB y Redis no pertenecen
a la red pública del proxy. UI no publica puerto de host. API permanece accesible
únicamente por loopback para mantenimiento; PostgreSQL/Redis no publican puertos.
El proxy publica solamente `80` y `443`, sin puerto de dashboard `8080` ni socket
Docker montado. El dashboard usa un hostname HTTPS propio y autenticación.

## Proxy y HTTPS

El acceso general es **`staging.bemol.com.ar`** y el dashboard protegido usa
**`traefik-staging.bemol.com.ar`**. Ambos tienen un registro A proxied en Cloudflare
hacia el VPS; el modo requerido es **Full (strict)**. El token DNS no permite leer
ese ajuste global: comprobarlo en el panel, sin cambiar toda la zona por iniciativa.
DNS no configura Traefik ni emite certificados.
No añadir AAAA sin IPv6 operativo, aliases, `www`, wildcard ni rutas institucionales
para resolver un problema del acceso general.

`deploy/traefik/traefik-static.staging.example.yaml` es una configuración estática
completa: entradas 80/443, forwarded headers confiados sólo desde rangos Cloudflare,
provider de archivos y resolver `cloudflare-staging`. Habilita el dashboard con
`api.insecure: false`, sin provider Docker. Instalarla como `traefik.yml` conservando
el contacto ACME real.

`deploy/traefik/traefik-staging.yaml` define todos los routers, también el general
HTTPS y la redirección HTTP. El file provider observa `/etc/traefik/dynamic`; su
servicio apunta a `http://bemol-ui-staging:3000`. El árbol privado del host se monta
en `/etc/traefik` y permite escribir el estado ACME.

El token DNS-01 y el almacenamiento ACME **activos** se conservan al cambiar de
proxy; no se regeneran, imprimen ni versionan. Son datos operativos vivos, no un
archivo de configuración histórica. El token tiene Zone:Read y DNS:Edit únicamente
sobre `bemol.com.ar`. Rutas vistas por el contenedor:

```dotenv
CF_DNS_API_TOKEN_FILE=/etc/traefik/dynamic/.secrets/cloudflare-dns-token
```

El resolver guarda su estado en
`/etc/traefik/dynamic/.secrets/acme-cloudflare-staging.json`. Mantener el directorio
privado y `.secrets` en `0700`, y entorno, token y JSON en `0600`. No poner secretos
en YAML dentro del directorio dinámico. Let's Encrypt emite el certificado exacto
del acceso general y Traefik administra su renovación; no se usa Certbot.
`propagation.requireAllRNS: false` tolera diferencias entre cachés recursivas sin
desactivar la comprobación autoritativa ni la validación ACME.

Para aplicar configuración del proxy, copiar los archivos versionados a sus rutas
privadas sólo con autorización. Los cambios dinámicos se recargan; cambios estáticos
o de entorno requieren recrear el proxy durante una ventana acordada:

```sh
cd /opt/bemol-infra
docker compose -f compose.proxy.yaml up -d --force-recreate
docker compose -f compose.proxy.yaml logs --tail 100 traefik
```

No confundir logs sin errores con renovación ACME comprobada. Verificar certificado
de origen, cobertura y vencimiento sin omitir la validación TLS.

### Dashboard protegido

Abrir **`https://traefik-staging.bemol.com.ar/dashboard/`**, con barra final. Permite
observar routers, servicios y middlewares; no es un reemplazo de Dokploy para
editar Compose o desplegar aplicaciones.

El router HTTPS cubre todo el hostname, incluidos `/dashboard/` y `/api`, y exige
BasicAuth antes de redirigir la raíz a `/dashboard/`. Mantiene la restricción a
Cloudflare, los headers y los límites generales de solicitudes y concurrencia.
El límite de login de la aplicación no se aplica a todos los recursos del panel:
su polling y assets también consumen solicitudes. HTTP sólo redirige a HTTPS.
El certificado del panel es exacto y separado del certificado de la aplicación,
con el mismo resolver DNS-01 `cloudflare-staging`.

Las credenciales son exclusivas del dashboard; no reutilizar root ni credenciales
de Bemol. Instalar el archivo `usuario:hash-bcrypt` como
`/etc/bemol/traefik/dynamic/.secrets/dashboard-users`, propiedad de root y permisos
`0600`, dentro de `.secrets` con `0700`. El middleware lo lee como
`/etc/traefik/dynamic/.secrets/dashboard-users` y elimina `Authorization` antes de
enviar la solicitud al servicio interno. No guardar usuarios ni hashes en YAML.

Las credenciales iniciales quedan únicamente en
`/etc/bemol/traefik/dashboard-access`, fuera del directorio dinámico, propiedad de
root y permisos `0600`; consultarlas por SSH autorizado. No copiarlas a Git, logs
ni workflows. Crear ambos archivos antes de activar el router y recrear el proxy
para aplicar `api.dashboard: true`. Comprobar TLS, `401` sin credenciales y con
credenciales incorrectas, y acceso autenticado tanto al panel como a `/api`.

Si se agrega un hostname TLS al mismo tiempo que se cambia la configuración
estática, detener primero el proxy antes de copiar ambos archivos e iniciarlo.
El file provider puede comenzar ACME al ver el router nuevo: recrear el proceso
durante ese desafío deja un TXT huérfano y puede causar `identical record already
exists`. No borrar desafíos ajenos ni resetear el almacén ACME; comprobar el emisor
y el registro exacto antes de una limpieza autorizada.

### Protecciones conservadas y límites

- Se restringe el acceso general a peers Cloudflare antes de confiar en
  `CF-Connecting-IP`. Los rangos necesitan mantenimiento; no autentican nuestra zona.
- `/actuator` y `/api/v1` públicos devuelven `403`, sin llegar a UI/API.
- Se conservan headers, gzip, límites por IP y autenticación, concurrencia y cuerpo
  de 32 MiB en POST/PUT/PATCH. GET de descargas/SSE queda sin buffering de cuerpo.
- Los contadores son por router/instancia; no equivalen a un límite global del host.
  El buffering de escrituras también puede demorar respuestas de Server Actions.
- La UI puede mostrar la IP del edge en metadatos de sesiones por su uso de
  `X-Real-IP`; esa diferencia de staging no autoriza a extenderla a producción.

## Backups y rollback limitado

El backup diario es independiente del proxy. `bemol-backup@staging.timer` ejecuta
`make backup-db ENV=staging` en `/opt/bemol-infra`, a las 02:15 del reloj del servidor,
con hasta 15 minutos aleatorios y recuperación de ejecuciones perdidas.
El helper selecciona exactamente un PostgreSQL vivo por volumen y label de servicio;
no depende de nombres efímeros de contenedor.

Los dumps quedan por defecto en `/var/backups/bemol/staging`, permisos `0600`,
retención de siete días. `BACKUP_DIR` y `BACKUP_RETENTION_DAYS` permiten cambiar esos
valores. La rotación ocurre sólo tras validar un dump nuevo con `pg_restore --list`;
esa validación **no** es un ensayo de restauración. Revisar el timer y
`Result`/`ExecMainStatus` del oneshot; `inactive/dead` después de éxito es normal.

PostgreSQL no respalda los adjuntos. Antes de un corte destructivo, preservar y
validar también los archivos locales o el destino S3 activo, según corresponda.
El deploy normal sólo automatiza el dump DB. Mantener una copia fuera del host:
el backup en el mismo disco no cubre pérdida del VPS.

Por decisión del usuario no se conserva configuración histórica de Dokploy ni un
rollback al panel. Se conservan los datos y las imágenes conocidas. Para volver a
una versión, fijar ambos tags/digests compatibles y ejecutar el mismo script.
No se revierten migraciones Flyway. Una restauración de DB/archivos requiere otro
plan aprobado, pausar escrituras y preservar datos nuevos antes de reemplazarlos.
No usar `down -v`, `docker system prune`, ni borrar volúmenes para arreglar un deploy.

## Comprobaciones y acceso institucional pendiente

Tras un cambio autorizado, comprobar estado y healthchecks de Compose, mounts,
imágenes efectivas, HTTPS general y login de plataforma, redirección HTTP, denegación
de rutas privadas y origen directo, logs y backup/timer. Si cambia almacenamiento,
comprobar carga/descarga autorizadas con datos descartables. No afirmar pruebas de
registro, login, correo, adjuntos o restauración si sólo se revisaron healthchecks.

API/UI aún construyen `<institucion>.staging.bemol.com.ar`; no hay DNS, TLS ni router
institucional aprovisionado. El objetivo `<institucion>-staging.bemol.com.ar` requiere
otra etapa de aplicación e infraestructura. No habilitarlo con un wildcard como
atajo. El RP actual es `staging.bemol.com.ar`; las passkeys del dominio retirado
necesitan registro nuevo. Se conserva el remitente SMTP existente según la decisión
del usuario; no se acredita un remitente nuevo por actualizar el dominio general.

El [contrato de aceptación local](institutional-access-checklist.md) utiliza fixtures
descartables y no acredita el VPS. El [registro de renombre](RENOMBRE-BEMOL.md)
documenta una operación pasada, no instrucciones para reinstalar Dokploy ni borrar
datos. No ejecutar tests, seeds, restauraciones o despliegues adicionales por
iniciativa al consultar esta guía.

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
  La aceptación local completa sigue pendiente. Se conserva la prueba de SSH
  simulado para `Q04.failed-deploy-request`, sin ejecutarla; no cubre el deploy
  real ni la coordinación de lock, backup y salud del entrypoint del servidor.

## Workflows SSH y dashboard verificados: 2026-10-22

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
- Dashboard y API de Traefik: `401` sin credenciales y `200` autenticados; raíz
  autenticada redirige a `/dashboard/`. Certificado de origen validado con el
  hostname exacto y cadena confiable; origen directo `403`, aplicación `200`.
- Se creó sólo el A proxied del dashboard, se conservaron el token DNS y el estado
  ACME activos, y se retiró el TXT huérfano creado por esta operación después de
  detener al único emisor. PostgreSQL/Redis no se reiniciaron durante la promoción
  ni el cambio del dashboard; el backup sigue operativo.
- Configuración pública y guía aplicadas en el VPS y versionadas en la rama
  `staging` de este repositorio. No se cambió el modo SSL de toda la zona
  Cloudflare ni se ejecutaron suites locales adicionales.
