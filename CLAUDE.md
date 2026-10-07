# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# GaptoMobile 2027 — Agent Instructions

## Fuentes de verdad

Documentación funcional/técnica:
Google Drive / GaptoMobile 2027 / 00_CORE

Orden de consulta:
1. GaptoMobile_2027_Project_Memory.md
2. GaptoMobile_2027_Working_Method.md
3. GaptoMobile_2027_DB_Schema.md
4. GaptoMobile_2027_Migration_V3.md cuando proceda

Implementación:
GitHub / rama main.

Estado físico:
Neon y Supabase.

Antes de modificar implementación:
- consultar Drive;
- revisar main;
- contrastar PostgreSQL cuando proceda;
- no modificar silenciosamente decisiones cerradas.

Nunca incorporar al repositorio:
- secretos;
- .env;
- datos V3 reales;
- dumps de producción;
- credenciales.

Los códigos que aparecen en comentarios y nombres (D-xxx, F04-Dxxx, OP-xx, INV-xx, WM 12C.x, RV3-Pn) remiten a decisiones y apartados de los documentos de 00_CORE. El repositorio no los redefine.

## Comandos

Python 3.13, dependencias fijadas en `backend/requirements-api.txt` (FastAPI, psycopg 3, pytest). No hay `pytest.ini` ni `pyproject`: se lanza desde la raíz del repo.

Las suites que tocan PostgreSQL exigen `GAPTO_TEST_DATABASE_URL`, que debe apuntar a una base **desechable** con la cadena de migrations aplicada. Sin esa variable, la suite hace `pytest.fail` en lugar de conectarse a una base por defecto. No se apuntan a Neon ni a Supabase salvo mandato explícito.

```bash
# Suites (cada directorio tiene su propio conftest)
python -m pytest tests/database -q        # contrato físico de las migrations
python -m pytest tests/backend -q         # motor financiero (servicios OP-xx)
python -m pytest tests/api -q -p no:cacheprovider --rootdir=tests/api   # adaptador HTTP VS-01
python -m pytest tests/migration -q       # pipeline RV3 (corpus sintéticos)

# Un test concreto
python -m pytest tests/backend/test_101_op01_crear_hecho.py::nombre_test -q

# Tests sin base de datos
python -m pytest tests/migration/test_rv3_000_repo_sin_datos_v3.py -q
python -m pytest tests/database/test_044_envdev_head_autorizado.py -q
```

La batería de concurrencia (`tests/database/test_027_concurrencia.py`) usa `GAPTO_CONCURRENCY_URL` y hace COMMIT real. Se omite si la variable no está definida.

Mobile (Expo / React Native, en `mobile/`):

```bash
npm test                     # jest (preset jest-expo, __tests__/**/*.test.ts?(x))
npx jest __tests__/envio.test.ts
npm run typecheck            # tsc --noEmit
npx expo start --lan
```

El cliente lee `EXPO_PUBLIC_GAPTO_API_URL` y `EXPO_PUBLIC_GAPTO_DEV_TOKEN` de `mobile/.env`. Ese fichero no se versiona y lo regenera `envdev_arranque.ps1`.

Backend en local (solo desarrollo; `create_app()` falla cerrado si `GAPTO_ENV` no es `development` o si la base conectada no está en la allowlist):

```bash
cd backend
uvicorn app.api.app:create_app_desde_entorno --factory --host 127.0.0.1
# requiere GAPTO_ENV=development, GAPTO_DATABASE_URL, GAPTO_DEV_TOKEN, GAPTO_DEV_OWNER_USER_ID
```

- `scripts/dev/bootstrap_dev_db.py --admin-dsn "..." [--recrear]`: crea `gapto2027_dev` en PostgreSQL LOCAL (rechaza hosts remotos) con fixtures sintéticos. Aplica la cadena solo hasta `HEAD_AUTORIZADO_ENVDEV`. Para subir ese head hay que cambiar la constante **y** `tests/database/test_044_envdev_head_autorizado.py` en un cambio revisado: publicar una migration en main no la autoriza en ENV-DEV.
- `scripts/dev/envdev_arranque.ps1`: arranque diario de ENV-DEV en Windows (cluster PG en 5434 solo loopback, backend en 8027, Expo).
- `scripts/postgres/run_clean_room.py` (`GAPTO_CLEANROOM_URL`): reconstruye desde cero la cadena de migrations sobre una base virgen y compara el contrato físico (huellas D-111). Es el runner de certificación. Usar `--desde 0002` si los roles de instancia ya existen.

## Arquitectura

### Base de datos (`migrations/`)
- Cadena lineal numerada `NNNN_fXX_YY_descripcion.sql`, aplicada en orden. No se editan migrations ya publicadas: cada cambio es una migration nueva con su test `tests/database/test_NNN_*.py` asociado.
- Todo vive en el schema `gapto`. `0001` provisiona cinco roles de instancia: `gapto_owner`, `gapto_migrator`, `gapto_internal`, `gapto_runtime` y `gapto_backup`.
- Multi-tenant por RLS con **FORCE RLS** en todas las tablas de dominio. El tenant se fija con la GUC `gapto.owner_user_id`. Las migrations que alteran tablas levantan FORCE, aplican el cambio y lo restauran en la misma transacción, y el postcheck verifica el recuento de tablas con FORCE.
- Muchas invariantes están en la base: triggers, constraint triggers `DEFERRABLE INITIALLY DEFERRED` que validan en el COMMIT, `EXCLUDE` temporales y revocaciones de DELETE sobre la "realidad financiera". Por eso gran parte de la lógica no está en Python.
- Cada migration lleva una cabecera larga con el contrato, lo que *no* hace a propósito, y los prechecks y postchecks.

### Backend (`backend/app/`)
- `core/`: `UnidadDeTrabajo` (una transacción READ COMMITTED por operación, con `SET LOCAL ROLE gapto_runtime` y las GUC de tenant/actor/request fijadas dentro de la transacción, nunca de sesión; reintenta la transacción **completa**, COMMIT incluido, ante 40P01/40001). También contiene los modelos de dominio, la clasificación de errores y la recurrencia.
- `repositories/`: SQL puro con psycopg. El owner nunca se pasa como parámetro: se lee con `current_setting('gapto.owner_user_id')`. Los snapshots de idempotencia viajan como texto JSON y se comparan como `jsonb` en SQL, sin round-trip por floats de Python.
- `services/`: operaciones de dominio OP-01..OP-22 (hechos, efectos, tesorería, posiciones, reglas/previsiones, transferencias, devoluciones, suplementos, correcciones, participantes, compartidos, neto…). Las fronteras entre servicios son deliberadas y están documentadas en la cabecera de cada uno. Las colaboraciones se inyectan por constructor (ver `tests/backend/conftest.py`).
- `api/`: adaptador HTTP FastAPI del vertical slice VS-01. Es una API de integración, pendiente de consolidar en F10. La identidad es de **desarrollo**, con Bearer `GAPTO_DEV_TOKEN`, y no es autenticación de producción. Su única escritura es `POST /v1/intenciones/gasto-pagado` → OP-22, en una sola transacción del adaptador (`ejecucion_gasto_pagado.py`). `traductor_gasto_pagado.py` mapea la intención a la composición de OP-22 con UUIDs deterministas (uuid5).

### Mobile (`mobile/`)
Expo 57 / RN 0.86 / React 19. No usa librería de navegación hasta F11: `App.tsx` implementa la navegación mínima de VS-01. La lógica pura vive en `src/domain/` (importe, fechas, intención), el envío en `src/state/useEnvioGasto.ts`, el cliente HTTP en `src/api/` y los tokens del Design System en `src/theme/`. `__tests__/ds_conformidad.test.ts` vigila la conformidad con esos tokens.

### Migración V3 (`scripts/migration_v3/`, `tests/migration/`)
Pipeline RV3 por fases (P1 equivalencia, P2/P3 inventario, P5 transformación, P6 carga, P7 integridad, P8 reconciliación, P9 runtime, P12 laboratorio Neon). Los tests usan corpus **sintéticos**. `tests/migration/conftest.py` desactiva los catálogos anclados a claves V3 reales salvo en los módulos que declaran el flag correspondiente (`DOMINIO_5 = True`, etc.). Los datos reales viven fuera del repo (`GAPTO_RV3_DATA_DIR`); `data/migration_v3/` solo contiene `.gitkeep`, y `test_rv3_000` falla si aparece cualquier otra cosa.

### Pruebas de mutación (`scripts/mutantes/`, `scripts/dev/mutantes_vs01.py`)
Arneses que aplican mutantes de texto exacto sobre el código y exigen que la suite discriminante falle. Escriben un journal o marcador antes de mutar y restauran verificando el SHA-256. Si una ejecución anterior se interrumpió, restauran y abortan. Si se modifica una línea protegida por un mutante, hay que actualizar el texto del mutante en el arnés.

## Convenciones

- Código, identificadores, comentarios y mensajes en **español**. Los comentarios suelen ir sin tildes en Python y SQL.
- Cada fichero lleva una cabecera `GAPTO MOBILE 2027` con Fichero, Ruta, Descripción y un historial de `Version`. Al modificar un fichero, se sube la versión y se añade una línea con la fase o decisión que motiva el cambio.
- Los tests se numeran por bloques: `tests/database` 001–0xx, `tests/backend` 100–14x, `tests/api` 150+, `tests/migration` rv3_000+.
- Los tests del motor se ejecutan como `gapto_runtime` con RLS activo y no como superusuario, para no dar falsos verdes. Los fixtures crean datos bajo `SET ROLE gapto_owner` con la GUC de tenant ya fijada.

## Método de trabajo (transición a Claude Code, pendiente de D-2xx)

### Rutas
Las rutas de esta máquina están en `CLAUDE.local.md` (no versionado). Si no existe, pide las rutas a Moisés antes de ejecutar un mandato que dependa de ellas.

- Repositorio: clon de origin/main. `core.autocrlf=false`; se respetan los finales de línea existentes en cada fichero.
- Documentos canónicos (carpeta Drive sincronizada `00_CORE`: Project_Memory, Working_Method, DB_Schema, Migration_V3, y expedientes de fase en la misma carpeta raíz; mockups validados en `01_Mockups_Validados`): solo lectura salvo mandato documental D-200.
- Evidencias: fuera del repositorio, en una carpeta por bloque (`evidencia_<bloque>\<nombre>_<yyyyMMdd-HHmmss>\`), siempre con `manifest_sha256.txt`. La salida de la terminal no es evidencia.
- ENV-DEV (cluster 5434, solo loopback): no se toca sin mandato; contiene credenciales.
- Copia antigua `_zip` del repositorio: respaldo temporal, no se usa.
- Canal de mandatos y handoffs: fuera del repositorio (ver `CLAUDE.local.md`).

### Roles y límites
- Moisés decide; la IA revisora es obligatoria para decisiones críticas y cierres de fase; Claude Code ejecuta mandatos.
- Claude Code no cierra fases, no declara veredictos definitivos, no modifica documentos canónicos ni sube nada a origin/main sin que el mandato lo diga y Moisés lo apruebe en la sesión.
- Cada sesión atiende un mandato. Primera línea del mandato = nombre del bloque (patrón `FASE — BLOQUE · Objeto (vX.Y)`).
- Al terminar un mandato: handoff con tabla de ficheros tocados y SHA-256 completos, resumen de evidencia (rutas), riesgos nuevos, propuesta de veredicto para la revisora en formato de copiar y pegar; después detenerse.

### STOP obligatorio (parar y preguntar antes de seguir)
- A: una realidad válida no es representable con el head físico vigente.
- B: la solución exige cambio físico del contrato PostgreSQL (DDL, migration nueva).
- C: dos decisiones canónicas vigentes se contradicen.
- D: hay que crear o modificar una garantía de seguridad, concurrencia, atomicidad o histórico.
- E: un comando afecta a Neon, Supabase, ENV-DEV, Drive u origin/main y el mandato no lo cubre expresamente.

### Prohibiciones
- Migrations publicadas (0001..0340) inmutables; ningún DDL sin mandato que lo autorice.
- Supabase permanece en 0310 (D-179): no aplicar 0320+ ni crear ramas, proyectos o clean-rooms en Supabase. `gappto-staging` (Neon y Supabase) no se toca.
- `gapto2027_cleanroom` de Neon: nunca se limpia con DELETE privilegiados ni desactivando guards/RLS; se recrea virgen (autorizado de forma permanente por Moisés) y queda marcada CONSUMIDA tras usarse.
- Tests que persisten filas: solo en clean-room o desechables, nunca contra bases de referencia.
- `HEAD_AUTORIZADO_ENVDEV` y `test_044` solo cambian en un cambio revisado.
- Nada de datos V3 reales, dumps ni credenciales en el repo. `decisiones_s20.json` nunca entra en Git.
- Ni `git push --force`, ni reescritura de historia, ni commits en ramas distintas de la que indique el mandato.

### Evidencia de proveedor
- La réplica local o ENV-DEV no certifican proveedor (Working Method 12C.3). La certificación de un bloque exige evidencia Neon sobre clean-room virgen: replay 0002..0340 y suites verdes, con manifest.
- Antes de ejecutar evidencia Neon: comprobar que la clean-room está virgen; si un lanzamiento se corta, la evidencia se descarta y se repite sobre clean-room recreada.

### Git
- Un mandato = un commit (o los que el mandato indique), mensaje con el identificador del bloque. Antes del commit se muestra `git diff --stat` y se espera aprobación.
- `git push` solo con aprobación explícita en la sesión. Tras el push: `git fetch` y comprobar que `origin/main` coincide con HEAD local.

### Idioma y estilo
- Español en código, comentarios, mensajes de commit y handoffs. Ejecución concisa, sin narración; resúmenes de comandos, no logs completos.

### Comandos y permisos
- Los comandos de solo lectura (git status/diff/log, Get-ChildItem, Get-Content, Get-FileHash, pytest, python --version) se lanzan como comandos simples y separados, no encadenados con `;` ni `|`, para que Moisés pueda aprobarlos de forma permanente.
- Los comandos que tocan Neon, Supabase, ENV-DEV, la carpeta de Drive o `origin/main` se lanzan siempre de uno en uno y se anuncian antes con lo que van a hacer.

### Plan y tiempos de espera
- Al recibir un mandato, antes de ejecutar nada, devolver un plan numerado con los pasos y una estimación de duración por paso (rango en minutos) y el total. Marcar qué pasos requieren aprobación de Moisés y cuáles son de larga duración (más de 5 min).
- Las estimaciones se basan en referencias del propio proyecto cuando existan (por ejemplo, duración de replays 0002..0340 y suites en evidencias anteriores); si no hay referencia, decirlo y estimar con rango amplio. Nunca dar una cifra exacta que no se pueda justificar.
- Durante la ejecución, al empezar cada paso indicar "Paso N/M — inicio hh:mm — estimado X min", y al terminarlo la duración real. Así Moisés sabe si puede ausentarse y cuánto.
- En pasos de larga duración, si el comando lo permite, mostrar progreso periódico; si no lo permite, decir antes de lanzarlo que no habrá salida hasta el final.
- En el handoff final, incluir una tabla paso / estimado / real, para que las estimaciones mejoren en bloques siguientes.
