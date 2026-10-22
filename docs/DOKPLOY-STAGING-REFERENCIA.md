# Archivo histórico de staging — NO operativo

> **Histórico del 2026-10-20: NO ejecutar como runbook actual.** Los nombres
> anteriores se conservan aquí como evidencia de aquella ventana. El código
> objetivo ya usa `bemol-*`; antes de desplegar seguir
> [RENOMBRE-BEMOL.md](RENOMBRE-BEMOL.md). Nada de este registro acredita el estado
> actual del host ni autoriza crear volúmenes vacíos o sustituir datos.

La configuración versionada de Traefik se reorganizó en
[deploy/traefik/](../deploy/traefik/README.md); su aplicación al servidor está pendiente.
Las rutas `deploy/dokploy/traefik-staging.yaml` citadas abajo pertenecen al historial
y no representan el conjunto actual de archivos.

Para aprender el flujo en orden, empezar por la [guía paso a paso](DOKPLOY-STAGING.md).
El proyecto visible se llama **Bemol**, el environment **staging** y el servicio
Compose **Staging**. En el historial aparecen sus nombres anteriores, Boero staging
y Bemol - Staging. Estas etiquetas no cambian el ID, los nombres Docker, los
repositorios ni los dominios.

**Estado de dominios registrado en aquella ventana:** el dominio general `staging.typeit.com.ar` se
administra en **Domains**; wildcard y políticas específicas siguen en el archivo
dinámico. La receta de campos y el resultado del corte están en la guía paso a paso.
Las versiones y resultados históricos que siguen no constituyen nuevas pruebas.

**Estado registrado: infraestructura migrada y operativa; validación funcional parcial.**
Este archivo registra cómo funcionaba y se operaba staging durante la migración del
2026-10-20 en el host `cristinet`. Staging es el único ambiente compartido
configurado en este repositorio; no hay un despliegue de producción.

Se instalaron Dokploy v0.30.8 y Traefik v3.6.25 durante una ventana autorizada.
El primer arranque conservó las imágenes SHA, valores efectivos y cinco volúmenes
anteriores. Los cuatro servicios permanentes (UI, API, PostgreSQL y Redis) están
saludables; el auxiliar `api-storage-init` es transitorio, no un quinto servidor.
En las comprobaciones de la migración se obtuvo HTTP 200 en health
general/institucional y panel. El sudo temporal fue revocado. Esta evidencia
corresponde a esa ventana, no a una comprobación nueva al editar esta guía.

Los pipelines de [API](https://github.com/TypeItOrg/bemol-api/actions/runs/39491621238)
y [UI](https://github.com/TypeItOrg/bemol-ui/actions/runs/39493133060) terminaron
correctamente y se comprobaron también sus despliegues nativos, salud HTTPS y
manifests de plataforma contra los SHA publicados. El usuario confirmó ingreso y
datos. El puerto 3000 está cerrado; el panel sólo se publica por HTTPS. El backup
diario PostgreSQL está activo y su servicio produjo un dump validado.

El usuario confirmó una **passkey registrada en el panel** y decidió mantenerla así;
registrarla no deshabilita el acceso con contraseña ni convierte el panel en
passkey-only. No se comprobó TOTP activo ni se exige activarlo para cerrar esta
migración por decisión del usuario. La
limpieza de secrets SSH legacy de ambos environments staging está completada.
La diferencia de IP mostrada en Sesiones fue aceptada exclusivamente para staging.

### Resultado de la validación funcional del 2026-10-20

| Recorrido | Resultado y alcance |
|---|---|
| Listados de personas e inscripciones | Lectura verificada; no se modificaron registros existentes |
| PDF demo existente | Preview y descarga correctos; archivo PDF de 1747 bytes |
| Alta de representado nuevo (`NEW`) | Bloqueada por HTTP 400: cuerpo inválido por omisión de `ownAccessRequested` en el contrato UI/API desplegado; el caso de uso no se ejecutó |
| Carga de un adjunto nuevo | No se inició: el alta anterior fue rechazada antes del upload; no puede darse por probada |
| `/my-dependents` | Mostró un error temporal y un `TimeoutError` en UI; al reintentar cargó la lista, sin la persona de prueba. Causa no identificada |
| Passkey de Bemol | Validación manual diferida por el usuario: «Luego lo pruebo yo a eso»; no probada ni declarada no aplicable |

El PDF descargado tuvo SHA-256
`fa54bd21742f38b9d32f91dcd381c64f6cb9be757f1ac8163ceeec6ec926cf47`.
Eso verifica lectura de un archivo preservado, no escritura de adjuntos nuevos.
No se crearon fixtures ni se alteraron datos existentes; la persona de prueba
continuó ausente tras el rechazo. Producción no fue tocada.

La incompatibilidad del alta ya existía en el código de aplicación. El usuario
indicó que la corrigió en `develop`; no se promovió ni se comprobó esa corrección
en staging como parte de esta migración. La revisión funcional no autoriza editar
o publicar cambios adicionales de aplicación.

Durante el timeout de UI, API respondió `GET representations/page` con HTTP 200
en 162 ms; los cuatro servicios seguían saludables y los recursos eran normales.
La lista se recuperó al reintentar; no se identificó la causa del timeout y no se
atribuye a Traefik. Los resultados
anteriores dejan la **aceptación funcional completa pendiente por aplicación**,
sin invalidar la migración operativa ni afirmar que todos los recorridos pasaron.

Se validó una restauración PostgreSQL aislada y se conservaron fuera del host el
dump final, configuración y copias offline de los cinco volúmenes. El wildcard
institucional es DNS-only y el panel usa el proxy Cloudflare, sin extras pagos.
Las copias de volúmenes/configuración fuera del host son snapshots de esta ventana,
no un nuevo respaldo automático de adjuntos o de los metadatos de Dokploy.

## 1. Qué hace cada pieza

**Idea central:** GitHub fabrica las imágenes; Dokploy las ejecuta; Traefik recibe
las visitas. Ninguna de esas piezas reemplaza la lógica de negocio de Bemol.

```text
push a staging → GitHub Actions valida y publica GHCR
              → pide el despliegue por HTTPS a Dokploy
              → Dokploy descarga las imágenes y ejecuta Compose

Internet → Cloudflare (sólo hostname general) → Traefik → UI → API → PostgreSQL/Redis
Internet → Traefik (subdominios institucionales DNS-only) ──┘
```

| Pieza | Responsabilidad | Lo que no hace |
|---|---|---|
| Repositorios API/UI | Código, Dockerfile y desarrollo local de cada aplicación | No guardan los valores privados de staging |
| GitHub Actions | Validar, construir y publicar las imágenes; pedir el deploy por HTTPS | No entra por SSH ni copia archivos `.env` al servidor |
| GHCR (registro de imágenes de GitHub) | Guardar las imágenes Docker publicadas | No inicia contenedores ni almacena la base de datos |
| Dokploy | Panel para variables privadas, despliegues, estado y logs | No compila UI/API en staging ni decide los permisos de Bemol |
| Docker Compose | Describir servicios, variables que recibe cada uno, redes y volúmenes | No descubre automáticamente qué variables necesita el código |
| Traefik | Proxy, HTTPS y reglas HTTP; reemplaza Nginx/Certbot en este staging | No crea instituciones ni autentica usuarios de Bemol |
| Cloudflare | DNS y proxy de los hostnames configurados como proxied | No oculta la IP de los hostnames DNS-only |
| UI / API | UI sirve la interfaz y actúa como intermediaria hacia API; API aplica el negocio y la autorización | API no se publica directamente en Internet |
| PostgreSQL / Redis | PostgreSQL conserva datos de negocio; Redis soporta estado temporal y mecanismos de autenticación/revocación | Redis no sustituye la base ni es una caché para vaciar sin evaluar el impacto |
| `boero-infra` | Configuración declarativa revisable y mantenimiento de datos | No debe contener secretos reales |

Compose sigue siendo **un único stack** de Bemol; no se convirtió PostgreSQL en
una base gestionada por el panel ni se migró el stack de aplicación a Docker Stack.
Dokploy usa Swarm para sus propios componentes, pero eso no cambia ese modo de Bemol.
Sólo UI se conecta a la red del proxy; API habla con PostgreSQL/Redis en la red
privada. El navegador utiliza la UI y sus rutas `/api/*`, no `http://api:8080`.

### Qué versión queda ejecutándose

Sólo un push a la rama `staging` de API o UI solicita este deploy, después de sus
validaciones y publicación. No activar otro auto-deploy por Git/webhook en Dokploy.
Se conservan los tags `sha-<commit>` y `staging` en GHCR.

En el uso normal `UI_VERSION=staging` y `API_VERSION=staging`: se descargan las
últimas imágenes publicadas de esa rama. No significa que el HEAD de Git ya esté
desplegado: una revisión con CI fallido no se publica, y UI/API tienen pipelines
independientes. Un redeploy puede actualizar ambas imágenes. Registrar sus digests
y los tags SHA al aceptar cada versión; para reproducir o volver atrás, fijar ambos
`sha-<commit>` en Dokploy. No reconstruir ni mover tags SHA.

El SHA de Git identifica el código; `sha-<commit>` es el nombre de un tag de
imagen. Su digest `sha256:...` identifica el contenido de la imagen descargada.
Son referencias distintas, y el commit de `boero-infra` tampoco es el de API/UI.

Un índice OCI puede cambiar sólo por la información de procedencia, manteniendo
idéntico el manifiesto ejecutable de `linux/amd64`. En la validación del flujo
separado, Dokploy descargó el índice nuevo de API y Compose conservó el contenedor
saludable porque ese manifiesto era idéntico; no se forzó una recreación.

En Docker 29 con containerd, verificar dos cosas: el digest de índice publicado
por Actions contra `docker image inspect <imagen>:staging` y el manifiesto de
plataforma de esa imagen (`docker image inspect --platform linux/amd64`) contra
`ImageManifestDescriptor.digest` del contenedor. Su `.Image` puede conservar el
índice anterior cuando el binario no cambió. No rechazar un despliegue ni forzar
un reinicio por esa diferencia si el índice nuevo fue descargado y el manifiesto
ejecutable coincide. Si no coincide, la nueva imagen todavía no está ejecutándose.

El job se llama **Request staging deployment**: un HTTP exitoso sólo confirma la
solicitud asíncrona, no la salud. Revisar el despliegue en Dokploy y los healthchecks.
Con proveedor Git, v0.30.8 reemplaza el título de la solicitud al terminar por el
commit de infraestructura. Ese título no acredita el SHA de UI/API: relacionar
los runs de Actions con los digests del registro y de los contenedores reales.
El rollback se hace fijando imágenes conocidas en Dokploy; no es automático.
Volver a imágenes previas no deshace migraciones de Flyway.

## 2. Dónde viven las variables

No hay un `.env` único que se suba desde la PC a todos los servicios. Hay
configuración local del desarrollador, valores privados del ambiente y parámetros
para fabricar una imagen. Son responsabilidades distintas.

| Lugar | Para qué sirve | ¿Se copia al staging operativo? |
|---|---|---|
| API/UI: `compose.yaml` y `.env.dev` opcional | Desarrollo Docker local; los Compose traen defaults y `.env.dev` los personaliza | No |
| UI nativa: archivos `.env*` que carga Next.js, por ejemplo `.env.local` | Ejecutar la UI fuera de Docker, según su guía local | No |
| Archivos `*.example` del repositorio | Documentar nombres y ejemplos de valores, nunca los secretos reales | Se versiona la plantilla, no se sincronizan sus valores automáticamente |
| Dokploy → Bemol → staging → Staging → Environment | Valores efectivos del stack: DB, JWT, mail, storage, URLs, versiones y límites | Es la fuente privada de runtime de este staging |
| Environment de Traefik y su archivo DNS privado | Resolver DNS-01 de Cloudflare y renovar TLS | Sólo lo recibe Traefik; no API/UI |
| GitHub → environment `staging` de cada aplicación | Credenciales para que Actions solicite el deploy | Sólo las usa ese job, no la aplicación |

**Por qué `.env.dev` es opcional:** `make dev` puede usar los defaults del Compose
local sin ese archivo. Si existe, se usa tanto para interpolar `${VARIABLE}` en el YAML como
para el `env_file` del servicio local. No implica que los secretos de staging sean
opcionales. Sin `--env-file`, Compose puede cargar `.env` para interpolación; eso
no lo inyecta entero en los contenedores. Las variables exportadas en la shell
también pueden intervenir. Un `.env` genérico no se convierte por su nombre en
configuración del servidor: cada herramienta carga sus propios archivos. Consultar las guías de
[API](https://github.com/TypeItOrg/bemol-api/tree/staging) y
[UI](https://github.com/TypeItOrg/bemol-ui/blob/staging/docs/DESARROLLO.md) para ejecución nativa.

En staging, Dokploy suministra los valores al ejecutar Compose. Las expresiones
`${...}` del YAML los resuelven y cada bloque `environment` determina qué recibe
su contenedor: **no se entrega todo el Environment a todos los servicios**. Por
ejemplo, UI recibe `BEMOL_API_URL=http://api:8080`; las credenciales DB van a API y
PostgreSQL, no al navegador. `DB_NAME` es la base de negocio; no sustituirlo por el
`POSTGRES_DB=postgres` que utiliza el servicio PostgreSQL de infraestructura.

### Build no es runtime

- **Build:** Actions ejecuta los Dockerfiles y genera artefactos. Los `.env` privados
  están excluidos del contexto Docker; no se empaqueta el Environment de Dokploy.
- **Runtime:** al crear los contenedores, Compose les pasa los valores del panel.
  Cambiar mail/URLs u otra variable de runtime exige **redeploy**; editar el campo
  o reiniciar el mismo contenedor no vuelve a crear su entorno.
- Lo que se incorpore al bundle del navegador durante `next build` —por ejemplo,
  una variable `NEXT_PUBLIC_*` que consuma el código— requiere **rebuild y publicación
  de otra imagen**. No se corrige después cambiando una variable del contenedor.
  Los secretos nunca deben ir en una variable pública.
- Una variable nueva requiere consumidor en la aplicación, paso explícito en
  Compose si corresponde, plantilla actualizada y valor real en Dokploy. Cambiar
  sólo `.env.dokploy.staging.example` no cambia el servidor.

## 3. Dominios, proxy y certificados

Son tres cosas distintas: **DNS** permite encontrar el servidor; **certificado TLS**
protege HTTPS y acredita el hostname; **proxy** recibe y reenvía la petición.
Tener wildcard DNS no configura por sí solo HTTPS ni la selección de institución.

### DNS y certificados, sin extras de pago

| Nombre | Registro | Cloudflare proxy |
|---|---|---|
| `staging.typeit.com.ar` | conservar el existente | Activado |
| `deploy-staging.typeit.com.ar` | A/AAAA al origen correcto | Activado |
| `*.staging.typeit.com.ar` | A/AAAA al mismo origen | **DNS-only** |

No crear un AAAA si el servidor no tiene IPv6 operativo. Conservar registros exactos
existentes; tienen precedencia sobre el wildcard y deben apuntar al mismo origen.
No cambiar registros ni modos SSL que afecten producción. Usar HTTPS al origen y
Full (strict), nunca Flexible; si el ajuste es global a la zona, revisar su impacto
antes de modificarlo.

El Universal SSL gratuito cubre `deploy-staging.typeit.com.ar` pero no
`cboero.staging.typeit.com.ar`. El wildcard DNS-only mantiene esa limitación conocida:
expone la IP y no tiene el proxy/WAF de Cloudflare. Un certificado wildcard de
Let's Encrypt en Traefik protege su HTTPS **sin ocultar la IP**. No activar ACM,
DNS Providers Enterprise ni otros complementos pagos.

Con proxy hay dos tramos HTTPS: navegador → Cloudflare usa su certificado del edge;
Cloudflare → Traefik usa el certificado del origen. En DNS-only el navegador llega
directamente a Traefik y utiliza el certificado Let's Encrypt del origen.

Traefik solicita `staging.typeit.com.ar` + `*.staging.typeit.com.ar` por DNS-01.
El token va en un archivo privado del host, disponible al **Traefik de Dokploy**;
no en Environment de Bemol, etiquetas ni secrets de Actions. Ver
`deploy/dokploy/traefik.env.example`. Persistir y respaldar también el almacenamiento
ACME; sus archivos y el token son privados, no material de diagnóstico para publicar.

### Subdominios institucionales automáticos

Con wildcard DNS + TLS + router ya configurados, editar `publicSubdomain` desde la
administración de una institución activa basta para que su hostname funcione.
No crear un registro/certificado/proxy por institución. La aplicación ya valida
formato, unicidad y nombres reservados; desconocidos/inactivos no son instituciones
válidas. El nombre de la institución no se convierte automáticamente en subdominio.
Renombrar rompe el enlace anterior; no promete alias ni redirecciones históricas.
WebAuthn mantiene RP `staging.typeit.com.ar` y el origen general exacto; no sustituir
orígenes por un wildcard. No hace falta modificar el código de la aplicación.

## 4. Operación cotidiana registrada (histórico; NO ejecutar)

La entrada habitual es el [panel de staging](https://deploy-staging.typeit.com.ar).
La passkey registrada por el usuario protege su acceso al panel; es independiente
del login institucional/plataforma y de las passkeys que se registren en Bemol.
El acceso con contraseña sigue disponible: registrar una passkey no lo deshabilita.

| Quiero… | Acción mínima | Qué comprobar |
|---|---|---|
| Publicar código API o UI | Promover el cambio a su rama `staging`; dejar correr Actions | CI, publicación GHCR y despliegue nativo Dokploy, no sólo el HTTP del job |
| Cambiar una variable de runtime | Environment → editar → Save; luego General → Deploy | Salud y función afectada; guardar o reiniciar no aplica un Environment nuevo. Con tags `staging`, el deploy también puede actualizar ambas imágenes |
| Cambiar Compose | Publicar en la rama de `boero-infra` configurada en el proveedor Git de Dokploy y redeploy desde el panel | El archivo/configuración efectiva; no reemplazar valores privados con ejemplos |
| Ver una falla | Revisar Deployments y Logs del Compose, luego UI/API según el error | El mensaje de la aplicación y sus healthchecks; no publicar logs con secretos |
| Cambiar reglas HTTP | Versionar el cambio y aplicarlo al archivo montado del host mediante el panel u operación autorizada | Git no lo instala automáticamente; dinámica: recarga del file provider; estática/Environment: recreación del proxy con ventana |
| Volver a una versión | Fijar ambos tags `sha-<commit>` conocidos y redeploy | Compatibilidad de base y salud; no hay rollback automático ni reversión Flyway |
| Comprobar backup diario | Consultar `boero-backup@staging.timer` y el resultado del servicio | Timer activo, último `Result=success` y archivo validado, no sólo unidad instalada |

No hay comandos de despliegue, parada ni rollback por SSH en el repositorio.
Usar Dokploy también para estado y logs; SSH queda para mantenimiento autorizado
del host y el backup existente. No usar **Fresh Volumes**, `down -v` ni prune para
actualizar una aplicación o sus variables: los datos deben conservarse.

**Configuración Traefik y Git no son el mismo estado:** Domains genera las
etiquetas nativas del hostname general durante el deploy. Para wildcard y reglas
específicas, el YAML de
`deploy/dokploy/` es la fuente versionada, pero el proxy lee su archivo montado en
el host. Publicar ese YAML o redeployar el Compose de Bemol no lo copia allí.
Aplicar el cambio conservando las reglas ya instaladas y luego comprobar la
recarga dinámica; para configuración estática, acordar la recreación del proxy.

### Secrets de Actions y promoción entre ramas

Secrets del environment `staging` en **ambos** repositorios:

| Secret | Valor |
|---|---|
| `DOKPLOY_URL` | `https://deploy-staging.typeit.com.ar` |
| `DOKPLOY_API_KEY` | Credencial Dokploy dedicada y privada para Actions |
| `DOKPLOY_STAGING_COMPOSE_ID` | ID del mismo servicio Compose Staging de Bemol |

El 2026-10-20 se verificó la eliminación de exactamente `DEPLOY_HOST`, `DEPLOY_PORT`,
`DEPLOY_USER`, `DEPLOY_SSH_KEY` y `DEPLOY_SSH_KNOWN_HOSTS` de los environments
`staging` de `boero-api` y `boero-ui`. Se conservaron los tres secrets Dokploy de
la tabla; no se modificaron los environments de producción.

No cambiar secrets de producción. No bloquear este endpoint detrás de una
pantalla de login de Cloudflare Access que Actions no pueda atravesar. La API key
es privilegiada: no imprimir respuestas ni habilitar trazas shell que la muestren.
En v0.30.8 hereda el rol de su usuario: una clave del owner es administrativa,
no se limita a `compose.deploy` ni a un Compose concreto. Usar una clave dedicada
permite revocarla por separado, no reduce sus permisos.

Ambas aplicaciones tienen los mismos dos archivos en `develop` y `staging`:

- `.github/workflows/ci.yaml` (**CI**) valida PR y pushes a develop/main. No publica imágenes ni recibe secrets de Dokploy.
- `.github/workflows/deploy-staging.yaml` (**Deploy staging**) sólo se activa por push a staging. Llama al mismo CI del mismo commit mediante `workflow_call`; si pasa, publica la imagen y solicita el despliegue. No dispara otro CI duplicado ni usa `workflow_run`, por lo que conserva la referencia de staging para sus restricciones de Environment.

Un push a `develop` valida el código, pero no publica imágenes ni despliega: su ejecución sigue siendo local. `main` también queda sólo con CI. Los archivos pueden ser iguales en ambas ramas porque los triggers y `github.ref_name` determinan qué se ejecuta. No hay workflows de QA ni producción, ni configuración de despliegue productivo en este repositorio.

Los runners se fijan en `ubuntu-24.04` y las cargas de artifacts usan Node 24. API reutiliza compilación mediante la caché nativa de GitHub, con clave por job/commit y restauración de la entrada previa, sin cachear resultados de tests ni publicar Build Scans. Su CI conserva perfiles de tiempos y reportes JUnit durante 7 días. Esto no traslada pruebas ni compilación al servidor de staging.

Conservar estos archivos al promover develop a staging, sin sobrescribir ni forzar ramas. Los grupos de concurrencia del caller y del CI reutilizable son diferentes.

### Retiro de QA del 2026-10-20

Se retiraron el workflow `Deploy QA` de API/UI en `develop` y `staging`, el perfil
API `qa`, el overlay, la plantilla y los comandos operativos de ese ambiente.
El checkout operativo de infraestructura también quedó actualizado. No se
encontraron contenedores, volúmenes ni redes QA en el host, ni un environment
`qa` en GitHub; no fue necesario borrar datos ni secrets de ese ambiente.

Con autorización explícita se eliminó únicamente el registro A
`testing.typeit.com.ar`, conservando una copia privada para recuperarlo. La
consulta DNS devolvió NXDOMAIN; los registros general, institucional, wildcard y
panel de staging se conservaron. Producción no se modificó.

Se conservan las pruebas automatizadas y los nombres reservados `qa`/`testing`:
sus fixtures históricos no configuran un ambiente compartido ni consumen RAM del
servidor. El harness institucional continúa siendo una verificación local.

## 5. Datos, persistencia y backups

Las imágenes y los contenedores pueden cambiar; los datos viven fuera de ellos,
en estos **volúmenes externos existentes**. Un redeploy debe reutilizarlos.

| Volumen | Contenido / montaje | Precaución |
|---|---|---|
| `boero-api-postgres-data-staging` | PostgreSQL 18 en `/var/lib/postgresql` | Datos de negocio; nunca dos PostgreSQL sobre él a la vez |
| `boero-api-redis-data-staging` | Persistencia Redis en `/data` | No vaciar para arreglar un deploy: puede afectar sesiones/revocaciones |
| `boero-api-enrollment-storage-staging` | Adjuntos locales en `/app/storage` | Necesita respaldo de archivos además del dump PostgreSQL |
| `boero-api-logs-staging` | Logs de API en `/app/logs` | No sustituye los datos ni una estrategia de backup |
| `boero-ui-next-cache-staging` | Caché Next en `/app/.next/cache` | Es caché regenerable; se conservó durante el corte, no es la base ni los adjuntos |

El File Mount `postgres-entrypoint.sh` es configuración, no una copia de la base.
`api-storage-init` prepara permisos del volumen de archivos antes de API; su salida
exitosa no demuestra por sí sola que una carga/descarga funcional haya pasado.

### Qué respaldo existe y qué no

Se conserva `make backup-db ENV=staging`: localiza exactamente un PostgreSQL vivo
por su volumen histórico y label de servicio, sin duplicar secretos de Dokploy.
Guarda dumps 0600 y valida con `pg_restore --list` antes de rotar; eso no sustituye
un ensayo de restauración. `.env.staging` ya no es obligatorio para ese backup;
`BACKUP_DIR` y `BACKUP_RETENTION_DAYS` pueden configurarse en el servicio systemd.
Por compatibilidad, si existe `.env.staging` sólo se leen esas dos opciones de
backup: ya no es fuente de configuración de la aplicación. No borrar ese archivo
privado durante esta limpieza. `BACKUP_POSTGRES_VOLUME` se reserva a los fixtures
locales: el backup diario mantiene por defecto `boero-api-postgres-data-staging`.
Mantener el checkout operativo de `/opt/boero-infra` para este backup y habilitar
`boero-backup@staging.timer` sólo después de ejecutar exitosamente el servicio.
El timer no coordina un lock con Dokploy: no programar un corte simultáneo.

En la migración se verificó el timer activo y un servicio finalizado correctamente. Programa el
backup diariamente a las 02:15 del reloj del servidor, con demora aleatoria máxima
de 15 minutos y recuperación de ejecuciones perdidas. Sin overrides, los dumps se
guardan en `/var/backups/boero/staging` con retención de siete días; la limpieza sólo
se ejecuta después de validar un dump nuevo. No borrar `/tmp/boero-infra-staging.lock` para forzar una ejecución. El servicio `oneshot` puede quedar `inactive/dead` después de
un éxito: revisar `Result`/`ExecMainStatus`, no confundirlo con un timer inactivo.

Los respaldos locales no cubren la pérdida del disco/host. Conservar además una
copia fuera de la máquina sin contratar servicios adicionales; PostgreSQL no incluye
los adjuntos locales, que necesitan su propio respaldo recuperable.

## 6. Límites y diferencias aceptadas o pendientes

- El hostname general sólo admite peers Cloudflare; instituciones DNS-only usan
  la IP de conexión. No confiar en headers CF enviados directamente por un cliente.
  Los rangos oficiales CF necesitan mantenerse actualizados.
- Las rutas públicas `/actuator` y `/api/v1` pasan de 404 a **403**, sin llegar a API.
- Rate limits por router/instancia y solicitudes en vuelo no equivalen a las zonas
  compartidas/conexiones de Nginx. Se conservan límites básicos, no una equivalencia
  exacta del contador global.
- El límite de cuerpo de 32 MiB requiere buffering en POST/PUT/PATCH. También
  puede demorar respuestas de Server Actions; GET de descargas/SSE no lo usa.
  Validar formularios, carga y descarga de adjuntos, y navegación antes de aceptar.
- Detrás de CF, Traefik puede entregar `X-Real-IP` del edge: la UI actual lo prefiere
  para metadatos de autenticación. Afecta la IP mostrada en Sesiones, no la decisión
  de autenticación ni los límites del proxy. No afirmar paridad de esa IP con Nginx.
  El usuario aceptó esta diferencia exclusivamente en staging; no extender esa
  aceptación a producción.
- El wildcard DNS-only expone el origen; un certificado válido no lo oculta.
  No habilitar proxy Cloudflare para esos hostnames sin resolver primero el TLS
  del edge. No contratar ACM u otros extras para este staging.
- Mantener Docker Cleanup desactivado hasta revisar los recursos retenidos del
  servidor: su limpieza global puede borrar contenedores, imágenes y redes.
  No ejecutar prune ni borrar volúmenes por iniciativa.
- La API key de Actions tiene los permisos de su usuario Dokploy. Una clave
  dedicada del owner sigue siendo administrativa; no presentarla como limitada
  al deploy de Bemol. Su protección y eventual revocación son importantes.

## 7. Único mecanismo de operación

- **Se conserva:** Actions/GHCR, `compose.dokploy.staging.yaml`, su base
  `compose.yaml`, Traefik/DNS/TLS, las plantillas Dokploy, el entrypoint PostgreSQL,
  los cinco volúmenes externos, el backup diario y la aceptación local.
- **Se retiró del repositorio:** overlays del deploy anterior, plantilla `.env`
  genérica, comandos/scripts de bootstrap/deploy/rollback por SSH, ejemplo Nginx,
  pruebas exclusivas de ese mecanismo y preparación de producción.
- **Fuera de alcance de esta limpieza:** servidor, contenedores detenidos,
  configuración privada, marker del corte, imágenes y volúmenes existentes.
  No se ejecutó un deploy ni se borraron recursos remotos. Las revisiones antiguas
  siguen en Git como referencia histórica, no como un segundo mecanismo soportado.
- Mantener Docker Cleanup desactivado hasta revisar los recursos retenidos del
  servidor. Esta limpieza de archivos no autoriza a borrarlos ni restaura backups.

`compose.yaml` contiene las definiciones base que extiende Dokploy y que usa el
harness local. No desplegarlo solo ni introducir otro Environment compartido.
La aceptación usa fixtures descartables, no un servidor adicional de desarrollo.
S3 sigue siendo un proveedor opcional de la aplicación; esta limpieza no lo activa
ni crea recursos pagos. Ver [almacenamiento](S3.md).

### Validación de la limpieza del 2026-10-20

Pasaron 13 pruebas dirigidas de configuración, backup y solicitudes HTTPS
simuladas, 10 del verificador de evidencia y la suite shell de backup con Docker
simulado. Los controles de workflows usaron copias de `origin/develop` de API/UI,
sin modificar sus checkouts locales. Se validaron sintaxis y enlaces locales.
El JSON completo de Compose, renderizado con valores sintéticos antes y después,
es idéntico: no cambian servicios, imágenes, redes, montajes ni volúmenes.

Esta validación no ejecutó el harness completo, un backup real ni una restauración,
ni accedió al servidor. La publicación en Git de esta limpieza no despliega
servicios ni actualiza el checkout operativo del host.
Actualizar el repositorio operativo del host requiere una entrega autorizada;
no hace falta recrear contenedores para aplicar esta limpieza sin cambios de Compose.

## Apéndice A. Configuración instalada y reconstrucción históricas (NO operativo)

Referencia histórica para entender lo instalado en aquella ventana. **No son tareas
pendientes ni instrucciones para reconstruir el servidor actual.** Para operar,
usar DOKPLOY-STAGING.md y completar primero el corte de RENOMBRE-BEMOL.md.

El servicio **Docker Compose** **Staging** toma este repositorio y el archivo
`compose.dokploy.staging.yaml`. Éste extiende `compose.yaml`; ambos deben estar en
el checkout. Configurar el dominio general en Domains según la guía paso a paso.
No activar isolated deployments ni dominios autogenerados: wildcard y reglas
específicas están en el archivo dinámico de Traefik.

1. Importar los valores privados actuales de staging en Environment y contrastar
   con `.env.dokploy.staging.example`. Conservar DB, JWT, refresh, mail, storage,
   autologin y WebAuthn; no reemplazar secretos con ejemplos. Mantener ambos
   `*_VERSION`, porque el archivo base los exige antes de resolver `extends`.
2. **Reconstrucción autorizada:** usar tags SHA conocidos y compatibles con los
   datos conservados. No mezclar recuperación de infraestructura con una versión
   nueva de la aplicación ni abrir escrituras antes de validar salud y datos.
3. Crear un **File Mount** de Dokploy: en su campo **File path** poner únicamente
   `postgres-entrypoint.sh`, con el contenido de `docker/postgres-entrypoint.sh`.
   Compose lo referencia como `../files/postgres-entrypoint.sh`; no pegar ese
   prefijo en el campo del panel. No depender del bind al checkout
   Git descartable ni permitir que Docker cree un directorio en lugar del archivo.
   El File Mount conserva una copia gestionada: si cambia el entrypoint en Git,
   actualizar también su contenido en Dokploy antes del redeploy; publicar el
   archivo del repositorio no actualiza esa copia automáticamente.
4. Verificar los cinco volúmenes externos existentes y la red
   `boero-network-staging`. No crear una base vacía sustituta si falta un volumen.
   Sólo UI se conecta además a `dokploy-network`, con alias `boero-ui-staging`.
   UI libera el puerto 3000; API conserva exclusivamente loopback 8080.
5. Instalar `deploy/dokploy/traefik-staging.yaml` como archivo independiente en el
   directorio dinámico **ya montado** por el Traefik instalado. Fusionar las claves
   de `traefik-static.staging.example.yaml` en su configuración estática existente:
   conservar providers, direcciones, redirecciones y rutas/resolvers del panel.
   Completar el contacto ACME. No reemplazar el documento entero por el fragmento.
6. Configurar el token mediante Environment de **Traefik**, usando la ruta `_FILE`
   del ejemplo; directorio privado 0700 y archivos 0600. Aplicar cambios estáticos
   requiere reiniciar/recrear Traefik dentro de la ventana acordada; guardar el
   archivo por API no lo recarga. Guardar su Environment sí solicita recrearlo.
7. Configurar el panel con HTTPS en `deploy-staging.typeit.com.ar`. Hacer su alta
   inicial mediante túnel SSH, sin dejar el puerto 3000 públicamente accesible.
   Después de verificar HTTPS, retirar la publicación directa de 3000 siguiendo
   la documentación oficial y comprobar desde fuera que quedó cerrada.

`api-storage-init` se ejecuta como dependencia de API y debe terminar bien antes
de iniciarla. Conserva archivos, corrige permisos y usa la misma imagen que API;
no corre como parte de un paso SSH ni requiere credenciales de aplicación.

## Referencias

Fuentes: [instalación](https://docs.dokploy.com/docs/core/installation),
[Compose](https://docs.dokploy.com/docs/core/docker-compose),
[API Compose](https://docs.dokploy.com/docs/api/compose),
[Universal SSL](https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/limitations/),
[wildcard DNS](https://developers.cloudflare.com/dns/manage-dns-records/reference/wildcard-dns-records/).
