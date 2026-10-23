# Acceso institucional: contrato de aceptación local

Este contrato corresponde a la verificación automatizada **local**. Ejecutar el
harness no modifica DNS público ni ambientes compartidos, y no autoriza por sí
solo despliegues remotos, cambios de producción, commits ni pushes.

## Decisiones

- El único ambiente compartido configurado es `staging`, operado por SSH y Compose;
  desarrollo local sigue perteneciendo a los repositorios de aplicación. No se
  configura un ambiente QA/testing ni producción.
- `publicSubdomain` opcional e independiente de `slug`, administrado por plataforma.
- Logos PNG/JPEG, máximo 2 MiB, administrados por plataforma o por una institución
  con `INSTITUTION_UPDATE`; almacenamiento y autorizaciones existentes se conservan.
- Accesos generales conservan selector. Los institucionales fijan contexto, nombre
  y logo. El contrato actual reconoce `cboero.staging.bemol.com.ar`. En staging se
  prepara con wildcard DNS-only y TLS wildcard en Traefik, sin Cloudflare; la
  verificación operativa queda pendiente. `cboero.bemol.com.ar` corresponde a una
  activación futura de producción. `cboero.testing.bemol.com.ar` queda únicamente
  como hostname sintético de los fixtures locales. Este contrato no acredita acceso
  público a esos hostnames.

## Requisitos obligatorios

Cada caso debe tener evidencia vigente de ejecución. Implementado no significa
verificado. Los IDs se mantienen en el manifiesto de aceptación; una prueba omitida,
fallida, sin ejecutar o perteneciente a otro estado del código impide el cierre.

| ID | Criterio |
| --- | --- |
| Q01 | Las configuraciones persistentes y los stacks descartables de aceptación conservan aislamiento de redes, volúmenes y secretos. |
| Q02 | El harness local usa perfil `prod`, PostgreSQL/Flyway y healthchecks; no usa H2 ni create-drop. |
| Q03 | El backup conserva selección segura, validación del dump, permisos, retención y restauración sobre datos descartables. |
| Q04 | El entrypoint de deploy usa lock compartido, valida recursos y backup, y falla ante errores de pull o de salud sin restauración automática. |
| C01 | Develop/main y PRs ejecutan CI sin publicar; sólo staging publica y solicita deploy tras CI del mismo commit. |
| I01 | Nombre público opcional, independiente, DNS-safe y reservado con unicidad PostgreSQL. |
| I02 | Resolver público mínimo; nombres desconocidos/inactivos son 404, indisponibilidad es 503. |
| A01 | Acceso general conserva selector y flujos; autenticación de plataforma se mantiene. |
| A02 | Acceso institucional sin selector, con identidad visible en escritorio/móvil y sin logo. |
| A03 | Formularios, JWT, loginAttempt y cabeceras no permiten cruzar instituciones. |
| A04 | Registro y login de llaves funcionan en accesos general/institucional y rechazan otros orígenes. |
| A05 | Refresh conserva rotación, deduplicación, propagación de cookies y fallos transitorios. |
| A06 | Registro, confirmación y recuperación usan tokens/URLs correctos, sin hosts hardcodeados. |
| L01 | Plataforma carga, reemplaza y elimina logos. |
| L02 | Institución hace lo mismo sólo con permiso y sobre su institución. |
| L03 | Validación de bytes, reemplazo seguro, actualización inmediata y fallback sin logo. |
| S01 | Se conservan migraciones anteriores, HEAD/index, trabajo ajeno, entorno privado y recursos existentes. |
| D01 | Ejemplos y runbook completos, separando activación pública de cierre local. |
| V01 | El verificador rechaza casos faltantes, omitidos, fallidos y evidencia desactualizada. |

## Ejecución y cierre

Desde `bemol-infra`: `make verify-institutional-access`. Los defaults buscan los
repositorios hermanos `bemol-api` y `bemol-ui`; ubicaciones distintas se indican
con `API_REPO` y `UI_REPO`. Para checkouts aún no movidos, usar las rutas reales
explícitas según [RENOMBRE-BEMOL.md](RENOMBRE-BEMOL.md), no renombrar directorios
desde el harness. El comando no lee secretos de ambientes
existentes ni reutiliza sus bases/volúmenes; sus recursos usan un namespace de aceptación.

La evidencia se escribe en `build/verification/institutional-access/`, ignorada por
Git. Debe contener estado por caso/ID, comandos, resultados, capturas y huella de los
repositorios. Nunca incluir contraseñas, JWT, refresh tokens, cookies ni archivos privados.

Estados permitidos: **pendiente**, **implementado**, **verificado**, **bloqueado**.
Sólo se puede comunicar «implementación completa y verificada localmente; no
desplegada» cuando todos los casos obligatorios pasan y la auditoría final vincula
cada requisito con su código, prueba y evidencia. Un bloqueo no cuenta como éxito.

## Separación respecto a los ambientes compartidos

Este harness no configura DNS, secretos de Actions ni despliegues de ambientes.
Staging se opera mediante [SSH y Compose](STAGING.md). Cambiar
configuración compartida, datos persistentes o incorporar otro ambiente requiere
autorización separada.

## Qué ejecuta el verificador

Requisitos locales: Docker en el contexto `default` con socket Unix local,
Compose compatible con `!override` (2.24.4 o posterior), OpenSSL, Python 3,
Java 21/Gradle del proyecto y pnpm/dependencias instaladas en la UI.

1. Ejecuta las pruebas negativas del propio verificador y las pruebas dirigidas
   de configuración/backups/workflows. Estas últimas simulan dependencias externas;
   **no** prueban un despliegue remoto.
2. Reejecuta los filtros de API registrados en `scripts/verification/api-tests.json`
   con PostgreSQL/Flyway/Redis reales para las pruebas de integración y los
   controles de compilación/formato y `staticAnalysis` (NullAway/ECJ main/test,
   sin ejecutar más suites). Ejecuta las suites UI registradas en
   `ui-tests.json`, TypeScript y lint/formato sólo de los archivos cambiados.
3. Construye imágenes `prod` de la API/UI actuales y crea **dos stacks descartables**
   propios, con TLS autofirmado y resolución de hosts únicamente dentro de Chromium.
   Las claves `qa`/`staging` y el dominio `testing.bemol.com.ar` se conservan
   únicamente como fixtures históricos consumidos por pruebas, no como ambientes
   desplegables. Ambos stacks usan el perfil `prod`, correo capturado y secretos
   sintéticos sin semillas implícitas. No son los ambientes compartidos existentes. Las identidades sintéticas
   de preparación se confirman sólo en estas bases; la prueba de registro confirma
   por separado un usuario nuevo mediante correo realmente capturado.
4. Ejecuta la batería Playwright sin mocks: flujos Chromium (correo, logos, permisos,
   refresh y llave virtual WebAuthn) y los dos rechazos directos HTTP de loginAttempt/JWT
   separados como `http-runtime`, no como evidencia visual. Después comprueba aislamiento, reinicio, Flyway y
   backup/restore en otra base **nueva**, nunca sobre una base existente.
5. Elimina sólo recursos identificados por namespace, propietario e IDs completos
   de esa ejecución. Compara HEAD/index, entorno privado, migraciones previas y
   recursos Docker preexistentes. Finalmente exige evidencia vigente para los 19 IDs.

Cada ejecución guarda sus reportes normalizados en `runs/<run-id>/`. Los mapas
registran nombres reales de pruebas: si una prueba se renombra, desaparece, se
omite o falla, el requisito queda incompleto. El manifiesto exige el tipo de prueba
necesario (unitaria, PostgreSQL, navegador o runtime), no permite reemplazar una
prueba real por un mock y verifica también la integridad de reportes y capturas
referenciados por el índice. `--audit-only` audita la evidencia existente sin ejecutar
pruebas; modificar cualquier fuente, borrar o alterar un reporte/captura invalida
ese cierre.

Las credenciales, correo completo, cookies y logs crudos permanecen en directorios
privados temporales, fuera de la evidencia. No se generan trazas de red. Si Docker
impide el cleanup, el comando falla y conserva el archivo de ownership privado
`/tmp/bemol-acceptance-state-<run-id>.json`; se puede repetir el cleanup seguro con:

```sh
python3 scripts/verification/runtime.py stop --state /tmp/bemol-acceptance-state-<run-id>.json
```

No usar `docker system prune`, `compose down -v` sobre proyectos compartidos ni
borrar recursos manualmente para hacer pasar el gate. Las imágenes locales de
aceptación quedan disponibles (no se eliminan imágenes ajenas). Opcionalmente
`ACCEPTANCE_API_IMAGE`/`ACCEPTANCE_UI_IMAGE` reutilizan una imagen local sólo si sus
etiquetas identifican la app y la huella exacta del árbol actual; una imagen antigua
se rechaza. El comando no publica imágenes ni se conecta por SSH.

## Disponibilidad actual y cambio de alcance

El cambio a SSH y Compose no elimina las pruebas institucionales ni el verificador
de evidencia. Q03 mantiene el contrato de seguridad del backup; Q04 requiere
evidencia vigente del entrypoint nuevo y de los workflows que lo invocan. Las
pruebas o reportes anteriores de peticiones HTTPS a Dokploy no acreditan ese
contrato. Los overlays de producción siguen fuera del alcance. Cambiar estos
contratos invalida evidencia anterior; no se ejecutó ni amplió la batería con esta
actualización de despliegue.

El runtime local genera sus overlays y Mailpit sin depender de archivos de ambiente.
Para backup, comprueba ownership y pasa explícitamente su volumen PostgreSQL
sintético al helper, sin utilizar el volumen predeterminado de staging. El Nginx
que genera el harness es sólo un proxy TLS descartable para las pruebas del
contrato de aplicación; no configura ni verifica el Traefik operativo.

Conservar el driver no prueba que toda la batería sea ejecutable: en los checkouts
actuales de UI no está presente la batería Playwright ni el script `test:acceptance`
que consume el runner. Si falta algún consumidor registrado, el cierre debe quedar
bloqueado; no sustituirlo por evidencia vieja ni ejecutar esta batería por iniciativa.
La limpieza de configuración no incluye levantar estos stacks o validar su runtime.
