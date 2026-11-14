# Staging: Nginx y Certbot

Nginx corre en Ubuntu, fuera de Docker. Recibe HTTP/HTTPS y envía las solicitudes
a `127.0.0.1:3000` del VPS, publicado por el contenedor UI. El despliegue de la
aplicación no instala ni actualiza estos archivos; ver [STAGING.md](STAGING.md).

## Archivos del proxy

| Fuente dentro de `deploy/nginx/` | Destino en el VPS |
|---|---|
| [nginx.conf](../deploy/nginx/nginx.conf) | `/etc/nginx/nginx.conf` — procesos, conexiones y ajustes HTTP generales |
| [conf.d/bemol.conf](../deploy/nginx/conf.d/bemol.conf) | `/etc/nginx/conf.d/bemol.conf` — entornos, upstreams, límites, logs, mapas y hosts desconocidos |
| [sites-available/staging.bemol.com.ar.conf](../deploy/nginx/sites-available/staging.bemol.com.ar.conf) | `/etc/nginx/sites-available/staging.bemol.com.ar.conf` — dominios y certificado de staging |
| [sites-available/bemol.com.ar.conf](../deploy/nginx/sites-available/bemol.com.ar.conf) | `/etc/nginx/sites-available/bemol.com.ar.conf` — dominios y certificado de producción |
| [snippets/bemol-cloudflare.conf](../deploy/nginx/snippets/bemol-cloudflare.conf) | `/etc/nginx/snippets/bemol-cloudflare.conf` — rangos confiables e IP real |
| [snippets/bemol-application.conf](../deploy/nginx/snippets/bemol-application.conf) | `/etc/nginx/snippets/bemol-application.conf` — TLS común, headers y rutas compartidas |

`deploy/nginx/` replica la estructura de `/etc/nginx`. El global incluye
`conf.d/*.conf` y `sites-enabled/*` dentro de `http`. `conf.d/bemol.conf` se carga
una sola vez y contiene mapas, zonas, upstreams y los `default_server`. Los
`snippets/` no se cargan solos: cada bloque `server` incluye `bemol-application.conf`.
Cada sitio se habilita con un enlace en `sites-enabled` y sólo declara sus bloques
`server` y su certificado. `$bemol_env` deriva del host
el entorno, su upstream (`3000` staging, `3100` producción) y la pantalla temporal.

Revisar los sitios habilitados antes de aplicar cambios: no cargar además el
`default` de Ubuntu ni otro archivo con los mismos hosts o `default_server`.
`conf.d` debe contener sólo `bemol.conf`.

## Dominios y acceso

| Dominio | Configuración prevista |
|---|---|
| `staging.bemol.com.ar` | Proxied por Cloudflare, TLS Full (strict); Nginx exige un peer Cloudflare |
| `admin.staging.bemol.com.ar` | Administración, DNS-only; regex compartida en Nginx y passkey exigida por la aplicación |
| `<institucion>.staging.bemol.com.ar` | Wildcard DNS-only hacia el VPS; admite acceso directo y un nivel de slug |
| `bemol.com.ar`, `www` y `*.bemol.com.ar` | Producción: todo proxied por Cloudflare, TLS Full (strict); Nginx exige un peer Cloudflare en todos los hosts y `www` redirige al dominio principal |
| Otros nombres | Cierre HTTP `444` o rechazo del handshake TLS |

El host `admin.staging.bemol.com.ar` coincide con la misma expresión regular de
subdominios de un nivel que las instituciones y comparte sus bloques HTTP/HTTPS;
no tiene bloques `server` propios. Nginx conserva `Host`: Next.js y la API reconocen
el dominio administrativo mediante `PLATFORM_PUBLIC_URL` y aplican sus controles
de acceso y passkeys.
El panel se publica en `/`, sin `/admin` en las URLs visibles; esa reescritura
interna la realiza Next.js, no Nginx.

Los institucionales usan HTTPS de Nginx, pero no heredan el WAF ni los límites del
edge Cloudflare. No añadir registros AAAA sin IPv6 operativo.

`bemol-cloudflare.conf` confía en `CF-Connecting-IP` sólo desde los rangos permitidos y
clasifica el peer original con `$realip_remote_addr`. Actualizar ambos bloques al
cambiar las listas oficiales [IPv4](https://www.cloudflare.com/ips-v4/) e
[IPv6](https://www.cloudflare.com/ips-v6/). Un header falsificado no autoriza el acceso.

Todas las rutas permitidas van a Next.js, incluido `/api/*`; no hay upstream público
de Spring. `/api/v1`, `/api/v1/*` y `/actuator*` devuelven `403`. Se conserva `Host`
y se reconstruyen los headers de IP antes de enviarlos a la aplicación.

Si el proxy no puede comunicarse con Next.js, los errores generados por Nginx
`502/503/504` se convierten en `503`. Sólo navegación `GET/HEAD` que acepta HTML
recibe la pantalla autocontenida `.deploy/maintenance/<entorno>/maintenance.html`; se excluyen
API, RSC y assets. El resto recibe JSON de indisponibilidad, nunca una página que
pueda reenviar una mutación. Se mantienen los headers de seguridad y se agrega
`no-store` y `Retry-After: 5` a estas respuestas.

Los errores HTTP que Next.js devuelve se conservan (`proxy_intercept_errors off`):
el fallback no reemplaza errores funcionales ni respuestas JSON de la aplicación.
Las rutas `/__bemol/maintenance` y `/__bemol/unavailable` son internas de Nginx.

## Límites y respuestas

- Tráfico general: 20 solicitudes/s por cliente, burst 100.
- Autenticación por cliente: promedio de 2 solicitudes/min, burst 4, en los POST
  definidos en el mapa. Incluye registro, recuperación y los pasos de las llaves
  de acceso; una ráfaga desde reposo admite hasta cinco solicitudes.
- Escrituras globales (`POST`, `PUT`, `PATCH`, `DELETE`): 5 solicitudes/s, burst 10,
  por entorno, compartidas entre los hosts de ese entorno. Incluye autenticación y Server Actions,
  aunque se invoquen desde otra URL; no depende del header `Next-Action`.
- Tráfico general global: 50 solicitudes/s, burst 100, por entorno.
- Todas las claves incluyen el entorno: staging nunca consume cuota de producción.
- Concurrencia: 50 conexiones por cliente y 200 globales por entorno; excesos devuelven `429`.
- Clientes institucionales: IPv4 por dirección e IPv6 por red `/64`.
  El dominio general cuenta por IP individual.
- Cuerpo máximo: 32 MiB. Respuestas sin buffering para streaming y compresión gzip.
- Sin caché HTTP compartida: Next.js conserva sus headers `Cache-Control`.

Los headers de seguridad y TLS están en `bemol-application.conf`, compartido por el
dominio general y los subdominios HTTPS. No agregar `add_header` en un `location`
sin conservar los heredados.
La caché de sesiones TLS no almacena respuestas HTTP.

Los límites son un punto de partida operativo, no una garantía de capacidad ante
ataques distribuidos. Usan `nodelay`: el exceso se rechaza, no se encola. La cuota
se recupera gradualmente; no hay un bloqueo fijo de cinco minutos.

Los rechazos del borde devuelven `429`, `Cache-Control: no-store` y `Retry-After: 30`.
El plazo indica cuándo volver a intentar, no garantiza capacidad disponible: otros
clientes pueden consumir el límite global o compartir una misma red.
`/__bemol/rate-limited` es interna y conserva los headers de seguridad heredados.
La respuesta es `text/plain` sin charset, con el texto exacto
`Demasiadas solicitudes. Intentá nuevamente en unos instantes.`. Es el contrato con
el manejo de errores de Server Actions de Next.js y el frontend. No sustituirlo
por HTML/JSON sin adaptar y verificar ese flujo. Los `429` del upstream conservan
su respuesta original (`proxy_intercept_errors off`).

Cambiar este repositorio no aplica la configuración al Nginx del host: instalar
los archivos y ejecutar `nginx -t` antes del reload es una operación separada.

## Preparar y aplicar la configuración

Confirmar host y puertos antes de operar. El host necesita Nginx con soporte TLS,
HTTP/2 e IP real, Certbot y el plugin DNS de Cloudflare. En una instalación existente,
conservar una copia privada recuperable de la configuración y los certificados
antes de reemplazarlos; no modificar DB ni volúmenes para cambiar el proxy.

1. Preparar `/etc/letsencrypt/cloudflare.ini`, propiedad de root y permiso `0600`,
   a partir de [la plantilla](../deploy/certbot/cloudflare.ini.example). Usar un token
   DNS limitado a la zona; no guardarlo en Git ni en `.env.staging`.
2. Emitir el certificado antes de cargar la configuración TLS, o comprobar que ya
   exista con los dos nombres correctos. La emisión inicial por DNS-01 es:

   ```sh
   sudo certbot certonly --dns-cloudflare \
     --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
     --cert-name bemol-staging \
     -d staging.bemol.com.ar -d '*.staging.bemol.com.ar'
   ```

3. Copiar primero `snippets/`, `conf.d/` y los sitios a los destinos de la tabla;
   preparar el enlace de cada sitio en `sites-enabled` y después instalar `nginx.conf`.
   Para activar la pantalla, publicar la nueva imagen UI y ejecutar `make deploy`
   antes de recargar Nginx: debe existir
   `/opt/bemol-infra/.deploy/maintenance/<entorno>/maintenance.html`, legible por sus workers.
   Comprobar la lectura con `sudo -u www-data test -r /opt/bemol-infra/.deploy/maintenance/staging/maintenance.html`;
   no ampliar permisos de directorios privados para resolver un fallo.
   Instalar juntos `conf.d/bemol.conf`, los snippets y los sitios, porque comparten
   los mapas del fallback. No hacen falta cambios en certificados, DNS ni volúmenes.
4. Validar antes de recargar un Nginx activo:

   ```sh
   sudo nginx -t && sudo systemctl reload nginx
   ```

   Si es la primera instalación y Nginx está detenido, iniciarlo y habilitarlo sólo
   después de validar. Un fallo de `nginx -t` debe detener la operación.

No usar `certbot --nginx`, que puede reescribir la configuración del repositorio,
ni repetir la emisión en cada despliegue. No forzar renovaciones ni borrar TXT ajenos.
Para rollback del proxy, restaurar la configuración conocida y validarla antes de recargar.

## Renovación y comprobaciones

Instalar [reload-nginx.sh](../deploy/certbot/reload-nginx.sh) en
`/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`, root y `0755`.
El hook valida y recarga Nginx sólo si ya está activo; no lo inicia.
Comprobar que `certbot.timer` esté habilitado y activo.

Una comprobación de renovación escribe TXT temporales y requiere autorización:

```sh
sudo certbot renew --cert-name bemol-staging --dry-run --run-deploy-hooks
```

Después de aplicar cambios, verificar HTTPS general/institucional y certificado
servido, redirección HTTP, rechazo del origen general directo incluso con headers
falsos, rutas privadas `403`, headers de seguridad y logs. La existencia de estos
archivos en Git no acredita su instalación ni el estado del VPS.
