# Producción: configuración y operación

Producción comparte el VPS con staging. Cada entorno tiene su propio proyecto
Compose, volúmenes, red, puertos, archivo `.env`, lock y PostgreSQL/Redis; ninguno
comparte datos con el otro. La operación es la de [STAGING.md](STAGING.md) cambiando
el entorno; aquí sólo se listan las diferencias.

## Una sola rama

`bemol-infra` usa únicamente `main`. Un solo checkout en `/opt/bemol-infra` sirve
a ambos entornos; `ENV` y el archivo `.env.<entorno>` seleccionan cuál se opera.
Un cambio en `main` llega a los dos entornos en su próximo deploy: aplicarlo
primero en staging (`make deploy`) y después en producción.

## Aislamiento en el VPS

| Recurso | Staging | Producción |
|---|---|---|
| Proyecto Compose | `bemol-staging` | `bemol-production` |
| Compose | `compose.staging.yaml` | `compose.production.yaml` |
| Archivo privado | `.env.staging` | `.env.production` |
| Volúmenes | `bemol-*-staging` | `bemol-*-production` |
| Red | `bemol-network-staging` | `bemol-network-production` |
| Puertos UI / API (`127.0.0.1`) | `3000` / `8080` | `3100` / `8180` |
| Lock | `/tmp/bemol-infra-staging.lock` | `/tmp/bemol-infra-production.lock` |
| Pantalla temporal | `.deploy/maintenance/staging/` | `.deploy/maintenance/production/` |
| Perfil | `SPRING_PROFILES_ACTIVE=staging` | `SPRING_PROFILES_ACTIVE=prod`, `DEPLOYMENT_ENV=production` |
| Certificado | `bemol-staging` | `bemol-production` |
| Backups | `/var/backups/bemol/staging` | `/var/backups/bemol/production` |

El perfil `prod` no carga `db/dev`: la base de producción arranca vacía, sólo con
las migraciones. No copiar datos de staging. Auto-login no existe en producción:
la API no registra su controlador con `prod` y la UI lo deshabilita.

## Recursos

El VPS tiene 2 vCPU y 3,7 GiB de RAM. Los límites de las plantillas suman unos
3,6 GiB: producción 2,1 GiB (UI 512m, API 1024m con heap al 60 %, PostgreSQL 512m, Redis 128m) y
staging 1,4 GiB (UI 384m, API 768m con heap al 50 %, PostgreSQL 256m, Redis 64m).
Son techos, no reservas, pero sin swap un pico simultáneo puede activar el OOM
killer del host. Mantener staging por debajo de producción. El VPS tiene 2 GiB de
swap en `/swapfile` y `vm.swappiness=10` en `/etc/sysctl.d/99-bemol-swappiness.conf`.

## Comandos

`make` usa `ENV=staging` por defecto; producción siempre requiere indicarlo:

```sh
cd /opt/bemol-infra
make deploy ENV=production
make backup-db ENV=production
make platform-passkey-setup ENV=production ACCOUNT_ID=UUID_DE_LA_CUENTA
```

Por SSH desde GitHub Actions, la clave de producción debe forzar
`cd /opt/bemol-infra && exec bash scripts/deploy-production.sh` y ser distinta de
la de staging; cada una sólo puede desplegar su entorno.

## Primera instalación

1. Crear `.env.production` desde `.env.production.example`, `chmod 600`. Generar
   secretos nuevos (`JWT_SECRET`, `REFRESH_REPLAY_ENCRYPTION_KEY`, `DB_PASSWORD`);
   no reutilizar los de staging. Bucket S3 y credenciales propios.
2. DNS en Cloudflare: `bemol.com.ar` y `www` proxied; `*.bemol.com.ar` DNS-only
   hacia el VPS (incluye `admin`). Sin AAAA mientras no haya IPv6 operativo.
3. Emitir el certificado:

   ```sh
   sudo certbot certonly --dns-cloudflare \
     --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
     --cert-name bemol-production \
     -d bemol.com.ar -d '*.bemol.com.ar'
   ```

4. Desplegar staging con este checkout (`make deploy`) para que exista
   `.deploy/maintenance/staging/`, y producción con `make deploy ENV=production`.
5. Instalar Nginx según [NGINX-STAGING.md](NGINX-STAGING.md): `00-bemol-common.conf`,
   ambos sitios y `application.conf` juntos; `nginx -t` antes de recargar.
6. Alta del administrador de plataforma y su passkey en `https://admin.bemol.com.ar`.
7. Backup manual, prueba de restauración y copia fuera del VPS antes de abrir.
