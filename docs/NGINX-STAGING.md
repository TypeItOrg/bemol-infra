# Staging: Nginx y Certbot

Nginx corre en Ubuntu, fuera de Docker. Recibe HTTP/HTTPS y envía las solicitudes
a `127.0.0.1:3000` del VPS, publicado por el contenedor UI. El despliegue de la
aplicación no instala ni actualiza estos archivos; ver [STAGING.md](STAGING.md).

## Archivos del proxy

| Fuente dentro de `deploy/nginx/` | Destino en el VPS |
|---|---|
| [nginx.conf](../deploy/nginx/nginx.conf) | `/etc/nginx/nginx.conf` — procesos, conexiones y ajustes HTTP generales |
| [sites-available/staging.bemol.com.ar.conf](../deploy/nginx/sites-available/staging.bemol.com.ar.conf) | `/etc/nginx/sites-available/staging.bemol.com.ar.conf` — upstream, límites, logs y dominios |
| [cloudflare.conf](../deploy/nginx/cloudflare.conf) | `/etc/bemol/nginx/cloudflare.conf` — rangos confiables e IP real |
| [application.conf](../deploy/nginx/application.conf) | `/etc/bemol/nginx/application.conf` — TLS, headers y rutas compartidas |

El global incluye `/etc/nginx/sites-enabled/*` dentro de `http`. El sitio se
habilita con un enlace al archivo de `sites-available`; contiene mapas, zonas,
upstream y bloques `server`, sin otro envoltorio `http`.

Revisar los sitios habilitados antes de aplicar cambios: no cargar además el
`default` de Ubuntu ni otro archivo con los mismos hosts o `default_server`.
El global no carga `/etc/nginx/conf.d` ni los antiguos directorios de Bemol.

## Dominios y acceso

| Dominio | Configuración prevista |
|---|---|
| `staging.bemol.com.ar` | Proxied por Cloudflare, TLS Full (strict); Nginx exige un peer Cloudflare |
| `<institucion>.staging.bemol.com.ar` | Wildcard DNS-only hacia el VPS; admite acceso directo y un nivel de slug |
| Otros nombres | Cierre HTTP `444` o rechazo del handshake TLS |

Los institucionales usan HTTPS de Nginx, pero no heredan el WAF ni los límites del
edge Cloudflare. No añadir registros AAAA sin IPv6 operativo.

`cloudflare.conf` confía en `CF-Connecting-IP` sólo desde los rangos permitidos y
clasifica el peer original con `$realip_remote_addr`. Actualizar ambos bloques al
cambiar las listas oficiales [IPv4](https://www.cloudflare.com/ips-v4/) e
[IPv6](https://www.cloudflare.com/ips-v6/). Un header falsificado no autoriza el acceso.

Todas las rutas permitidas van a Next.js, incluido `/api/*`; no hay upstream público
de Spring. `/api/v1`, `/api/v1/*` y `/actuator*` devuelven `403`. Se conserva `Host`
y se reconstruyen los headers de IP antes de enviarlos a la aplicación.

Si el proxy no puede comunicarse con Next.js, los errores generados por Nginx
`502/503/504` se convierten en `503`. Sólo navegación `GET/HEAD` que acepta HTML
recibe la pantalla autocontenida `.deploy/maintenance/maintenance.html`; se excluyen
API, RSC y assets. El resto recibe JSON de indisponibilidad, nunca una página que
pueda reenviar una mutación. Se mantienen los headers de seguridad y se agrega
`no-store` y `Retry-After: 5` a estas respuestas.

Los errores HTTP que Next.js devuelve se conservan (`proxy_intercept_errors off`):
el fallback no reemplaza errores funcionales ni respuestas JSON de la aplicación.
Las rutas `/__bemol/maintenance` y `/__bemol/unavailable` son internas de Nginx.

## Límites y respuestas

- Tráfico general: 20 solicitudes/s por cliente, burst 100.
- Autenticación: 30 solicitudes/min, burst 20, en los POST definidos en el mapa.
- Concurrencia: 50 conexiones por cliente y 200 por host; excesos devuelven `429`.
- Clientes institucionales: IPv4 por dirección e IPv6 por red `/64`.
  El dominio general cuenta por IP individual.
- Cuerpo máximo: 32 MiB. Respuestas sin buffering para streaming y compresión gzip.
- Sin caché HTTP compartida: Next.js conserva sus headers `Cache-Control`.

Los headers de seguridad y TLS están en `application.conf`, compartido por los dos
hosts HTTPS. No agregar `add_header` en un `location` sin conservar los heredados.
La caché de sesiones TLS no almacena respuestas HTTP.

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

3. Copiar primero los archivos compartidos y el sitio a los destinos de la tabla;
   preparar su enlace en `sites-enabled` y después instalar el archivo global.
   Para activar la pantalla, publicar la nueva imagen UI y ejecutar `make deploy`
   antes de recargar Nginx: debe existir
   `/opt/bemol-infra/.deploy/maintenance/maintenance.html`, legible por sus workers.
   Comprobar la lectura con `sudo -u www-data test -r /opt/bemol-infra/.deploy/maintenance/maintenance.html`;
   no ampliar permisos de directorios privados para resolver un fallo.
   Instalar juntos el sitio y `application.conf`, porque comparten los mapas del
   fallback. No hacen falta cambios en certificados, DNS ni volúmenes.
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
