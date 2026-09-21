# ============================================================
# GAPTO MOBILE 2027
# Fichero: rv3_p5.py
# Ruta: scripts/mutantes/rv3_p5.py
# Descripcion: Arnes de mutacion de RV3 / P5 (transformacion V3 -> 0330).
#   Cada mutante declara su transformacion textual exacta sobre
#   scripts/migration_v3/rv3_p5_transformacion.py y su test DISCRIMINANTE.
#   Un mutante solo esta MUERTO si cae su discriminante; si solo caen tests
#   colaterales se informa DUDOSO. El arbol del repositorio NUNCA se modifica:
#   cada mutante se ejecuta sobre una copia temporal (tests/migration +
#   scripts/migration_v3), de modo que un aborto no puede dejar codigo mutado.
#   Antes de mutar se exige que la suite de la copia sin mutar este VERDE.
#   Los tests fisicos usan GAPTO_RV3_IMPORT_URL si esta definida.
#
# Uso:
#   python scripts/mutantes/rv3_p5.py            # todos
#   python scripts/mutantes/rv3_p5.py M30 M33    # subconjunto
#
# Version: 0.12.0 (M120..M126: P5 v0.18.0, respuestas A-F; M105 reanclado)
# Version: 0.11.0 (M111..M119: P5 v0.17.0, respuestas del propietario; M92/M93 reanclados)
# Version: 0.10.0 (M85..M110: P5 v0.16.0, dominio 5 reglas financieras y versiones)
# Version: 0.9.0 (M80..M84: P5 v0.15.0, capacidades, direcciones y coordenadas)
# Version: 0.8.0 (M75..M79: P5 v0.14.0, clasificacion de registros)
# Version: 0.7.0 (M70..M74: P5 v0.13.0, arbol de categorias D2-E)
# Version: 0.6.0 (M66..M69: P5 v0.12.0, cuarta ronda S20)
# Version: 0.5.0 (M61..M65: P5 v0.11.0, dominio 10)
# Version: 0.4.0 (M58..M60: P5 v0.10.0, tercera ronda S20)
# Version: 0.3.0 (M52..M57: P5 v0.9.0, dominio 9)
# Version: 0.2.0 (M48..M51: P5 v0.8.0, segunda ronda S20)
# Version: 0.1.0 (M30..M40 P5 v0.6.0 respuestas S20; M41..M47 P5 v0.7.0 dominio 8B)
# ============================================================
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
OBJ = "scripts/migration_v3/rv3_p5_transformacion.py"
T9 = "tests/migration/test_rv3_009_p5_s20_decisiones.py"
T10 = "tests/migration/test_rv3_010_p5_dominio8b.py"
T11 = "tests/migration/test_rv3_011_p5_dominio9.py"
T12 = "tests/migration/test_rv3_012_p5_dominio10.py"
T13 = "tests/migration/test_rv3_013_p5_categorias.py"
T14 = "tests/migration/test_rv3_014_p5_clasificacion.py"
T15 = "tests/migration/test_rv3_015_p5_capacidades_direcciones.py"
T16 = "tests/migration/test_rv3_016_p5_dominio5.py"

MUTANTES = {
    "M30": ("gate de la fuente suplementaria siempre abierto",
            [('    if ARQ_FUENTE_DECISIONES_ESTADO == "APROBADA":\n', '    if True:\n')],
            T9 + "::test_fuente_suplementaria_falla_cerrada_fuera_de_lab"),
    "M31": ("decision que contradice V3 sin corrige_v3 aceptada",
            [('and not it.get("corrige_v3"):', 'and False:')],
            T9 + "::test_decision_que_contradice_v3_exige_correccion_explicita"),
    "M32": ("reparto que no suma 100 aceptado",
            [('!= Decimal(100) or \\', '!= Decimal(100) and False or \\')],
            T9 + "::test_reparto_no_100_y_actor_desconocido_fallan"),
    "M33": ("financiador no demostrado sustituido por el proveedor V3",
            [('        if cp in FINANCIADOR_NO_DEMOSTRADO:\n', '        if False:\n')],
            T9 + "::test_financiador_no_demostrado_es_null_sin_rol"),
    "M34": ("vigencia PROPUESTA aceptada fuera de laboratorio",
            [('if PARTICIPACION_FIN_VIGENCIA_ESTADO != "CONFIRMADA" and not ds.modo_lab:', 'if False:')],
            T9 + "::test_participacion_fin_self_vigencia_propuesta_solo_en_lab"),
    "M35": ("participacion de financiacion inferida sin decision",
            [('    if (co, cl) not in PARTICIPACION_FIN_SELF:\n        ds.ledger.append({"regla": "D8-H", "origen": origen})\n        return\n', ''),
             ('desde = PARTICIPACION_FIN_SELF[(co, cl)]', 'desde = PARTICIPACION_FIN_SELF.get((co, cl))')],
            T9 + "::test_financiacion_sin_decision_no_recibe_participacion"),
    "M36": ("tipo de financiacion decidido ignorado",
            [('    if cp in TIPO_FINANCIACION_DECIDIDO:\n        return', '    if False:\n        return')],
            T9 + "::test_tipo_decidido_prevalece_y_prestamo_con_vivienda_sin_garantia"),
    "M37": ("garantia creada para financiacion no HIPOTECA",
            [('        if tipo == "HIPOTECA" and viv:\n', '        if viv:\n')],
            T9 + "::test_tipo_decidido_prevalece_y_prestamo_con_vivienda_sin_garantia"),
    "M38": ("conflicto de vigencia anterior al inicio no elevado",
            [('        if fecha_inicio and str(desde) < str(fecha_inicio):\n', '        if False:\n')],
            T9 + "::test_vigencia_anterior_al_inicio_se_eleva"),
    "M39": ("configuracion de cuentas devuelta a PROPUESTA",
            [('CONFIG_CUENTAS_ESTADO = "CONFIRMADA"', 'CONFIG_CUENTAS_ESTADO = "PROPUESTA"')],
            T9 + "::test_configuracion_confirmada_en_produccion"),
    "M40": ("persona suplementaria sin mapeo a su registro origen",
            [('        ds.mapear(CONT_DECISIONES, clave, "terceros", tid, "tercero", confianza="VALIDADA")\n', '')],
            T9 + "::test_todo_destino_tiene_mapeo_a_registro_existente"),
    "M41": ("derecho indeterminado abierto con saldo 0",
            [('"importe_original_documentado": None, "saldo_apertura": None, "fecha_inicio_seguimiento": None,',
              '"importe_original_documentado": None, "saldo_apertura": Decimal("0"), "fecha_inicio_seguimiento": FECHA_INICIO_LEDGER,')],
            T10 + "::test_indeterminada_nunca_cero"),
    "M42": ("transitoria cobrada tras el corte aceptada",
            [('or cobros[0][1] >= FECHA_INICIO_LEDGER:', ':')],
            T10 + "::test_transitoria_cobrada_tras_el_corte_falla"),
    "M43": ("canon de transitorias no comprobado",
            [('    if (trans_n, trans_total) != CANON_TRANSITORIAS:\n', '    if False:\n')],
            T10 + "::test_canon_de_transitorias"),
    "M44": ("principal de Universidad inventado desde los cobros",
            [('            sub.update(saldo_apertura=Decimal("0"), fecha_inicio_seguimiento=FECHA_INICIO_LEDGER,\n',
              '            sub.update(importe_original_documentado=CANON_UNIVERSIDAD, saldo_apertura=Decimal("0"), fecha_inicio_seguimiento=FECHA_INICIO_LEDGER,\n')],
            T10 + "::test_liquidada_sin_principal_nunca_inventa_principal"),
    "M45": ("cobros de evidencia sin mapeo",
            [('        for eo, ec in origenes[1:]:\n', '        for eo, ec in []:\n')],
            T10 + "::test_trazabilidad_y_evidencia_vinculada"),
    "M46": ("contraparte desconocida sustituida por el propietario",
            [('            ds.ledger.append({"regla": "D8B-C", "origen": f"{co}/{cl}", "derecho": d["id"]})\n',
              '            sub["contraparte_actor_id"] = ds.self_id\n            ds.ledger.append({"regla": "D8B-C", "origen": f"{co}/{cl}", "derecho": d["id"]})\n')],
            T10 + "::test_abierto_saldo_igual_a_importe_y_contraparte_desconocida_null"),
    "M47": ("transitoria con importe distinto del cobro aceptada",
            [('if co != _GC and _importe_v3(fuente, ctx, co, cl) != cobros[0][0]:', 'if False:')],
            T10 + "::test_transitoria_con_importe_distinto_falla"),
    "M48": ("financiador decidido por el propietario ignorado",
            [('            if fdec is not None:\n                fin_actor', '            if False:\n                fin_actor')],
            T9 + "::test_financiador_decidido_y_vigencia_justificada"),
    "M49": ("vigencia anterior al inicio sin justificacion no elevada",
            [('            if not dec.get("justificacion"):\n', '            if False:\n')],
            T9 + "::test_vigencia_anterior_al_inicio_se_eleva"),
    "M50": ("vigencia de la participacion del derecho fijada al corte",
            [('desde = fechas[0] if d["genera"] else min((f for f in fechas if f), default=None)', 'desde = FECHA_INICIO_LEDGER')],
            T10 + "::test_participacion_del_derecho_100_propietario_con_fecha_de_origen"),
    "M51": ("filas relacionadas por el propietario sin vincular",
            [('        for vo, vc in d.get("vinculados", []):\n', '        for vo, vc in []:\n')],
            T10 + "::test_vinculado_relacionado_por_el_propietario"),
    "M52": ("aporte estimado convertido en capital invertido de apertura",
            [('"capital_invertido_apertura": None, "fecha_capital_invertido_apertura": None,\n            "estado": estado',
              '"capital_invertido_apertura": Decimal(str(v("aporte_estimado"))), "fecha_capital_invertido_apertura": v("fecha_inicio"),\n            "estado": estado')],
            T11 + "::test_posicion_sin_padre_con_gestor_v3_y_sin_capital_inventado"),
    "M53": ("tipo_producto propuesto aceptado fuera de laboratorio",
            [('        if TIPO_PRODUCTO_ESTADO != "CONFIRMADA":\n', '        if False:\n')],
            T11 + "::test_tipo_producto_propuesto_falla_fuera_de_lab"),
    "M54": ("vigencia del objetivo inventada con fecha_inicio",
            [('fila = {"id": oid, "inversion_entidad_id": eid, "vigente_desde": None,',
              'fila = {"id": oid, "inversion_entidad_id": eid, "vigente_desde": v("fecha_inicio"),')],
            T11 + "::test_objetivos_version_sin_vigencia_inventada"),
    "M55": ("fila V3 cuenta duplicada como inversion",
            [('        if (cont, ci) in CUENTAS_DERIVADAS:\n', '        if False:\n')],
            T11 + "::test_cuenta_v3_no_se_duplica_como_inversion"),
    "M56": ("incoherencia del ROI objetivo no comprobada",
            [('- roi) > Decimal("0.01"):', '- roi) > Decimal("999999"):')],
            T11 + "::test_roi_objetivo_incoherente_falla"),
    "M57": ("gestor discrepante con dealer aceptado",
            [('        if prov and dealer and prov != dealer:\n', '        if False:\n')],
            T11 + "::test_gestor_discrepante_falla_s20"),
    "M58": ("contraparte V3 aceptada sin validar el contrato",
            [('            _validar_inquilino(fuente, ctx, co, cl, pk, d["id"])\n', '')],
            T10 + "::test_contraparte_persona_v3_validada_como_inquilino"),
    "M59": ("participacion de inversion fijada al corte",
            [('"porcentaje": Decimal(100), "vigente_desde": str(v("fecha_inicio")),',
              '"porcentaje": Decimal(100), "vigente_desde": FECHA_INICIO_LEDGER,')],
            T11 + "::test_participacion_100_propietario_desde_fecha_inicio"),
    "M60": ("declaracion del propietario sobre el tipo perdida",
            [('                                          NOTA_TIPO_PRODUCTO.get(ci)) if x) or None})',
              '                                          None) if x) or None})')],
            T11 + "::test_cerrada_sin_fecha_ni_motivo_inventados"),
    "M61": ("sustitucion de participante con vigencias solapadas",
            [('desde = max(inicio, _dia(inact[(per, rolv)]))', 'desde = inicio')],
            T12 + "::test_participantes_self_y_sustitucion_sin_solape"),
    "M62": ("persona propia convertida en tercero del contrato",
            [('            if fu.uuid_origen("public.personas", per) in persona_propia:\n', '            if False:\n')],
            T12 + "::test_participantes_self_y_sustitucion_sin_solape"),
    "M63": ("fecha de inicio validada ignorada",
            [('inicio = FECHA_INICIO_CONTRATO_VALIDADA.get(ck, v("fecha_inicio"))', 'inicio = v("fecha_inicio")')],
            T12 + "::test_fecha_validada_prevalece_y_origen_se_conserva"),
    "M64": ("total_inversion no comprobado",
            [('!= dv("total_inversion"):', '!= dv("total_inversion") and False:')],
            T12 + "::test_valoraciones_por_metodo_y_total_comprobado"),
    "M65": ("objeto de alquiler desconocido convertido en OTRO",
            [('tipo = TIPO_CONTRATO_V3.get(str(v("objeto_alquiler")))', 'tipo = TIPO_CONTRATO_V3.get(str(v("objeto_alquiler")), "OTRO")')],
            T12 + "::test_valor_v3_sin_mapping_falla"),
    "M66": ("duplicado de captura creado como segunda vigencia",
            [('                parts = {k: p for k, p in parts.items() if k != dup}\n', '')],
            T12 + "::test_duplicado_de_captura_una_sola_vigencia_y_origen_fusionado"),
    "M67": ("duplicado de captura sin comprobar coherencia",
            [('raise ErrorP5("S1_DUPLICADO_CAPTURA_INCOHERENTE", f"{cpt}/{dup}")', 'pass')],
            T12 + "::test_duplicado_de_captura_una_sola_vigencia_y_origen_fusionado"),
    "M68": ("fianza abierta con saldo 0 en lugar de la fianza",
            [('"importe_original_documentado": Decimal(str(fz)), "saldo_apertura": Decimal(str(fz)),',
              '"importe_original_documentado": Decimal(str(fz)), "saldo_apertura": Decimal("0"),')],
            T12 + "::test_fianza_obligacion_abierta_con_inquilino_principal"),
    "M69": ("repercusion a actor que no es inquilino",
            [('raise ErrorP5("S1_REPERCUSION_NO_INQUILINO", f"{origen} {ak}")', 'pass')],
            T12 + "::test_servicio_repercutible_validado_contra_el_contrato"),
    "M70": ("categorias propuestas aceptadas fuera de laboratorio",
            [('    if CATEGORIAS_ESTADO != "CONFIRMADA":\n        if not ds.modo_lab:\n            raise ErrorP5("S20_CATEGORIAS"',
              '    if False:\n        if not ds.modo_lab:\n            raise ErrorP5("S20_CATEGORIAS"')],
            T13 + "::test_propuesta_falla_cerrada_fuera_de_lab"),
    "M71": ("jerarquia del arbol aplanada",
            [('"parent_id": ids.get(ruta[:-1]), "nombre": nombre', '"parent_id": None, "nombre": nombre')],
            T13 + "::test_categorias_trazadas_con_jerarquia_ambito_y_orden"),
    "M72": ("nodo del arbol sin mapeo a su registro origen",
            [('        ds.mapear(CONT_ARBOL, clave, "categorias_financieras", cid, "categoria")\n', '')],
            T13 + "::test_categorias_trazadas_con_jerarquia_ambito_y_orden"),
    "M73": ("ambito de ingreso no distinguido",
            [('ambito = "INGRESO" if ruta[0] in RAICES_INGRESO else "GASTO"', 'ambito = "GASTO"')],
            T13 + "::test_categorias_trazadas_con_jerarquia_ambito_y_orden"),
    "M74": ("duplicado del arbol no detectado",
            [('            raise ErrorP5("S7_ARBOL_DUPLICADO", " > ".join(ruta))', '            pass')],
            T13 + "::test_arbol_mal_formado_o_duplicado_falla"),
    "M75": ("tipo heterogeneo sin decision clasificado por defecto",
            [('        raise ErrorP5("S20_CLASIFICACION_REGISTRO", clave)', '        return ("NULL", None)')],
            T14 + "::test_tipo_heterogeneo_sin_decision_falla_s20"),
    "M76": ("decision por registro ignorada frente al tipo",
            [('    if clave in regs:\n        v = regs[clave]', '    if False:\n        v = regs[clave]')],
            T14 + "::test_registro_decidido_prevalece_y_tipo_resuelve_el_resto"),
    "M77": ("desglose sin comprobar el total",
            [('                if sum(x for _, x in r[1]) != Decimal(str(tot)):', '                if False:')],
            T14 + "::test_desglose_debe_cuadrar"),
    "M78": ("decision sobre registro inexistente aceptada",
            [('            raise ErrorP5("S8_CLASIFICACION_SIN_ORIGEN", clave)', '            pass')],
            T14 + "::test_ruta_no_canonica_y_registro_inexistente_fallan"),
    "M79": ("naturaleza FUERA tratada como categoria",
            [('    if tipo.startswith("FUERA"):\n        return ("FUERA"', '    if False:\n        return ("FUERA"')],
            T14 + "::test_registro_decidido_prevalece_y_tipo_resuelve_el_resto"),
    "M80": ("capacidades deducidas: todo el catalogo en vez de las declaradas",
            [('        for cod in c["codigos"]:\n', '        for cod in CAPACIDADES_CATALOGO:\n')],
            T15 + "::test_capacidades_solo_las_declaradas"),
    "M81": ("capacidad sobre cuenta inexistente aceptada",
            [('            raise ErrorP5("S8_DECISION_SIN_ORIGEN", f"capacidad {c[\'id\']} -> {c[\'origen\']}")',
              '            continue')],
            T15 + "::test_capacidad_sobre_cuenta_inexistente_falla"),
    "M82": ("localidad ambigua resuelta eligiendo la primera",
            [('    if len(cand) > 1:\n        raise ErrorP5("S7_LOCALIDAD_AMBIGUA", origen)\n', '')],
            T15 + "::test_localidad_ambigua_falla_cerrado"),
    "M83": ("localidad inexistente convertida en direccion sin localidad",
            [('    if not cand:\n        raise ErrorP5("S8_LOCALIDAD_SIN_MAESTRO", origen)\n',
              '    if not cand:\n        return None\n')],
            T15 + "::test_localidad_inexistente_falla_cerrado"),
    "M84": ("coordenadas sin redondeo a 6 decimales",
            [('    q = lambda v: Decimal(str(v)).quantize(_Q6, rounding=ROUND_HALF_UP)', '    q = lambda v: Decimal(str(v))')],
            T15 + "::test_coordenadas_manuales_redondeadas_a_6_decimales"),
    # ---- dominio 5 (P5 v0.16.0): reglas financieras y versiones
    "M85": ("RODANTE generalizado a toda recurrencia",
            [("rodante=(co, cl) in RODANTES_VALIDADOS)", "rodante=True)")],
            T16 + "::test_rodante_solo_para_el_caso_validado"),
    "M86": ("RODANTE con ventana relativa inventada desde rango V3",
            [("    if rodante:\n        fecha_modo, dd, dh = \"ANCLA\", None, None", "    if False:\n        fecha_modo, dd, dh = \"ANCLA\", None, None")],
            T16 + "::test_rodante_solo_para_el_caso_validado"),
    "M87": ("inactivatedon -> vigente_hasta sin restar el dia",
            [("    hasta = _dia(ina, -1)\n    if hasta < desde:", "    hasta = _dia(ina, 0)\n    if hasta < desde:")],
            T16 + "::test_fin_dia_anterior_a_la_inactivacion"),
    "M88": ("fin desconocido -> regla abierta (NULL = vigente)",
            [("        raise PendienteD5(\"S6\", \"D5_FIN_NO_DEMOSTRADO\", \"activo=false sin inactivatedon\")", "        return desde, None, notas")],
            T16 + "::test_fin_desconocido_o_anterior_al_inicio_pendiente"),
    "M89": ("fecha posterior a captura/pago aceptada como inicio",
            [("        elif (cre is not None and ini > cre) or (ult is not None and ini > ult):", "        elif False:")],
            T16 + "::test_inicio_no_demostrado_no_crea_regla"),
    "M90": ("createon como sustituto del inicio",
            [("        desde = ini\n", "        desde = cre or ini\n")],
            T16 + "::test_gasto_ordinario_calendario_ventana"),
    "M91": ("ahorro remunerado como gasto",
            [("                v, notas = _version(ds, co, cl, f, ctx, \"TRANSFERENCIA\")", "                v, notas = _version(ds, co, cl, f, ctx, \"GASTO\")")],
            T16 + "::test_ahorro_es_transferencia_sin_gasto"),
    "M92": ("aportacion a inversion como gasto",
            [("        tipo = fz.get(\"tipo\") or (\"GASTO\" if co == G else \"INGRESO\")", "        tipo = (\"GASTO\" if co == G else \"INGRESO\")")],
            T16 + "::test_aportacion_fusion_n1_versiones_contiguas"),
    "M93": ("fusion N:1 copiada como dos reglas",
            [("    FUSIONES = ([FUSION_MEDIOLANUM] if FUSION_MEDIOLANUM else [])", "    FUSIONES = ([] if FUSION_MEDIOLANUM else [])")],
            T16 + "::test_aportacion_fusion_n1_versiones_contiguas"),
    "M94": ("versiones no contiguas aceptadas",
            [("        if a[2][\"vigente_hasta\"] is None or _dia(a[2][\"vigente_hasta\"], 1) != b[2][\"vigente_desde\"]:", "        if False:")],
            T16 + "::test_fusion_con_hueco_o_incompatible_falla"),
    "M95": ("tipo de hecho Isa fabricado sin decision (S1 ignorado)",
            [("                if ISA_TIPO_HECHO_DECIDIDO is None:\n                    raise PendienteD5", "                if False:\n                    raise PendienteD5")],
            T16 + "::test_isa_pendiente_s1_sin_decision"),
    "M96": ("cobro de derecho admitido como INGRESO",
            [("ISA_TIPOS_ADMITIDOS = {\"REEMBOLSO\", \"GENERACION_DERECHO_OBLIGACION\"}", "ISA_TIPOS_ADMITIDOS = {\"REEMBOLSO\", \"GENERACION_DERECHO_OBLIGACION\", \"INGRESO\"}")],
            T16 + "::test_isa_como_ingreso_rechazado"),
    "M97": ("renta duplicada (contrato + ingreso como dos reglas)",
            [("        disp[\"FUSIONADA\"].append((f\"{I}/{kl}+{C}/{ck}\", rid))\n        hechos.add((I, kl))", "        disp[\"FUSIONADA\"].append((f\"{I}/{kl}+{C}/{ck}\", rid))")],
            T16 + "::test_renta_n1_contrato_mas_ingreso"),
    "M98": ("regla_renta_id no completado",
            [("        con[\"regla_renta_id\"] = rid", "        pass")],
            T16 + "::test_renta_n1_contrato_mas_ingreso"),
    "M99": ("vigencia de renta desde el ingreso V3 y no desde el contrato validado",
            [("desde=con[\"fecha_inicio\"])", "desde=None)")],
            T16 + "::test_renta_n1_contrato_mas_ingreso"),
    "M100": ("importe cero/desconocido convertido en FIJO",
             [("    if imp.estado != fu.CONOCIDO or imp.valor is None or Decimal(str(imp.valor)) <= 0:", "    if imp.estado != fu.CONOCIDO and False:")],
             T16 + "::test_importe_cero_o_desconocido_no_es_fijo"),
    "M101": ("transferencia/aportacion presupuestable",
             [("        return None, False\n    if r[0] == \"FUERA\":", "        return None, True\n    if r[0] == \"FUERA\":")],
             T16 + "::test_ahorro_es_transferencia_sin_gasto"),
    "M102": ("importe_referencia_lado rellenado por conveniencia",
             [("\"moneda\": moneda, \"importe_referencia_lado\": None,", "\"moneda\": moneda, \"importe_referencia_lado\": \"SALIDA\" if flujo == \"TRANSFERENCIA\" else None,")],
             T16 + "::test_ahorro_es_transferencia_sin_gasto"),
    "M103": ("contenedor presupuestario G-V3-03 convertido en regla",
             [("            disp[\"EXCLUIDA_D11\"].append(f\"{co}/{cl}\")\n            continue", "            disp[\"EXCLUIDA_D11\"].append(f\"{co}/{cl}\")")],
             T16 + "::test_exclusiones_y_pendientes_de_familia"),
    "M104": ("compra financiada duplicada como regla de gasto",
             [("            disp[\"EXCLUIDA_D8\"].append(f\"{co}/{cl}\")\n            continue", "            disp[\"EXCLUIDA_D8\"].append(f\"{co}/{cl}\")")],
             T16 + "::test_exclusiones_y_pendientes_de_familia"),
    "M105": ("cuota de prestamo tambien tratada como regla (doble expectativa)",
             [("            ds.ledger.append({\"regla\": \"D5-T\", \"origen\": f\"{co}/{cl}\"})\n            continue", "            ds.ledger.append({\"regla\": \"D5-T\", \"origen\": f\"{co}/{cl}\"})")],
             T16 + "::test_exclusiones_y_pendientes_de_familia"),
    "M106": ("gasto a plazos como regla sin decidir su naturaleza",
             [("                raise PendienteD5(\"S20\", \"D5_GASTO_A_PLAZOS_NATURALEZA\", f\"cuotas={g('cuotas').valor}\")", "                pass")],
             T16 + "::test_exclusiones_y_pendientes_de_familia"),
    "M107": ("version sin mapeo a su origen",
             [("            ds.mapear(co, cl, \"regla_versiones\", vid, rol, tipo=\"FUSIONADO\" if len(vorig) > 1 else \"DIVIDIDO\")", "            pass")],
             T16 + "::test_trazabilidad_y_determinismo"),
    "M108": ("ventana invertida/fuera de rango aceptada",
             [("    return (a, b) if 1 <= a <= b <= 31 else None", "    return (a, b)")],
             T16 + "::test_rango_no_representable_no_se_deforma"),
    "M109": ("activo=true con inactivatedon cierra la regla",
             [("    if act.valor is True:\n", "    if act.valor is True and ina is None:\n")],
             T16 + "::test_activo_con_inactivatedon_contradictorio_regla_abierta"),
    "M110": ("SEMESTRAL como intervalo 1",
             [("\"SEMESTRAL\": (\"MENSUAL\", 6)", "\"SEMESTRAL\": (\"MENSUAL\", 1)")],
             T16 + "::test_semestral_es_mensual_intervalo_6_y_anual"),
    # ---- P5 v0.17.0: respuestas del propietario 2026-09-21
    "M111": ("solape de fusion no truncado al inicio del sucesor",
             [("                prev[2][\"vigente_hasta\"] = fin", "                pass")],
             T16 + "::test_fusion_propietario_solape_trunca_al_inicio_del_sucesor"),
    "M112": ("fusiones decididas por el propietario ignoradas (reglas duplicadas)",
             [("    FUSIONES = ([FUSION_MEDIOLANUM] if FUSION_MEDIOLANUM else []) + list(FUSIONES_PROPIETARIO)", "    FUSIONES = ([FUSION_MEDIOLANUM] if FUSION_MEDIOLANUM else [])")],
             T16 + "::test_fusion_propietario_solape_trunca_al_inicio_del_sucesor"),
    "M113": ("firma de fusion sin entidad de origen",
             [("v[\"categoria_id\"], ent_v,", "v[\"categoria_id\"], None,")],
             T16 + "::test_fusion_propietario_hueco_o_firma_distinta_falla"),
    "M114": ("inicio confirmado ignorado",
             [("        if clave in INICIO_CONFIRMADO:", "        if False:")],
             T16 + "::test_inicio_confirmado_por_el_propietario"),
    "M115": ("fin por modificacion restando un dia (excluye la ultima ocurrencia)",
             [("        return desde, mod, notas", "        return desde, _dia(mod, -1), notas")],
             T16 + "::test_fin_por_fecha_de_modificacion_decidida"),
    "M116": ("fecha de modificacion usada como fin sin decision",
             [("    if ina is None and clave in FIN_POR_MODIFICACION:", "    if ina is None:")],
             T16 + "::test_fin_por_fecha_de_modificacion_decidida"),
    "M117": ("compra financiada abierta inactiva aceptada",
             [("                    or g(\"activo\") is not True:", "                    or False:")],
             T16 + "::test_compra_financiada_abierta_incoherente_no_se_crea"),
    "M118": ("compra financiada abierta registrada como cerrada",
             [("            \"estado\": \"ACTIVA\" if abierta is not None else \"CERRADA\",", "            \"estado\": \"CERRADA\",")],
             T16 + "::test_compra_financiada_decidida_abierta_y_cerrada"),
    "M119": ("saldo de apertura = capital total en vez de pendiente",
             [("            abierta = pend\n", "            abierta = capital\n")],
             T16 + "::test_compra_financiada_decidida_abierta_y_cerrada"),
    # ---- P5 v0.18.0: respuestas A-F del propietario
    "M120": ("inicio por creacion decidido ignorado",
             [("        elif clave in INICIO_POR_CREACION:", "        elif False:")],
             T16 + "::test_inicio_por_creacion_decidido"),
    "M121": ("createon posterior al ultimo pago aceptado como inicio",
             [("            if cre is None or (ult is not None and cre > ult):", "            if cre is None:")],
             T16 + "::test_inicio_por_creacion_decidido"),
    "M122": ("cobro parcial convertido en regla",
             [("        if (co, cl) in COBRO_PARCIAL_NO_REGLA:", "        if False:")],
             T16 + "::test_cobro_parcial_no_es_regla"),
    "M123": ("cuota de prestamo sin excluir (pendiente/regla)",
             [("and _texto(pr) and CUOTA_PRESTAMO_SIN_REGLA:", "and _texto(pr) and False:")],
             T16 + "::test_exclusiones_y_pendientes_de_familia"),
    "M124": ("cuota de prestamo sin financiacion aceptada",
             [("                raise ErrorP5(\"S8_HUERFANO\", f\"{co}/{cl} prestamo_id={_texto(pr)}\")", "                pass")],
             T16 + "::test_cuota_de_prestamo_sin_financiacion_falla"),
    "M125": ("compra cancelada registrada como liquidada",
             [("(\"CANCELADA\" if cancelada else \"LIQUIDADA\")", "\"LIQUIDADA\"")],
             T16 + "::test_compra_financiada_cancelada"),
    "M126": ("cancelacion incoherente aceptada",
             [("        if cancelada and not (g(\"activo\") is False and g(\"cuotas_restantes\") not in (None, 0)):", "        if False:")],
             T16 + "::test_compra_financiada_cancelada"),
}


def _copia() -> Path:
    d = Path(tempfile.mkdtemp(prefix="rv3mut_"))
    for sub in ("scripts/migration_v3", "tests/migration"):
        shutil.copytree(RAIZ / sub, d / sub, ignore=shutil.ignore_patterns("__pycache__"))
    return d


def _pytest(d: Path, objetivo: str) -> tuple[int, str]:
    # test_rv3_000 audita el arbol real del repositorio: no aplica a la copia parcial.
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", objetivo,
                        "--ignore=tests/migration/test_rv3_000_repo_sin_datos_v3.py"],
                       cwd=d, capture_output=True, text=True)
    return r.returncode, (r.stdout.strip().splitlines() or ["(sin salida)"])[-1]


def main(sel: list[str]) -> int:
    t0 = time.time()
    base = _copia()
    rc, res = _pytest(base, "tests/migration")
    print(f"[{time.strftime('%H:%M:%S')}] linea base: {res}", flush=True)
    shutil.rmtree(base, ignore_errors=True)
    if rc != 0 or " passed" not in res:
        print("ABORTO: la suite sin mutar no esta verde")
        return 2
    vivos = 0
    for mid in (sel or list(MUTANTES)):
        desc, cambios, disc = MUTANTES[mid]
        d = _copia()
        try:
            f = d / OBJ
            src = f.read_bytes().decode("utf-8")
            for a, b in cambios:
                if src.count(a) != 1:
                    print(f"{mid}: TRANSFORMACION NO APLICABLE ({src.count(a)} coincidencias) -> DUDOSO")
                    vivos += 1
                    break
                src = src.replace(a, b)
            else:
                f.write_bytes(src.encode("utf-8"))
                rd, _ = _pytest(d, disc)
                rt, rest = _pytest(d, "tests/migration")
                if rd != 0:
                    v = "MUERTO"
                elif rt != 0:
                    v, vivos = "DUDOSO (solo colaterales)", vivos + 1
                else:
                    v, vivos = "VIVO", vivos + 1
                print(f"[{time.strftime('%H:%M:%S')}] {mid} {v:<26} {desc} | suite: {rest}", flush=True)
        finally:
            shutil.rmtree(d, ignore_errors=True)
    print(f"RESULTADO: {'OK' if vivos == 0 else 'FALLO'} vivos/dudosos={vivos} ({time.time() - t0:.1f} s)")
    return 0 if vivos == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
