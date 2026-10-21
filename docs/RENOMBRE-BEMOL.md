# Renombre integral a Bemol: corte operativo pendiente

El producto se llama **Bemol**, incluidos sus identificadores técnicos. Los nombres
anteriores no son una compatibilidad permanente. Este cambio prepara código,
configuración y documentación; **no renombra recursos remotos, no despliega, no
copia datos y no modifica credenciales privadas**. El usuario confirmó que ya
renombró los repositorios remotos a `bemol-api`, `bemol-ui` y `bemol-infra`.

## Alcance y excepciones

- Aplicaciones/proyectos/imágenes: `bemol-api`, `bemol-ui`, `bemol-infra`;
  GHCR `ghcr.io/typeitorg/bemol-api` y `ghcr.io/typeitorg/bemol-ui`.
- Backend: `ar.edu.utn.frvm.typeit.bemol_api`, `BemolApiApplication`, funciones
  SQL activas `bemol_*`, claves de aplicación Redis `bemol:*`, prefijo S3 `bemol/`.
- UI: paquete `bemol-ui`, variable de servidor `BEMOL_API_URL`, marca Bemol.
- Staging: los cinco volúmenes externos y la red de la tabla siguiente,
  alias `bemol-ui-staging`, routers/servicios/middlewares Traefik `bemol-*`.
- Backups: `bemol-backup@staging.timer`/`.service`, lock
  `/tmp/bemol-infra-staging.lock`, destino `/var/backups/bemol/staging`, dumps
  `bemol-staging-<UTC>.dump`; checkout operativo objetivo `/opt/bemol-infra`.
- Se preservan **Felipe Boero**, `Conservatorio Boero`, `cboero`, apellidos y
  escudo institucional: son la institución/personas, no el producto.
- No se reescriben migraciones Flyway aplicadas, registros de negocio,
  evidencias históricas ni backups. Las correcciones de funciones/índices van en
  una migración adicional; el historial conserva nombres y checksums originales.

Los checkouts locales actuales siguen siendo `boero-api`, `boero-ui` y
`boero-infra`; no se movieron cwd, worktrees ni directorios del sandbox. Los
defaults del tooling ya buscan los nombres canónicos `bemol-api` y `bemol-ui`.
Mientras estos checkouts conserven su ubicación anterior, indicar explícitamente
sus rutas reales al ejecutar una verificación autorizada:

```sh
API_REPO=/home/matias/Workspace/Repositories/TypeIt/boero-api \
UI_REPO=/home/matias/Workspace/Repositories/TypeIt/boero-ui \
make verify-institutional-access
```

Ese override es transitorio, no un default compatible permanente. Si se mueven los
checkouts en una operación posterior, actualizar worktrees, integraciones y rutas
del host antes de retirar el override; no apuntar a directorios inexistentes.

## Identidades persistentes objetivo

| Anterior, sólo para inventario/transición | Destino |
| --- | --- |
| `boero-api-postgres-data-staging` | `bemol-api-postgres-data-staging` |
| `boero-api-redis-data-staging` | `bemol-api-redis-data-staging` |
| `boero-api-enrollment-storage-staging` | `bemol-api-enrollment-storage-staging` |
| `boero-api-logs-staging` | `bemol-api-logs-staging` |
| `boero-ui-next-cache-staging` | `bemol-ui-next-cache-staging` |
| `boero-network-staging` | `bemol-network-staging` |
| Base/rol `boero` (verificar nombres efectivos) | Base/rol `bemol` |
| Prefijo S3 `boero/` / claves Redis `boero:*` | `bemol/` / `bemol:*` |
| `/opt/boero-infra`, `/var/backups/boero/staging` | `/opt/bemol-infra`, `/var/backups/bemol/staging` |

Compose exige volúmenes y red **externos**: si faltan los destinos, debe fallar;
no crearlos vacíos como sustitutos de datos que deban conservarse. Staging configura
`DB_REQUIRE_EXISTING=true`: el wrapper PostgreSQL rechaza una base ausente en vez
de crearla. Actualizar también su **File Mount** en Dokploy antes del corte; un
push no reemplaza ese archivo gestionado. Los fixtures locales descartables sí
pueden crear su base; no usan las identidades persistentes de staging.

## Recreación de recursos de prueba confirmados

El usuario autoriza descartar los datasets de prueba y regenerarlos con seeders.
Para recursos **individualmente confirmados como pruebas descartables**, no hace
falta respaldar ni migrar esos datos: el camino mínimo es recrearlos con nombres
Bemol y volver a sembrarlos. Esto no declara descartables todos los entornos ni
autoriza producción, borrados globales, publicaciones Git o cambios de política.

1. Identificar host/contexto y lista exacta de contenedores, volúmenes, red y base
   del producto; excluir otras aplicaciones y los servicios/metadatos de Dokploy.
   Confirmar que se acepta perder adjuntos, sesiones y datos de esos recursos.
2. Detener sólo el stack de prueba confirmado y, si corresponde, su timer anterior.
   Retirar únicamente sus recursos inventariados; nunca usar prune ni limpiar
   volúmenes ajenos. No respaldar datasets descartables por rutina.
3. Crear explícitamente los nuevos recursos externos y la base/rol de prueba.
   Staging conserva `DB_REQUIRE_EXISTING=true`: una primera inicialización requiere
   aprovisionar la base Bemol antes del arranque normal, no desactivar la protección
   a ciegas. Conservar las claves JWT/refresh, credenciales y dominios que no se
   estén renombrando; regenerar datos no exige regenerar secretos.
4. Usar imágenes/configuración Bemol compatibles y seeders del entorno indicado.
   En remoto, respetar la entrega autorizada Actions/GHCR → Dokploy: disponer de
   acceso SSH no autoriza publicar cambios ni saltar ese flujo. Coordinar alias,
   archivo Traefik y referencias Domains si se aplica el renombre remoto.
5. Comprobar identidad del nuevo destino, salud y datos sembrados, y retirar los
   consumidores anteriores sólo de ese entorno. La recreación local no acredita
   que staging haya cambiado ni que un deploy remoto esté autorizado.

En esta vía no hay rollback de datos descartados: ante una falla se corrige el
arranque y se recrea/repite el seed autorizado. Los secretos, configuración y
recursos ajenos no forman parte del descarte. Si aparece cualquier dato que no sea
descartable, detener esa eliminación y aplicar la vía de persistencia siguiente.

## Secuencia para datos no descartables, sin ejecución automática

1. **Inventario y aprobación de ventana.** Verificar host/contexto Docker real,
   `composeId`/`appName`, proveedor Git, manifests SHA, mounts, redes, DB/roles,
   Redis, storage activo/journal y timer/backup existentes. Registrar configuración
   privada de forma recuperable y redactada. No confundir este YAML con el estado
   vivo ni asumir que un bucket/rol se llama como el ejemplo.
2. **Respaldo verificable.** Guardar dump PostgreSQL con restauración aislada,
   copia recuperable de adjuntos/S3, persistencia Redis y configuración/permisos.
   Mantener copia fuera del host. Registrar conteos/checksums, versiones/destinos
   y respaldo de Flyway. Un `pg_restore --list` no prueba restauración completa.
3. **Entrega coordinada.** Los repositorios GitHub ya fueron renombrados por el
   usuario; comprobar remotes, enlaces, permisos GHCR/Actions, integraciones y
   actualizar el proveedor Git de Dokploy. Publicar y verificar manifests `bemol-*`
   antes de seleccionarlos; conservar imágenes anteriores inmutables para rollback.
   Fijar ambos SHA compatibles. No publicar contra infraestructura a medio migrar.
4. **Pausar escrituras.** Detener productores/consumidores de API/UI y acordar la
   indisponibilidad. Detener y deshabilitar el timer anterior y esperar su servicio
   terminado antes de cambiar lock/ruta/unidades: no permitir dos planificadores.
5. **Migrar recursos, nunca sustituirlos por vacíos.** Copiar los volúmenes con los
   servicios detenidos, conservando UID/GID/permisos y verificando contenido.
   PostgreSQL/Redis requieren copia consistente, no un `cp` en caliente; jamás
   arrancar dos PostgreSQL sobre el mismo directorio. Crear/verificar la nueva red.
   Renombrar/restaurar DB y rol preservando ownership, grants, extensiones y datos;
   actualizar `DB_NAME`/`DB_USER` privados sólo después de verificarlo. Conservar
   contraseña y claves de autenticación, sin imprimirlas ni reinicializarlas.
6. **Migrar namespaces de estado.** Redis necesita mover las claves al prefijo
   nuevo sin perder tipo, valor ni TTL, incluidos intentos de login, ceremonias
   WebAuthn, autenticación reciente y cualquier clave afectada inventariada. No usar
   `FLUSHDB`/`FLUSHALL` ni borrar revocaciones. Resolver colisiones bajo ventana.
   Si S3 está activo, copiar objetos al prefijo nuevo conservando cada sufijo de
   key relativo: la API resuelve `prefijo + key`. Validar conteos/checksums y permisos
   IAM. Inventariar destinos y trabajos pendientes del journal: pueden conservar
   el destino anterior y **no se actualizan automáticamente** al cambiar la variable.
   Resolverlos con un plan específico; no asumir que copiar objetos migra el journal.
   No retirar ni borrar el prefijo origen durante la ventana de rollback.
7. **Cambiar la configuración como una unidad.** Seleccionar recursos y DB/rol
   ya migrados, imágenes Bemol, `BEMOL_API_URL`, `STORAGE_S3_PREFIX` y configuración
   privada de WebAuthn RP name Bemol. **Mantener RP ID, orígenes, dominios, JWT y
   claves de refresh:** no hay necesidad de romper credenciales por la marca.
   Coordinar alias UI, archivo dinámico Traefik y los cinco middlewares `@file` de
   Domains; no dejar routers apuntando al alias anterior ni reglas sin protección.
   Renombrar `appName` técnico de Dokploy con plan específico del recurso real,
   sin inventar un sufijo ni recrear servicios a ciegas; conservar `composeId` si
   la operación lo permite, o actualizar sus consumidores si cambia.
8. **Backup nuevo y validación del corte.** Copiar los respaldos históricos sin
   alterarlos, instalar las unidades Bemol y verificar un backup/restore dirigido
   al volumen nuevo antes de habilitar el único timer. La nueva retención sólo
   procesa `bemol-*.dump`; los archivos antiguos requieren conservación/retiro
   explícitos según política, no se borran automáticamente. Desplegar por Dokploy,
   comprobar salud e identidades efectivas; verificar datos, login/refresh/passkeys,
   invitaciones, búsqueda, adjuntos y backups antes de abrir escrituras.
9. **Retirar el origen sólo con aceptación.** Conservar recursos anteriores sin
   escrituras durante la ventana de rollback. Tras aceptación y respaldo externo,
   retirarlos en una operación destructiva separada, inventariada y aprobada.
   No usar prune, `down -v` ni Fresh Volumes. Limpiar aliases/consumidores de
   transición cuando dejen de existir, no mantenerlos como contrato permanente.

## Rollback de datos no descartables

Antes de abrir escrituras nuevas, restaurar coordinadamente imágenes inmutables,
configuración anterior, File Mount, alias/reglas del proxy, DB/rol/destinos de
storage/Redis y el único planificador de backup correspondiente. Una migración
Flyway aplicada no se revierte al cambiar de imagen: verificar compatibilidad o
usar la restauración aislada acordada, nunca alterar historia/checksums.

En particular, `20261021223422__rename_search_functions_to_bemol.sql` ejecuta tres
`ALTER FUNCTION ... RENAME TO`: desaparecen los nombres anteriores de
`boero_normalize_text(text)`, `boero_search_vector(text)` y
`boero_search_rank(text, text, text)`. La imagen anterior sigue llamándolos, por lo
que **volver sólo a esa imagen no basta**. Antes de arrancarla, durante la ventana
y con escritores detenidos, acordar la reversión de esos tres nombres sobre las
firmas exactas (`bemol_*` → `boero_*`) o la restauración consistente prevista.
No editar ni borrar la migración aplicada, su checksum ni la historia Flyway;
planificar también la posterior recuperación de los nombres Bemol antes de
reimplantar la imagen nueva.

Después de reabrir escrituras, los recursos origen ya pueden estar desactualizados.
Detener el tráfico y preservar/capturar datos nuevos antes de decidir rollback;
no restaurar backups ni volver a volúmenes viejos por iniciativa porque se
perderían escrituras posteriores al corte.

## Evidencia y límites de esta entrega

Este repositorio no ejecuta automáticamente las secuencias anteriores, tests,
backups ni despliegues. Las operaciones locales autorizadas se informan por
separado y no son evidencia de recreación remota ni de autorización productiva.
La sintaxis y el render de Compose no prueban la migración ni la existencia de
imágenes/destinos remotos. El cambio no está listo para un deploy automático sobre
el entorno previo sin completar los pasos operativos anteriores.

El harness sólo admite namespaces/labels/archivos de estado `bemol-acceptance-*`.
Se retiró la compatibilidad anterior tras verificar que no había estados ni
recursos locales de aceptación pendientes de cleanup. No se modifican evidencias
históricas ni se amplía la limpieza a recursos ajenos.
