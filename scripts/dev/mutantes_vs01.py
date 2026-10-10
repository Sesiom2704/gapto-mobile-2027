# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_vs01.py
# Ruta: scripts/dev/mutantes_vs01.py
# Descripcion: Arnes de mutacion de VS-01 (adaptador HTTP + cliente movil).
#   Demuestra que los tests de tests/api y mobile/__tests__ discriminan los
#   mecanismos que afirman (WM 12C.2). Cumple D-181/D-192:
#     - cada mutante declara transformacion (texto exacto, 1 ocurrencia) y
#       discriminante (suite que debe fallar);
#     - E/S byte a byte; journal durable ANTES de tocar el primer byte;
#     - al arrancar, si hay journal pendiente: restaura, verifica y aborta;
#     - preflight verde de ambas suites antes del primer mutante;
#     - tras cada mutante se restaura y verifica identidad byte-exacta;
#     - un veredicto unico por mutante: MUERTO | VIVO | NO_CLASIFICABLE.
#   Requiere GAPTO_TEST_DATABASE_URL (base local desechable) y node_modules
#   instalados en mobile/. No es evidencia de proveedor.
#   v0.2.0 (F05-D003): A02 apunta a la financiacion sellada; mutantes nuevos
#   A11..A20 (lock de cuenta, lectura fuera de la transaccion, recalculo en
#   reintento, revalidacion antes de identidad, agregado exacto, fecha,
#   vigencia en la fecha del pago, importe de la propuesta, propuesta de
#   cuentas-pago, fail-closed de identidad) y M09..M12 (cliente).
#   v0.3.0 (F05 §18, tras F04-D051): se retira A15 junto con la guarda
#   `_agregado_sin_extras`; la propiedad la impone OP-22 y la discrimina
#   D050-M1 en scripts/mutantes/f04_d050.py.
#   v0.4.0 (F05-01 S6-WIRE+UI (este mandato)): M07 se reancla con la MISMA
#   semantica (un indeterminado se clasifica como rechazo definitivo) sobre la
#   linea que sustituye a la anterior en cliente.ts 0.3.0 (el mensaje
#   indeterminado se calcula una vez en `msgIndeterminado`). Nuevos U01..U06
#   del cliente de categorias (suite js): visibilidad en el registro,
#   error de carga que no selecciona «Sin categoria» (AJ-09), obligatoria que
#   bloquea, valor canonico con punto en el sellado, «Usar...» solo en nodo
#   elegible, aviso D-198 solo con padre y U07 (una categoria habilitada de
#   gasto no capturable se oculta en el registro, contra la decision de Moises
#   de mostrarla con su motivo: F09 §12.97.3, lamina R05). Censo: A01..A20 sin
#   A15 (19 py), M01..M12 y U01..U07 (19 js) = 38. Correccion de ejecucion:
#   `npx` se resuelve con shutil.which (en Windows es npx.cmd y subprocess sin
#   shell no lo encontraba: el preflight js fallaba con FileNotFoundError).
#   v0.5.0 (F05-01 S6-WIRE+UI (este mandato), commit 2): U08..U10 de las
#   acciones EDIT-* de Ajustes > Categorias (suite js): Editar orden envia N
#   llamadas (una por hermano) en lugar de UNA a reordenar con el conjunto
#   completo; «Desactivar» desactiva la rama sin confirmacion; reactivar en
#   cascada en el cliente (Q4: solo el nodo). M07 conserva su ancla (el
#   RECHAZADO del cliente ahora conserva `detalle`, fuera del ancla).
#   Censo: 19 py + M01..M12 y U01..U10 (22 js) = 41.
#   v0.6.0 (F05-01 S6-WIRE+UI, correctivo AJ-S6WIREUI-09): U11 (el selector
#   siempre afirma que las subcategorias se pueden usar: `usables` devuelve
#   true sin comprobar ningun descendiente elegible). Discriminante: suite js
#   (regcat.test.tsx, casos AJ-09).
#   Censo: 19 py + M01..M12 y U01..U11 (23 js) = 42.
#   v0.7.0 (F05-01 S7-MAG UI, hito 2; F05-D020, F09 §12.97.10): U12 (Editar
#   orden de magnitudes envia un SUBCONJUNTO en lugar del conjunto completo),
#   U13 (el reintento del alta NUEVA usa un magnitud_id NUEVO en vez del del
#   formulario: duplicaria) y U14 (deshabilitar reenvia solo ante un impacto
#   cambiado en lugar de pedir otra confirmacion, M15). Discriminante: suite
#   js (ajustes_magnitudes.test.tsx).
#   Censo: 19 py + M01..M12 y U01..U14 (26 js) = 45.
#   v0.8.0 (F05-01 S7-MAG UI correctivo AJ-S7MAGUI-02/03): U15 (ignora el
#   resultado de la recarga tras un comando y muestra el aviso de estado
#   actualizado aunque una lectura haya fallado) y U16 (con impacto visible
#   envia el primer POST con `confirmacion_impacto: null` sin hoja previa: el
#   servidor deshabilitaria sin confirmacion si el impacto desaparece).
#   Discriminante: suite js (ajustes_magnitudes.test.tsx).
#   Censo: 19 py + M01..M12 y U01..U16 (28 js) = 47.
#   v0.9.0 (F05-01 P7 · N3, AJ-P7BAT-04/12): U17 invierte la condicion del
#   aviso de nivel (`usables(actual) ?` -> `!usables(actual) ?`) en las dos
#   lineas (motivo «Desactivada» y resto de motivos): sin descendiente
#   elegible el aviso promete subcategorias usables. Discriminante: suite js;
#   el test que lo mata por asercion de texto es regcat «AJ-09 N3: aviso de
#   nivel sin descendiente elegible, motivo «Solo ingresos» (literal exacto)».
#   Censo: 19 py + M01..M12 y U01..U17 (29 js) = 48.
#   v0.10.0 (F05-02 B2; F05-D027 §42.7): un mutante por guarda de la
#   integracion de preferencias en REG-01. Cliente (suite js,
#   preferencias_registro.test.tsx): U18 vuelve el fallback de cuenta unica
#   sin filtro de moneda (AJ-B1-09); U19 sobrescribe un campo tocado
#   (D-PREF-03); U20 ofrece la tarjeta con «Sin categoria» (D-PREF-05); U21
#   edita con estado parcial (E05); U22 usa un UUID nuevo en cada reintento del
#   alta (R06); U23 vuelve a pedir la propuesta en el reintento del registro
#   (CC-02-4); U24 preselecciona una cuenta fuera de la lista (AJ-B1-11).
#   Backend (suite py, test_171): A21 la propuesta ignora el rechazo de la
#   guarda C-a y devuelve propuesta con una categoria no elegible.
#   Censo: 20 py + M01..M12 y U01..U24 (36 js) = 56.
#   v0.11.0 (F05-02 B3; lamina SET-PREF S01-S06): un mutante por guarda nueva
#   del cliente de Ajustes > Preferencias (suite js; los mata
#   ajustes_preferencias.test.tsx salvo U35): U25 «Guardar» habilitado sin
#   proponer nada (espejo del CHECK); U26 sin deteccion de la existente del
#   mismo ambito (S03: crearia otra); U27 el empate del servidor no lleva a la
#   existente (S03 por carrera); U28 VERSION_DESFASADA reintenta solo en vez de
#   recargar y avisar (S06); U29 la cuenta actual no disponible se puede
#   reenviar sin elegir; U30 editar envia la clave de tipo de hecho a NULL
#   (estado parcial, E05: la preferencia por tipo pasaria a general); U31
#   la marca «No disponible» la decide el cliente por la lista de REG-01 en
#   vez del servidor (D-PREF-04); U32 el selector lista categorias que REG-01 oculta (AJ-B1-10); U33 el
#   reintento del alta usa un UUID nuevo; U34 desactivar sin el row_version
#   cargado; U35 (AJ-B2-04, preferencias_registro.test.tsx) tras recargar sin
#   conflicto se muestra error en vez de volver a la tarjeta. Decision de
#   ejecucion: altas en este arnes (misma infraestructura js y mismo journal)
#   y no un arnes nuevo.
#   Censo: 20 py + M01..M12 y U01..U35 (47 js) = 67.
#
#   v0.12.0 (F05-03/F05-04 J2 §1.5; F05 §46.5 E3): texto protegido de U26
#   actualizado (preferenciaDeAmbito recibe el tipo GASTO de la lista). Mismo
#   mutante y mismo discriminante; censo sin cambios (67).
#   v0.13.0 (F05-03/F05-04 J2 §1.2; F05-D032 C6): A16 (fecha futura) pasa del
#   validador del DTO, retirado, a la guarda FECHA_FUTURA de la ejecucion con el
#   «hoy» del owner (mismo discriminante, test_151); el texto protegido de A12
#   incluye esa guarda (paso 3.0). Censo sin cambios (67).
#   v0.14.0 (F05-03/F05-04 J2 §2.5; F05 §46.4 R6): textos protegidos
#   actualizados por los cuatro ambitos de Ajustes › Preferencias y la
#   naturaleza del selector: U11 (`usables` con `p.naturaleza ?? 'GASTO'`),
#   U26 (la deteccion de la existente pasa a `preferenciaDeClave`; el mutante
#   anula la condicion que la activa), U28 (formularioDesde con las cuentas y
#   los tipos), U31 (textosPropone con el tipo) y U32 (visibleEnRegistro con
#   el tipo). Mismos discriminantes; censo sin cambios (67).
#   v0.15.0 (F05-03/F05-04 J2 §2.3): textos protegidos de M10 (la guarda de
#   fecha futura lleva el texto por tipo) y U03 (la obligatoria vacia NO
#   declarada «No lo sé»). Mismos discriminantes; censo sin cambios (67).
# Version: 0.15.0
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
JOURNAL = RAIZ / ".mutantes_vs01.journal.json"

PY = [sys.executable, "-m", "pytest", "tests/api", "-q", "-x", "-p", "no:cacheprovider", "--rootdir=tests/api"]
# En Windows `npx` es npx.cmd: subprocess sin shell no lo resuelve por nombre (se resuelve con which).
JS = [shutil.which("npx") or "npx", "jest", "--silent"]

# (id, fichero, texto_original, texto_mutado, suite_discriminante)
MUTANTES = [
    ("A01", "backend/app/api/traductor_gasto_pagado.py", "presupuestable=intencion.presupuestable", "presupuestable=True", "py"),
    ("A02", "backend/app/api/traductor_gasto_pagado.py", 'if intencion.financiacion.estado == "PROPUESTA_ACEPTADA":', "if True:", "py"),
    ("A03", "backend/app/api/traductor_gasto_pagado.py", 'if intencion.atribucion == "SOLO_MIO":', "if True:", "py"),
    ("A04", "backend/app/api/traductor_gasto_pagado.py", 'return uuid.uuid5(intencion, f"gapto.vs01.gasto_pagado.{rol}")', "return uuid.uuid4()", "py"),
    ("A05", "backend/app/api/lecturas_vs01.py", '"PARCIAL" if (sin_reparto or otra_moneda) else "CONFIRMADO"', '"CONFIRMADO"', "py"),
    ("A06", "backend/app/api/lecturas_vs01.py", "WHERE ef.moneda = 'EUR' AND ef.estado_atribucion = 'COMPLETA'", "WHERE ef.estado_atribucion = 'COMPLETA'", "py"),
    ("A07", "backend/app/api/app.py", "if not hmac.compare_digest(cabecera.encode(), esperado.encode()):", "if False:", "py"),
    ("A08", "backend/app/api/app.py", "    verificar_base_permitida(nombre, cfg)\n", "    pass\n", "py"),
    ("A09", "backend/app/api/dto_vs01.py", 'model_config = ConfigDict(extra="forbid", frozen=True)', 'model_config = ConfigDict(extra="ignore", frozen=True)', "py"),
    ("A10", "backend/app/api/errores_http.py", '"No se ha podido confirmar el registro. Puedes reintentar: no se duplicará.",\n        True,', '"No se ha podido confirmar el registro. Puedes reintentar: no se duplicará.",\n        False,', "py"),
    ('A11', 'backend/app/api/ejecucion_gasto_pagado.py', '"SELECT id FROM gapto.cuentas WHERE id = %s FOR NO KEY UPDATE"', '"SELECT id FROM gapto.cuentas WHERE id = %s"', 'py'),
    ('A12', 'backend/app/api/ejecucion_gasto_pagado.py', '        # 1. Lock contractual de la cuenta.\n        bloquear_cuenta(sesion, intencion.cuenta_id)\n        actor = leer_actor_self(sesion)\n\n        # 2. Identidad antes que cualquier revalidacion contextual.\n        ya_materializada = repo_hechos.leer_estado(sesion, intencion.intencion_id) is not None\n\n        if not ya_materializada:\n            # 3.0 Fecha funcional del owner (C6): nada futuro.\n            if es_futura(sesion, intencion.fecha_hecho, reloj):\n                return RechazoIntegracion(CODIGO_FECHA_FUTURA)\n            # 3. Intencion nueva: relectura bajo el lock.\n            _validar_cuenta_nueva(sesion, intencion)\n            # 4. Revalidacion de la propuesta sellada, en la fecha del pago.\n            if intencion.financiacion.estado == "PROPUESTA_ACEPTADA" and not participacion_self_100(\n                sesion, intencion.cuenta_id, actor, intencion.fecha_hecho\n            ):\n                return RechazoIntegracion(CODIGO_PROPUESTA_OBSOLETA)\n', '        # 1. Lock contractual de la cuenta.\n        actor = leer_actor_self(sesion)\n        _previa = participacion_self_100(sesion, intencion.cuenta_id, actor, intencion.fecha_hecho)\n        bloquear_cuenta(sesion, intencion.cuenta_id)\n\n        # 2. Identidad antes que cualquier revalidacion contextual.\n        ya_materializada = repo_hechos.leer_estado(sesion, intencion.intencion_id) is not None\n\n        if not ya_materializada:\n            # 3.0 Fecha funcional del owner (C6): nada futuro.\n            if es_futura(sesion, intencion.fecha_hecho, reloj):\n                return RechazoIntegracion(CODIGO_FECHA_FUTURA)\n            # 3. Intencion nueva: relectura bajo el lock.\n            _validar_cuenta_nueva(sesion, intencion)\n            # 4. Revalidacion de la propuesta sellada, en la fecha del pago.\n            if intencion.financiacion.estado == "PROPUESTA_ACEPTADA" and not _previa:\n                return RechazoIntegracion(CODIGO_PROPUESTA_OBSOLETA)\n', 'py'),
    ('A13', 'backend/app/api/ejecucion_gasto_pagado.py', '        datos = componer(intencion, actor)\n', "        _int = intencion\n        if not participacion_self_100(sesion, intencion.cuenta_id, actor, intencion.fecha_hecho):\n            _int = intencion.model_copy(update={'financiacion': __import__('app.api.dto_vs01', fromlist=['x']).FinanciacionNoDeterminada(estado='NO_DETERMINADA')})\n        datos = componer(_int, actor)\n", 'py'),
    ('A14', 'backend/app/api/ejecucion_gasto_pagado.py', '        if not ya_materializada:\n', '        if True:\n', 'py'),
    ('A16', 'backend/app/api/ejecucion_gasto_pagado.py', '            if es_futura(sesion, intencion.fecha_hecho, reloj):\n',
     '            if False:\n', 'py'),
    ('A17', 'backend/app/api/ejecucion_gasto_pagado.py', '                sesion, intencion.cuenta_id, actor, intencion.fecha_hecho\n            ):\n                return RechazoIntegracion', "                sesion, intencion.cuenta_id, actor, __import__('datetime').date.today()\n            ):\n                return RechazoIntegracion", 'py'),
    ('A18', 'backend/app/api/dto_vs01.py', '            and self.financiacion.importe != self.importe\n', '            and False\n', 'py'),
    ('A19', 'backend/app/api/lecturas_vs01.py', '"SELF_100" if participacion_self_100(sesion, f[0], actor, fecha) else "NO_DETERMINADA"', '"SELF_100"', 'py'),
    ('A20', 'backend/app/api/configuracion.py', '    if entorno != ENTORNO_UNICO_PERMITIDO:\n', '    if False:\n', 'py'),
    # ---------------------------------------------------------------- F05-02 B2 (backend)
    ("A21", "backend/app/preferencias/lecturas.py",
     "        if rechazo is not None:\n            return rechazo\n    return resolver(",
     "        if False:\n            return rechazo\n    return resolver(", "py"),
    ("M01", "mobile/src/state/useEnvioGasto.ts", "if (enVuelo.current) return; // doble tap", "if (false) return; // doble tap", "js"),
    ("M02", "mobile/src/state/useEnvioGasto.ts", "      if (selladaRef.current) {\n        // Intención", "      if (false) {\n        // Intención", "js"),
    ("M03", "mobile/src/domain/intencion.ts", "presupuestable: null,\n    soloMio", "presupuestable: true,\n    soloMio", "js"),
    ("M04", "mobile/src/domain/intencion.ts", "soloMio: false,", "soloMio: true,", "js"),
    ("M05", "mobile/App.tsx", "if (registrado) setRefresco((n) => n + 1);", "if (false) setRefresco((n) => n + 1);", "js"),
    ("M06", "mobile/src/state/useEnvioGasto.ts", "} else if (r.tipo === 'RECHAZADO') {", "} else if (false) {", "js"),
    ("M07", "mobile/src/api/cliente.ts", "      return { tipo: 'INDETERMINADO', mensaje: msgIndeterminado };\n    } catch {", "      return { tipo: 'RECHAZADO', codigo: 'X', mensaje: '' } as any;\n    } catch {", "js"),
    ("M08", "mobile/src/domain/importe.ts", "if (dec.length > 2) return { ok: false, motivo: 'DECIMALES' };", "", "js"),
    ('M09', 'mobile/src/domain/intencion.ts', "if (b.propuesta === 'SELF_100' && !b.propuestaRechazada) {", "if (b.propuesta === 'SELF_100') {", 'js'),
    ('M10', 'mobile/src/domain/intencion.ts', "  else if (b.fechaHecho > hoyIso) e.fecha = tipo === 'GASTO' ? 'Solo gastos ya ocurridos: la fecha no puede ser futura.' : 'Solo ingresos ya cobrados: la fecha no puede ser futura.';\n", '', 'js'),
    ('M11', 'mobile/src/screens/RegistroGastoScreen.tsx', '  }, [b.fechaHecho]);', '  }, []);', 'js'),
    ('M12', 'mobile/src/screens/HomeScreen.tsx', '          <Columna etiqueta="Gastos">\n            <EstadoDato estado="NO_DISPONIBLE" />\n          </Columna>', '          <Columna etiqueta="Gastos">\n            <CeldaGastos lectura={gasto} onReintentar={cargar} />\n          </Columna>', 'js'),
    # ---------------------------------------------------------------- F05-01 S6-WIRE+UI (cliente de categorias)
    ("U01", "mobile/src/domain/categoria.ts", "  if (elegible(n, naturaleza)) return true;\n  if (n.enabled", "  return true;\n  if (n.enabled", "js"),
    ("U02", "mobile/src/screens/RegistroGastoScreen.tsx", "    if (r.tipo !== 'OK') return setArbol({ fase: 'ERROR' });", "    if (r.tipo !== 'OK') { setB((x) => ({ ...x, categoria: { estado: 'SIN_CATEGORIA' } })); return setArbol({ fase: 'ERROR' }); }", "js"),
    ("U03", "mobile/src/domain/intencion.ts", "        if (m.obligatoria && !esDesconocida(b, m.magnitud_id)) em[m.magnitud_id] = ", "        if (false) em[m.magnitud_id] = ", "js"),
    ("U04", "mobile/src/domain/intencion.ts", "magnitudes.push(Object.freeze({ magnitud_id: m.magnitud_id, valor: r.valor }));", "magnitudes.push(Object.freeze({ magnitud_id: m.magnitud_id, valor: texto }));", "js"),
    ("U05", "mobile/src/components/SelectorCategorias.tsx", "          {actual && p.esSeleccionable(actual) ? (", "          {actual ? (", "js"),
    ("U06", "mobile/src/screens/NuevaCategoriaScreen.tsx", "        {padre !== null ? (\n          <View testID=\"aviso-d198\"", "        {true ? (\n          <View testID=\"aviso-d198\"", "js"),
    ("U07", "mobile/src/domain/categoria.ts", "  if (n.enabled && (n.ambito === naturaleza || n.ambito === 'AMBOS') && !n.capturable) return true;\n", "", "js"),
    # ---------------------------------------------------------------- F05-01 S6-WIRE+UI commit 2 (EDIT-* y Editar orden)
    ("U08", "mobile/src/screens/CategoriasAjustesScreen.tsx",
     "    const r = await p.cliente.reordenarCategorias({ parent_id: padre, hermanos: orden.map((n) => ({ id: n.id, row_version: n.row_version })) });",
     "    let r: any = null;\n    for (const n of orden) r = await p.cliente.reordenarCategorias({ parent_id: padre, hermanos: [{ id: n.id, row_version: n.row_version }] });",
     "js"),
    ("U09", "mobile/src/screens/CategoriasAjustesScreen.tsx",
     "<FilaAccion testID=\"accion-desactivar\" titulo=\"Desactivar\" critica onPress={() => setTarea({ tipo: 'DESACTIVAR' })} />",
     "<FilaAccion testID=\"accion-desactivar\" titulo=\"Desactivar\" critica onPress={() => void desactivar('RAMA')} />",
     "js"),
    ("U10", "mobile/src/screens/CategoriasAjustesScreen.tsx",
     "    const r = await p.cliente.reactivarCategoria(detalle.id, { row_version: detalle.row_version });\n",
     "    const r = await p.cliente.reactivarCategoria(detalle.id, { row_version: detalle.row_version });\n"
     "    for (const d of descendientes(arbol!, detalle.id).filter((x) => !x.enabled)) await p.cliente.reactivarCategoria(d.id, { row_version: d.row_version });\n",
     "js"),
    # ---------------------------------------------------------------- correctivo AJ-S6WIREUI-09
    ("U11", "mobile/src/components/SelectorCategorias.tsx",
     "  const usables = (n: CategoriaNodo) => !!arbol && tieneDescendienteElegible(arbol, n, p.naturaleza ?? 'GASTO');\n",
     "  const usables = (_n: CategoriaNodo) => true;\n",
     "js"),
    # ---------------------------------------------------------------- F05-01 S7-MAG UI (hito 2)
    ("U12", "mobile/src/components/MagnitudesCategoria.tsx",
     "      const r = await p.cliente.reordenarMagnitudes(cat.id, { asociaciones: conjuntoReordenar(orden) });\n",
     "      const r = await p.cliente.reordenarMagnitudes(cat.id, { asociaciones: conjuntoReordenar(orden.slice(1)) });\n",
     "js"),
    ("U13", "mobile/src/components/NuevaMagnitud.tsx",
     "      magnitud_id: idIntento,\n",
     "      magnitud_id: p.nuevoId(),\n",
     "js"),
    ("U14", "mobile/src/components/MagnitudesCategoria.tsx",
     "      if (nuevas) return setHoja({ tipo: 'DESHABILITAR', afectadas: nuevas, previas: confirmadas, cambiado: true });\n",
     "      if (nuevas) { await p.cliente.deshabilitarMagnitud(m.id, { row_version: m.row_version, confirmacion_impacto: nuevas.map((a) => a.id) }); return setHoja(null); }\n",
     "js"),
    ("U15", "mobile/src/components/MagnitudesCategoria.tsx",
     "    const verificado = await recargarTodo();\n",
     "    await recargarTodo(); const verificado = true;\n",
     "js"),
    ("U16", "mobile/src/components/MagnitudesCategoria.tsx",
     "              else setHoja({ tipo: 'DESHABILITAR', afectadas: visibles, previas: null, cambiado: false });\n",
     "              else void deshabilitar(m);\n",
     "js"),
    # ---------------------------------------------------------------- F05-01 P7 · N3 (microcopy AJ-S6WIREUI-09)
    ("U17", "mobile/src/components/SelectorCategorias.tsx",
     "                  ? `${actual.nombre} está desactivada y no se puede elegir. ${usables(actual) ? 'Sus subcategorías activas sí.' : 'Sus subcategorías tampoco se pueden elegir ahora. Elige otra categoría o registra sin categoría.'}`\n"
     "                  : `${actual.nombre} no se puede elegir (${p.motivo(actual)!.toLowerCase()}). ${usables(actual) ? 'Sus subcategorías sí.' : 'Sus subcategorías tampoco se pueden elegir ahora. Elige otra categoría o registra sin categoría.'}`}\n",
     "                  ? `${actual.nombre} está desactivada y no se puede elegir. ${!usables(actual) ? 'Sus subcategorías activas sí.' : 'Sus subcategorías tampoco se pueden elegir ahora. Elige otra categoría o registra sin categoría.'}`\n"
     "                  : `${actual.nombre} no se puede elegir (${p.motivo(actual)!.toLowerCase()}). ${!usables(actual) ? 'Sus subcategorías sí.' : 'Sus subcategorías tampoco se pueden elegir ahora. Elige otra categoría o registra sin categoría.'}`}\n",
     "js"),
    # ---------------------------------------------------------------- F05-02 B2 (preferencias en REG-01)
    ("U18", "mobile/src/domain/preferencias.ts",
     "      x = { ...x, cuentaId: null, cuentaOrigen: 'PENDIENTE', cuentaPropuesta: null, propuesta: null, propuestaRechazada: false };\n",
     "      x = lista.length === 1 ? { ...x, cuentaId: lista[0].cuenta_id, cuentaOrigen: 'INFERIDO', cuentaPropuesta: 'UNICA', propuesta: lista[0].propuesta_financiacion, propuestaRechazada: false } : { ...x, cuentaId: null, cuentaOrigen: 'PENDIENTE', cuentaPropuesta: null, propuesta: null, propuestaRechazada: false };\n",
     "js"),
    ("U19", "mobile/src/domain/preferencias.ts", "  if (b.cuentaOrigen !== 'USUARIO') {\n", "  if (true) {\n", "js"),
    ("U20", "mobile/src/domain/preferencias.ts",
     "  if (payload.categoria.estado !== 'CATEGORIA') return null;", "  if (false) return null;", "js"),
    ("U21", "mobile/src/domain/preferencias.ts",
     "    cuenta_default_id: c.cuenta ? f.cuenta : e.cuenta_default_id,\n    presupuestable_default: c.presupuestable ? f.presupuestable : e.presupuestable_default,\n",
     "    cuenta_default_id: c.cuenta ? f.cuenta : null,\n    presupuestable_default: c.presupuestable ? f.presupuestable : null,\n",
     "js"),
    ("U22", "mobile/src/components/GuardarPreferencia.tsx",
     "p.cliente.altaPreferencia({ id: idAlta, ...plan.contenido })",
     "p.cliente.altaPreferencia({ id: p.nuevoId(), ...plan.contenido })", "js"),
    ("U23", "mobile/src/screens/RegistroGastoScreen.tsx",
     '<BotonPrimario testID="reintentar" titulo="Reintentar" onPress={reintentar} />',
     "<BotonPrimario testID=\"reintentar\" titulo=\"Reintentar\" onPress={() => { editable.current = true; void pedirPropuesta(b.fechaHecho, categoriaActual.current, cuentas.fase === 'OK' ? cuentas.lista : []); return reintentar(); }} />",
     "js"),
    ("U24", "mobile/src/domain/preferencias.ts",
     "  if (p.cuenta && lista.some((x) => x.cuenta_id === p.cuenta!.valor)) {\n", "  if (p.cuenta) {\n", "js"),
    # ---------------------------------------------------------------- F05-02 B3 (Ajustes > Preferencias)
    ("U25", "mobile/src/domain/preferencias.ts",
     "  return f.cuenta !== null || f.presupuestable !== null;\n", "  return true;\n", "js"),
    ("U26", "mobile/src/screens/PreferenciasAjustesScreen.tsx",
     "      (vista.v === 'NUEVA' && datos && claveCompleta\n",
     "      (false && datos && claveCompleta\n", "js"),
    ("U27", "mobile/src/screens/PreferenciasAjustesScreen.tsx",
     "      if (otra) return setConflicto(otra);\n", "", "js"),
    ("U28", "mobile/src/screens/PreferenciasAjustesScreen.tsx",
     "      setForm(formularioDesde(actual, t === 'INGRESO' ? d.cuentasIngreso : d.cuentas, d.tipos)); // S06: la versión actual, sin reintento automático\n",
     "      return void guardar(); // reintento automatico\n", "js"),
    ("U29", "mobile/src/domain/preferencias.ts",
     "  if (f.cuenta !== null && typeof f.cuenta === 'object') r.push('CUENTA_NO_DISPONIBLE');\n", "", "js"),
    ("U30", "mobile/src/domain/preferencias.ts",
     "    return {\n      tipo_hecho_id: base.tipo_hecho_id,\n", "    return {\n      tipo_hecho_id: null,\n", "js"),
    ("U31", "mobile/src/screens/PreferenciasAjustesScreen.tsx",
     "                        propone={textosPropone(x, nombreCuenta, tipoX(x)).join(' · ')}\n                        noDisponible={x.cuenta_default_id !== null && cuentaNoDisponible(x)}\n",
     "                        propone={textosPropone(x, nombreCuenta, tipoX(x)).join(' · ')}\n                        noDisponible={x.cuenta_default_id !== null && nombreCuenta(x.cuenta_default_id) === null}\n",
     "js"),
    ("U32", "mobile/src/screens/PreferenciasAjustesScreen.tsx",
     "            esVisible={(n) => visibleEnRegistro(datos.arbol, n, tipoF)}\n", "            esVisible={() => true}\n", "js"),
    ("U33", "mobile/src/screens/PreferenciasAjustesScreen.tsx",
     "p.cliente.altaPreferencia({ id: idAlta!, ...contenido })", "p.cliente.altaPreferencia({ id: p.nuevoId(), ...contenido })", "js"),
    ("U34", "mobile/src/screens/PreferenciasAjustesScreen.tsx",
     "        ? await p.cliente.desactivarPreferencia(x.id, x.row_version)\n", "        ? await p.cliente.desactivarPreferencia(x.id, 1)\n", "js"),
    ("U35", "mobile/src/components/GuardarPreferencia.tsx",
     "    intento.current = null;\n    setFase({ f: 'EDITANDO' });\n  };\n\n  const tras",
     "    intento.current = null;\n    setFase({ f: 'ERROR' });\n  };\n\n  const tras", "js"),
]


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def correr(suite: str) -> int:
    if suite == "py":
        return subprocess.run(PY, cwd=RAIZ, capture_output=True).returncode
    return subprocess.run(JS, cwd=RAIZ / "mobile", capture_output=True).returncode


def recuperar_si_pendiente() -> bool:
    if not JOURNAL.exists():
        return False
    j = json.loads(JOURNAL.read_text(encoding="utf-8"))
    ruta = RAIZ / j["fichero"]
    original = bytes.fromhex(j["original_hex"])
    ruta.write_bytes(original)
    if sha(ruta.read_bytes()) != j["sha256"]:
        sys.exit("RECUPERACION FALLIDA: identidad no verificada")
    JOURNAL.unlink()
    return True


def main() -> None:
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    for suite in ("py", "js"):
        if correr(suite) != 0:
            sys.exit(f"PREFLIGHT ROJO en suite {suite}: no se muta nada.")
    veredictos = []
    for mid, fichero, a, b, suite in MUTANTES:
        ruta = RAIZ / fichero
        original = ruta.read_bytes()
        texto = original.decode("utf-8")
        if texto.count(a) != 1:
            veredictos.append((mid, "NO_CLASIFICABLE", "transformacion no aplicable"))
            continue
        JOURNAL.write_text(json.dumps({"fichero": fichero, "original_hex": original.hex(), "sha256": sha(original)}), encoding="utf-8")
        os.sync() if hasattr(os, "sync") else None
        try:
            ruta.write_bytes(texto.replace(a, b).encode("utf-8"))
            rc = correr(suite)
            v = "MUERTO" if rc != 0 else "VIVO"
        finally:
            ruta.write_bytes(original)
            ok = sha(ruta.read_bytes()) == sha(original)
            JOURNAL.unlink(missing_ok=True)
        veredictos.append((mid, v if ok else "NO_CLASIFICABLE", suite))
    for v in veredictos:
        print(*v)
    print("RESUMEN", sum(1 for v in veredictos if v[1] == "MUERTO"), "/", len(veredictos), "muertos")
    sys.exit(0 if all(v[1] == "MUERTO" for v in veredictos) else 1)


if __name__ == "__main__":
    main()
