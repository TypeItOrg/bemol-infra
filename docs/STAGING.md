# Staging con Docker Compose y Traefik

La configuración preparada usa GitHub Actions para validar y publicar imágenes,
SSH para ejecutar el despliegue y dos proyectos Compose en el VPS: aplicación y
proxy. Esta documentación describe el reemplazo de Dokploy, pendiente de aplicar
al servidor. No acredita el estado actual del host. Staging sigue siendo el único
entorno compartido configurado.

## Archivos que se usan

| Archivo | Responsabilidad |
|---|---|
| [compose.yaml](../compose.yaml) | Definiciones comunes de UI, API, PostgreSQL, Redis y preparación de permisos de storage |
| [compose.staging.yaml](../compose.staging.yaml) | Perfil staging, autologin opcional, integración con el proxy y nombres de redes y volúmenes |
| [compose.traefik.staging.yaml](../compose.traefik.staging.yaml) | Proxy, puertos 80/443, token DNS y almacenamiento ACME |
| [deploy/staging.env](../deploy/staging.env) | Dominio base y nombre de staging; de ambos se deriva el hostname |
| [.env.staging.example](../.env.staging.example) | Plantilla pública del entorno privado de la aplicación |
| [scripts/prepare-staging.sh](../scripts/prepare-staging.sh) | Generación de configuración y verificación de volúmenes existentes |
| [scripts/compose-staging.sh](../scripts/compose-staging.sh) | Proyecto Compose y archivos de entorno compartidos por los comandos |
| [scripts/deploy-staging.sh](../scripts/deploy-staging.sh) | Bloqueo compartido, pull y actualización de contenedores |
| [deploy/traefik/](../deploy/traefik/README.md) | Reglas del proxy separadas por responsabilidad y validación de certificados |

Los archivos `compose.dokploy.staging.yaml`, `.env.dokploy.staging.example` y
`deploy/dokploy/` quedan como referencia del corte anterior. Los workflows nuevos
no los usan. El historial de ese despliegue se conserva en
[DOKPLOY-STAGING.md](DOKPLOY-STAGING.md).

## Compose base y diferencias de staging

La aplicación combina los archivos en este orden: `compose.yaml` y después
`compose.staging.yaml`. El segundo agrega o sobrescribe la configuración del
primero; no vuelve a definir imágenes, recursos, healthchecks ni permisos comunes.
`scripts/compose-staging.sh` carga ambos junto con los archivos de entorno, por
lo que `make prepare-staging` y `make deploy-staging` usan la misma combinación.

El base no se despliega por sí solo: necesita la configuración de un entorno.
Cuando se prepare producción se añadirá `compose.prod.yaml` con su perfil y
recursos propios, reutilizando el mismo base. Producción no está configurada.

## Dominio y variables privadas

Ejecutar `make render-staging-config` genera en `build/staging/`:

- `domains.env`: sólo valores públicos derivados de `BASE_DOMAIN` y
  `STAGING_SUBDOMAIN`, incluidos WebAuthn, URLs y dominio institucional.
- `.env.staging.example`: ejemplo completo para preparar el entorno privado.
- `traefik/dynamic/`: seis archivos de reglas listos para el proxy.

Antes del primer deploy, y al cambiar el dominio, las plantillas de Traefik o el
Compose de la aplicación, ejecutar `make prepare-staging` en el VPS. Este comando
genera los archivos y comprueba la configuración y los volúmenes existentes.
`make render-staging-config` permite generar sólo los archivos, sin consultar
Docker. El deploy cotidiano reutiliza la configuración preparada.

El archivo privado real es `/opt/bemol-infra/.env.staging`, con permisos 0600 y
valores existentes de DB, autenticación, correo, storage y versiones. No reemplazar
sus secretos por los placeholders del ejemplo. El deploy carga ese archivo y luego
`domains.env`: los valores públicos derivados prevalecen sin sustituir secretos.
La aplicación y el proxy usan así el mismo dominio de origen.

El renderer reemplaza cada archivo generado mediante un rename, evitando que el
proxy lea un YAML truncado. Los archivos privados y `build/` quedan fuera de Git.

## Despliegue automático

Los workflows de API y UI conservan sus validaciones y la publicación en GHCR de
`sha-<commit>` y `staging`. Después abren SSH y ejecutan este comando fijo:

```bash
cd /opt/bemol-infra && exec bash scripts/deploy-staging.sh
```

Cada GitHub Environment `staging` necesita estos secrets:

| Secret | Contenido |
|---|---|
| `DEPLOY_HOST` | Hostname o IP del VPS verificado |
| `DEPLOY_PORT` | Puerto SSH, por ejemplo 22 |
| `DEPLOY_USER` | Usuario con acceso a Docker y al checkout operativo |
| `DEPLOY_SSH_KEY` | Clave privada de despliegue |
| `DEPLOY_SSH_KNOWN_HOSTS` | Entrada del host SSH cuya huella se verificó previamente |

El cliente exige esa clave de host; no descubre ni acepta una huella nueva durante
el workflow. El resultado SSH propaga el exit code del script. El script espera
hasta 600 segundos la salud definida por los contenedores; esto no sustituye una
verificación funcional del negocio. No ejecuta rollback automático.

La preparación, los despliegues de API/UI y el backup PostgreSQL comparten
`/tmp/bemol-infra-staging.lock` para evitar operaciones simultáneas. Los usuarios
del timer y del deploy deben poder abrir el mismo lock; preparar su propietario/grupo durante el corte.

El deploy utiliza la versión de `bemol-infra` instalada en `/opt/bemol-infra`; no
hace `git pull` automático. Actualizar ese checkout es una operación de
infraestructura separada. Los pipelines de aplicaciones actualizan sus imágenes.

## Operación manual

Desde `/opt/bemol-infra`, `make deploy-staging` aplica las versiones seleccionadas
en `.env.staging`. Para elegir otra imagen, editar `API_VERSION` o `UI_VERSION`,
por ejemplo a `sha-<commit>`, y ejecutar el mismo comando. Para el flujo normal,
ambas variables pueden permanecer en `staging`.

Un tag `staging` obtiene lo último publicado; un deploy del stack puede actualizar
ambas aplicaciones. El script respeta los tags elegidos en el archivo privado.
Volver a una imagen no revierte migraciones Flyway ni datos.

El proxy se inicia separadamente con
`docker compose -f compose.traefik.staging.yaml up -d`, después de preparar sus
archivos y liberar 80/443. Los despliegues de aplicaciones no recrean el proxy.
Estado y logs se consultan con los comandos Compose del proyecto correspondiente;
no hay un panel de despliegue adicional. Para la aplicación,
`scripts/compose-staging.sh ps` y `scripts/compose-staging.sh logs` usan el mismo
proyecto y entorno que el deploy.

El backup sigue usando `make backup-db ENV=staging` y el timer existente. Sus
volúmenes y política de retención se conservan; este cambio no ejecuta backups ni
restauraciones y no respalda por sí solo los adjuntos.

## Corte del VPS desde Dokploy

Preparar y verificar el corte antes de habilitar los secrets SSH de Actions:

1. Confirmar el host, proyectos Compose reales, imágenes, redes y mounts. Conservar
   los cinco volúmenes externos declarados en `compose.staging.yaml` y la red
   privada `bemol-network-staging`. Si falta un dataset, resolverlo antes de
   desplegar; no crear una base vacía sustituta.
2. Instalar el checkout operativo y su `.env.staging` con valores existentes.
   El usuario de despliegue necesita Docker Compose, Bash, Python 3 y `flock`,
   permisos sobre checkout/lock y lectura de las imágenes GHCR. Autenticar GHCR
   como ese usuario si las imágenes son privadas; el login de Dokploy no lo
   configura automáticamente.
3. Crear la red externa `bemol-proxy-staging`. Sólo UI y Traefik la comparten;
   API/DB/Redis siguen en la red privada. No se necesita `dokploy-network` en la
   nueva configuración.
4. Preparar `.deploy/traefik.staging.yaml` desde el ejemplo estático, con el contacto
   ACME real; el token privado en `/etc/bemol/secrets/cloudflare-dns-token`; y el
   almacenamiento persistente `/var/lib/bemol/traefik/staging/`. Conservar el estado
   ACME que cubra el dominio elegido, sin dos proxies escribiéndolo a la vez.
5. Desactivar los disparadores anteriores. Detener el stack antiguo usando su
   proyecto real y esperar que termine PostgreSQL antes de iniciar el nuevo sobre
   sus mismos volúmenes. Detener el proxy anterior para liberar 80/443. No borrar
   volúmenes, usar Fresh Volumes, ejecutar prune ni forzar un reinicio de Swarm.
6. Ejecutar `make prepare-staging`. La preparación se detiene si falta un volumen
   externo o sigue en uso por otro proyecto, para evitar iniciar un segundo
   PostgreSQL. Cuando termine, ejecutar `make deploy-staging` y levantar el
   Compose de Traefik. La preparación no descarga imágenes ni inicia contenedores.
7. Comprobar imágenes seleccionadas, salud, HTTPS general e institucional,
   certificado wildcard y políticas del proxy. El panel de Dokploy no se migra al
   proxy nuevo. Habilitar la integración SSH y retirar únicamente los componentes
   identificados como Dokploy cuando se haya comprobado el reemplazo. Revocar los
   antiguos secrets `DOKPLOY_*` de ambos repositorios.

Publicar estos archivos no ejecuta ese corte ni desinstala Dokploy.
