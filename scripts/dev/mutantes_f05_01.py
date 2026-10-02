# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_01.py
# Ruta: scripts/dev/mutantes_f05_01.py
# Descripcion: Arnes de mutacion de F05-01 backend (S1 guarda, S2 inventario,
#   S3 lecturas). Demuestra que tests/api/test_152..154 discriminan los
#   mecanismos que afirman (WM 12C.2). Cumple D-181/D-192:
#     - cada mutante declara su transformacion (lista de sustituciones de
#       texto exacto, cada una con UNA ocurrencia) y su discriminante (tests);
#     - E/S byte a byte; journal durable ANTES de tocar el primer byte, con
#       todos los ficheros que el mutante va a modificar;
#     - al arrancar, si hay journal pendiente: restaura, verifica y aborta;
#     - preflight verde de los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y verifica identidad byte-exacta;
#     - un veredicto unico por mutante: MUERTO | VIVO | NO_CLASIFICABLE.
#   Mutantes equivalentes documentados (no cuentan en el gate, WM 12C.5):
#     E01 sin comprobacion explicita de owner en la guarda: bajo gapto_runtime
#         la RLS ya oculta la fila ajena; es defensa en profundidad.
#   Requiere GAPTO_TEST_DATABASE_URL (base local desechable 0001..0340).
#   No es evidencia de proveedor.
#
#   v0.2.0 (F05-01, S4/S5): mutantes S01..S18 de la gestion del arbol
#   (advisory global y por comando, normalizacion, NULL-safe, RAMA sobre
#   todo el subarbol, row_version, confirmacion de ambito, cadena de
#   ancestros, idempotencia del alta, traduccion fisica por identidad y
#   matriz de auditoria), mas los discriminantes test_155..157.
#
#   v0.3.0 (F05-01, S6-C07; F05-D014 §28.4): se RETIRA C07 (bloqueo
#   transitorio CATEGORIA_REQUIERE_MAGNITUDES, retirado del codigo) y se
#   anaden M01..M23: locks FOR SHARE y su orden, invocacion y posicion de C07,
#   regla de valor sin redondeo, orden de los codigos, identidad derivada,
#   unidad snapshot, wire estructural, lectura de capturabilidad e inventario
#   de escritores de magnitudes. Discriminantes nuevos: test_158 y test_154.
#   Equivalente documentado: E02 (C07 sin comprobacion explicita de owner de
#   la magnitud: no existe; la RLS bajo gapto_runtime la oculta y el WITH
#   CHECK de categoria_magnitudes impide asociarla).
#
#   v0.3.1 (auditoria S6-C07, AJ-S6C07-02, solo documental): el censo
#   vigente es C01..C17 sin C07 (retirado), S01..S21 con S10b y M01..M23:
#   61 mutantes. Ninguna transformacion ni discriminante cambia.
#
#   v0.4.0 (F05-01 S6-ICONO (F05-D013)): mutantes I01..I21 del comando de
#   icono y del alta con icono (advisory, row_version y su orden frente a la
#   validacion y a la comparacion, validacion exacta sin recorte ni
#   mayusculas, pertenencia a CLAVES_PUBLICADAS, null, misma clave sin
#   escritura, auditoria y motivo, categoria deshabilitada, persistencia e
#   idempotencia del alta, COLUMNAS_EDITABLES, DTO y status HTTP).
#   Discriminante nuevo: test_159 (preflight incluido). Censo vigente:
#   C01..C17 sin C07, S01..S21 con S10b, M01..M23 e I01..I21: 82 mutantes.
#   Equivalentes documentados sin cambios: E01 y E02.
#
#   v0.5.0 (F05-01 S6-ICONO-AJ (AJ-S6ICONO-02, AJ-S6ICONO-03)): I22 (el alta
#   valida icon_key despues de la idempotencia AJ-S4-05; invierte solo D3 y
#   conserva validar antes de escribir) e I23 (defensa residual del CHECK de
#   0340 sin traduccion por identidad, AJ-S4-07). Discriminante: test_159.
#   Censo vigente: C01..C17 sin C07, S01..S21 con S10b, M01..M23 e I01..I23:
#   84 mutantes. Ninguna transformacion ni discriminante previo cambia.
#
#   v0.6.0 (F05-01 R-LOCALE; AJ-S6ICONO-AJ-02): la funcion del trigger se
#   identifica por su firma (servicio._funcion_trigger). Nuevos: L01
#   (traduccion dependiente del idioma: vuelve el prefijo ingles "function "),
#   L02 (firma sin delimitar: prefijo del nombre sin "()"), ambos con
#   discriminante test_160, e I24 (defensa residual del CHECK de icon_key
#   traducida por el texto INGLES del mensaje en vez de por identidad; muere
#   con la base local en espanol, discriminante test_159). S15 conserva su
#   semantica (traduccion por texto libre del mensaje) con ancla nueva,
#   porque la linea que mutaba ya no existe. Discriminante nuevo en el
#   preflight: test_160. Censo vigente: C01..C17 sin C07, S01..S21 con S10b,
#   M01..M23, I01..I24, L01..L02: 87 mutantes.
#   Equivalente documentado nuevo: E03 (traducir la defensa residual buscando
#   el NOMBRE de la constraint en el texto del mensaje): el nombre aparece
#   literal en el mensaje en cualquier idioma, asi que ningun test sin
#   artificio lo distingue de la traduccion por diag.constraint_name.
#   Los mutantes se ejecutan con la base local con lc_messages en espanol.
#
#   v0.7.0 (F05-01 S6-ORDEN (F05-D012 §26.3)): serie O01..O11 del comando
#   atomico `reordenar` (advisory, comparacion de conjuntos por subconjunto o
#   por tamano, row_version, escritura parcial antes de rechazar, auditoria y
#   motivo, escritura de filas que no cambian, bandera de idempotencia, lock
#   FOR NO KEY UPDATE de los hermanos y orden objetivo 1..n). Discriminante
#   nuevo en el preflight: test_161. Censo vigente: C01..C17 sin C07,
#   S01..S21 con S10b, M01..M23, I01..I24, L01..L02 y O01..O11: 98 mutantes
#   (corregido en v0.8.0, AJ-S6ORDEN-01: la v0.7.0 decia O01..O10 / 97).
#
#   v0.8.0 (F05-01 S6-WIRE+UI (este mandato); F05 §26.2 AJ-03): `categoria`
#   obligatoria en el wire VS-01. Nuevos W01 (categoria opcional con default
#   None) y W02 (SIN_CATEGORIA invoca la guarda C-a). C08 («null explicito
#   aceptado») se reancla con la MISMA semantica sobre la declaracion del
#   campo, porque el validador explicito de `null` desaparece: ahora lo
#   rechaza el tipo. Discriminantes: test_150 (nuevo en el preflight) y
#   test_152. Equivalente documentado nuevo: E04 («la respuesta admite el
#   estado de compatibilidad retirado» en el Literal de ResultadoGastoPagado):
#   ningun camino productivo puede producirlo (estado_categorial es siempre
#   categoria.estado), asi que ampliar el Literal no cambia ninguna respuesta.
#   [E04 retirado por AJ-S6WIREUI-02: el Literal forma parte del esquema
#   OpenAPI expuesto. Desde v0.9.0 es el mutante W03.]
#   Censo vigente: 98 + W01..W02 = 100 mutantes.
#
#   v0.9.0 (F05-01 S6-WIRE+UI, correctivo AJ-S6WIREUI-02): E04 se retira de
#   los equivalentes («retirado por AJ-S6WIREUI-02: el Literal forma parte
#   del esquema OpenAPI expuesto») y entra como mutante real W03 (el Literal
#   de estado_categorial de ResultadoGastoPagado admite NO_CAPTURADA_LEGACY).
#   Discriminante: test_150 (test de contrato: Literal del DTO, enum OpenAPI
#   y respuesta real). Censo vigente: 100 + W03 = 101 mutantes. Equivalentes
#   documentados vigentes: E01, E02 y E03.
#
#   v0.10.0 (F05-01 S7-MAG (F05-D020)): serie MG01..MG18 del catalogo de
#   magnitudes (D27 del mandato S7-MAG backend: el prefijo M ya lo usa la
#   serie C07 M01..M23). Mecanismos: advisory, FOR NO KEY UPDATE de la
#   categoria (R16), identidad de la asociacion, conjunto de reordenar por
#   cardinalidad, savepoint de comando en magnitudes y en desactivar(RAMA)
#   (D-MAG-10 B5), compactacion al retirar, normalizacion y su alcance a las
#   deshabilitadas, limite 80, confirmacion de impacto, auditoria ELIMINAR,
#   42501 fuera del punto prevalidado (R19), n_hechos, posicion n al asociar,
#   escritura de filas sin cambio de orden e idempotencias de asociar.
#   Discriminantes nuevos (preflight incluido): test_162, test_163, test_164.
#   Censo vigente (corrige de paso AJ-S6ORDEN-01, F05 §32: la serie O es
#   O01..O11): C01..C17 sin C07 (16), S01..S21 con S10b (22), M01..M23 (23),
#   I01..I24 (24), L01..L02 (2), O01..O11 (11), W01..W03 (3) = 101; mas
#   MG01..MG18 (18) = 119 mutantes. Equivalentes documentados: E01, E02, E03.
#
#   v0.11.0 (F05-01 S7-MAG correctivo AJ-S7MAGIMPL-01/02): MG12 cambia de
#   significado y de texto («traduce 42501 a MAGNITUD_NO_ADMITIDA en cualquier
#   punto»; el servicio ya no traduce 42501 en ninguno, D32 ajustada);
#   discriminante test_164. MG17 y MG15 se reanclan con la MISMA semantica
#   (MG17: la condicion de idempotencia del alta compara ahora tambien el
#   asociacion_id derivado; MG15: la llamada a insertar_asociacion ya no lleva
#   el argumento retirado `rls_prevalidado`). Nuevos: MG19 (asociacion_id aleatorio tambien en NUEVA) y MG20
#   (idempotencia del alta sin comparar el asociacion_id), discriminante
#   test_162. Censo vigente: 101 + MG01..MG20 (20) = 121 mutantes.
#   Equivalentes documentados: E01, E02, E03.
# Version: 0.11.0
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_01.journal.json"

T150 = "tests/api/test_150_f05_vs01_api.py"
T152 = "tests/api/test_152_f05_01_elegibilidad_categoria.py"
T153 = "tests/api/test_153_f05_01_lecturas_categorias.py"
T154 = "tests/api/test_154_f05_01_inventario_categorias.py"
T155 = "tests/api/test_155_f05_01_gestion_categorias.py"
T156 = "tests/api/test_156_f05_01_concurrencia_catalogo.py"
T157 = "tests/api/test_157_f05_01_bolsa_intensional.py"
T158 = "tests/api/test_158_f05_01_c07_magnitudes.py"
T159 = "tests/api/test_159_f05_01_icono_categoria.py"
T160 = "tests/api/test_160_f05_01_traduccion_locale.py"
T161 = "tests/api/test_161_f05_01_reordenar_hermanos.py"
T162 = "tests/api/test_162_f05_01_magnitudes_comandos.py"
T163 = "tests/api/test_163_f05_01_magnitudes_concurrencia.py"
T164 = "tests/api/test_164_f05_01_magnitudes_atomicidad.py"
MSERV = "backend/app/magnitudes/servicio.py"
MLECT = "backend/app/magnitudes/lecturas.py"
MNORM = "backend/app/magnitudes/normalizacion.py"
ICON = "backend/app/categorias/iconos.py"
DTOC = "backend/app/api/dto_categorias.py"
ERRH = "backend/app/api/errores_http.py"
CAP = "backend/app/api/captura_magnitudes.py"
SERV = "backend/app/categorias/servicio.py"
REPO = "backend/app/categorias/repositorio.py"
NORM = "backend/app/categorias/normalizacion.py"
ELEG = "backend/app/api/elegibilidad_categoria.py"
EJEC = "backend/app/api/ejecucion_gasto_pagado.py"
DTO = "backend/app/api/dto_vs01.py"
TRAD = "backend/app/api/traductor_gasto_pagado.py"
LECT = "backend/app/categorias/lecturas.py"
ANCLA_LECT = "from app.core.unidad_trabajo import SesionMotor\n"

REORDENAR_FIRMA = (
    "def reordenar(sesion: SesionMotor, *, parent_id, hermanos: list[tuple[uuid.UUID, int]]) -> ResultadoReorden | Rechazo:\n"
    "    repo.tomar_advisory(sesion)\n"
)
REORDENAR_VERSION = (
    '    if any(persistidos[cid]["row_version"] != rv for cid, rv in hermanos):\n'
    "        return Rechazo(VERSION_DESFASADA)\n"
)

ICONO_FIRMA = (
    "def cambiar_icono(sesion: SesionMotor, *, categoria_id, icon_key: str | None, row_version: int) -> Resultado | Rechazo:\n"
    "    repo.tomar_advisory(sesion)\n"
)

GUARDA_EN_RAMA = (
    "            # 3b. Guarda categorial C-a, solo para seleccion nueva explicita.\n"
    "            if intencion.categoria_id is not None:\n"
    "                rechazo = validar_seleccion_categoria(sesion, intencion.categoria_id, \"GASTO\")\n"
    "                if rechazo is not None:\n"
    "                    return RechazoIntegracion(rechazo)\n"
)
GUARDA_ANTES_IDENTIDAD = (
    "        if intencion.categoria_id is not None:\n"
    "            rechazo = validar_seleccion_categoria(sesion, intencion.categoria_id, \"GASTO\")\n"
    "            if rechazo is not None:\n"
    "                return RechazoIntegracion(rechazo)\n"
)

# (id, descripcion, [(fichero, original, mutado)], [tests discriminantes])
MUTANTES = [
    ("C01", "guarda sin FOR SHARE", [(ELEG, '"WHERE id = %s FOR SHARE",', '"WHERE id = %s",')], [T152]),
    ("C02", "AMBOS = cualquier naturaleza",
     [(ELEG, "    if not AMBITOS_ADMITIDOS.get(tipo_efecto):\n        # Naturaleza sin semantica categorial: ni siquiera se lee la fila.\n        return CODIGO_CATEGORIA_NO_ELEGIBLE\n", ""),
      (ELEG, "    return ambito in AMBITOS_ADMITIDOS.get(tipo_efecto, frozenset())",
       '    return ambito == "AMBOS" or ambito in AMBITOS_ADMITIDOS.get(tipo_efecto, frozenset())')], [T152]),
    ("C03", "sin comprobar enabled", [(ELEG, "    if not fila[1]:\n        return CODIGO_CATEGORIA_NO_ELEGIBLE\n", "")], [T152]),
    ("C04", "sin comprobar ambito",
     [(ELEG, "    if not ambito_compatible(tipo_efecto, fila[2]):\n        return CODIGO_CATEGORIA_NO_ELEGIBLE\n", "")], [T152]),
    ("C05", "guarda antes del reconocimiento de identidad",
     [(EJEC, GUARDA_EN_RAMA, ""),
      (EJEC, "        if not ya_materializada:\n", GUARDA_ANTES_IDENTIDAD + "        if not ya_materializada:\n")],
     [T152, T154]),
    ("C06", "guarda no invocada",
     [(EJEC, "                rechazo = validar_seleccion_categoria(sesion, intencion.categoria_id, \"GASTO\")\n"
             "                if rechazo is not None:\n                    return RechazoIntegracion(rechazo)\n",
       "                rechazo = validar_seleccion_categoria(sesion, intencion.categoria_id, \"GASTO\")\n")], [T152]),
    ("C08", "null explicito aceptado como legacy",
     [(DTO, "    categoria: CategoriaVs01\n", "    categoria: CategoriaVs01 | None\n")], [T152]),
    ("C09", "el traductor no sella la categoria",
     [(TRAD, '            estado_atribucion="COMPLETA",\n            categoria_id=intencion.categoria_id,\n',
       '            estado_atribucion="COMPLETA",\n')], [T152]),
    ("C10", "DELETE runtime de categorias_financieras",
     [(LECT, ANCLA_LECT, ANCLA_LECT + "\n\ndef _borrar(sesion, i):\n    sesion.uno(\"DELETE FROM gapto.categorias_financieras WHERE id = %s\", (i,))\n")],
     [T154]),
    ("C11", "segundo llamador de componer sin guarda",
     [(LECT, ANCLA_LECT, ANCLA_LECT + "from app.api.traductor_gasto_pagado import componer\n\n\ndef _atajo(i, a):\n    return componer(i, a)\n")],
     [T154]),
    ("C12", "SQL con tabla dinamica fuera de lista blanca",
     [(LECT, ANCLA_LECT, ANCLA_LECT + "\n\ndef _dinamica(sesion, t):\n    sesion.uno(f\"UPDATE gapto.{t} SET enabled = false\")\n")],
     [T154]),
    ("C13", "la frontera alcanza OP-04 sin OP-22",
     [(LECT, ANCLA_LECT, ANCLA_LECT + "from app.services.efectos_service import EfectosService  # noqa: F401\n")],
     [T154]),
    ("C14", "consumidor de categoria_id sin clasificar",
     [(LECT, ANCLA_LECT, ANCLA_LECT + "\n\ndef _nuevo(sesion, categoria_id):\n    return categoria_id\n")],
     [T154]),
    ("C15", "literal de tabla troceado",
     [(LECT, ANCLA_LECT, ANCLA_LECT + "\n_T = \"categorias_\" + \"financieras\"\n")], [T154]),
    ("C16", "el arbol filtra deshabilitadas",
     [(LECT, "\"WHERE owner_user_id = current_setting('gapto.owner_user_id')::uuid \"\n            \"ORDER BY",
       "\"WHERE owner_user_id = current_setting('gapto.owner_user_id')::uuid AND enabled \"\n            \"ORDER BY")],
     [T153]),
    ("C17", "el uso cuenta hechos anulados",
     [(LECT, "WHERE e.categoria_id = %s AND h.estado = 'ACTIVO' ", "WHERE e.categoria_id = %s ")], [T153]),
    # ---------------------------------------------------------------- S4 / S5
    ("S01", "advisory vaciado (ningun comando serializa)",
     [(REPO, '    sesion.uno(\n        "SELECT pg_advisory_xact_lock(', '    return None\n    sesion.uno(\n        "SELECT pg_advisory_xact_lock(')],
     [T156]),
    ("S02", "mover sin advisory", [(SERV, "def mover(sesion: SesionMotor, *, categoria_id, parent_id, row_version: int) -> Resultado | Rechazo:\n    repo.tomar_advisory(sesion)\n",
                                    "def mover(sesion: SesionMotor, *, categoria_id, parent_id, row_version: int) -> Resultado | Rechazo:\n")], [T154, T156]),
    ("S03", "desactivar sin advisory", [(SERV, "def desactivar(sesion: SesionMotor, *, categoria_id, modo: str, row_version: int) -> Resultado | Rechazo:\n    repo.tomar_advisory(sesion)\n",
                                         "def desactivar(sesion: SesionMotor, *, categoria_id, modo: str, row_version: int) -> Resultado | Rechazo:\n")], [T154, T156]),
    ("S04", "orden sin advisory", [(SERV, "def ordenar(sesion: SesionMotor, *, categoria_id, orden: int, row_version: int) -> Resultado | Rechazo:\n    repo.tomar_advisory(sesion)\n",
                                    "def ordenar(sesion: SesionMotor, *, categoria_id, orden: int, row_version: int) -> Resultado | Rechazo:\n")], [T154, T156]),
    ("S05", "ambito sin advisory", [(SERV, "                   row_version: int) -> Resultado | Rechazo:\n    repo.tomar_advisory(sesion)\n",
                                     "                   row_version: int) -> Resultado | Rechazo:\n")], [T154, T156]),
    ("S06", "normalizacion sin casefold", [(NORM, "    texto = nombre_visible(nombre).casefold()\n", "    texto = nombre_visible(nombre)\n")], [T155]),
    ("S07", "normalizacion sin quitar diacriticos", [(NORM, 'if unicodedata.category(c) != "Mn"', "if True")], [T155]),
    ("S08", "hermanos con = en vez de IS NOT DISTINCT FROM", [(REPO, "AND parent_id IS NOT DISTINCT FROM %s AND enabled ", "AND parent_id = %s AND enabled ")], [T155]),
    ("S09", "UNIQUE fisica como unica defensa", [(SERV, "    return any(normalizar(n) == clave for _, n in repo.hermanos_activos(sesion, parent_id, excluir))", "    return False")], [T155]),
    ("S10", "RAMA recorre solo nodos habilitados (no atraviesa intermedios deshabilitados)",
     [(REPO, '" SELECT id FROM gapto.categorias_financieras WHERE parent_id = %s"',
       '" SELECT id FROM gapto.categorias_financieras WHERE parent_id = %s AND enabled"'),
      (REPO, '" SELECT c.id FROM d JOIN gapto.categorias_financieras c ON c.parent_id = d.id"',
       '" SELECT c.id FROM d JOIN gapto.categorias_financieras c ON c.parent_id = d.id AND c.enabled"')], [T155]),
    ("S10b", "RAMA no atraviesa intermedios deshabilitados de nivel >= 2",
     [(REPO, '" SELECT c.id FROM d JOIN gapto.categorias_financieras c ON c.parent_id = d.id"',
       '" SELECT c.id FROM d JOIN gapto.categorias_financieras c ON c.parent_id = d.id AND c.enabled"')], [T155]),
    ("S11", "sin control de row_version", [(SERV, '    if fila["row_version"] != row_version:\n', "    if False:\n")], [T155]),
    ("S12", "ambito sin confirmacion del uso", [(SERV, "    if dict(confirmacion_uso) != vigente:\n", "    if False:\n")], [T155]),
    ("S13", "solo el padre inmediato, no la cadena de ancestros",
     [(SERV, "    return all(enabled for _, enabled in repo.cadena_ancestros(sesion, parent_id))", "    return repo.cadena_ancestros(sesion, parent_id)[0][1]")], [T155]),
    ("S14", "alta idempotente aunque haya evolucionado", [(SERV, '            existente["row_version"] == 1 and existente["nombre"] == visible', '            existente["nombre"] == visible')], [T155]),
    ("S15", "traduccion por texto libre del error", [(SERV, "        return _funcion_trigger(diag.context)\n", "        return diag.message_primary if _funcion_trigger(diag.context) else None\n")], [T155]),
    ("S16", "DESACTIVAR auditado con otro motivo valido", [(SERV, 'operacion = "DESACTIVAR_RAMA" if modo == "RAMA" else "DESACTIVAR"', 'operacion = "DESACTIVAR_RAMA" if modo == "RAMA" else "REACTIVAR"')], [T155]),
    ("S17", "DESACTIVAR_RAMA auditado como DESACTIVAR", [(SERV, 'operacion = "DESACTIVAR_RAMA" if modo == "RAMA" else "DESACTIVAR"', 'operacion = "DESACTIVAR"')], [T155]),
    ("S18", "RAMA sin auditar descendientes", [(SERV, "        _auditar(sesion, cid, operacion, antes)\n", "        if cid == categoria_id:\n            _auditar(sesion, cid, operacion, antes)\n")], [T155]),
    ("S19", "request_id distinto por nodo en RAMA",
     [(SERV, "        _auditar(sesion, cid, operacion, antes)\n", "        sesion.uno(\"SELECT set_config('gapto.request_id', gen_random_uuid()::text, true)\")\n        _auditar(sesion, cid, operacion, antes)\n")], [T155]),
    ("S20", "accion fisica incorrecta", [(SERV, "auditoria.ACCION_CREAR if operacion == \"ALTA\" else auditoria.ACCION_ACTUALIZAR", "auditoria.ACCION_CREAR if operacion == \"ALTA\" else \"ANULAR\"")], [T155]),
    ("S21", "reactivacion en cascada",
     [(SERV, '    rechazo = _escribir(sesion, lambda: repo.actualizar(sesion, categoria_id, {"enabled": True}))\n',
       '    rechazo = _escribir(sesion, lambda: [repo.actualizar(sesion, i, {"enabled": True}) for i in [categoria_id] + repo.subarbol(sesion, categoria_id)])\n')], [T155]),
    # ---------------------------------------------------------------- S6-C07
    ("M01", "asociaciones sin FOR SHARE",
     [(CAP, '"WHERE categoria_id = %s ORDER BY id FOR SHARE",', '"WHERE categoria_id = %s ORDER BY id",')], [T158]),
    ("M02", "magnitudes sin FOR SHARE",
     [(CAP, '"WHERE id = ANY(%s) ORDER BY id FOR SHARE",', '"WHERE id = ANY(%s) ORDER BY id",')], [T158]),
    ("M03", "orden de locks invertido (magnitudes antes que asociaciones)",
     [(CAP, "    asociaciones = _asociaciones(sesion, categoria_id)\n    fichas = _magnitudes(sesion, sorted({a.magnitud_id for a in asociaciones}))\n", "    previas = sesion.conexion.execute(\"SELECT magnitud_id FROM gapto.categoria_magnitudes WHERE categoria_id = %s\", (categoria_id,)).fetchall()\n    fichas = _magnitudes(sesion, sorted({f[0] for f in previas}))\n    asociaciones = _asociaciones(sesion, categoria_id)\n")], [T158]),
    ("M04", "C07 no invocada", [(EJEC, "                # 3c. C07: magnitudes de la categoria elegida (servidor autoridad).\n                rechazo = validar_magnitudes(sesion, intencion.categoria_id, intencion.magnitudes)\n                if rechazo is not None:\n                    return RechazoIntegracion(rechazo)\n", "")], [T158, T154]),
    ("M05", "C07 antes del reconocimiento de identidad",
     [(EJEC, "                # 3c. C07: magnitudes de la categoria elegida (servidor autoridad).\n                rechazo = validar_magnitudes(sesion, intencion.categoria_id, intencion.magnitudes)\n                if rechazo is not None:\n                    return RechazoIntegracion(rechazo)\n", ""),
      (EJEC, "        if not ya_materializada:\n", "        if intencion.categoria_id is not None:\n            rechazo = validar_magnitudes(sesion, intencion.categoria_id, intencion.magnitudes)\n            if rechazo is not None:\n                return RechazoIntegracion(rechazo)\n" + "        if not ya_materializada:\n")],
     [T158, T154]),
    ("M06", "precision ignorada (PostgreSQL redondearia)",
     [(CAP, "    return decimales <= precision_decimales and enteros <= DIGITOS_ENTEROS_MAX",
       "    return enteros <= DIGITOS_ENTEROS_MAX")], [T158]),
    ("M07", "capacidad numeric(18,6) no comprobada",
     [(CAP, "    return decimales <= precision_decimales and enteros <= DIGITOS_ENTEROS_MAX",
       "    return decimales <= precision_decimales")], [T158]),
    ("M08", "los ceros a la derecha cuentan como precision",
     [(CAP, "d.normalize().as_tuple()", "d.as_tuple()")], [T158]),
    ("M09", "obligatoria ausente no comprobada", [(CAP, "    if any(a.obligatoria and a.magnitud_id not in enviadas for a in asociaciones):\n        return CODIGO_MAGNITUD_OBLIGATORIA_AUSENTE\n", "")], [T158]),
    ("M10", "obligatoria deshabilitada no comprobada", [(CAP, "    if any(a.obligatoria and not disponible(a.magnitud_id) for a in asociaciones):\n        return CODIGO_CATEGORIA_MAGNITUD_NO_DISPONIBLE\n", "")], [T158]),
    ("M11", "opcional deshabilitada admitida",
     [(CAP, "    if any(m not in por_id or not disponible(m) for m in enviadas):\n",
       "    if any(m not in por_id for m in enviadas):\n")], [T158]),
    ("M12", "magnitud no asociada admitida",
     [(CAP, "    if any(m not in por_id or not disponible(m) for m in enviadas):\n",
       "    if any(m in por_id and not disponible(m) for m in enviadas):\n")], [T158]),
    ("M13", "orden de codigos 2 <-> 3",
     [(CAP, "        return CODIGO_MAGNITUD_NO_ADMITIDA\n", "        return CODIGO_INTERCAMBIO\n"),
      (CAP, "        return CODIGO_MAGNITUD_OBLIGATORIA_AUSENTE\n", "        return CODIGO_MAGNITUD_NO_ADMITIDA\n"),
      (CAP, "        return CODIGO_INTERCAMBIO\n", "        return CODIGO_MAGNITUD_OBLIGATORIA_AUSENTE\n")], [T158]),
    ("M14", "identidad de fila aleatoria (reintento no idempotente)",
     [(TRAD, 'return uuid.uuid5(intencion_id, f"magnitud:{magnitud_id}")', "return uuid.uuid4()")], [T158]),
    ("M15", "identidad de fila con otra derivacion",
     [(TRAD, 'return uuid.uuid5(intencion_id, f"magnitud:{magnitud_id}")',
       "return uuid.uuid5(magnitud_id, str(intencion_id))")], [T158]),
    ("M16", "unidad fijada por el adaptador en vez de snapshot F04",
     [(TRAD, "            unidad=None,\n", '            unidad="u",\n')], [T158]),
    ("M17", "duplicadas no rechazadas en el DTO",
     [(DTO, '        if len(ids) != len(set(ids)):\n            raise ValueError("magnitud_id repetida en la peticion")\n', "")],
     [T158]),
    ("M18", "cero con signo aceptado",
     [(DTO, '        if valor.startswith("-") and decimal.Decimal(valor) == 0:\n', "        if False:\n")], [T158]),
    ("M19", "sintaxis admite signo +",
     [(DTO, 'VALOR_CANONICO = re.compile(r"-?(0|', 'VALOR_CANONICO = re.compile(r"[-+]?(0|')], [T158]),
    ("M20", "lectura: capturable ignora enabled",
     [(LECT, "        if mid is None or not enabled:\n", "        if mid is None:\n")], [T158]),
    ("M21", "lectura: opcional deshabilitada bloquea",
     [(LECT, '            if obligatoria:\n                nodo["capturable"] = False\n',
       '            if True:\n                nodo["capturable"] = False\n')], [T158]),
    ("M22", "writer runtime de asociaciones (F05-01-R16)",
     [(LECT, ANCLA_LECT, ANCLA_LECT + "\n\ndef _asociar(sesion, c, m):\n    sesion.uno(\"INSERT INTO gapto.categoria_magnitudes (categoria_id, magnitud_id) VALUES (%s, %s)\", (c, m))\n")],
     [T154]),
    ("M23", "la frontera escribe hecho_magnitudes sin OP-22",
     [(LECT, ANCLA_LECT, ANCLA_LECT + "\n\ndef _atajo(sesion, h, m):\n    sesion.uno(\"INSERT INTO gapto.hecho_magnitudes (hecho_id, magnitud_id, valor, unidad) VALUES (%s, %s, 1, 'u')\", (h, m))\n")],
     [T154]),
    # ---------------------------------------------------------------- S6-ICONO
    ("I01", "cambiar_icono sin advisory",
     [(SERV, ICONO_FIRMA, ICONO_FIRMA.replace("    repo.tomar_advisory(sesion)\n", ""))], [T154, T156]),
    ("I02", "cambiar_icono sin control de row_version",
     [(SERV, ICONO_FIRMA + "    nodo = _nodo(sesion, categoria_id, row_version)\n",
       ICONO_FIRMA + "    nodo = repo.leer(sesion, categoria_id, bloquear=True) or Rechazo(NO_ENCONTRADO)\n")], [T159]),
    ("I03", "validacion sin distinguir mayusculas",
     [(ICON, "    return icon_key in CLAVES_PUBLICADAS", "    return icon_key.lower() in CLAVES_PUBLICADAS")], [T159]),
    ("I04", "validacion con recorte",
     [(ICON, "    return icon_key in CLAVES_PUBLICADAS", "    return icon_key.strip() in CLAVES_PUBLICADAS")], [T159]),
    ("I05", "el servicio recorta la clave antes de validarla y la persiste recortada",
     [(SERV, "    # AJ-ICON-03/05: pertenencia exacta a la biblioteca publicada; None = sin icono.\n",
       "    icon_key = icon_key.strip() if icon_key is not None else None\n")], [T159]),
    ("I06", "pertenencia a CLAVES_PUBLICADAS retirada (solo formato)",
     [(ICON, "    return icon_key in CLAVES_PUBLICADAS",
       '    return __import__("re").fullmatch(PATRON, icon_key) is not None and len(icon_key) <= LONGITUD_MAXIMA')],
     [T159]),
    ("I07", "UPDATE y auditoria aunque la clave no cambie",
     [(SERV, '    if icon_key == nodo["icon_key"]:\n        return Resultado(categoria=nodo, idempotente=True)\n', "")],
     [T159]),
    ("I08", "cambio de icono sin auditoria",
     [(SERV, '    _auditar(sesion, categoria_id, "ICONO", antes)\n', "")], [T159]),
    ("I09", "cambio de icono auditado con otro motivo",
     [(SERV, '    "ICONO": "F05-01 ICONO",\n', '    "ICONO": "F05-01 RENOMBRAR",\n')], [T159]),
    ("I10", "el alta no persiste icon_key",
     [(SERV, "presupuestable_default=presupuestable_default, icon_key=icon_key))",
       "presupuestable_default=presupuestable_default, icon_key=None))")], [T159, T155]),
    ("I11", "idempotencia del alta ignora icon_key",
     [(SERV, '            and existente["enabled"] and existente["icon_key"] == icon_key\n',
       '            and existente["enabled"]\n')], [T155]),
    ("I12", "categoria deshabilitada rechazada",
     [(SERV, "    # Q7: tambien en deshabilitadas; solo cambia icon_key (no reactiva).\n",
       '    if not nodo["enabled"]:\n        return Rechazo(PADRE_DESHABILITADO)\n')], [T159]),
    ("I13", "null rechazado",
     [(ICON, "    if icon_key is None:\n        return True\n", "    if icon_key is None:\n        return False\n")], [T159]),
    ("I14", "el alta no valida icon_key",
     [(SERV, "    if not icono_valido(icon_key):\n        return Rechazo(ICONO_NO_VALIDO)\n    visible = nombre_visible(nombre)\n",
       "    visible = nombre_visible(nombre)\n")], [T159, T154]),
    ("I15", "cambiar_icono reactiva la categoria",
     [(SERV, '{"icon_key": icon_key}))', '{"icon_key": icon_key, "enabled": True}))')], [T159]),
    ("I16", "icon_key fuera de COLUMNAS_EDITABLES",
     [(REPO, '"ambito", "icon_key"})', '"ambito"})')], [T154, T159]),
    ("I17", "ICONO_CATEGORIA_NO_VALIDO como 409",
     [(ERRH, '"ICONO_CATEGORIA_NO_VALIDO": (422,', '"ICONO_CATEGORIA_NO_VALIDO": (409,')], [T159]),
    ("I18", "comparacion con la clave persistida antes del row_version",
     [(SERV, ICONO_FIRMA, ICONO_FIRMA + "    previa = repo.leer(sesion, categoria_id, bloquear=True)\n"
       '    if previa is not None and previa["icon_key"] == icon_key:\n'
       "        return Resultado(categoria=previa, idempotente=True)\n")], [T159]),
    ("I19", "validacion del icono antes del nodo y del row_version",
     [(SERV, ICONO_FIRMA, ICONO_FIRMA + "    if not icono_valido(icon_key):\n        return Rechazo(ICONO_NO_VALIDO)\n")],
     [T159]),
    ("I20", "icon_key ausente aceptado en el comando",
     [(DTOC, "    # Sin default: la clave debe venir; null es un valor valido (sin icono).\n    icon_key: str | None\n",
       "    icon_key: str | None = None\n")], [T159]),
    ("I21", "el INSERT del alta descarta icon_key",
     [(REPO, "(categoria_id, parent_id, nombre, ambito, presupuestable_default, icon_key),",
       "(categoria_id, parent_id, nombre, ambito, presupuestable_default, None),")], [T159]),
    ("I22", "el alta valida icon_key despues de la idempotencia (D3 invertida)",
     [(SERV, "    if not icono_valido(icon_key):\n        return Rechazo(ICONO_NO_VALIDO)\n    visible = nombre_visible(nombre)\n",
       "    visible = nombre_visible(nombre)\n"),
      (SERV, "    rechazo = _escribir(sesion, lambda: repo.insertar(",
       "    if not icono_valido(icon_key):\n        return Rechazo(ICONO_NO_VALIDO)\n"
       "    rechazo = _escribir(sesion, lambda: repo.insertar(")], [T159]),
    ("I23", "CHECK de icon_key sin traduccion (defensa residual retirada)",
     [(SERV, '    "ck_categorias_financieras__icon_key_no_vacia_recortada": ICONO_NO_VALIDO,\n', "")], [T159]),
    ("I24", "defensa residual del CHECK de icon_key traducida por el texto ingles del mensaje",
     [(SERV, '    "ck_categorias_financieras__icon_key_no_vacia_recortada": ICONO_NO_VALIDO,\n', ""),
      (SERV, "    if diag.constraint_name in _CONSTRAINTS:\n",
       '    if exc.sqlstate == "23514" and "violates check constraint" in (diag.message_primary or "") '
       'and "icon_key" in (diag.message_primary or ""):\n'
       "        return ICONO_NO_VALIDO\n"
       "    if diag.constraint_name in _CONSTRAINTS:\n")], [T159]),
    # ---------------------------------------------------------------- R-LOCALE
    ("L01", "traduccion de triggers dependiente del idioma (prefijo ingles)",
     [(SERV, '    "gapto.fn_check_jerarquia_aciclica()": PADRE_NO_VALIDO,\n',
       '    "function gapto.fn_check_jerarquia_aciclica()": PADRE_NO_VALIDO,\n'),
      (SERV, '    "gapto.fn_check_categoria_deriva()": MOVIMIENTO_BLOQUEADO,\n',
       '    "function gapto.fn_check_categoria_deriva()": MOVIMIENTO_BLOQUEADO,\n'),
      (SERV, '    "gapto.fn_check_bolsa_prioridad()": MOVIMIENTO_BLOQUEADO,\n',
       '    "function gapto.fn_check_bolsa_prioridad()": MOVIMIENTO_BLOQUEADO,\n')], [T160]),
    ("L02", "firma sin delimitar (prefijo del nombre sin parentesis)",
     [(SERV, "re.escape(firma)", 're.escape(firma.removesuffix("()"))')], [T160]),
    # ---------------------------------------------------------------- S6-ORDEN
    ("O01", "reordenar sin advisory",
     [(SERV, REORDENAR_FIRMA, REORDENAR_FIRMA.replace("    repo.tomar_advisory(sesion)\n", ""))], [T154, T156]),
    ("O02", "conjunto aceptado si es subconjunto del persistido",
     [(SERV, "set(pedidos) != set(persistidos):", "not set(pedidos) <= set(persistidos):")], [T161]),
    ("O03", "conjunto comparado solo por tamano (acepta id de otro padre)",
     [(SERV, "set(pedidos) != set(persistidos):", "len(set(pedidos)) != len(persistidos):")], [T161]),
    ("O04", "row_version de los hermanos no comprobada",
     [(SERV, REORDENAR_VERSION, "")], [T161]),
    ("O05", "escritura parcial: row_version comprobada fila a fila tras escribir las anteriores",
     [(SERV, REORDENAR_VERSION, ""),
      (SERV, "    for cid, pos in cambian:\n        antes = repo.snapshot(sesion, cid)\n",
       "    for cid, pos in cambian:\n        if persistidos[cid][\"row_version\"] != dict(hermanos)[cid]:\n"
       "            return Rechazo(VERSION_DESFASADA)\n        antes = repo.snapshot(sesion, cid)\n")], [T161]),
    ("O06", "reordenacion sin auditoria",
     [(SERV, '        _auditar(sesion, cid, "REORDENAR", antes)\n', "")], [T161]),
    ("O07", "reordenacion auditada con otro motivo",
     [(SERV, '    "REORDENAR": "F05-01 REORDENAR",\n', '    "REORDENAR": "F05-01 ORDEN",\n')], [T161]),
    ("O08", "escribe tambien las filas cuyo orden no cambia",
     [(SERV, ' for pos, cid in enumerate(pedidos) if persistidos[cid]["orden"] != pos]',
       " for pos, cid in enumerate(pedidos)]")], [T161]),
    ("O09", "bandera de idempotencia siempre False",
     [(SERV, "        idempotente=not cambian,\n", "        idempotente=False,\n")], [T161]),
    ("O10", "hermanos leidos sin FOR NO KEY UPDATE",
     [(REPO, "AND parent_id IS NOT DISTINCT FROM %s ORDER BY id FOR NO KEY UPDATE",
       "AND parent_id IS NOT DISTINCT FROM %s ORDER BY id")], [T156]),
    ("O11", "orden objetivo 1..n en vez de 0..n-1",
     [(SERV, "for pos, cid in enumerate(pedidos)", "for pos, cid in enumerate(pedidos, start=1)")], [T161]),
    # ---------------------------------------------------------------- S6-WIRE
    ("W01", "categoria vuelve a ser opcional con default None",
     [(DTO, "    categoria: CategoriaVs01\n", "    categoria: CategoriaVs01 | None = None\n")], [T150, T152]),
    ("W02", "SIN_CATEGORIA invoca la guarda C-a",
     [(EJEC, "            if intencion.categoria_id is not None:\n",
       '            if intencion.estado_categorial in ("CATEGORIA", "SIN_CATEGORIA"):\n')], [T152]),
    ("W03", "la respuesta admite el estado retirado NO_CAPTURADA_LEGACY (ex E04)",
     [(DTO, '    estado_categorial: Literal["CATEGORIA", "SIN_CATEGORIA"]\n',
       '    estado_categorial: Literal["CATEGORIA", "SIN_CATEGORIA", "NO_CAPTURADA_LEGACY"]\n')], [T150]),
    # ---------------------------------------------------------------- S7-MAG (F05-D020)
    ("MG01", "asociar sin advisory (CATEGORIAS, owner)",
     [(MSERV, '    unidad_default, precision_decimales}): alta rapida + asociacion atomicas."""\n'
              "    repo_cat.tomar_advisory(sesion)\n",
       '    unidad_default, precision_decimales}): alta rapida + asociacion atomicas."""\n')], [T154, T163]),
    ("MG02", "categoria leida sin FOR NO KEY UPDATE (R16)",
     [(MSERV, "    return repo_cat.leer(sesion, categoria_id, bloquear=True) is not None\n",
       "    return repo_cat.leer(sesion, categoria_id, bloquear=False) is not None\n")], [T163]),
    ("MG03", "identidad de la asociacion sin comparar magnitud ni obligatoria_actual",
     [(MSERV, '    if a is None or a["magnitud_id"] != magnitud_id or a["obligatoria"] != obligatoria_actual:\n',
       "    if a is None:\n")], [T162]),
    ("MG04", "conjunto de reordenar comparado por cardinalidad",
     [(MSERV, "    if len(set(ids)) != len(ids) or set(esperado) != real:\n",
       "    if len(set(ids)) != len(ids) or len(esperado) != len(real):\n")], [T162]),
    ("MG05", "comandos de magnitudes sin savepoint de alcance de comando",
     [(MSERV, "        with sesion.conexion.transaction():  # savepoint de alcance de comando (D-MAG-10)\n",
       "        if True:  # savepoint de alcance de comando (D-MAG-10)\n")], [T164]),
    ("MG06", "retirar sin compactar las restantes",
     [(MSERV, '        modificadas.extend(_escribir_orden(sesion, restantes, [x["asociacion_id"] for x in restantes]))\n',
       "")], [T162]),
    ("MG07", "colision de nombre sin normalizar (literal)",
     [(MSERV, "        if mid != excluir and normalizar(existente) == clave:\n",
       "        if mid != excluir and existente == nombre:\n")], [T162]),
    ("MG08", "colision de nombre solo contra magnitudes habilitadas",
     [(MSERV, "        if mid != excluir and normalizar(existente) == clave:\n",
       "        if mid != excluir and enabled and normalizar(existente) == clave:\n")], [T162]),
    ("MG09", "limite del nombre de magnitud 80 -> 100",
     [(MNORM, "LONGITUD_NOMBRE = 80\n", "LONGITUD_NOMBRE = 100\n")], [T162]),
    ("MG10", "confirmacion de impacto no revalidada contra el conjunto vigente",
     [(MSERV, '    if set(confirmacion_impacto or ()) != {c["categoria_id"] for c in impacto}:\n',
       "    if confirmacion_impacto is None and impacto:\n")], [T162, T163]),
    ("MG11", "retirar sin auditoria ELIMINAR",
     [(MSERV, '        _auditar_asociacion(sesion, asociacion_id, "RETIRAR", antes)\n', "        pass\n")], [T162]),
    ("MG12", "traduce 42501 a MAGNITUD_NO_ADMITIDA en cualquier punto (R19, D32 ajustada)",
     [(MSERV, "    return _CONSTRAINTS.get(exc.diag.constraint_name)\n",
       '    return MAGNITUD_NO_ADMITIDA if exc.sqlstate == "42501" else _CONSTRAINTS.get(exc.diag.constraint_name)\n')],
     [T164]),
    ("MG13", "n_hechos como recuento de asociaciones",
     [(MLECT, '         "n_hechos": hechos.get(mid, 0)}\n',
       '         "n_hechos": len(por_magnitud.get(mid, []))}\n')], [T162]),
    ("MG14", "desactivar(RAMA) sin savepoint de alcance de comando (B5)",
     [(SERV, "        with sesion.conexion.transaction():  # savepoint de alcance de comando (D-MAG-10 B5)\n",
       "        if True:  # savepoint de alcance de comando (D-MAG-10 B5)\n")], [T164]),
    ("MG15", "nueva asociacion en la posicion 0 en vez de n",
     [(MSERV, "            obligatoria=obligatoria, orden=len(persistidas)))\n",
       "            obligatoria=obligatoria, orden=0))\n")], [T162]),
    ("MG16", "escribe tambien las asociaciones cuyo orden no cambia",
     [(MSERV, "    cambian = [(aid, pos) for pos, aid in enumerate(objetivo) if actual[aid] != pos]\n",
       "    cambian = [(aid, pos) for pos, aid in enumerate(objetivo)]\n")], [T162]),
    ("MG17", "alta rapida idempotente sin comparar la obligatoriedad de la asociacion",
     [(MSERV, '                and existente["obligatoria"] == obligatoria\n', "")], [T162]),
    ("MG18", "asociar existente idempotente aunque cambie la obligatoriedad",
     [(MSERV, '        if existente["obligatoria"] != obligatoria:\n            return Rechazo(ASOCIACION_YA_EXISTE)\n',
       "        if False:\n            return Rechazo(ASOCIACION_YA_EXISTE)\n")], [T162]),
    ("MG19", "asociacion_id aleatorio tambien en el alta rapida (NUEVA)",
     [(MSERV, "    asociacion_id = _asociacion_id_del_alta(mid, categoria_id) if nueva is not None else uuid.uuid4()\n",
       "    asociacion_id = uuid.uuid4()\n")], [T162]),
    ("MG20", "idempotencia del alta rapida sin comparar el asociacion_id derivado",
     [(MSERV, '                and existente is not None and existente["asociacion_id"] == asociacion_id\n',
       "                and existente is not None\n")], [T162]),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(tests: list[str]) -> int:
    cmd = [sys.executable, "-m", "pytest", *tests, "-q", "-x", "-p", "no:cacheprovider", "--rootdir=tests/api"]
    return subprocess.run(cmd, cwd=RAIZ, capture_output=True).returncode


def recuperar_si_pendiente() -> bool:
    if not JOURNAL.exists():
        return False
    j = json.loads(JOURNAL.read_text(encoding="utf-8"))
    for f in j["ficheros"]:
        ruta = RAIZ / f["fichero"]
        ruta.write_bytes(bytes.fromhex(f["original_hex"]))
        if sha(ruta.read_bytes()) != f["sha256"]:
            sys.exit(f"RECUPERACION FALLIDA: identidad no verificada en {f['fichero']}")
    JOURNAL.unlink()
    return True


def main() -> None:
    if not os.getenv("GAPTO_TEST_DATABASE_URL"):
        sys.exit("Falta GAPTO_TEST_DATABASE_URL (base local desechable).")
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    if correr([T150, T152, T153, T154, T155, T156, T157, T158, T159, T160, T161, T162, T163, T164]) != 0:
        sys.exit("PREFLIGHT ROJO: no se muta nada.")
    veredictos = []
    for mid, desc, cambios, tests in MUTANTES:
        ficheros = sorted({c[0] for c in cambios})
        originales = {f: (RAIZ / f).read_bytes() for f in ficheros}
        textos = {f: b.decode("utf-8") for f, b in originales.items()}
        aplicable = True
        for f, a, b in cambios:
            if textos[f].count(a) != 1:
                aplicable = False
                break
            textos[f] = textos[f].replace(a, b)
        if not aplicable:
            veredictos.append((mid, "NO_CLASIFICABLE", "transformacion no aplicable", desc))
            continue
        JOURNAL.write_text(
            json.dumps({"mutante": mid, "ficheros": [
                {"fichero": f, "original_hex": originales[f].hex(), "sha256": sha(originales[f])} for f in ficheros
            ]}),
            encoding="utf-8",
        )
        if hasattr(os, "sync"):
            os.sync()
        v = "NO_CLASIFICABLE"
        try:
            for f in ficheros:
                (RAIZ / f).write_bytes(textos[f].encode("utf-8"))
            v = "MUERTO" if correr(tests) != 0 else "VIVO"
        finally:
            ok = True
            for f in ficheros:
                (RAIZ / f).write_bytes(originales[f])
                ok = ok and sha((RAIZ / f).read_bytes()) == sha(originales[f])
            JOURNAL.unlink(missing_ok=True)
        veredictos.append((mid, v if ok else "NO_CLASIFICABLE", ",".join(pathlib.Path(t).stem for t in tests), desc))
    for v in veredictos:
        print(*v, sep=" | ")
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    print(f"RESUMEN {muertos} / {len(veredictos)} muertos")
    sys.exit(0 if muertos == len(veredictos) else 1)


if __name__ == "__main__":
    main()
