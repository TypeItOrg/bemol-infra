# Traefik de Bemol

El proxy está definido en
[compose.traefik.staging.yaml](../../compose.traefik.staging.yaml). La aplicación
combina [compose.yaml](../../compose.yaml) con las diferencias de
[compose.staging.yaml](../../compose.staging.yaml). Sólo UI comparte la red
externa `bemol-proxy-staging` con Traefik, mediante el alias `bemol-ui-staging`.
API, PostgreSQL y Redis permanecen en la red privada de la aplicación.

La configuración está preparada en Git; el corte del VPS desde Dokploy sigue
pendiente. Consultar [STAGING.md](../../docs/STAGING.md) para preparar los archivos,
conservar datos y realizar ese cambio. Los archivos históricos de Dokploy no son
la entrada de los nuevos workflows.

## Dominios centralizados

[deploy/staging.env](../staging.env) define `BASE_DOMAIN` y `STAGING_SUBDOMAIN`.
El generador deriva `STAGING_DOMAIN` uniendo ambos. Desde el repositorio:

```bash
make render-staging-config
```

El comando produce en `build/staging/`:

- `traefik/dynamic/`: seis YAML listos para el proxy.
- `domains.env`: valores públicos derivados para Compose, sin secretos.
- `.env.staging.example`: ejemplo para preparar el entorno privado.

Las fuentes pueden usar `${BASE_DOMAIN}`, `${STAGING_SUBDOMAIN}` y
`${STAGING_DOMAIN}`. Los sufijos `_REGEX` escapan los hostnames para expresiones
regulares. El renderer conserva `${2}` de las redirecciones. El proxy carga el
resultado generado; el file provider no expande esas variables de shell.

Antes del primer deploy o tras cambiar el dominio o las plantillas, ejecutar
`make prepare-staging` en el VPS: genera estos archivos y comprueba el Compose y
los volúmenes de la aplicación. El deploy habitual reutiliza los archivos generados.

El deploy carga `.env.staging` y luego `domains.env`. Por eso el dominio de la UI,
los enlaces de correo y WebAuthn se derivan del mismo archivo público que usan las
reglas de Traefik. Los archivos generados se reemplazan mediante rename para que
el watcher no lea contenido a medio escribir.

## Responsabilidades de los archivos

| Fuente | Responsabilidad |
|---|---|
| [static/traefik.staging.example.yaml](static/traefik.staging.example.yaml) | Entrypoints, file provider, confianza en Cloudflare y resolver ACME |
| [dynamic/staging/routers.yaml](dynamic/staging/routers.yaml) | Dominios, rutas, métodos, prioridades y uso del certificado wildcard |
| [dynamic/staging/services.yaml](dynamic/staging/services.yaml) | Destino UI y transportes HTTP |
| [dynamic/staging/middlewares-common.yaml](dynamic/staging/middlewares-common.yaml) | Headers y compresión |
| [dynamic/staging/middlewares-access.yaml](dynamic/staging/middlewares-access.yaml) | Origen Cloudflare, limpieza de headers directos y denegación de rutas privadas |
| [dynamic/staging/middlewares-limits.yaml](dynamic/staging/middlewares-limits.yaml) | Rate limiting, concurrencia y tamaño de escrituras |
| [dynamic/staging/middlewares-redirects.yaml](dynamic/staging/middlewares-redirects.yaml) | HTTPS y hostname canónico |

Los seis YAML generados comparten el namespace del file provider; los nombres de
archivo no establecen prioridades. Los anchors YAML quedan dentro de su documento.
Las rutas general/institucional usan prioridad 100, escrituras 200,
autenticación 300, rutas privadas 400 y `www` 500.

Los dos servicios llegan a `http://bemol-ui-staging:3000`. La ruta general conserva
el transporte predeterminado del despliegue anterior; las rutas específicas e
institucionales mantienen su transporte personalizado y `flushInterval: -1ms`.

## Archivos que monta el Compose

| Recurso del VPS | Dentro del contenedor | Acceso |
|---|---|---|
| `.deploy/traefik.staging.yaml` | `/etc/traefik/traefik.yaml` | Sólo lectura |
| `build/staging/traefik/dynamic/` | `/etc/traefik/dynamic/` | Sólo lectura |
| `/etc/bemol/secrets/cloudflare-dns-token` | `/run/secrets/cloudflare-dns-token` | Sólo lectura |
| `/var/lib/bemol/traefik/staging/` | `/var/lib/traefik/` | Lectura y escritura |

Preparar la estática local desde el ejemplo, con el contacto ACME real. `.deploy/`
está ignorado por Git. El Compose declara los mounts con `create_host_path: false`
para que los archivos y directorios se preparen explícitamente. Publica 80/443 y
debe iniciarse después de liberar esos puertos en el proxy anterior.

## Token DNS y certificados

El Compose pasa directamente esta variable al proceso de Traefik:

```dotenv
CF_DNS_API_TOKEN_FILE=/run/secrets/cloudflare-dns-token
```

Su entrada `volumes` hace visible el archivo privado del VPS en esa ruta. El token
no va en Git, en imágenes ni en el entorno de la aplicación. Mantener archivo 0600
y propietario que permita su lectura al proxy. La variable se declara en
`environment` del [Compose del proxy](../../compose.traefik.staging.yaml).

`dnsChallenge.provider: cloudflare` selecciona la integración de lego que conoce
los nombres `CF_DNS_API_TOKEN` y `CF_DNS_API_TOKEN_FILE`. El token necesita Zone:Read
y DNS:Edit sobre la zona DNS del dominio base. El resolver solicita
`${STAGING_DOMAIN}` y `*.${STAGING_DOMAIN}`. El estado ACME persistente contiene
certificados y claves privadas; conservarlo sin dos proxies escribiéndolo a la vez.

| Validación ACME | Requisito | Wildcard de Let's Encrypt |
|---|---|---|
| HTTP-01 | Desafío HTTP accesible por el puerto 80; no requiere token DNS | No |
| DNS-01 | TXT temporal, automatizado mediante las credenciales del proveedor DNS | Sí |

Certbot suele usar HTTP-01 con Nginx, Apache o webroot. Traefik puede realizar esa
validación y renovar por sí mismo. El wildcard institucional preparado mantiene
DNS-01: cada renovación necesita acceso válido al proveedor DNS. Sin él falla la
renovación; el certificado emitido conserva su validez hasta vencer.

Otro proveedor DNS requiere su valor `dnsChallenge.provider` y sus credenciales
específicas; ver [los proveedores de lego](https://go-acme.github.io/lego/dns/).
La credencial corresponde a quien administra los DNS, independientemente del VPS
o del registrador. Esta configuración conserva Cloudflare y sus políticas de
proxy; no cambia automáticamente al seleccionar otro servicio.
