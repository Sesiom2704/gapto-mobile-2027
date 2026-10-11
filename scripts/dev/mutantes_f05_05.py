# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_05.py
# Ruta: scripts/dev/mutantes_f05_05.py
# Descripcion: Arnes de mutacion de F05-05 K2+K3 (mandato §3: un mutante por
#   guarda, prefijos por dominio SE senales, AF afinidades, BU busqueda, AC
#   actividad, RE resultado del mes, I13 contrato I13 v2; tabla
#   GUARDAS_MUTANTES.md en la evidencia). Mismo motor que
#   mutantes_f05_j2j3.py (D-181, D-192, D-193, WM 12C.2):
#     - sustituciones de texto exacto (UNA ocurrencia) y discriminantes;
#     - journal durable ANTES de tocar el primer byte; si al arrancar hay un
#       journal pendiente: restaura, verifica y aborta;
#     - preflight verde de todos los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y se verifica la identidad byte a byte;
#     - veredicto unico: MUERTO | VIVO | NO_CLASIFICABLE.
#   Los mutantes AF de orden de locks (AF01, AF02) los discrimina la bateria
#   serial test_191: ejecutar con GAPTO_F0505_CONCURRENCIA=1 (si no, esos
#   discriminantes se omiten y el mutante sale VIVO).
#   Los mutantes I13x debilitan el propio comprobador de test_154 (I13 v2):
#   sus pruebas negativas con imports plantados exigen que la violacion se
#   detecte, asi que un comprobador debilitado las pone en rojo.
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable> GAPTO_F0505_CONCURRENCIA=1
#        python scripts/dev/mutantes_f05_05.py [--solo ID,ID]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-05 K3 §3)
# Version: 0.2.0 (F05-05 K4-E, AJ-F0505C-01 hueco A9): RE12, filtro de tipo de efecto del
#   Resultado del mes (el reembolso, DERECHO_COBRO, entra como ingreso). Censo: 77.
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_05.journal.json"

# Discriminantes
T154 = "tests/api/test_154_f05_01_inventario_categorias.py"
T184 = "tests/api/test_184_f05_05_periodos.py"
T185 = "tests/api/test_185_f05_05_senales.py"
T186 = "tests/api/test_186_f05_05_afinidades.py"
T187_ = "tests/api/test_187_f05_05_busqueda.py"
# El test de rendimiento (caso 9, 3.000 terceros < 50 ms) no discrimina ninguna guarda y depende
# del entorno (coste de conexion): se ejecutan los demas tests del fichero por nodeid.
T187 = [f"{T187_}::{t}" for t in ("test_caso34_sensible_a_acentos", "test_caso9_homonimos_por_naturaleza_y_uso",
                                          "test_inactivos_solo_con_incluir_inactivos", "test_comodines_del_usuario_son_literales",
                                          "test_sin_q_la_lista_de_siempre_con_activos_e_inactivos", "test_limite_50_en_orden_normalizado")]
T188 = "tests/api/test_188_f05_05_actividad.py"
T189 = "tests/api/test_189_f05_05_resultado_mes.py"
T191 = "tests/api/test_191_f05_05_concurrencia_serial.py"
J_SEN = "mobile/__tests__/senales_selectores.test.tsx"
J_ACT = "mobile/__tests__/actividad_inicio.test.tsx"

# Codigo mutado
SEN = "backend/app/senales/lecturas.py"
FECHA = "backend/app/comun/fecha_funcional.py"
AFS = "backend/app/afinidades/servicio.py"
AFR = "backend/app/afinidades/repositorio.py"
AFL = "backend/app/afinidades/lecturas.py"
TERL = "backend/app/terceros/lecturas.py"
ACT = "backend/app/actividad/lecturas.py"
INI = "backend/app/inicio/lecturas.py"
M_SEN = "mobile/src/domain/senales.ts"
M_ACT = "mobile/src/domain/actividad.ts"
M_INI = "mobile/src/domain/inicio.ts"
M_REG = "mobile/src/screens/RegistroGastoScreen.tsx"
M_SELT = "mobile/src/components/SelectorTercero.tsx"
M_REC = "mobile/src/components/RecordarAfinidad.tsx"
M_ACTS = "mobile/src/screens/ActividadScreen.tsx"
M_HOME = "mobile/src/screens/HomeScreen.tsx"
M_PREF = "backend/app/preferencias/resolver.py"

MUTANTES: list[tuple[str, str, list[tuple[str, str, str]], list[str]]] = [
    # ---------------------------------------------------------------- SE senales (A1/A2/A4/A6, R1-R8)
    ("SE01", "categorias deshabilitadas sugeridas (R3)",
     [(SEN, "elegibles = {cid for cid, n in nodos.items() if n[\"enabled\"] and ambito_compatible(tipo, n[\"ambito\"])}",
       "elegibles = {cid for cid, n in nodos.items() if ambito_compatible(tipo, n[\"ambito\"])}")], [T185]),
    ("SE02", "ambito incompatible sugerido (R3, C02)",
     [(SEN, "elegibles = {cid for cid, n in nodos.items() if n[\"enabled\"] and ambito_compatible(tipo, n[\"ambito\"])}",
       "elegibles = {cid for cid, n in nodos.items() if n[\"enabled\"]}")], [T185]),
    ("SE03", "hechos anulados cuentan como uso",
     [(SEN, "    \"WHERE h.estado = 'ACTIVO' AND e.tipo_efecto = %s AND e.categoria_id IS NOT NULL \"\n    \"AND h.fecha_hecho > %s AND h.fecha_hecho <= %s \"\n    \"GROUP BY e.categoria_id\"",
       "    \"WHERE e.tipo_efecto = %s AND e.categoria_id IS NOT NULL \"\n    \"AND h.fecha_hecho > %s AND h.fecha_hecho <= %s \"\n    \"GROUP BY e.categoria_id\"")], [T185]),
    ("SE04", "ventana sin limite inferior (R7: 365 dias)",
     [(SEN, "VENTANA_DIAS = 365", "VENTANA_DIAS = 36500")], [T185]),
    ("SE05", "frecuencia por efecto y no por hecho (count sin DISTINCT)",
     [(SEN, "    \"SELECT e.categoria_id, count(DISTINCT h.id), max(h.fecha_hecho) \"\n    \"FROM gapto.hecho_efectos e JOIN gapto.hechos_financieros h ON h.id = e.hecho_id \"\n    \"WHERE h.estado = 'ACTIVO' AND e.tipo_efecto = %s AND e.categoria_id IS NOT NULL \"\n    \"AND h.fecha_hecho > %s AND h.fecha_hecho <= %s \"\n    \"GROUP BY",
       "    \"SELECT e.categoria_id, count(h.id), max(h.fecha_hecho) \"\n    \"FROM gapto.hecho_efectos e JOIN gapto.hechos_financieros h ON h.id = e.hecho_id \"\n    \"WHERE h.estado = 'ACTIVO' AND e.tipo_efecto = %s AND e.categoria_id IS NOT NULL \"\n    \"AND h.fecha_hecho > %s AND h.fecha_hecho <= %s \"\n    \"GROUP BY")], [T185]),
    ("SE06", "desempate sin recencia (R6)",
     [(SEN, "        return (-n, -ultima.toordinal(), *clave_orden(nodos[cid]))", "        return (-n, *clave_orden(nodos[cid]))")], [T185]),
    ("SE07", "afinidades no van primero (A4)",
     [(SEN, "            salida.append(_candidata(nodos[cid], MOTIVO_AFINIDAD, uso_ter.get(cid)))\n            elegidas.add(cid)\n",
       "            pass\n")], [T185]),
    ("SE08", "afinidad hacia categoria deshabilitada sugerida",
     [(SEN, "            afinidades = [f[0] for f in cur.fetchall() if f[0] in elegibles]", "            afinidades = [f[0] for f in cur.fetchall() if f[0] in nodos]")], [T185]),
    ("SE09", "mas de 3 candidatas",
     [(SEN, "    return salida[:LIMITE_CATEGORIAS]", "    return salida")], [T185]),
    ("SE10", "RECIENTE para todo el bloque del tipo (R4: solo el primero)",
     [(SEN, "            reciente = primero and (fecha - ultima).days < DIAS_RECIENTE", "            reciente = (fecha - ultima).days < DIAS_RECIENTE")], [T185]),
    ("SE11", "candidata repetida entre bloques",
     [(SEN, "        for cid in sorted((c for c in uso_tipo if c in elegibles and c not in elegidas), key=_orden_uso(uso_tipo, nodos)):",
       "        for cid in sorted((c for c in uso_tipo if c in elegibles), key=_orden_uso(uso_tipo, nodos)):")], [T185]),
    ("SE12", "terceros deshabilitados en Recientes",
     [(SEN, "    \"WHERE h.estado = 'ACTIVO' AND th.codigo = %s AND t.enabled \"", "    \"WHERE h.estado = 'ACTIVO' AND th.codigo = %s \"")], [T185]),
    ("SE13", "Recientes sin limite de 5",
     [(SEN, "    return salida[:LIMITE_TERCEROS]", "    return salida")], [T185]),
    ("SE14", "Recientes por frecuencia en lugar de recencia (R4)",
     [(SEN, "    recientes.sort(key=lambda x: (-x[\"ultimo_uso\"].toordinal(), normalizar(x[\"nombre\"]), str(x[\"tercero_id\"])))",
       "    recientes.sort(key=lambda x: (-x[\"usos\"], normalizar(x[\"nombre\"]), str(x[\"tercero_id\"])))")], [T185]),
    ("SE15", "ventana con current_date en vez de la fecha recibida (R7)",
     [(FECHA, "    return fecha - dt.timedelta(days=dias), fecha", "    return dt.date.today() - dt.timedelta(days=dias), dt.date.today()")], [T185, T184]),
    ("SE16", "cliente: mas de 3 sugeridas",
     [(M_SEN, "  return s.candidatas.slice(0, MAX_SUGERIDAS).map((c) => ({", "  return s.candidatas.map((c) => ({")], [J_SEN]),
    ("SE17", "cliente: motivo AFINIDAD con texto de frecuencia",
     [(M_SEN, "      return `La guardaste para ${ctx.tercero ?? 'este tercero'}`;", "      return `Sueles usarla con ${ctx.tercero ?? 'este tercero'}`;")], [J_SEN]),
    ("SE18", "chips con la categoria ya elegida (solo PENDIENTE)",
     [(M_REG, "    b.categoria.estado === 'PENDIENTE' && !bloqueado && arbol.fase === 'OK'", "    !bloqueado && arbol.fase === 'OK'")], [J_SEN]),
    ("SE19", "sugeridas para fecha futura",
     [(M_REG, "    if (!esFechaIso(actual.fechaHecho) || actual.fechaHecho > hoyIso) return setSugeridas([]);",
       "    if (!esFechaIso(actual.fechaHecho)) return setSugeridas([]);")], [J_SEN]),
    # ---------------------------------------------------------------- AF afinidades (A5, R9, R16)
    ("AF01", "orden R9 roto: la categoria antes que el tercero",
     [(AFS, "    repo.tomar_advisory(sesion)\n    tercero = _tercero_bloqueado(sesion, tercero_id)\n",
       "    repo.tomar_advisory(sesion)\n    repo.leer_categoria_compartida(sesion, categoria_id)\n    tercero = _tercero_bloqueado(sesion, tercero_id)\n")], [T191]),
    ("AF02", "categoria NKU en lugar de FOR SHARE (R16 literal)",
     [(AFR, "\"SELECT owner_user_id, enabled, ambito FROM gapto.categorias_financieras WHERE id = %s FOR SHARE\"",
       "\"SELECT owner_user_id, enabled, ambito FROM gapto.categorias_financieras WHERE id = %s FOR NO KEY UPDATE\"")], [T191]),
    ("AF03", "sin advisory TERCEROS en el alta",
     [(AFS, "         categoria_id: uuid.UUID) -> Resultado | Rechazo:\n    repo.tomar_advisory(sesion)\n",
       "         categoria_id: uuid.UUID) -> Resultado | Rechazo:\n")], [T186, T191]),
    ("AF04", "alta con tercero deshabilitado",
     [(AFS, "    if tercero is None or not tercero[\"enabled\"]:\n        return Rechazo(TERCERO_NO_ELEGIBLE)",
       "    if tercero is None:\n        return Rechazo(TERCERO_NO_ELEGIBLE)")], [T186]),
    ("AF05", "alta con categoria deshabilitada",
     [(AFS, "            if categoria is not None and not categoria[\"enabled\"]:", "            if False:")], [T186]),
    ("AF06", "sin savepoint: el rechazo deja row_version subido",
     [(AFS, "        with conexion.transaction():  # savepoint: un rechazo deshace tambien row_version\n            repo_ter.incrementar_version(sesion, tercero_id)\n            categoria",
       "        repo_ter.incrementar_version(sesion, tercero_id)\n        if True:\n            categoria")], [T186]),
    ("AF07", "sin incremento de row_version del tercero",
     [(AFS, "        with conexion.transaction():  # savepoint: un rechazo deshace tambien row_version\n            repo_ter.incrementar_version(sesion, tercero_id)\n",
       "        with conexion.transaction():  # savepoint: un rechazo deshace tambien row_version\n")], [T186]),
    ("AF08", "par duplicado: error en lugar de idempotente con aviso",
     [(AFS, "        if exc.sqlstate == \"23505\" and exc.diag.constraint_name == _UNIQUE_PAR:", "        if False:")], [T186]),
    ("AF09", "42501 enmascarado como categoria no elegible",
     [(AFS, "            return Rechazo(REFERENCIA_NO_DISPONIBLE, {\"sqlstate\": exc.sqlstate})", "            return Rechazo(CATEGORIA_NO_ELEGIBLE)")], [T186]),
    ("AF10", "id reutilizado con otro par aceptado como idempotente",
     [(AFS, "        if previa[\"tercero_id\"] == tercero_id and previa[\"categoria_id\"] == categoria_id:", "        if True:")], [T186]),
    ("AF11", "baja sin auditoria",
     [(AFS, "    auditoria.registrar(sesion, tabla=TABLA, registro_id=afinidad_id, accion=ACCION_ELIMINAR,\n                        datos_antes_json=antes, motivo=MOTIVOS[\"BAJA\"])\n", "")], [T186]),
    ("AF12", "alta sin auditoria",
     [(AFS, "    auditoria.registrar(sesion, tabla=TABLA, registro_id=afinidad_id, accion=auditoria.ACCION_CREAR,\n                        datos_despues_json=repo.snapshot(sesion, afinidad_id), motivo=MOTIVOS[\"ALTA\"])\n", "")], [T186]),
    ("AF13", "el incremento toca un campo de negocio",
     [("backend/app/terceros/repositorio.py", "\"UPDATE gapto.terceros SET row_version = row_version + 1, updated_at = now() \"",
       "\"UPDATE gapto.terceros SET row_version = row_version + 1, updated_at = now(), naturaleza = NULL \"")], [T186]),
    ("AF14", "Segun tu historial repite las ya guardadas",
     [(AFL, "             for h in historial if h[\"categoria_id\"] not in ya]", "             for h in historial]")], [T186]),
    ("AF15", "cliente: Recordar ofrecido aunque ya este guardada",
     [(M_REC, "      setEstado(r.datos.guardadas.some((g) => g.categoria_id === p.categoria.id) ? 'NADA' : 'OFRECER');",
       "      setEstado('OFRECER');")], [J_SEN]),
    ("AF16", "cliente: Recordar reintenta con identidad nueva",
     [(M_REC, "    const r = await p.cliente.altaAfinidad({ id: id.current, tercero_id: p.tercero.id, categoria_id: p.categoria.id });",
       "    const r = await p.cliente.altaAfinidad({ id: p.nuevoId(), tercero_id: p.tercero.id, categoria_id: p.categoria.id });")], [J_SEN]),
    # ---------------------------------------------------------------- BU busqueda
    ("BU01", "comodines del usuario sin escapar",
     [(TERL, "    return \"%\" + texto.replace(\"\\\\\", \"\\\\\\\\\").replace(\"%\", r\"\\%\").replace(\"_\", r\"\\_\") + \"%\"",
       "    return \"%\" + texto + \"%\"")], T187),
    ("BU02", "busqueda sin inactivos aunque se pidan / con inactivos sin pedirlos",
     [(TERL, "    if not incluir_inactivos:\n        filas = [x for x in filas if x[\"enabled\"]]\n", "")], T187),
    ("BU03", "busqueda sin limite de 50",
     [(TERL, "    return filas[:LIMITE_BUSQUEDA]", "    return filas")], T187),
    ("BU04", "busqueda de texto vacio devuelve todo",
     [(TERL, "    q = texto.strip()\n    if not q:\n        return []\n", "    q = texto.strip()\n")], T187),
    ("BU05", "cliente: busqueda de servidor desde 1 caracter",
     [(M_SELT, "  const enServidor = nombre.length >= MIN_BUSQUEDA;", "  const enServidor = nombre.length >= 1;")], [J_SEN]),
    # ---------------------------------------------------------------- AC actividad (A7/A8, R11/R12)
    ("AC01", "hechos anulados en la Actividad",
     [(ACT, "    cond = [\"h.estado = 'ACTIVO'\"]", "    cond = [\"true\"]")], [T188]),
    ("AC02", "limite superior del periodo inclusivo",
     [(ACT, "        cond.append(\"h.fecha_hecho < %(hasta)s\")", "        cond.append(\"h.fecha_hecho <= %(hasta)s\")")], [T188]),
    ("AC03", "orden secundario inestable (keyset fecha DESC, id ASC)",
     [(ACT, "\"ORDER BY h.fecha_hecho DESC, h.id ASC LIMIT %(limite)s\"", "\"ORDER BY h.fecha_hecho DESC, h.id DESC LIMIT %(limite)s\"")], [T188]),
    ("AC04", "cursor con desigualdad que repite la fila frontera",
     [(ACT, "(h.fecha_hecho = %(c_fecha)s AND h.id > %(c_id)s)", "(h.fecha_hecho = %(c_fecha)s AND h.id >= %(c_id)s)")], [T188]),
    ("AC05", "subcategorias excluidas del filtro de categoria",
     [(ACT, "        ids = _descendientes(catalogo(sesion), f.categoria) if f.incluir_subcategorias else [f.categoria]",
       "        ids = [f.categoria]")], [T188]),
    ("AC06", "busqueda sin el nombre de la categoria",
     [(ACT, "        busqueda += [_COINCIDE_TERCERO, _COINCIDE_CATEGORIA, _COINCIDE_CONTEXTO, _COINCIDE_NOTA]",
       "        busqueda += [_COINCIDE_TERCERO, _COINCIDE_CONTEXTO, _COINCIDE_NOTA]")], [T188]),
    ("AC07", "tu parte inventada con reparto sin indicar (P-ACT-03)",
     [(ACT, "            if estado == \"COMPLETA\":\n                tu_parte", "            if estado in (\"COMPLETA\", \"NO_DISPONIBLE\"):\n                tu_parte")], [T188]),
    ("AC08", "estado de reparto optimista (no el peor)",
     [(ACT, "            estado = max((e[4] for e in efs), key=lambda s: _PEOR[s])", "            estado = min((e[4] for e in efs), key=lambda s: _PEOR[s])")], [T188]),
    ("AC09", "maestro desactivado no marcado",
     [(ACT, "                        if obj is not None and not obj[\"enabled\"]]", "                        if obj is not None and False]")], [T188]),
    ("AC10", "una fila por efecto (sin varias)",
     [(ACT, "            \"varias\": len(categorias) > 1,", "            \"varias\": False,")], [T188]),
    ("AC11", "rol de cuenta invertido en transferencias",
     [(ACT, "                rol = \"ORIGEN\" if c[\"importe\"] < 0 else \"DESTINO\"", "                rol = \"DESTINO\" if c[\"importe\"] < 0 else \"ORIGEN\"")], [T188]),
    ("AC12", "total ignora los filtros",
     [(ACT, "    total = sesion.uno(\"SELECT count(*) \" + _FROM + \"WHERE \" + \" AND \".join(cond), params)[0]",
       "    total = sesion.uno(\"SELECT count(*) \" + _FROM + \"WHERE h.estado = 'ACTIVO'\")[0]")], [T188]),
    ("AC13", "cliente: la busqueda respeta el periodo (debe ir a todo el historial)",
     [(M_ACT, "  const rango = q ? null : rangoPeriodo(p, hoyIso);", "  const rango = rangoPeriodo(p, hoyIso);")], [J_ACT]),
    ("AC14", "cliente: importe tratado como texto",
     [(M_ACT, "    q: q && !importe ? q : null,", "    q: q || null,")], [J_ACT]),
    ("AC15", "cliente: transferencia con signo",
     [(M_ACT, "  if (r.tipo === 'INGRESO') return `+${total}`;\n  return total;", "  if (r.tipo === 'INGRESO') return `+${total}`;\n  return `−${total}`;")], [J_ACT]),
    ("AC16", "cliente: «tu parte» inventada sin reparto",
     [(M_ACT, "  return 'Sin indicar';\n", "  return formatearEur(r.importe_total ?? '0');\n")], [J_ACT]),
    ("AC17", "cliente: fallo de red como lista vacia",
     [(M_ACTS, "        {carga.fase === 'OK' && carga.filas.length === 0 && !(buscando && textoVigente === '') ? (",
       "        {(carga.fase === 'ERROR' || (carga.fase === 'OK' && carga.filas.length === 0)) && !(buscando && textoVigente === '') ? (")], [J_ACT]),
    # ---------------------------------------------------------------- RE resultado del mes (A9)
    ("RE01", "lo sin indicar cuenta como propio",
     [(INI, "            else:  # NO_DISPONIBLE\n                resto = delta\n", "            else:  # NO_DISPONIBLE\n                propios[tipo] += delta\n                resto = delta\n")], [T189]),
    ("RE02", "PARCIAL sin su parte propia",
     [(INI, "            if estado == \"PARCIAL\":\n                propios[tipo] += propio\n", "            if estado == \"PARCIAL\":\n")], [T189]),
    ("RE03", "COMPLETA cuenta el total y no la parte propia",
     [(INI, "            if estado == \"COMPLETA\":\n                propios[tipo] += propio\n", "            if estado == \"COMPLETA\":\n                propios[tipo] += delta\n")], [T189]),
    ("RE04", "otras monedas suman",
     [(INI, "    \"WHERE h.estado = 'ACTIVO' AND h.moneda = 'EUR' \"", "    \"WHERE h.estado = 'ACTIVO' \"")], [T189]),
    ("RE05", "hechos anulados suman",
     [(INI, "    \"WHERE h.estado = 'ACTIVO' AND h.moneda = 'EUR' \"", "    \"WHERE h.moneda = 'EUR' \"")], [T189]),
    ("RE06", "sin indicar contado por efecto y no por hecho",
     [(INI, "                pendiente[tipo][hecho_id] = pendiente[tipo].get(hecho_id, _CERO) + resto",
       "                pendiente[tipo][uuid.uuid4()] = resto")], [T189]),
    ("RE07", "resultado con el signo invertido",
     [(INI, "        \"resultado\": _texto(propios[\"INGRESO\"] - propios[\"GASTO\"]),", "        \"resultado\": _texto(propios[\"GASTO\"] - propios[\"INGRESO\"]),")], [T189]),
    ("RE08", "mes cerrado por la derecha (incluye el dia 1 del siguiente)",
     [(INI, "    \"AND h.fecha_hecho >= %(inicio)s AND h.fecha_hecho < %(fin)s \"", "    \"AND h.fecha_hecho >= %(inicio)s AND h.fecha_hecho <= %(fin)s \"")], [T189]),
    ("RE09", "diciembre: fin de mes mal calculado",
     [(FECHA, "    fin = dt.date(inicio.year + (inicio.month == 12), 1 if inicio.month == 12 else inicio.month + 1, 1)",
       "    fin = dt.date(inicio.year, 12 if inicio.month == 12 else inicio.month + 1, 1)")], [T184, T189]),
    ("RE10", "cliente: Ingresos con color de estado (D-HOME-03)",
     [(M_HOME, "    <Text testID={`mes-${campo}`} style={[importe.secondary, { color: c.textPrimary, fontVariant: ['tabular-nums'] }]}",
       "    <Text testID={`mes-${campo}`} style={[importe.secondary, { color: campo === 'ingresos' ? c.positive : c.textPrimary, fontVariant: ['tabular-nums'] }]}")], [J_ACT]),
    ("RE11", "cliente: linea sin indicar sin importe",
     [(M_INI, "    ...(g.n > 0 ? [`${g.n} ${g.n === 1 ? 'gasto' : 'gastos'} (${formatearEur(g.importe)})`] : []),",
       "    ...(g.n > 0 ? [`${g.n} ${g.n === 1 ? 'gasto' : 'gastos'}`] : []),")], [J_ACT]),
    ("RE12", "filtro de tipo de efecto: el reembolso (DERECHO_COBRO) cuenta como ingreso (A9: solo GASTO/INGRESO)",
     [(INI, "    \"SELECT e.hecho_id, e.tipo_efecto, e.importe_delta, e.estado_atribucion, \"",
       "    \"SELECT e.hecho_id, CASE WHEN e.tipo_efecto = 'DERECHO_COBRO' THEN 'INGRESO' ELSE e.tipo_efecto END, e.importe_delta, e.estado_atribucion, \""),
      (INI, "    \"AND e.tipo_efecto IN ('GASTO', 'INGRESO')\"", "    \"AND e.tipo_efecto IN ('GASTO', 'INGRESO', 'DERECHO_COBRO')\"")], [T189]),
    # ---------------------------------------------------------------- I13 contrato I13 v2 (producto)
    ("I13a", "un resolver de propuesta importa las senales",
     [(M_PREF, "from __future__ import annotations\n", "from __future__ import annotations\n\nfrom app.senales import lecturas as _senales  # noqa: F401\n")], [T154]),
    ("I13b", "el selector consume algo mas que el tipo de la sugerida",
     [("mobile/src/components/SelectorCategorias.tsx", "import type { SugeridaCategoria } from '../domain/senales';",
       "import type { SugeridaCategoria } from '../domain/senales';\nimport { MAX_SUGERIDAS } from '../domain/senales';")], [T154]),
    ("I13c", "los chips eligen con una llamada nueva a elegirNodo",
     [(M_REG, "                    onPress={() => selectorCategorias.props.onElegir(n)}", "                    onPress={() => elegirNodo(n)}")], [T154]),
    ("I13d", "el modulo de senales bloquea filas",
     [(SEN, "    return sesion.uno(\"SELECT 1 FROM gapto.terceros WHERE id = %s\", (tercero_id,)) is not None",
       "    return sesion.uno(\"SELECT 1 FROM gapto.terceros WHERE id = %s FOR SHARE\", (tercero_id,)) is not None")], [T154]),
    # ---------------------------------------------------------------- I13x comprobador I13 v2 (test_154)
    ("I13x1", "comprobador: sin cierre transitivo de imports del backend",
     [(T154, "        if any(m.startswith(\"app.senales\") for m in _cierre(grafo, nombre)):", "        if False:")], [T154]),
    ("I13x2", "comprobador: no exige el conjunto exacto de consumidores",
     [(T154, "    if consumidores != set(CONSUMIDORES_SENALES):", "    if not consumidores <= set(CONSUMIDORES_SENALES) | set(consumidores):")], [T154]),
    ("I13x3", "comprobador: el cliente movil deja de ser frontera y no se recorre nada",
     [(T154, "            if actual != CLI:  # el cliente HTTP es frontera: sus tipos de senales no son un consumo\n                pila.extend(",
       "            if False:\n                pila.extend(")], [T154]),
    ("I13x4", "comprobador: no detecta escritura en el modulo de senales",
     [(T154, "        if escritura.search(codigo):\n            v.append(f\"i: {f.name} escribe o bloquea\")", "        pass")], [T154]),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


TIEMPO_MAXIMO_S = 900  # un mutante que cuelga la suite cuenta como no superada (se anota en el log)


def _ejecutar(cmd: list[str], cwd: pathlib.Path) -> int:
    """Ejecuta con tiempo maximo; al agotarlo mata el ARBOL de procesos (en
    Windows, npx deja vivo el node hijo si solo se mata el padre)."""
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        return proc.wait(timeout=TIEMPO_MAXIMO_S)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.kill()
        proc.wait()
        print(f"TIEMPO AGOTADO ({TIEMPO_MAXIMO_S} s): {' '.join(cmd[-3:])}", flush=True)
        return 124


def correr(tests: list[str]) -> int:
    py = [t for t in tests if not t.startswith("mobile/")]
    js = [t.removeprefix("mobile/") for t in tests if t.startswith("mobile/")]
    rc = 0
    if py:
        rc = rc or _ejecutar([sys.executable, "-m", "pytest", *py, "-q", "-x", "-p", "no:cacheprovider", "--rootdir=tests/api"], RAIZ)
    if js:
        npx = shutil.which("npx") or "npx"
        rc = rc or _ejecutar([npx, "jest", "--silent", "--runInBand", *js], RAIZ / "mobile")
    return rc


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
    solo = None
    if "--solo" in sys.argv:
        solo = set(sys.argv[sys.argv.index("--solo") + 1].split(","))
    elegidos = [m for m in MUTANTES if solo is None or m[0] in solo]
    preflight = sorted({t for m in elegidos for t in m[3]})  # exactamente los discriminantes (nodeids incluidos)
    if correr(preflight) != 0:
        sys.exit("PREFLIGHT ROJO: no se muta nada.")
    veredictos = []
    for mid, desc, cambios, tests in elegidos:
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
        veredictos.append((mid, v if ok else "NO_CLASIFICABLE", ",".join(pathlib.Path(t).name for t in tests), desc))
    for v in veredictos:
        print(*v, sep=" | ")
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    print(f"RESUMEN {muertos} / {len(veredictos)} muertos")
    sys.exit(0 if muertos == len(veredictos) else 1)


if __name__ == "__main__":
    main()
