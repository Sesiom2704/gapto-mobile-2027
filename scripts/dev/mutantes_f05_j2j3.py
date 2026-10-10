# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f05_j2j3.py
# Ruta: scripts/dev/mutantes_f05_j2j3.py
# Descripcion: Arnes de mutacion de F05-03/F05-04 J2+J3 (mandato §3: un
#   mutante por guarda nueva o modificada, con tabla guarda -> mutante ->
#   test que lo mata). Mismo motor que mutantes_f05_02.py (D-181, D-192,
#   D-193, WM 12C.2):
#     - cada mutante declara sustituciones de texto exacto (UNA ocurrencia) y
#       sus discriminantes (fichero o nodeid);
#     - journal durable ANTES de tocar el primer byte; si al arrancar hay un
#       journal pendiente: restaura, verifica y aborta;
#     - preflight verde de todos los discriminantes antes del primer mutante;
#     - tras cada mutante se restaura y se verifica la identidad byte a byte;
#     - veredicto unico: MUERTO | VIVO | NO_CLASIFICABLE.
#   Las guardas de §1.5 (preferencias) viven en mutantes_f05_02.py
#   (PF30..PF38). Equivalentes documentados (no se mutan): el filtro de owner
#   del contrato de elegibilidad (redundante con FORCE RLS) y la guarda de
#   cierre (ck_cuentas__cierre_deshabilita hace que toda cuenta cerrada este
#   deshabilitada, motivo previo).
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable> python scripts/dev/mutantes_f05_j2j3.py [--solo ID,ID]
#   No ejecutar en paralelo con otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F05-03/F05-04 J2 §1.1: EL01..EL08)
# Version: 0.2.0 (F05-03/F05-04 J2 §1.2: FF01..FF05, fecha funcional del owner)
# Version: 0.3.0 (F05-03/F05-04 J2 §1.3/§1.4: TE01..TE07 terceros, CX01..CX03
#   contextos. Equivalentes documentados: `existe_entidad` en el alta de
#   contexto (la PK fisica de entidades da el mismo
#   IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION) y el filtro tipo CONTEXTO del
#   bloqueo (la lectura posterior ya filtra))
# Version: 0.4.0 (F05-03/F05-04 J2 §1.6: PL02..PL21 plantillas y acciones; el
#   advisory PLANTILLAS (PL01) lo discrimina la bateria serial de concurrencia)
# Version: 0.5.0 (F05-03/F05-04 J2 §1.7: RG02..RG15 registro por tipo. Equivalente
#   documentado (RG06): la comprobacion MISMA_CUENTA del adaptador, porque OP-10 rechaza
#   igual con MISMA_CUENTA. El orden INVERSIONES -> cuenta (RG01) lo discrimina la
#   bateria serial de locks)
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f05_j2j3.journal.json"

T167 = "tests/api/test_167_f05_02_resolver.py"
T168 = "tests/api/test_168_f05_02_writers.py"
T174 = "tests/api/test_174_f05_03_elegibilidad_cuentas.py"
ELEG = "backend/app/comun/elegibilidad_cuentas.py"
EJEC = "backend/app/api/ejecucion_gasto_pagado.py"
RES = "backend/app/preferencias/resolver.py"
T177 = "tests/api/test_177_f05_04_terceros.py"
T178 = "tests/api/test_178_f05_04_contextos.py"
TSERV = "backend/app/terceros/servicio.py"
TLECT = "backend/app/terceros/lecturas.py"
CSERV = "backend/app/contextos/servicio.py"
T179 = "tests/api/test_179_f05_03_plantillas.py"
PSRV = "backend/app/plantillas/servicio.py"
PPROP = "backend/app/plantillas/propuesta.py"
T180 = "tests/api/test_180_f05_04_registro.py"
REGI = "backend/app/api/ejecucion_registro.py"
DTOR = "backend/app/api/dto_registro.py"
CAPM = "backend/app/api/captura_magnitudes.py"
TRAD = "backend/app/api/traductor_registro.py"
T176 = "tests/api/test_176_f05_03_fecha_funcional.py"
FF = "backend/app/comun/fecha_funcional.py"
PSERV = "backend/app/preferencias/servicio.py"
PLECT = "backend/app/preferencias/lecturas.py"

MUTANTES = [
    # --- §1.1 contrato unico de elegibilidad (R1, C1)
    ("EL01", "elegibilidad sin la guarda de habilitada",
     [(ELEG, "    if not enabled:\n        return DESHABILITADA\n", "")],
     [f"{T174}::test_motivos_en_orden_fijo"]),
    ("EL02", "elegibilidad sin la regla de ledger",
     [(ELEG, "    if inicio_ledger is not None and inicio_ledger > fecha:\n        return LEDGER_POSTERIOR\n", "")],
     [f"{T174}::test_motivos_en_orden_fijo"]),
    ("EL03", "ledger exige fecha estrictamente posterior al inicio",
     [(ELEG, "    if inicio_ledger is not None and inicio_ledger > fecha:",
       "    if inicio_ledger is not None and inicio_ledger >= fecha:")],
     [f"{T174}::test_motivos_en_orden_fijo"]),
    ("EL04", "operacion GASTO exige la capacidad equivocada",
     [(ELEG, '    "GASTO": "PAGAR_GASTO",', '    "GASTO": "RECIBIR_INGRESO",')],
     [f"{T174}::test_matriz_r1_sobre_las_cuentas_sinteticas"]),
    ("EL05", "OP-10 destino exige TRANSFERIR_SALIDA",
     [(ELEG, '    "TRANSFERENCIA_DESTINO": "TRANSFERIR_ENTRADA",', '    "TRANSFERENCIA_DESTINO": "TRANSFERIR_SALIDA",')],
     [f"{T174}::test_matriz_r1_sobre_las_cuentas_sinteticas"]),
    ("EL06", "COMPRA_TARJETA implica PAGAR_GASTO",
     [(ELEG, '"AND k.capacidad_codigo = %s) AS capacidad "',
       '"AND k.capacidad_codigo IN (%s, \'COMPRA_TARJETA\')) AS capacidad "')],
     [f"{T174}::test_compra_tarjeta_y_domiciliar_no_implican_pagar_gasto"]),
    ("EL07", "confirmacion VS-01 sin la regla unica (solo moneda)",
     [(EJEC, "    if motivo is not None:\n        raise ErrorMotor(CodigoError.CUENTA_DESCONOCIDA",
       "    if False:\n        raise ErrorMotor(CodigoError.CUENTA_DESCONOCIDA")],
     [f"{T174}::test_gasto_pagado_con_cuenta_no_elegible"]),
    ("EL08", "preferencia de INGRESO validada con la regla de GASTO",
     [(RES, '    return "INGRESO" if fila is not None and fila[0] == "INGRESO" else "GASTO"',
       '    return "GASTO"')],
     [f"{T168}::test_preferencia_de_ingreso_exige_recibir_ingreso"]),
    # --- §1.2 fecha funcional del owner (C6)
    ("FF01", "hoy_owner ignora la zona del owner",
     [(FF, "    return zona(None if fila is None else fila[0])", "    return zona(None)")],
     [f"{T176}::test_hoy_owner"]),
    ("FF02", "hoy en UTC (sin convertir a la zona)",
     [(FF, "    return instante.astimezone(zona_owner_).date()", "    return instante.date()")],
     [f"{T176}::test_hoy_owner"]),
    ("FF03", "zona no reconocida cae a UTC y no a Europe/Madrid",
     [(FF, "    return ZoneInfo(ZONA_POR_DEFECTO)", '    return ZoneInfo("UTC")')],
     [f"{T176}::test_hoy_owner"]),
    ("FF04", "lista de preferencias con current_date de la sesion",
     [(PLECT, "    hoy = hoy_owner(sesion, reloj)", '    hoy = sesion.uno("SELECT current_date")[0]')],
     [f"{T176}::test_preferencias_evaluan_la_cuenta_con_hoy_owner"]),
    ("FF05", "writer de preferencias sin el reloj inyectado",
     [(PSERV, '        sesion, hoy_owner(sesion, reloj), operacion_de_tipo(sesion, v["tipo_hecho_id"])',
       '        sesion, hoy_owner(sesion), operacion_de_tipo(sesion, v["tipo_hecho_id"])')],
     [f"{T176}::test_preferencias_evaluan_la_cuenta_con_hoy_owner"]),
    # --- §1.3 terceros (C2, R5)
    ("TE01", "alta de tercero sin el advisory TERCEROS",
     [(TSERV, "    repo.tomar_advisory(sesion)\n    visible = _validos(nombre, naturaleza)\n    if isinstance(visible, Rechazo):\n        return visible\n    existente",
       "    visible = _validos(nombre, naturaleza)\n    if isinstance(visible, Rechazo):\n        return visible\n    existente")],
     [f"{T177}::test_el_writer_toma_el_advisory_terceros"]),
    ("TE02", "alta de tercero idempotente con otro contenido",
     [(TSERV, "        return Resultado(tercero=existente, idempotente=True) if igual else Rechazo(IDENTIDAD_REUTILIZADA)",
       "        return Resultado(tercero=existente, idempotente=True)")],
     [f"{T177}::test_mismo_uuid_con_otro_contenido"]),
    ("TE03", "tercero sin control de row_version",
     [(TSERV, '    if fila["row_version"] != row_version:\n        return Rechazo(VERSION_DESFASADA)\n', "")],
     [f"{T177}::test_editar_desactivar_reactivar_con_version_y_auditoria"]),
    ("TE04", "PK de otro owner sin traduccion por identidad",
     [(TSERV, '_CONSTRAINTS = {"pk_terceros": IDENTIDAD_REUTILIZADA}', "_CONSTRAINTS = {}")],
     [f"{T177}::test_uuid_de_otro_owner_sin_efectos"]),
    ("TE05", "trigger de naturaleza sin traduccion por firma",
     [(TSERV, "        return NATURALEZA_NO_ADMITIDA\n", "        return None\n")],
     [f"{T177}::test_naturaleza_contra_tercero_personas_traducida_por_firma"]),
    ("TE06", "candidatos sin los inactivos",
     [(TLECT, '    return [x for x in _todos(sesion) if normalizar(x["nombre"]) == clave]',
       '    return [x for x in _todos(sesion) if normalizar(x["nombre"]) == clave and x["enabled"]]')],
     [f"{T177}::test_candidatos_por_normalizacion_incluidos_inactivos_y_homonimos_validos"]),
    ("TE07", "tercero sin limite de longitud del nombre",
     [(TSERV, "LONGITUD_MAXIMA = 160", "LONGITUD_MAXIMA = 1000")],
     [f"{T177}::test_longitud_del_nombre_es_regla_de_dominio_sin_intentar_escribir"]),
    # --- §1.4 contextos (C2, R5)
    ("CX01", "alta de contexto sin el advisory CONTEXTOS",
     [(CSERV, "    repo.tomar_advisory(sesion)\n    visible = _validos(nombre, tipo_contexto, fecha_inicio, fecha_fin)",
       "    visible = _validos(nombre, tipo_contexto, fecha_inicio, fecha_fin)")],
     [f"{T178}::test_advisory_contextos_y_nunca_inversiones"]),
    ("CX02", "contexto con fechas invertidas",
     [(CSERV, "    if desde is not None and hasta is not None and hasta < desde:\n        return Rechazo(ENTRADA_INVALIDA)\n", "")],
     [f"{T178}::test_entrada_invalida"]),
    ("CX03", "contexto sin control de row_version",
     [(CSERV, '    if fila["row_version"] != row_version:\n        return Rechazo(VERSION_DESFASADA)\n', "")],
     [f"{T178}::test_editar_desactivar_reactivar"]),
    # --- §1.6 plantillas y acciones rapidas (A1/A2/A3, R1/R3, A11)
    ("PL02", "plantilla de tipo no admitido",
     [(PSRV, "    if codigo not in TIPOS_ADMITIDOS:\n        return Rechazo(TIPO_NO_ADMITIDO)\n", "")],
     [f"{T179}::test_tipos_admitidos_y_rechazados"]),
    ("PL03", "plantilla sin valor propuesto",
     [(PSRV, "        return Rechazo(SIN_VALOR)\n", "        pass\n")],
     [f"{T179}::test_sin_valor_y_campos_no_admitidos"]),
    ("PL04", "categoria de la plantilla sin ambito por tipo",
     [(PSRV, "        if fila is None or not fila[0] or not ambito_compatible(codigo, fila[1]):",
       "        if fila is None or not fila[0]:")],
     [f"{T179}::test_categoria_por_ambito_del_tipo_y_cuenta_por_capacidad"]),
    ("PL05", "tercero de la plantilla sin elegibilidad",
     [(PSRV, "            return Rechazo(TERCERO_NO_ELEGIBLE)\n", "            pass\n")],
     [f"{T179}::test_tercero_y_contexto_admitidos_y_entidad_solo_contexto"]),
    ("PL06", "entidad de la plantilla no limitada a CONTEXTO",
     [(PSRV, '        if fila is None or not fila[0] or fila[1] != "CONTEXTO":\n            return Rechazo(ENTIDAD_NO_CONTEXTO)',
       '        if fila is None or not fila[0]:\n            return Rechazo(ENTIDAD_NO_CONTEXTO)')],
     [f"{T179}::test_tercero_y_contexto_admitidos_y_entidad_solo_contexto"]),
    ("PL07", "cuenta de la plantilla sin la regla unica",
     [(PSRV, "        return Rechazo(CUENTA_NO_ELEGIBLE)\n", "        pass\n")],
     [f"{T179}::test_categoria_por_ambito_del_tipo_y_cuenta_por_capacidad"]),
    ("PL08", "alta sin unicidad de nombre",
     [(PSRV, "    otra = _repetida(sesion, v[\"nombre\"], plantilla_id)\n    if otra is not None:\n        return Rechazo(NOMBRE_REPETIDO, {\"plantilla_id\": otra[\"id\"]})\n    rechazo = _escribir(sesion, lambda: repo.insertar_plantilla",
       "    rechazo = _escribir(sesion, lambda: repo.insertar_plantilla")],
     [f"{T179}::test_caso9_nombre_repetido_normalizado_y_reactivacion"]),
    ("PL09", "reactivacion sin volver a comprobar el nombre",
     [(PSRV, "    otra = _repetida(sesion, fila[\"nombre\"], plantilla_id)\n    if otra is not None:\n        return Rechazo(NOMBRE_REPETIDO, {\"plantilla_id\": otra[\"id\"]})\n",
       "")],
     [f"{T179}::test_caso9_nombre_repetido_normalizado_y_reactivacion"]),
    ("PL10", "desactivar plantilla sin cascada a sus acciones",
     [(PSRV, "    accs = repo.acciones_de_plantilla_bloqueadas(sesion, plantilla_id)\n", "    accs = []\n")],
     [f"{T179}::test_caso10_desactivar_en_cascada_y_reactivar_sin_volver_a_inicio"]),
    ("PL11", "acciones sin limite de 3",
     [(PSRV, "    if len(habilitadas) >= LIMITE_ACCIONES:\n        return Rechazo(ACCION_LIMITE_ALCANZADO)\n", "")],
     [f"{T179}::test_caso8_limite_de_tres_y_una_por_plantilla"]),
    ("PL12", "dos accesos de la misma plantilla",
     [(PSRV, "        return Rechazo(ACCION_PLANTILLA_YA_EN_INICIO)\n", "        pass\n")],
     [f"{T179}::test_caso8_limite_de_tres_y_una_por_plantilla"]),
    ("PL13", "acceso a una plantilla desactivada",
     [(PSRV, '    if plantilla is None or not plantilla["enabled"]:\n        return Rechazo(ACCION_PLANTILLA_NO_DISPONIBLE)',
       '    if plantilla is None:\n        return Rechazo(ACCION_PLANTILLA_NO_DISPONIBLE)')],
     [f"{T179}::test_accion_sobre_plantilla_desactivada_o_ajena"]),
    ("PL14", "icono de acceso sin la biblioteca publicada",
     [(PSRV, "    if not icono_valido(icono_key):\n        return Rechazo(ICONO_ACCION_NO_VALIDO)\n    habilitadas", "    habilitadas")],
     [f"{T179}::test_accion_icono_nombre_idempotencia"]),
    ("PL15", "reordenar sin exigir el conjunto completo",
     [(PSRV, "    if not pedidas or len(set(pedidas)) != len(pedidas) or set(pedidas) != set(persistidas):",
       "    if not pedidas or len(set(pedidas)) != len(pedidas) or not set(pedidas) <= set(persistidas):")],
     [f"{T179}::test_reordenar_atomico_y_conjunto_completo"]),
    ("PL16", "RLS 42501 sin traduccion estable",
     [(PSRV, '        if exc.sqlstate == "42501":\n            return Rechazo(REFERENCIA_NO_DISPONIBLE)\n', "")],
     [f"{T179}::test_rls_traducida_a_codigo_estable_si_falta_la_validacion"]),
    ("PL17", "idempotencia del alta sin comparar el contenido",
     [(PSRV, "        return Resultado(plantilla=existente, idempotente=True) if igual else Rechazo(IDENTIDAD_REUTILIZADA)",
       "        return Resultado(plantilla=existente, idempotente=True)")],
     [f"{T179}::test_mismo_uuid_con_otro_contenido"]),
    ("PL18", "propuesta aplica una categoria no elegible",
     [(PPROP, "            if fila is not None and fila[0] and ambito_compatible(tipo, fila[1]):\n                campos[\"categoria\"]",
       "            if True:\n                campos[\"categoria\"]")],
     [f"{T179}::test_caso5_categoria_deshabilitada_queda_pendiente_sin_fallback"]),
    ("PL19", "propuesta aplica una cuenta no elegible",
     [(PPROP, "            if motivo_cuenta(sesion, p[\"cuenta_default_id\"], tipo, fecha) is None:",
       "            if True:")],
     [f"{T179}::test_caso4_cuenta_no_disponible_cae_a_la_capa_siguiente"]),
    ("PL20", "propuesta con plantilla de otro tipo o desactivada",
     [(PPROP, '    if plantilla_id is not None and (p is None or not p["enabled"] or p["tipo_hecho_id"] != tipo_id):',
       "    if plantilla_id is not None and p is None:")],
     [f"{T179}::test_plantilla_de_otro_tipo_o_desactivada_no_aplica"]),
    ("PL21", "preferencias sin el contexto que aplica la plantilla",
     [(PPROP, '        categoria_id if categoria_id is not None else (campos["categoria"] or {}).get("valor"))',
       "        categoria_id)")],
     [f"{T179}::test_caso2_solo_categoria_con_cuenta_de_una_preferencia"]),
    # --- §1.7 registro por tipo (A2..A6, A9; R1..R3; C3)
    ("RG02", "gasto sin revalidar el tercero bajo lock",
     [(EJEC, "            rechazo = validar_tercero(sesion, intencion.tercero_id) or validar_contexto(sesion, intencion.contexto_id)",
       "            rechazo = validar_contexto(sesion, intencion.contexto_id)")],
     [f"{T180}::test_caso17_desactivado_entre_carga_y_confirmacion"]),
    ("RG03", "gasto sin revalidar el contexto bajo lock",
     [(EJEC, "            rechazo = validar_tercero(sesion, intencion.tercero_id) or validar_contexto(sesion, intencion.contexto_id)",
       "            rechazo = validar_tercero(sesion, intencion.tercero_id)")],
     [f"{T180}::test_caso17_desactivado_entre_carga_y_confirmacion"]),
    ("RG04", "ingreso sin la capacidad RECIBIR_INGRESO",
     [(REGI, '            rechazo_cuenta(sesion, intencion.cuenta_id, "INGRESO", intencion.fecha_hecho)\n', "")],
     [f"{T180}::test_ingreso_exige_recibir_ingreso_y_categoria_de_ingreso"]),
    ("RG05", "ingreso con la guarda C-a de GASTO",
     [(REGI, 'validar_categoria_y_magnitudes(sesion, intencion.categoria_id, "INGRESO",',
       'validar_categoria_y_magnitudes(sesion, intencion.categoria_id, "GASTO",')],
     [f"{T180}::test_caso3_ingreso_composicion_c14"]),
    ("RG07", "transferencia sin capacidad de origen",
     [(REGI, '            rechazo_cuenta(sesion, intencion.cuenta_origen_id, "TRANSFERENCIA_ORIGEN", intencion.fecha_hecho)\n', "")],
     [f"{T180}::test_caso8_liquidacion_de_la_tarjeta_y_capacidades"]),
    ("RG08", "transferencia sin capacidad de destino",
     [(REGI, '            rechazo_cuenta(sesion, intencion.cuenta_destino_id, "TRANSFERENCIA_DESTINO", intencion.fecha_hecho)\n', "")],
     [f"{T180}::test_caso8_liquidacion_de_la_tarjeta_y_capacidades"]),
    ("RG09", "transferencia sin la guarda de replay propia",
     [(REGI, "            if not _replay_transferencia(sesion, intencion):", "            if False:")],
     [f"{T180}::test_guarda_de_replay_propia_de_op10"]),
    ("RG10", "guarda de replay que ignora la nota",
     [(REGI, "        and fila[2] == intencion.nota and fila[3] == intencion.moneda",
       "        and fila[3] == intencion.moneda"),
      (REGI, " and fila[9] == intencion.nota and fila[10] == intencion.nota", "")],
     [f"{T180}::test_guarda_de_replay_propia_de_op10"]),
    ("RG11", "nota sin canonicalizar",
     [(DTOR, "    limpio = valor.strip()\n    return limpio or None", "    return valor")],
     [f"{T180}::test_ingreso_sin_indicar_y_nota_canonica"]),
    ("RG12", "C07 ignora «No lo sé»",
     [(CAPM, "    no_lo_se = set(desconocidas)\n", "    no_lo_se = set()\n")],
     [f"{T180}::test_caso2_y_28_no_lo_se_sin_fila_de_magnitud"]),
    ("RG13", "contexto vinculado como principal",
     [(TRAD, '                          tipo_relacion="RELACIONADO_CON", principal=False, efecto_id=None),',
       '                          tipo_relacion="RELACIONADO_CON", principal=True, efecto_id=None),')],
     [f"{T180}::test_caso1_y_12_gasto_con_tercero_y_contexto"]),
    ("RG14", "tercero de ingreso con rol VENDEDOR",
     [(TRAD, 'ROL_TERCERO = {"GASTO": "VENDEDOR", "INGRESO": "OTRO"}', 'ROL_TERCERO = {"GASTO": "VENDEDOR", "INGRESO": "VENDEDOR"}')],
     [f"{T180}::test_caso3_ingreso_composicion_c14"]),
    ("RG15", "ingreso sin la guarda de fecha futura",
     [(REGI, "            if es_futura(sesion, intencion.fecha_hecho, reloj):\n                return RechazoRegistro(CODIGO_FECHA_FUTURA)\n            rechazo_cuenta(sesion, intencion.cuenta_id",
       "            rechazo_cuenta(sesion, intencion.cuenta_id")],
     [f"{T180}::test_fecha_futura_en_ingreso_y_transferencia"]),
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
    solo = None
    if "--solo" in sys.argv:
        solo = set(sys.argv[sys.argv.index("--solo") + 1].split(","))
    elegidos = [m for m in MUTANTES if solo is None or m[0] in solo]
    preflight = sorted({t.split("::")[0] for m in elegidos for t in m[3]})
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
