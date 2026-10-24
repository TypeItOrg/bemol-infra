# Staging: Nginx + Certbot

La operación vigente está en [STAGING.md](STAGING.md). Esta guía detalla el proxy
del host y TLS, sin conservar procedimientos para reinstalar el proxy anterior.
La evidencia histórica al final no sustituye una comprobación actual del VPS.

## Responsabilidades

```text
Navegador → Cloudflare (general) o directo (institucional) → Nginx del host
                                                         ↓ 127.0.0.1:3000
                                                         Next.js → API → DB / Redis
```

| Archivo dentro de `deploy/nginx/` | Contexto y responsabilidad |
|---|---|
| `nginx.conf` | Proceso, eventos, logs e includes del contexto `http` |
| `conf.d/upstreams.conf` | Sólo UI y mapa de Upgrade; no hay upstream público de API |
| `conf.d/cloudflare.conf` | IP real confiable y clasificación del peer de conexión |
| `conf.d/compression.conf` | Gzip y tipos comprimibles |
| `conf.d/cache.conf` | Sin caché compartida; conservar `Cache-Control` de Next.js |
| `conf.d/limits.conf` | Zonas por IP/host, límite de autenticación, tamaños y timeouts |
| `snippets/tls.conf` | Certificado general + wildcard y sesiones TLS |
| `snippets/security.conf` | Headers de seguridad, sin cookies ni tokens en logs |
| `snippets/proxy.conf` | Headers del upstream, conexión y streaming sin buffering de respuesta |
| `snippets/application.conf` | Límites efectivos, rutas privadas y envío a Next.js |
| `sites/staging.conf` | Hosts aceptados, separación general/institucional y HTTPS |

`nginx.conf` se instala en `/etc/nginx/nginx.conf`. El árbol completo se copia a
`/etc/bemol/nginx/`; sus includes son absolutos. No se cargan además las antiguas
`sites-enabled` ni `conf.d` del host: duplicarían gzip, hosts y reglas de IP real.
No agregar `add_header` en un `location` sin conservar los headers heredados.

`/api/*` sigue siendo de Next.js. `/api/v1`, `/api/v1/*` y `/actuator*` devuelven
`403` desde Nginx. Spring sigue en la red interna; su puerto de mantenimiento
permanece en loopback. No agregar un `location /api/` que apunte a Spring.

El host general exige un peer Cloudflare incluso si el cliente falsifica headers.
Los subdominios institucionales admiten conexión directa y sólo un nivel de slug
DNS válido. `CF-Connecting-IP` se acepta únicamente desde los rangos confiables;
el upstream recibe `X-Real-IP` y `X-Forwarded-For` reconstruidos. Los hosts ajenos
se cierran en HTTP y se rechazan durante el handshake TLS. Nginx no publica dashboard; no modificar DNS ajeno por iniciativa.

### Caché y diferencias de límites

No se agrega caché de disco ni reglas `expires` globales. Los assets versionados
de Next.js mantienen sus headers actuales; HTML, sesiones y documentos privados
no se convierten en contenido público por extensión de archivo. La caché de
sesiones TLS no almacena respuestas HTTP.

Las tasas nominales son 20 solicitudes/s por IP, burst 100; autenticación
30/min, burst 20; concurrencia 50 por IP y 200 por host. Nginx comparte esas zonas
entre los workers y rutas.
El acceso general cuenta por IP; el institucional conserva IPv4 por dirección
e IPv6 por red `/64`, incluidos los límites de autenticación y concurrencia.
La clave IPv6 usa los primeros ocho bytes de la dirección binaria, sin depender
de cómo se abrevian los ceros al escribir la IP. No registrar esa clave binaria.
El límite de cuerpo es 32 MiB para cualquier método; las respuestas no se
bufferizan. Nginx puede almacenar temporalmente cuerpos de solicitud en disco.

Los rangos Cloudflare se mantienen en dos bloques del mismo archivo: confianza
de IP real y clasificación del peer original. Actualizar ambos con las listas
[IPv4](https://www.cloudflare.com/ips-v4/) e [IPv6](https://www.cloudflare.com/ips-v6/).

## Certificados y cambios autorizados

Antes de modificar configuración, confirmar host, puertos, imágenes y mounts.
Mantener el lock `/tmp/bemol-infra-staging.lock` durante la ventana y crear un
backup privado verificado de `/etc/nginx`, `/etc/bemol/nginx`, `/etc/letsencrypt`
y del checkout operativo con su entorno. No imprimir secretos ni borrar volúmenes.

El certificado `bemol-staging` cubre el dominio general y el wildcard. Certbot
usa DNS-01 con Cloudflare y `/etc/letsencrypt/cloudflare.ini`, root y `0600`.
La emisión inicial requiere autorización y no forma parte del deploy habitual:

```sh
sudo certbot certonly --dns-cloudflare \
  --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
  --cert-name bemol-staging \
  -d staging.bemol.com.ar -d '*.staging.bemol.com.ar'
```

Conservar la cuenta ACME y el token DNS existentes. No ejecutar desafíos
simultáneos, usar `--force-renewal`, borrar TXT ajenos ni usar el instalador
`--nginx`, que puede reescribir la configuración separada.

El hook `deploy/certbot/reload-nginx.sh` se instala en
`/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`, root y `0755`.
Sólo analiza y recarga Nginx si ya está activo; no lo inicia.

Tras una modificación autorizada, validar antes de recargar:

```sh
sudo nginx -t && sudo systemctl reload nginx
```

Un fallo de análisis impide la recarga. El rollback de configuración consiste en
restaurar la copia conocida de Nginx y volver a validarla antes de recargar; no
restaurar DB, archivos o volúmenes para corregir el proxy.

`certbot.timer` gestiona la renovación. Una comprobación autorizada mediante
`certbot renew --cert-name bemol-staging --dry-run --run-deploy-hooks` escribe TXT
temporales: verificar también la recarga y el certificado realmente servido.
No ejecutar esa operación ni ampliar la aceptación por iniciativa.

## Corte verificado: 2026-10-23

- Destino `cristinet`, con sudo interactivo y lock compartido durante la ventana.
  No se guardó la contraseña ni se configuró acceso administrativo permanente.
- Backup de configuración privado y comparado contra sus orígenes:
  `/var/backups/bemol/proxy-20261023T174542Z/config.tgz`, con inventario y checksum.
  Incluye la configuración del proxy anterior, Nginx, Certbot y el checkout privado.
- Dump validado: `/var/backups/bemol/staging/bemol-staging-20261023T174510Z.dump`.
  El intento anterior del timer había coincidido con PostgreSQL arrancando; la
  repetición finalizó con éxito. No se cambió la política del servicio ni se hizo
  un ensayo de restauración; esa carrera con el arranque puede volver a ocurrir.
- Agrupación IPv6 `/64` comprobada en Nginx 1.28.3 con un proceso temporal y
  socket Unix, sin puertos públicos: ceros abreviados, bytes binarios cero/salto
  de línea, claves de autenticación, dominio general por IP y rechazo `429` al
  compartir red. IPv4 y redes distintas permanecieron independientes. El proceso
  y sus archivos temporales se retiraron; no se ejecutaron suites de aplicación.
- Certificado `bemol-staging` emitido con la cuenta ACME y el token DNS existentes,
  para dominio general y wildcard, válido hasta 2027-01-21. `nginx -t` nativo pasó
  con los archivos y certificados reales. No se instaló ni actualizó ningún paquete.
- Sólo se recreó UI, con el mismo ID de imagen y mounts, fijando temporalmente su
  digest y publicando `127.0.0.1:3000`. `.env.staging` conserva su contenido exacto
  y sus tags habituales para los siguientes deploys. API/PostgreSQL/Redis mantienen
  IDs, imágenes, mounts y tiempos de arranque; quedaron saludables.
- Se conservó la redirección previa del login de plataforma en subdominios
  institucionales: `303` a `/auth/login`. Nginx quedó activo y habilitado.
- Páginas general/plataforma e institucional `200`, `/api/health` de Next.js `200`,
  rutas privadas `403`, origen general directo `403` incluso con headers falsos,
  redirección HTTP institucional `301` y headers de seguridad presentes.
- Desde fuera del VPS: login general e institucional `200`, ambos con TLS
  validado; HTTP general `301` al mismo host por HTTPS. El certificado de origen
  servido coincide con el archivo de Certbot.
- HTML de acceso con `private, no-cache, no-store`; un asset versionado con gzip
  y `public, max-age=31536000, immutable`, sin caché compartida agregada en Nginx.
- `certbot renew --dry-run --run-deploy-hooks` finalizó correctamente: DNS-01 y
  hook de análisis/recarga verificados, sin reiniciar el proceso maestro de Nginx.
  Timer Certbot activo/habilitado, ejecución del servicio exitosa; timer de backup
  activo/habilitado y último backup exitoso. El lock de mantenimiento se liberó.
- El plugin Cloudflare emitió un aviso de deprecación de su SDK instalado; emisión
  y renovación simulada funcionaron. No se cambiaron dependencias fuera de alcance.
- No se probaron autenticación real, refresh, passkeys, correo ni adjuntos; no se
  usaron datos de negocio para tests. No se hicieron commits ni pushes.
