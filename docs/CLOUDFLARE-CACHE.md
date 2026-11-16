# Caché de imágenes en Cloudflare

Cloudflare cachea por defecto sólo archivos con extensión estática (`.js`, `.css`,
`.webp`, `.png`, …). Las imágenes optimizadas de Next (`/_next/image?url=…`) y los
logos de instituciones (`/api/public/institutions/<id>/logo?v=…`) no tienen
extensión, así que hoy cada visita las pide al VPS. Además, la caché interna de
Next vive en el contenedor y se pierde en cada deploy.

## Qué envía el origen

Los encabezados viven en `bemol-ui` (`next.config.ts` y
`fetch-institution-logo.service.ts`); Cloudflare sólo tiene que respetarlos.
`/_next/image` responde `public` con TTL de un día y los logos con `v`, de un año;
los logos sin `v` responden `no-store`. Nginx no modifica `Cache-Control` del upstream.

## Regla de caché

En Cloudflare, zona `bemol.com.ar` → **Caching → Cache Rules → Create rule**:

- Nombre: `Imágenes optimizadas y logos`
- Expresión (editor):

  ```txt
  (http.request.uri.path eq "/_next/image")
  or (starts_with(http.request.uri.path, "/api/public/institutions/")
      and ends_with(http.request.uri.path, "/logo"))
  ```

- Cache eligibility: **Eligible for cache**.
- Edge TTL: **Use cache-control header if present, bypass cache if not**.
- Browser TTL: **Respect origin TTL**.
- Cache key: dejar la query string completa (default); `url`, `w`, `q` y `v`
  forman parte de la clave.

La regla cubre staging y producción porque comparten zona; cada host tiene su
propia entrada en caché. La regla no filtra por `v`: los logos sin versión
responden `no-store` y Cloudflare no los guarda.

## Formatos

Cloudflare (planes no Enterprise) ignora `Vary: Accept`. Next sirve WebP a todos
los navegadores actuales, así que una sola variante en caché es correcta. No
habilitar `images.formats` con AVIF en `bemol-ui` sin revisar esta regla: un
navegador sin AVIF podría recibir la variante cacheada de otro.

## Reemplazar una imagen

- Logos: subir uno nuevo cambia `v`; no hace falta purgar.
- `public/images/*` o `public/brand/*` con el mismo nombre: el cambio aparece en
  hasta un día. Para verlo antes, purgar en **Caching → Configuration → Purge
  Cache** por URL (incluye las URLs `/_next/image?url=…`).

## Verificar

```sh
curl -sI 'https://bemol.com.ar/_next/image?url=%2Fimages%2Finstitutional-header.webp&w=1920&q=90' \
  | grep -i -e cf-cache-status -e cache-control
```

La primera respuesta muestra `cf-cache-status: MISS`; la siguiente, `HIT`.
Copiar la URL exacta desde la pestaña Network del navegador si el ancho no coincide.
