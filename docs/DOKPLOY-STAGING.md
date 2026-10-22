> **Referencia del despliegue anterior con Dokploy.** La configuración de reemplazo
> y el corte pendiente del VPS se describen en [STAGING.md](STAGING.md). Este
> documento conserva el procedimiento anterior; no es la guía operativa nueva.

# Bemol / staging: Dokploy y Traefik paso a paso

Esta guía explica el entorno existente en `cristinet`, desde encontrar su Compose
hasta publicar una versión y comprobarla. No es una orden de reinstalar ni de
volver a migrar: **staging ya existe**. Primero leer; ejecutar cambios sólo con la
autorización y la ventana que correspondan. No hay otro entorno compartido ni
producción configurada en este repositorio.

**Renombre aplicado en staging el 2026-10-21:** los identificadores técnicos activos
son `bemol-*`. Se recrearon únicamente los datasets de prueba autorizados y se
regeneraron con seeders; no repetir ese descarte sobre datos que deban conservarse.
El [registro del corte](RENOMBRE-BEMOL.md) distingue controles vivos, límites y las
vías de recreación descartable o migración persistente. Los volúmenes y red son
externos; una DB ausente detiene PostgreSQL en lugar de crearla vacía.

La migración operativa previa se validó el 2026-10-20. Sus resultados y límites se
conservan como historial en la [referencia de staging](DOKPLOY-STAGING-REFERENCIA.md).
No confundir ese historial
con una comprobación del servidor en cada edición de este documento.

## Antes de empezar: las tres responsabilidades

```text
GitHub Actions: comprueba el código, construye y publica imágenes en GHCR.
Dokploy: toma esas imágenes y administra los contenedores del servidor.
Traefik: recibe las visitas HTTP/HTTPS y las dirige a la UI.

Navegador → Traefik → UI → API → PostgreSQL / Redis
```

GHCR es el registro donde se guardan imágenes, no los datos de la aplicación.
Compose es la receta de servicios/redes/volúmenes; no es una imagen ni otro servidor.
Cloudflare administra DNS y, donde se habilita su proxy, queda delante de Traefik.

## Paso 1. Encontrar el recurso y distinguir sus nombres

1. Entrar al [panel](https://deploy-staging.typeit.com.ar).
2. En **Projects**, abrir el proyecto existente **Bemol**.
3. Seleccionar el environment **staging**; no el environment por defecto del proyecto.
4. Abrir su servicio Compose **Bemol staging**. Contiene UI, API, PostgreSQL y Redis;
   no hay un Compose diferente por aplicación.

No crear un proyecto, environment ni servicio duplicado para seguir esta guía.
En una instalación nueva autorizada se crearían en ese orden, eligiendo **Docker
Compose**, no Application ni Docker Stack. Al crear el servicio, **Dokploy genera
su `composeId`**. No lo genera GitHub, el YAML ni quien elige el nombre.

| Dato | Qué significa | ¿Lo elegimos? |
|---|---|---|
| Name: `Bemol staging` | Nombre visible del servicio en el proyecto Bemol | Sí; lápiz junto al título → Name → Update |
| `composeId` | Identificador interno que usa la API | No; Dokploy lo asigna al crear el recurso |
| `bemol-staging-8u7h7g` | `appName` técnico del Compose actual | Inmutable mediante update en v0.30.8; el cambio se hizo creando un recurso soportado nuevo |

El nombre visible se puede cambiar sin deploy; **no sustituye el `composeId`** ni
exige cambiar los secrets de Actions. El proyecto padre se llama Bemol; el environment es staging.
El Compose anterior fue retirado después del corte documentado en
[RENOMBRE-BEMOL.md](RENOMBRE-BEMOL.md). No intentar cambiar `appName` con SQL ni
crear otro servicio duplicado para seguir esta guía.

## Paso 2. Entender qué repositorio lee Dokploy

En **General → Provider**, comprobar, sin reemplazar la configuración existente:

| Campo | Valor |
|---|---|
| Provider | Git |
| Repository URL | `https://github.com/TypeItOrg/bemol-infra.git` |
| Branch | `main` |
| Compose Path | `./compose.dokploy.staging.yaml` |
| Autodeploy | Desactivado |

`main` aquí es **la rama de infraestructura**, no el código productivo de API/UI.
Las aplicaciones llegan como imágenes construidas desde sus ramas `staging`.
Autodeploy queda apagado porque Actions solicita el deploy sólo después del CI.

El archivo activo extiende partes de [compose.yaml](../compose.yaml). Ambos deben
estar en el checkout; no desplegar la base por separado. **Preview Compose** permite
revisar la receta, pero no muestra una prueba de salud ni garantiza qué se ejecuta.

## Paso 3. Ubicar las variables privadas

1. Abrir **Environment** del Compose **Bemol staging**.
2. Ejecutar `make render-staging-config` y comparar los nombres con el ejemplo
   generado `build/staging/.env.staging.example`. La
   [plantilla fuente](../.env.staging.example) obtiene el dominio de
   [deploy/staging.env](../deploy/staging.env); no copiar sus placeholders al panel.
3. Conservar claves de autenticación, correo y WebAuthn existentes. Cambiar nombres
   DB/rol y destinos de storage sólo después de copiar/migrar y verificar sus datos;
   los ejemplos no son valores para sobrescribir la configuración privada.
4. Mantener `UI_VERSION=staging` y `API_VERSION=staging` para el flujo normal.

Guardar deja preparada la configuración del próximo deploy; no cambia el entorno
de un contenedor vivo. Compose pasa explícitamente las variables necesarias a cada
servicio. Agregar un campo al panel no lo vuelve automáticamente accesible a la API.
Los `.env` locales de API/UI no se copian al servidor.

## Paso 4. Reconocer los datos persistentes y el File Mount

Después del corte autorizado, comprobar los cinco volúmenes externos migrados:
`bemol-api-postgres-data-staging`, `bemol-api-redis-data-staging`,
`bemol-api-enrollment-storage-staging`, `bemol-api-logs-staging` y
`bemol-ui-next-cache-staging`. Si falta uno, **detenerse**, no crear una base vacía.

El PostgreSQL usa además un **File Mount** gestionado por Dokploy:

1. En la configuración de mounts del servicio, el **File path** es únicamente
   `postgres-entrypoint.sh`.
2. Su contenido corresponde a [docker/postgres-entrypoint.sh](../docker/postgres-entrypoint.sh).
3. Compose lo monta desde `../files/postgres-entrypoint.sh`; ese prefijo no se escribe
   en el campo File path del panel.

No depende del directorio Git descartable. Si cambia su contenido versionado,
actualizar también el File Mount antes de un deploy autorizado. Sólo UI pertenece
además a `dokploy-network`, con alias `bemol-ui-staging`; API/DB/Redis no se publican
por esa red. El auxiliar `api-storage-init` prepara permisos y luego termina.

## Paso 5. Entender dónde se definen los dominios

El dominio de aplicación indicado para staging es `staging.bemol.com.ar`; las
reglas preparadas utilizan la zona `bemol.com.ar` y su wildcard institucional. El
dominio del panel se conserva abajo como referencia documentada independiente,
no como resultado de una comprobación actual de DNS. El panel pertenece a su
propia zona; no se renombra al cambiar el dominio de la aplicación.

| Nombre | Destino | Proxy Cloudflare |
|---|---|---|
| `staging.bemol.com.ar` | IP del servidor de staging | Activado |
| `deploy-staging.typeit.com.ar` | IP del mismo servidor | Activado |
| `*.staging.bemol.com.ar` | IP del mismo servidor | DNS-only |

Conservar registros exactos existentes: tienen precedencia sobre el wildcard. No
crear AAAA sin IPv6 operativo ni alterar ajustes de toda la zona sin revisar impacto.

DNS permite encontrar la IP; **no configura el proxy ni el certificado**. El
hostname del panel se administra con su configuración de Web Server.

**Transición preparada en Git; no aplicada al servidor en este cambio.** El último
registro operativo con Domains corresponde al dominio anterior
`staging.typeit.com.ar`, con wildcard y reglas específicas en un archivo dinámico. La
configuración objetivo define todas las rutas de la aplicación en
[archivos propios separados por responsabilidad](../deploy/traefik/README.md).

Antes de aplicar la transición, conservar la entrada Domains existente y comprobar
el estado real del host. No recrearla ni retirarla sólo por leer esta guía. Después
del corte documentado en el README de Traefik, no volver a crear dominios de la
aplicación en Domains: duplicarían las rutas del file provider. El dominio del panel
`deploy-staging.typeit.com.ar` mantiene su configuración propia de Dokploy.

El wildcard institucional es DNS-only: expone el origen. Se conserva así, sin
extras pagos, porque el certificado gratuito del edge de Cloudflare no cubre
`institucion.staging.bemol.com.ar`. El certificado del origen es otra cosa.

## Paso 6. Localizar y comprender la configuración de Traefik

El dominio base (`BASE_DOMAIN`) y el nombre de staging (`STAGING_SUBDOMAIN`) se
definen una sola vez en [deploy/staging.env](../deploy/staging.env).
`STAGING_DOMAIN` se deriva de ambos; no se configura por separado.
Las plantillas de [deploy/traefik/](../deploy/traefik/README.md) se procesan con
`make render-staging-config`. La división permite distinguir qué se enruta, a qué
destino y con qué políticas:

| Archivo dinámico | Responsabilidad |
|---|---|
| `routers.yaml` | Hostnames, rutas, métodos, prioridades y TLS |
| `services.yaml` | Alias UI y transportes HTTP |
| `middlewares-common.yaml` | Headers y compresión |
| `middlewares-access.yaml` | Origen Cloudflare, headers del tráfico directo y denegación |
| `middlewares-limits.yaml` | Rate limiting, concurrencia y tamaño de escrituras |
| `middlewares-redirects.yaml` | HTTPS y hostname canónico |

Las seis fuentes están en `deploy/traefik/dynamic/staging/`. Se instalan sus
resultados de `build/staging/traefik/dynamic/`, que el file provider carga juntos;
no instalar las plantillas con variables sin resolver. Sus nombres no definen la prioridad de los routers. Los servicios
general y especializado apuntan a `http://bemol-ui-staging:3000`; conservan sus
respectivas políticas de transporte. Sólo UI comparte red con el proxy.

Hay dos ejemplos estáticos para responsabilidades distintas:

- [Proxy independiente](../deploy/traefik/static/traefik.staging.example.yaml):
  documento completo con entrypoints, file provider y resolver ACME. El
  [Compose independiente](../compose.traefik.staging.yaml) define su contenedor,
  variable del token y montajes; permanece pendiente de aplicar al servidor.
- [Integración con Dokploy](../deploy/dokploy/traefik-static.staging.example.yaml):
  fragmento para fusionar con la configuración compartida existente sin reemplazar
  los providers ni las rutas del panel.

El panel **Traefik File System** permite consultar los archivos montados; no es la
fuente de las reglas de Bemol después de la transición. El dashboard de Traefik
inspecciona la configuración efectiva y no ejecuta Compose ni despliegues.

**Git y el servidor son estados distintos.** Publicar infra o desplegar el Compose
no copia este conjunto al proxy. La transición del README incluye el reemplazo del
monolito, verificación del router `@file`, retiro de la entrada Domains de la
aplicación y vuelta al estado previo. No modificar routers del panel ni conservar
copias duplicadas de las mismas reglas dentro del directorio observado.

## Paso 7. Seguir cómo se obtiene y renueva HTTPS

El resolver `cloudflare-staging` solicita a Let's Encrypt un certificado para
`staging.bemol.com.ar` y `*.staging.bemol.com.ar`:

1. Traefik inicia la solicitud mediante ACME, el protocolo de certificados.
2. Su proveedor DNS usa el token privado de Cloudflare para publicar temporalmente
   el TXT de validación DNS-01.
3. Let's Encrypt comprueba ese TXT y emite el certificado wildcard.
4. Traefik conserva el estado ACME y administra la renovación automática.

La configuración del token está descrita en [traefik.env.example](../deploy/dokploy/traefik.env.example):
`CF_DNS_API_TOKEN_FILE` apunta a un archivo privado, no contiene el token en Git.
Es el ejemplo de integración con Dokploy; el [Compose independiente](../compose.traefik.staging.yaml)
declara la variable y el montaje para el proxy nuevo. Va en el entorno de **Traefik**,
no en Environment de Bemol ni en los secrets de Actions. Su alcance es la zona
`bemol.com.ar`, con Zone:Read y DNS:Edit. Mantener directorio privado 0700 y
token/estado ACME 0600; respaldarlos sin publicarlos.

No crear otro token ni reiniciar el proxy si ya está configurado. Revisar logs de
Traefik, vigencia y cobertura del certificado al validar renovaciones. No se usa
Certbot. El almacenamiento ACME del fragmento está bajo
`/etc/dokploy/traefik/dynamic/.secrets/`, dentro del árbol montado del proxy.

En nombres proxied hay dos HTTPS: navegador → Cloudflare y Cloudflare → Traefik.
Usar Full (strict), no Flexible. En nombres DNS-only el navegador llega a Traefik
directamente: tener certificado válido no oculta la IP.

## Paso 8. Entender el alta automática de un subdominio institucional

Ejemplo conceptual: una institución activa con `publicSubdomain=escuela` usa
`https://escuela.staging.bemol.com.ar`. No crear registros reales para leer esta guía.

1. En la administración de la institución, configurar su subdominio público con
   los permisos correspondientes; no se deduce automáticamente de su nombre o slug.
2. El wildcard DNS ya dirige ese nombre al servidor.
3. El certificado wildcard ya cubre HTTPS para ese nombre.
4. El router wildcard de Traefik lo envía a la misma UI.
5. Bemol resuelve `publicSubdomain` y aplica el contexto de la institución.

**No hay una llamada a Cloudflare ni un certificado por cada institución.** El
token DNS del paso 7 valida certificados, no crea un registro A por institución.
La aplicación comprueba formato, unicidad y nombres reservados. Desconocidos o
inactivos no son instituciones válidas; renombrar rompe el enlace anterior.
Validar accesos nuevos sólo con datos de prueba autorizados. El RP WebAuthn se
mantiene en `staging.bemol.com.ar`; no cambiarlo ni poner un wildcard como origen.

## Paso 9. Obtener el Compose ID y conectar GitHub Actions

El ID fue generado por **Dokploy al crear el servicio**, no al renombrarlo. Para
obtenerlo desde esta versión del panel:

1. Abrir el Compose **Bemol staging**, no el proyecto ni una pestaña de contenedor.
2. Mirar la URL del navegador. Tiene esta estructura:
   `/dashboard/project/<projectId>/environment/<environmentId>/services/compose/<composeId>`.
3. Copiar únicamente el segmento que sigue a `/services/compose/`: ése es el ID.
   También lo devuelve la API al consultar el recurso; no confundirlo con `appName`.
4. En **cada** repositorio GitHub (`bemol-api` y `bemol-ui`), ir a **Settings →
   Environments → staging → Environment secrets**.
5. Comprobar los tres valores existentes de la tabla. No es necesario regenerar
   la API key ni cambiar un secret que ya apunta al servicio correcto.

| Secret | Qué se carga y de dónde sale |
|---|---|
| `DOKPLOY_URL` | `https://deploy-staging.typeit.com.ar`, la dirección del panel/API |
| `DOKPLOY_API_KEY` | Clave privada del perfil Dokploy, sección API/CLI; usar la existente dedicada a Actions |
| `DOKPLOY_STAGING_COMPOSE_ID` | El ID copiado del recurso; **el mismo en API y UI** porque despliegan el mismo stack |

GitHub no descubre estos valores: los carga quien configura la integración. El ID
no es `Staging`, `Bemol`, `staging`, el nombre de un YAML ni el SHA de una imagen.
Si se elimina y recrea el recurso, tendrá otra identidad y habrá que actualizar
la integración. No hacerlo para cambiar un nombre visible.

La API key hereda los permisos de su usuario Dokploy: la del owner es
administrativa, no una credencial limitada a este deploy. No compartirla, imprimirla
ni colocarla en URLs; mantener su revocación independiente de otras claves.

## Paso 10. Seguir un despliegue completo desde GitHub

1. Desarrollar localmente en `develop`; su **CI** comprueba, no publica imágenes.
2. Promover a `staging` mediante la integración Git autorizada.
3. **Deploy staging** llama al CI reutilizable del mismo commit.
4. Si pasa, construye la imagen y publica los tags `sha-<commit>` y `staging` en GHCR.
5. Envía una petición HTTPS `POST /api/compose.deploy` a `DOKPLOY_URL`, con cabecera
   `x-api-key` y un cuerpo que contiene `composeId: DOKPLOY_STAGING_COMPOSE_ID`.
6. Dokploy recibe la solicitud, toma infra/main + Environment y descarga las
   imágenes. Mientras exista la entrada Domains de la aplicación, incorpora sus
   etiquetas; después de la transición, las rutas de Bemol provienen de archivos.
7. Compose recrea lo que cambió, reutilizando las redes y volúmenes Bemol ya migrados.
   Durante la transición no desplegar hasta completar RENOMBRE-BEMOL.md.
8. Revisar **Deployments** en Dokploy y luego **Containers**, logs y salud HTTPS.

La respuesta HTTP del paso 5 sólo confirma la solicitud asíncrona. Un check verde
no acredita por sí solo que el destino esté saludable. El título del despliegue
puede mostrar el commit de infraestructura, no el SHA de API/UI. Verificar imágenes
como explica la referencia. No hay SSH ni compilación de las aplicaciones en el VPS.
Un deploy del stack puede actualizar **ambas** imágenes; los pipelines son independientes.

## Paso 11. Aplicar una variable nueva o volver a una versión conocida

Para cambiar una variable de runtime ya declarada en Compose:

1. Abrir **Environment**, modificar sólo el valor deseado y pulsar **Save**.
2. Revisar las versiones seleccionadas: con tags `staging`, Deploy puede descargar
   otra imagen. Si sólo se quiere cambiar configuración, fijar antes ambos tags
   SHA de imágenes conocidas y compatibles.
3. En **General → Deploy**, solicitar el despliegue autorizado.
4. Esperar el resultado y verificar salud y la función afectada.

Guardar o reiniciar el contenedor no actualiza su entorno. Una variable nueva
necesita consumidor en la aplicación, paso explícito por Compose y plantilla/valor
privado actualizados. Lo compilado en el bundle del navegador requiere otra imagen.

El tag `staging` es una referencia móvil de GHCR y funciona con cualquier motor
Docker; no depende de Dokploy. Si pasa de la imagen A a la B, pedir otra vez
`:staging` obtiene B, aunque el historial muestre un deploy anterior. Para volver
a A, seleccionar su tag `sha-<commit>` conservado y desplegarlo. El historial de
operaciones no fija por sí solo las versiones de API/UI; registrar ambas referencias
y conservar las imágenes en GHCR. Los tags SHA se mantienen sin sobrescribir;
el digest identifica de forma inmutable el contenido de una imagen.

Para volver a una versión, seleccionar ambos tags SHA conocidos y desplegar sólo
si son compatibles con la base actual. No hay rollback automático ni reversión de
migraciones Flyway. No restaurar un backup encima de datos nuevos por iniciativa.

## Paso 12. Operar sin perder datos y saber dónde mirar

- **Containers:** salud y estado; **Logs:** mensajes; **Monitoring:** CPU/RAM.
- **Deployments:** historial de operaciones, no un backup de base o archivos.
- **Stop:** detiene el stack; **Fresh Volumes:** no es parte de una actualización.
- **Rebuild:** no es necesario en el flujo normal de imágenes fabricadas en Actions.
- **Backups / Volume Backups:** que existan pestañas no significa que haya una
  política configurada allí. El backup diario PostgreSQL sigue siendo independiente:
  systemd ejecuta `make backup-db ENV=staging` en `/opt/bemol-infra`, mediante
  `bemol-backup@staging.timer`; el destino por defecto es `/var/backups/bemol/staging`.

El backup valida el dump antes de rotar y conserva la selección del volumen de
staging. No respalda adjuntos ni sustituye una copia fuera del host. Consultar
retención, horarios y límites en la referencia; no ejecutar un backup o restauración
real como parte de una lectura. No usar `down -v`, prune ni borrar recursos retenidos.

Si falla HTTPS, revisar Traefik/DNS/certificados; si falla una solicitud de deploy,
revisar Actions y sus secrets; si el deploy arrancó pero el servicio falla, revisar
Deployments/Containers/Logs. No publicar logs crudos con valores privados.

## Nombres visibles y nombres técnicos

El proyecto se llama **Bemol**, su environment **staging** y el servicio Compose
**Bemol staging**. El recurso actual usa repositorios/imágenes/recursos `bemol-*`.
Su Compose ID es nuevo y está configurado en los dos repositorios de aplicaciones;
no confundirlo con el `appName` ni reutilizar el ID del servicio retirado.

## Para profundizar

- [Referencia técnica, límites, backups y evidencia de migración](DOKPLOY-STAGING-REFERENCIA.md).
- [Compose en Dokploy](https://docs.dokploy.com/docs/core/docker-compose).
- [API Compose y su campo composeId](https://docs.dokploy.com/docs/api/compose).
- [ACME y renovación de certificados en Traefik](https://doc.traefik.io/traefik/reference/install-configuration/tls/certificate-resolvers/acme/).

## Registro histórico: dominio general nativo del 2026-10-20

Este registro conserva la configuración nativa de Domains de aquella ventana.
La reorganización actual de reglas en archivos está preparada en Git y no acredita
que se haya aplicado al host. Los nombres siguientes tampoco prueban el estado
actual del renombre técnico Bemol.

**Aplicado y verificado.** `staging.typeit.com.ar` aparece en Domains del servicio
Staging, con HTTPS, resolver `cloudflare-staging` y los cinco middlewares de la tabla.
Se comprobó el despliegue nativo **Done**, los routers HTTP/HTTPS `@docker` habilitados
y la ausencia de middlewares heredados según el inventario de transición: la entrada del panel atiende realmente el
tráfico general, no es decorativa. Wildcard y rutas específicas permanecen `@file`.

La tabla conserva los parámetros anteriores como referencia de recuperación. No
recrear esta entrada después del corte a archivos salvo que se esté deshaciendo
la transición; prevalecen los valores efectivos capturados antes del cambio.

| Campo anterior de Domains | Valor registrado |
|---|---|
| Service Name | `ui` |
| Host | `staging.typeit.com.ar` |
| Path / Internal Path | `/` / `/` |
| Strip Path / Custom Entrypoint | Desactivados |
| Container Port | `3000` |
| HTTPS | Activado |
| Certificate Provider | Custom |
| Custom Certificate Resolver | `cloudflare-staging` |
| Middlewares, en este orden | `bemol-cloudflare-only@file`, `bemol-common@file`, `bemol-rate-cloudflare@file`, `bemol-flight-cloudflare@file`, `bemol-flight-host@file` |

Para no cambiar código durante el corte se utilizó un patch temporal del Compose
con los manifests ejecutables exactos de UI/API. No se abrió ni modificó Environment.
Ese pin cambió referencias de imagen y recreó API/UI con el mismo contenido;
PostgreSQL/Redis no se recrearon. El patch quedó **deshabilitado** después del corte:
no fija versiones en los próximos deploys de Actions y se conserva como registro.

La ruta general nativa usa el servicio y transporte predeterminados que genera
Dokploy. No hereda el `serversTransport` personalizado ni el `flushInterval: -1ms`
del servicio de archivo. Ese transporte sigue para wildcard y rutas específicas;
no afirmar equivalencia de todos los parámetros internos. Los límites, headers,
compresión y restricción Cloudflare se conservan mediante los cinco middlewares.

Las comprobaciones HTTP dieron: general/institucional/panel 200, HTTP → HTTPS 301,
rutas privadas 403 y origen directo del hostname general 403. Se comprobó el
certificado institucional y su cobertura wildcard. Las imágenes y todos los mounts
se compararon antes/después, no se restauraron datos ni se tocaron migraciones.
No se hicieron pruebas funcionales con registros de negocio ni una restauración.

El archivo dinámico se aplicó desde el panel y su configuración queda versionada
en este repositorio. Publicar infra en Git no sincroniza ese archivo automáticamente
ni actualiza el checkout operativo del host: ese checkout y los recursos retenidos
del host no se modificaron con esta limpieza.

## Nombre de la aplicación

La aplicación se llama **Bemol**. Los nombres anteriores no se conservan como
contrato permanente: su retiro requiere migración de recursos/datos y un corte
coordinado. Consultar [la transición de nombre](RENOMBRE-BEMOL.md).
