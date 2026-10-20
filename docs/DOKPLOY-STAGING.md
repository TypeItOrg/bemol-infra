# Staging con Dokploy

**Estado: preparación; todavía no se hizo el corte.** El servidor sigue con
Nginx y el stack anterior hasta completar los requisitos y avisar al responsable.
Esta guía sólo aplica a staging. No instala ni modifica producción o QA.

Preparación verificada el 2026-10-20: sudo operativo, respaldo privado de
configuración y dump PostgreSQL restaurado en un contenedor aislado sin red ni
volúmenes persistentes. Se crearon y verificaron por API los registros wildcard
institucional DNS-only y panel con proxy Cloudflare, sin cambiar los existentes.
Eso **no confirma** que Dokploy o el panel estén instalados ni certificados.
Antes de cada corte repetir el inventario y los respaldos necesarios.

## El flujo, sin scripts de despliegue propios

```text
push a staging → GitHub Actions valida y publica GHCR
              → pide el despliegue por HTTPS a Dokploy
              → Dokploy descarga las imágenes y ejecuta Compose

Internet → Cloudflare (sólo hostname general) → Traefik → UI → API → PostgreSQL/Redis
Internet → Traefik (subdominios institucionales DNS-only) ──┘
```

- **Actions:** validaciones, build y publicación. Se conservan los tags
  `sha-<commit>` y `staging`. Sólo un push a la rama `staging` solicita este deploy.
- **Dokploy:** variables privadas del ambiente, descarga, arranque, logs e historial.
  No compila UI/API en el servidor. No activar otro auto-deploy por Git/webhook.
- **Traefik:** proxy, HTTPS, wildcard y políticas HTTP. Nginx/Certbot dejan de
  intervenir en staging después de aceptar el corte.
- **boero-infra:** Compose y configuración declarativa revisable; no contiene secretos.
- **Aplicación:** relaciona un subdominio con una institución. No llama a Cloudflare.

En el uso normal `UI_VERSION=staging` y `API_VERSION=staging`: se descargan las
últimas imágenes publicadas de esa rama. No significa que el HEAD de Git ya esté
desplegado: una revisión con CI fallido no se publica, y UI/API tienen pipelines
independientes. Un redeploy puede actualizar ambas imágenes. Registrar sus digests
y los tags SHA al aceptar cada versión; para reproducir o volver atrás, fijar ambos
`sha-<commit>` en Dokploy. No reconstruir ni mover tags SHA.

El job se llama **Request staging deployment**: un HTTP exitoso sólo confirma la
solicitud asíncrona, no la salud. Revisar el despliegue en Dokploy y los healthchecks.
No se conserva el rollback automático del shell anterior. Volver a imágenes previas
no deshace migraciones de Flyway.

## Accesos necesarios

1. SSH `home-server-staging`, usuario `staging`, con sudo temporal para instalar,
   respaldar configuración protegida y cambiar los servicios durante la ventana.
   Revocar el sudo temporal al terminar. No usar el socket Docker para eludir sudo.
2. Cloudflare: editar únicamente registros de staging en `typeit.com.ar` y disponer
   de un token DNS limitado a esa zona, con `Zone:Read` y `DNS:Edit`. Revisar si el
   token privado actual de Certbot sirve; no imprimirlo ni ponerlo en el chat/Git.
3. GitHub: lectura de `boero-infra` desde Dokploy y descarga de imágenes GHCR (si
   son privadas), más administración del environment `staging` en UI/API.
4. Cuenta administradora de Dokploy. Completar personalmente el alta/contraseña y
   2FA; proteger el panel, no compartir credenciales por chat.

Después del alta y de crear una API key desde el panel, **deshabilitar Docker
Cleanup como primer cambio autenticado** (`settings.updateDockerCleanup`,
`enableDockerCleanup=false`) y comprobar el valor antes de reiniciar Dokploy.
En v0.30.8 está activado por defecto: su limpieza diaria es global y puede borrar
contenedores legacy detenidos, imágenes y redes que necesitamos para volver atrás.
No modifica volúmenes, pero eso no alcanza para preservar el rollback. No ejecutar
prune por iniciativa durante la migración.

## DNS y certificados, sin extras de pago

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

Traefik solicita `staging.typeit.com.ar` + `*.staging.typeit.com.ar` por DNS-01.
El token va en un archivo privado del host, disponible al **Traefik de Dokploy**;
no en Environment de Boero, etiquetas ni secrets de Actions. Ver
`deploy/dokploy/traefik.env.example`. Persistir y respaldar también el almacenamiento
ACME; sus archivos y el token son privados, no material de diagnóstico para publicar.

## Configuración única en Dokploy

Crear un servicio **Docker Compose** desde este repositorio, con el archivo
`compose.dokploy.staging.yaml`. Éste extiende `compose.yaml`; ambos deben estar en
el checkout. No combinarlo con `compose.staging.yaml`. No activar isolated
deployments ni dominios autogenerados sobre el servicio: las reglas Boero están en
el archivo dinámico de Traefik.

1. Importar los valores privados actuales de staging en Environment y contrastar
   con `.env.dokploy.staging.example`. Conservar DB, JWT, refresh, mail, storage,
   autologin y WebAuthn; no reemplazar secretos con ejemplos. Mantener ambos
   `*_VERSION`, porque el archivo base los exige antes de resolver `extends`.
2. **Primer arranque:** usar los mismos tags SHA de UI/API que estén ejecutándose
   en el momento del corte. No mezclar migración de infraestructura con una versión
   nueva de la aplicación. No activar todavía los workflows modificados.
3. Crear un **File Mount** de Dokploy: en su campo **File path** poner únicamente
   `postgres-entrypoint.sh`, con el contenido de `docker/postgres-entrypoint.sh`.
   Compose lo referencia como `../files/postgres-entrypoint.sh`; no pegar ese
   prefijo en el campo del panel. No depender del bind al checkout
   Git descartable ni permitir que Docker cree un directorio en lugar del archivo.
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
   del ejemplo; directorio privado 0700 y archivos 0600. Guardar Environment o la
   configuración estática recrea Traefik: hacerlo dentro de la ventana acordada.
7. Configurar el panel con HTTPS en `deploy-staging.typeit.com.ar`. Hacer su alta
   inicial mediante túnel SSH, sin dejar el puerto 3000 públicamente accesible.
   Después de verificar HTTPS, retirar la publicación directa de 3000 siguiendo
   la documentación oficial y comprobar desde fuera que quedó cerrada.

`api-storage-init` se ejecuta como dependencia de API y debe terminar bien antes
de iniciarla. Conserva archivos, corrige permisos y usa la misma imagen que API;
no corre como parte de un paso SSH ni requiere credenciales de aplicación.

### Diferencias HTTP que hay que comprobar antes de aceptar

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
  para metadatos de autenticación. No afirmar paridad de IP de auditoría con Nginx;
  resolver o aceptar expresamente esta diferencia antes del corte definitivo.

## Corte: avisar primero, no ejecutar como parte de una prueba

La instalación estándar requiere libres **80, 443 y 3000**. Actualmente Nginx y UI
los ocupan; instalar Dokploy no es un paso inocuo previo a la ventana.

Release elegida y revisada: **Dokploy v0.30.8**, con Traefik v3.6.25. Su
[instalador de release](https://github.com/Dokploy/dokploy/releases/download/v0.30.8/install.sh)
tiene SHA-256
`534679c2f2730d369302df4e938d4dfaec177731b6d91cb87d8ecc7ca7cbc9bd`, contrastado
con el digest publicado por GitHub. Descargar/verificar no lo ejecuta. El script
conserva Docker si ya existe, pero **fuerza la salida de Swarm**, lo inicializa y
recrea `dokploy-network`: no ejecutarlo sobre un Swarm existente con servicios.
Volver a comprobar ese estado y los rangos de red antes de la ventana; no usar
inicializar Swarm como una supuesta comprobación inocua.
El instalador deja `/etc/dokploy` con permisos amplios: revisar y restringir el
árbol de configuración antes de guardar credenciales, sin romper el acceso de
los servicios. Su mensaje final tampoco prueba éxito; comprobar servicios y salud.

1. Confirmar sudo, DNS/accesos, capacidad, imágenes SHA, mounts y plan de vuelta.
   Antes del instalador, restringir el acceso externo a 3000 para que nadie pueda
   reclamar el alta inicial del panel. Preservar SSH y no publicar los puertos de
   Swarm a Internet. Comprobar reglas efectivas para tráfico Docker, no suponer que
   una regla UFW alcanza para los puertos que Docker publica.
   Pausar envíos a staging y esperar a que no haya despliegues en curso en ambos
   repositorios. Avisar inicio/impacto y obtener la conformidad para la ventana.
   Con el checkout actualizado, tomar el lock existente
   `/tmp/boero-infra-staging.lock` y crear `.deploy/staging/dokploy-managed` dentro
   de ese lock. Los scripts legacy y `make down` rechazan entonces staging antes
   de mutar; también falla un job SSH viejo que estuviera esperando el lock.
   Conservar el marker después del corte. Backup y consultas no quedan bloqueados.
2. Crear un dump PostgreSQL validado, respaldar configuración privada y Nginx/
   Certbot sin mostrarlos. Verificar una restauración en una base descartable.
   Registrar digests, referencias y nombres de volúmenes actuales.
3. Detener escrituras y el stack anterior con **stop**, sin borrar contenedores,
   volúmenes ni red. Con los servicios detenidos, copiar los volúmenes persistentes
   (incluidos adjuntos y Redis) a un respaldo recuperable. Evitar dos PostgreSQL
   simultáneos sobre el mismo volumen. No usar `down -v`, prune ni reinitializar PG.
4. Detener Nginx e instalar una versión estable explícita de Dokploy desde el
   instalador oficial de esa release, revisado antes de ejecutarlo con privilegios.
   No sobrescribir Docker existente ni elegir `latest` sin revisión. Configurar
   panel/proxy/Compose como arriba y arrancar con los mismos SHA.
5. Verificar contenedores saludables, TLS/SAN, DNS, HTTPS/redirects, rutas bloqueadas,
   headers/compresión, login/logout/passkeys y sesiones existentes. Verificar
   instituciones, adjuntos reales, persistencia y permisos. Crear/renombrar una
   institución sólo con datos de prueba autorizados; limpiar o revertir ese cambio.
6. Reactivar y probar el backup diario. Sólo tras aceptación cambiar ambas versiones
   a `staging`, configurar los secrets y publicar los cambios de workflows mediante
   la entrega Git autorizada. Ejecutar un despliegue controlado y comprobar salud.
7. Deshabilitar Certbot únicamente para este sitio cuando Traefik tenga certificado
   válido/renovación configurada. Conservar configuración anterior para vuelta,
   quitar acceso SSH de los jobs y revocar sudo temporal cuando ya no se necesite.

**Si falla:** detener primero el stack nuevo y Traefik; reiniciar los contenedores
anteriores y Nginx con sus imágenes/configuración guardadas. Nunca escribir en los
volúmenes desde dos stacks a la vez. No restaurar backups ni tocar Flyway por
iniciativa: puede borrar escrituras nuevas; requiere una decisión explícita.
Sólo después de detener el stack nuevo y decidir volver al flujo legacy, retirar
el marker bajo el lock. No quitarlo para forzar un despliegue normal.

## Actions y operación cotidiana

Secrets del environment `staging` en **ambos** repositorios:

| Secret | Valor |
|---|---|
| `DOKPLOY_URL` | `https://deploy-staging.typeit.com.ar` |
| `DOKPLOY_API_KEY` | Credencial Dokploy dedicada, con el menor alcance disponible |
| `DOKPLOY_STAGING_COMPOSE_ID` | ID del mismo servicio Compose de Boero staging |

No cambiar secrets de producción/QA. No bloquear este endpoint detrás de una
pantalla de login de Cloudflare Access que Actions no pueda atravesar. La API key
es privilegiada: no imprimir respuestas ni habilitar trazas shell que la muestren.

Operar despliegues, logs, estado y cambios de variables desde Dokploy. Para rollback,
fijar los dos tags SHA conocidos en Environment y redeploy; revisar compatibilidad
de la base antes. No usar los antiguos `make deploy-*`, `bootstrap`, `rollback-*`,
`down` ni sus scripts para administrar el stack migrado.

Se conserva `make backup-db ENV=staging`: localiza exactamente un PostgreSQL vivo
por su volumen histórico y label de servicio, sin duplicar secretos de Dokploy.
Guarda dumps 0600 y valida con `pg_restore --list` antes de rotar; eso no sustituye
un ensayo de restauración. `.env.staging` ya no es obligatorio para ese backup;
`BACKUP_DIR` y `BACKUP_RETENTION_DAYS` pueden configurarse en el servicio systemd.
Mantener el checkout operativo de `/opt/boero-infra` para este backup y habilitar
`boero-backup@staging.timer` sólo después de ejecutar exitosamente el servicio.
El timer no coordina un lock con Dokploy: no programar un corte simultáneo.

Los respaldos locales no cubren la pérdida del disco/host. Conservar además una
copia fuera de la máquina sin contratar servicios adicionales; PostgreSQL no incluye
los adjuntos locales, que necesitan su propio respaldo recuperable.

## Subdominios automáticos

Con wildcard DNS + TLS + router ya configurados, editar `publicSubdomain` desde la
administración de una institución activa basta para que su hostname funcione.
No crear un registro/certificado/proxy por institución. La aplicación ya valida
formato, unicidad y nombres reservados; desconocidos/inactivos no son instituciones
válidas. El nombre de la institución no se convierte automáticamente en subdominio.
Renombrar rompe el enlace anterior; no promete alias ni redirecciones históricas.
WebAuthn mantiene RP `staging.typeit.com.ar` y el origen general exacto; no sustituir
orígenes por un wildcard. No hace falta modificar el código de la aplicación.

## Qué se retira y qué queda

- **Sale del flujo staging:** SSH desde CI, git pull remoto, edición de hashes en
  `.env`, locks/rollback del deploy shell y operación manual Nginx/Certbot.
- **Queda:** Actions/GHCR, Dockerfiles, Compose base, perfiles, cinco volúmenes,
  secretos actuales y backup validado. Las variables locales `.env.dev` no cambian.
- **No borrar todavía:** scripts compartidos, overlays legacy y ejemplos Nginx:
  producción/QA o el plan de vuelta aún los usan. Eliminar su uso en staging no
  autoriza eliminarlos para todos los ambientes.

Fuentes: [instalación](https://docs.dokploy.com/docs/core/installation),
[Compose](https://docs.dokploy.com/docs/core/docker-compose),
[API Compose](https://docs.dokploy.com/docs/api/compose),
[Universal SSL](https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/limitations/),
[wildcard DNS](https://developers.cloudflare.com/dns/manage-dns-records/reference/wildcard-dns-records/).
