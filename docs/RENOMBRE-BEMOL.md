# Cambio de nombre a Bemol

La aplicación se llama **Bemol**. Este cambio de código no despliega ni renombra
recursos remotos. Los checkouts y repositorios existentes siguen ubicados en
`boero-api`, `boero-ui` y `boero-infra`; no sustituir sus rutas por destinos inexistentes.

## Identificadores nuevos

- Backend: proyecto Gradle y `spring.application.name` `bemol-api`; paquete
  `ar.edu.utn.frvm.typeit.bemol_api`; entrada `BemolApiApplication`.
- Frontend: paquete `bemol-ui`; variable del servidor `BEMOL_API_URL`.
  Es el único nombre admitido; configurar esta variable antes de iniciar la UI.
  Compose compartido también entrega la variable nueva.
- Contenedores locales e imagen local del backend: prefijo `bemol-`.
  Los volúmenes y redes conservan su identidad anterior.
- Marca visible, invitaciones, documentación y nombre mostrado por WebAuthn:
  Bemol. Las configuraciones privadas existentes de `WEBAUTHN_RP_NAME` deben
  actualizarse a Bemol en cada entorno; no cambiar el RP ID ni los orígenes.

## Referencias anteriores conservadas por compatibilidad

No es seguro eliminar todas las coincidencias de `boero` mediante reemplazo:

| Referencia | Motivo |
| --- | --- |
| `Felipe Boero`, `Conservatorio Boero`, `cboero`, apellidos y logo institucional | Identidad de la institución/personas, no de la aplicación. El fallback genérico usa el icono de la aplicación, no el escudo institucional. |
| Migraciones, seeds históricos y funciones SQL `boero_*` con sus consumidores | Historial Flyway y funciones usadas por índices existentes. No se reescriben scripts aplicados ni se alteran datos. |
| Bases/usuarios PostgreSQL, volúmenes Docker, red compartida, prefijo S3 `boero/` | Cambiarlos sin migrar puede conectar a una base vacía o dejar adjuntos inaccesibles. |
| Claves Redis `boero:*` | Conservan intentos de login, autenticación reciente y ceremonias WebAuthn durante la transición. No vaciar Redis. |
| Repositorios GitHub, imágenes GHCR, rutas `/opt/boero-infra`, proyecto Dokploy y nombres Traefik | Son contratos con recursos externos ya configurados. Los workflows continúan publicando las imágenes existentes para no romper el despliegue. |
| Unidades systemd, lock y nombres/rutas de backups | Evitan dos planificadores simultáneos y conservan la retención de backups existentes. |

## Transición operativa pendiente

1. Inventariar el entorno real y obtener backups verificables de PostgreSQL y
   adjuntos; registrar imágenes inmutables y configuración actual para rollback.
2. Configurar `BEMOL_API_URL` en las variables privadas antes de publicar la UI
   y actualizar Compose. Para rollback, restaurar también la configuración
   correspondiente a la imagen anterior.
3. Para renombrar repositorios remotos, coordinar GitHub, remotes, integraciones,
   proveedor Git de Dokploy y checkouts operativos. Publicar/verificar imágenes
   `bemol-*` antes de cambiar referencias GHCR; conservar las antiguas para rollback.
4. Actualizar Traefik y Dokploy coordinadamente, preservando aliases anteriores
   mientras existan consumidores y manteniendo dominios, RP ID y secretos.
5. Conservar los nombres físicos persistentes. Si se exige renombrarlos también,
   realizar una migración separada con ventana, copia validada, permisos y rollback;
   nunca crear volúmenes vacíos, mover objetos S3 o renombrar bases a ciegas.
6. Verificar login/refresh, passkeys, invitaciones, búsqueda, adjuntos, backups y
   salud del entorno antes de retirar compatibilidad. No se ha realizado esa
   validación ni se ha desplegado este cambio.
