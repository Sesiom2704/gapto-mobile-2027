# ============================================================
# GAPTO MOBILE 2027
# Fichero: mutantes_f06_02_03.py
# Ruta: scripts/dev/mutantes_f06_02_03.py
# Descripcion: Arnes de mutacion del bloque T3-F06 F06-02/03 (contratos de alquiler, servicios y terceros), partes
#   SERVIDOR y CLIENTE (mandato v1.2 §8; contrato N1 v1.2 §XII.3 «un mutante por guarda», mapa §1.5 de traduccion
#   fisica O-15 y fila C-31 del trigger aciclico). Mismo motor que mutantes_f06_01h.py (journal durable, restauracion
#   verificada por SHA-256, journal previo -> se restaura y se aborta NO-PASS, preflight verde, veredicto a disco con
#   fsync en cuanto se conoce, --solo, repeticiones).
#   Catalogo del SERVIDOR:
#     M-CON-nn   una guarda de §XII.3 cada uno (solape, partes, principal, YO, renta, vigencias, clausula, servicios,
#                roles, 0P, guarda §VII.1, OP-21, advisory, inactivos, uso del selector, orden de recursos);
#     M-FIS-nn   una fila del mapa §1.5 cada uno (O-15): la fila se quita de MAPA_FISICO, de modo que la violacion
#                fisica que fuerza el oraculo (test_306, que salta la validacion previa) deja de traducirse al
#                codigo del mapa; M-FIS-17 quita la firma de fn_check_jerarquia_aciclica() de FUNCIONES_TRIGGER (C-31).
#   NO_APLICA_SERVIDOR: guardas que viven solo en la base (GRANT/CHECK de 0351/0355) y no tienen codigo que mutar
#     aqui; se listan en NO_APLICA con su motivo y el mutante o test que las cubre (se imprimen y se cuentan aparte).
#   Catalogo del CLIENTE (mobile/): MC-CON-nn, con oraculos Jest (suites contratos_*.test.ts(x)).
#   Formato de cada mutante: (id, desc, [(fichero, viejo, nuevo), ...], [tests], equivalencia_o_None, repeticiones).
#   Las sustituciones se aplican en orden sobre el texto ya sustituido; cada `viejo` debe aparecer EXACTAMENTE una
#   vez en ese momento (si no, NO_CLASIFICABLE sin tocar el arbol). `repeticiones` (por defecto 1): n pasadas con el
#   arbol mutado; MUERTO solo si muere en todas. 3 en los que dependen de orden o tiempo y en todo el que use
#   test_307 (concurrencia con COMMIT real, GAPTO_F060203_CONCURRENCIA=1, en subproceso propio).
#   Tests: "tests/<ruta>.py::<nombre>" (pytest; tests/api con --rootdir=tests/api) y
#   "jest:__tests__/<fichero>::<patron -t>" (npx jest en mobile/; el patron es una expresion regular: sin
#   metacaracteres). Un test OMITIDO (skipped/xfail) no es verde: preflight ROJO / NO_CLASIFICABLE.
#   Uso: GAPTO_TEST_DATABASE_URL=<base desechable, formato postgresql://, con la cadena hasta 0355>
#        python -u scripts/dev/mutantes_f06_02_03.py [--grupo servidor|cliente|todos] [--solo ID,ID]
#                                                    [--salida fichero] [--check]
#   --check: sin base ni tests; comprueba que cada `viejo` aparece exactamente una vez, que los ficheros de test
#   existen y que no hay ids repetidos, e imprime el catalogo (incluidos los NO_APLICA). No ejecutar en paralelo con
#   otro arnes ni con la suite sobre el mismo arbol.
# Version: 0.1.0 (F06 T3-F06 Bloque 3 F06-02/03, paso 6; mandato v1.2 §8; contrato v1.2 §XII.3)
# Version: 0.2.0 (F06 T3-F06 Bloque 3, paso 6, 1.a pasada de servidor 77/87): discriminantes nuevos para M-CON-39b,
#   39c, 39e, 39f y 42b (test_301/302: vigencias invertidas y tercero inactivo en C-CON-06) y equivalencias
#   documentadas de M-CON-08, 34b, 34c (CHECK del mapa §1.5 con el mismo codigo), 39a (misma clausula del predicado)
#   y 45 (FORCE RLS).
# Version: 0.2.1 (paso 6): la 0.2.0 publicada en 6f80102 aplico cinco cambios al mutante SIGUIENTE (tuplas en varias
#   lineas); se rehacen acotados a la tupla de cada mutante. Ningun texto de mutante cambia.
# Version: 0.2.2 (paso 9, defecto V-bis de las capturas): MC-CON-23 con el texto nuevo del filtro (`enabled !== false`)
#   y MC-CON-23b nuevo (volver a exigir `enabled`), que mata el oraculo de la forma real del servidor.
# Version: 0.3.0 (F06 T3 · MANT N1 arneses, AJ-03 del 19-11; enmienda 01): base limpia por mutante (cada llamada a correr clona la plantilla de GAPTO_TEST_DATABASE_URL y la elimina al terminar) y clasificacion de la muerte, con scripts/dev/base_limpia_mutante.py; sin cambios en mutaciones, discriminantes ni restauracion.
# Version: 0.4.0 (F06 T3 · cadena de noche 21->22-11, T-C MANT N1 RK-ARN-03): MK6-01 y MK6-02, mutantes del
#   instrumento de advisory de test_307 (sin filtro de base; sin filtro de backend), con su oraculo K6-AIS.
#   Ningun otro mutante cambia.
# ============================================================

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import base_limpia_mutante  # MANT N1 arneses, AJ-03 del 19-11

RAIZ = pathlib.Path(__file__).resolve().parents[2]
JOURNAL = RAIZ / ".mutantes_f06_02_03.journal.json"

SRV = "backend/app/contratos/servicio.py"
SVS = "backend/app/contratos/servicios.py"
TER = "backend/app/contratos/terceros.py"
MOD = "backend/app/contratos/modelos.py"
BAS = "backend/app/contratos/base.py"
ERR = "backend/app/contratos/errores.py"
LEC = "backend/app/contratos/lecturas.py"
RUT = "backend/app/contratos/rutas.py"

T299 = "tests/api/test_299_f06_02_03_guarda_no_composicion_renta.py::"
T300 = "tests/api/test_300_f06_02_03_alta_contrato.py::"
T301 = "tests/api/test_301_f06_02_03_editar_terminar_formalizar.py::"
T302 = "tests/api/test_302_f06_02_03_sucesor_y_personas.py::"
T303 = "tests/api/test_303_f06_02_03_clausula_y_servicios.py::"
T304 = "tests/api/test_304_f06_02_03_terceros_roles_y_clasificacion.py::"
T305 = "tests/api/test_305_f06_02_03_lecturas.py::"
T306 = "tests/api/test_306_f06_02_03_traduccion_fisica.py::"
T307 = "tests/api/test_307_f06_02_03_concurrencia_serial.py::"
T308 = "tests/api/test_308_f06_02_03_inventario_op21_y_ordenes.py::"
T307F = "tests/api/test_307_f06_02_03_concurrencia_serial.py"   # RK-ARN-03: mutantes del INSTRUMENTO de K6/K9
T14P = "tests/backend/test_14p_f06_02_03_modelos_y_errores_puros.py::"
CONCURRENCIA = "tests/api/test_307_f06_02_03_concurrencia_serial.py"


def L(*lineas: str) -> str:
    """Texto de varias lineas terminado en salto de linea (los `viejo` y `nuevo` son lineas completas)."""
    return "\n".join(lineas) + "\n"


MUTANTES: list[tuple] = [
    # ---------------------------------------------------------------- solape y lock de la propiedad (O-2, O-10, O-25)
    ("M-CON-01a", "alta sin lock de la propiedad (O-10): la propiedad se lee, no se bloquea",
     [(SRV, L('    if repo_prop.bloquear(sesion, propiedad_id) is None:                                     # nivel 3',
              '        return Rechazo(e.AGREGADO_NO_ENCONTRADO)',
              '    existentes, nuevos = _ids_terceros(datos.personas)'),
       L('    if repo_prop.leer(sesion, propiedad_id) is None:',
         '        return Rechazo(e.AGREGADO_NO_ENCONTRADO)',
         '    existentes, nuevos = _ids_terceros(datos.personas)'))],
     [T307 + "test_k1_dos_altas_firmadas_en_la_misma_habitacion", T307 + "test_k2_formalizar_frente_a_alta_firmada_en_la_misma_habitacion"],
     None, 3),
    ("M-CON-01b", "preludio abrir() sin lock de la propiedad (O-10): formalizar, terminar y demas escrituras",
     [(SRV, L('    if repo_prop.bloquear(sesion, previo["propiedad_id"]) is None:',
              '        return Rechazo(e.AGREGADO_NO_ENCONTRADO)',
              '    terceros = bloquear_terceros(sesion, existentes=existentes or [], nuevos=nuevos or [])'),
       L('    if repo_prop.leer(sesion, previo["propiedad_id"]) is None:',
         '        return Rechazo(e.AGREGADO_NO_ENCONTRADO)',
         '    terceros = bloquear_terceros(sesion, existentes=existentes or [], nuevos=nuevos or [])'))],
     [T307 + "test_k2_formalizar_frente_a_alta_firmada_en_la_misma_habitacion",
      T307 + "test_k3_alta_y_terminacion_cruzadas_en_la_misma_propiedad"], None, 3),
    ("M-CON-02", "un borrador cuenta en el solape (solo el cancelado se ignora)",
     [(SRV, 'if c["id"] in excluir or c["estado_documental"] != "FORMALIZADO" or c["tipo_contrato"] == m.TIPO_OTRO:',
       'if c["id"] in excluir or c["estado_documental"] == "CANCELADO" or c["tipo_contrato"] == m.TIPO_OTRO:')],
     [T301 + "test_el_borrador_existente_no_cuenta_para_el_solape",
      T301 + "test_formalizar_con_solape_sigue_siendo_borrador_y_no_cuenta_otro_borrador"], None, 1),
    ("M-CON-03a", "solape en un solo sentido (O-25): una habitacion nueva ya no choca con una vivienda completa firmada",
     [(SRV, L('        if tipo_fisico == m.TIPO_HABITACION and not (',
              '                c["tipo_contrato"] == m.TIPO_VIVIENDA',
              '                or (c["tipo_contrato"] == m.TIPO_HABITACION and c["habitacion"] == habitacion)):'),
       L('        if tipo_fisico == m.TIPO_HABITACION and not (',
         '                False',
         '                or (c["tipo_contrato"] == m.TIPO_HABITACION and c["habitacion"] == habitacion)):'))],
     [T301 + "test_o_25_vivienda_primero_y_despues_habitacion"], None, 1),
    ("M-CON-03b", "solape en un solo sentido (O-25): una vivienda completa nueva ya no choca con una habitacion firmada",
     [(SRV, '        fin_c = (fin_de or {}).get(c["id"], c["fecha_fin_real"])\n',
       L('        if tipo_fisico == m.TIPO_VIVIENDA and c["tipo_contrato"] == m.TIPO_HABITACION:',
         '            continue',
         '        fin_c = (fin_de or {}).get(c["id"], c["fecha_fin_real"])'))],
     [T301 + "test_o_25_habitacion_primero_y_despues_vivienda"], None, 1),
    ("M-CON-04", "solape aceptado en un FORMALIZADO nuevo (O-2): la coincidencia del alta no rechaza",
     [(SRV, L('        if coinciden:',
              '            return _rechazo_solape(coinciden)',
              '    if d.clausula is not None:                                                              # 7'),
       L('        if False:',
         '            return _rechazo_solape(coinciden)',
         '    if d.clausula is not None:                                                              # 7'))],
     [T301 + "test_o_2_fin_previsto_vencido_no_libera_la_habitacion", T301 + "test_o_25_vivienda_primero_y_despues_habitacion"],
     None, 1),
    ("M-CON-05a", "solape no comprobado al formalizar un borrador",
     [(SRV, L('    if coinciden:',
              '        return _rechazo_solape(coinciden)                                   # sigue siendo borrador'),
       L('    if False:',
         '        return _rechazo_solape(coinciden)                                   # sigue siendo borrador'))],
     [T301 + "test_o_2_fin_previsto_vencido_no_libera_la_habitacion",
      T301 + "test_formalizar_con_solape_sigue_siendo_borrador_y_no_cuenta_otro_borrador"], None, 1),
    ("M-CON-05b", "solape no comprobado al corregir la terminacion (retrasar el fin real)",
     [(SRV, '    if fecha_fin_real > anterior:                                         # retrasar: puede coincidir con otro firmado\n',
       '    if False:                                                             # retrasar: puede coincidir con otro firmado\n')],
     [T301 + "test_corregir_terminacion_que_crea_solape_es_409"], None, 1),
    ("M-CON-05c", "solape no comprobado al editar fecha de inicio o habitacion de un FORMALIZADO (O-28)",
     [(SRV, '    if c["estado_documental"] == "FORMALIZADO" and (mueve_inicio or "habitacion" in cambios):\n',
       '    if False and (mueve_inicio or "habitacion" in cambios):\n')],
     [T301 + "test_o_28_cambio_de_inicio_o_habitacion_que_solapa_con_un_firmado"], None, 1),
    ("M-CON-06a", "el fin PREVISTO se usa como limite de ocupacion en el solape (O-2)",
     [(SRV, '.get(c["id"], c["fecha_fin_real"])\n', '.get(c["id"], c["fecha_fin_real"] or c["fecha_fin_prevista"])\n')],
     [T301 + "test_o_2_fin_previsto_vencido_no_libera_la_habitacion", T301 + "test_ocupacion_hasta_el_fin_real_inclusive"],
     None, 1),
    ("M-CON-06b", "el fin PREVISTO se usa como limite de la situacion derivada (FINALIZADO) en la lectura (O-1b)",
     [(LEC, L('    if c["fecha_fin_real"] is not None and c["fecha_fin_real"] < hoy:',
              '        return "FINALIZADO"'),
       L('    if (c["fecha_fin_real"] or c["fecha_fin_prevista"]) is not None and (c["fecha_fin_real"] or c["fecha_fin_prevista"]) < hoy:',
         '        return "FINALIZADO"'))],
     [T305 + "test_o_1b_escenario_a1_validado_de_la_lamina_v08", T14P + "test_el_fin_previsto_no_libera_y_finalizado_exige_fin_real_anterior_a_hoy"],
     None, 1),
    ("M-CON-07", "solape no comprobado en el sucesor (C-CON-05): se excluyen todos los contratos de la propiedad",
     [(SRV, L('    rechazo = _validar_nuevo(sesion, ficha, c["propiedad_id"], c["tipo_contrato"], c["habitacion"], nuevo,',
              '                             abierto.terceros, excluir=frozenset({contrato_id}))'),
       L('    rechazo = _validar_nuevo(sesion, ficha, c["propiedad_id"], c["tipo_contrato"], c["habitacion"], nuevo,',
         '                             abierto.terceros, excluir=frozenset({contrato_id, *[x["id"] for x in repo.contratos_de_propiedad(sesion, c["propiedad_id"])]}))'))],
     [T302 + "test_sucesor_requisitos"], None, 1),
    # ---------------------------------------------------------------- habitacion y ficha
    ("M-CON-08", "`habitacion` aceptada en VIVIENDA_COMPLETA u OTRO (sin HABITACION_NO_ADMITIDA previa)",
     [(SRV, L('    if tipo_fisico != m.TIPO_HABITACION and habitacion is not None:',
              '        return Rechazo(e.HABITACION_NO_ADMITIDA)'),
       L('    if False:',
         '        return Rechazo(e.HABITACION_NO_ADMITIDA)'))],
     [T300 + "test_habitacion_reglas_por_tipo_y_contra_la_ficha"], 'la CHECK ck_contratos__habitacion (fila del mapa §1.5) devuelve el MISMO codigo HABITACION_NO_ADMITIDA con el mismo HTTP y estado identico; la ruta fisica la mata M-FIS-06 en test_306', 1),
    ("M-CON-09a", "ficha con habitaciones NULL o 0 tratada como ilimitada",
     [(SRV, L('        if not ficha["habitaciones"]:               # NULL o 0: la columna admite 0 y no se inventan (D-A-11)',
              '            return Rechazo(e.HABITACIONES_NO_INDICADAS)',
              '        if habitacion > ficha["habitaciones"]:',
              '            return Rechazo(e.HABITACION_FUERA_DE_FICHA)'),
       L('        if ficha["habitaciones"] and habitacion > ficha["habitaciones"]:',
         '            return Rechazo(e.HABITACION_FUERA_DE_FICHA)'))],
     [T300 + "test_habitacion_reglas_por_tipo_y_contra_la_ficha"], None, 1),
    ("M-CON-09b", "ficha con habitaciones NULL o 0 tratada como 0 (HABITACION_FUERA_DE_FICHA en lugar de HABITACIONES_NO_INDICADAS)",
     [(SRV, '            return Rechazo(e.HABITACIONES_NO_INDICADAS)\n', '            return Rechazo(e.HABITACION_FUERA_DE_FICHA)\n')],
     [T300 + "test_habitacion_reglas_por_tipo_y_contra_la_ficha"], None, 1),
    # ---------------------------------------------------------------- partes, principal, YO (O-22, O-23, O-24, INV-ALQ-07/15)
    ("M-CON-10", "FORMALIZADO sin inquilino aceptado (solo se exige arrendador)",
     [(MOD, '    if not (roles & ROLES_ARRENDADOR) or "INQUILINO" not in roles_con_principal:\n',
       '    if not (roles & ROLES_ARRENDADOR):\n')],
     [T300 + "test_o_23_agencia_y_administrador_no_formalizan", T301 + "test_formalizar_exige_partes_y_principal_y_cancelar_solo_un_borrador",
      T14P + "test_agencia_y_administrador_nunca_cuentan_para_formalizar"], None, 1),
    ("M-CON-11", "AGENCIA contada como arrendador (O-23)",
     [(MOD, 'ROLES_ARRENDADOR = frozenset({"PROPIETARIO", "GESTOR"})\n', 'ROLES_ARRENDADOR = frozenset({"PROPIETARIO", "GESTOR", "AGENCIA"})\n')],
     [T300 + "test_o_23_agencia_y_administrador_no_formalizan", T14P + "test_agencia_y_administrador_nunca_cuentan_para_formalizar"], None, 1),
    ("M-CON-12", "principal exigido a AVALISTA (O-24)",
     [(MOD, 'ROLES_PRINCIPAL_OBLIGATORIO = frozenset({"PROPIETARIO", "GESTOR", "INQUILINO"})\n',
       'ROLES_PRINCIPAL_OBLIGATORIO = frozenset({"PROPIETARIO", "GESTOR", "INQUILINO", "AVALISTA"})\n')],
     [T300 + "test_o_24_principal_por_rol", T14P + "test_principal_solo_obligatorio_en_propietario_gestor_e_inquilino"], None, 1),
    ("M-CON-13", "principal no exigido a INQUILINO (O-24)",
     [(MOD, 'ROLES_PRINCIPAL_OBLIGATORIO = frozenset({"PROPIETARIO", "GESTOR", "INQUILINO"})\n',
       'ROLES_PRINCIPAL_OBLIGATORIO = frozenset({"PROPIETARIO", "GESTOR"})\n')],
     [T300 + "test_o_24_principal_por_rol", T14P + "test_principal_solo_obligatorio_en_propietario_gestor_e_inquilino"], None, 1),
    ("M-CON-14a", "YO aceptado como INQUILINO (O-22)",
     [(MOD, 'ROLES_PROHIBIDOS_PARA_YO = {"INQUILINO": e.INQUILINO_NO_PUEDE_SER_YO,\n', 'ROLES_PROHIBIDOS_PARA_YO = {\n')],
     [T300 + "test_o_22_yo_no_es_inquilino_ni_agencia_ni_administrador", T302 + "test_o_22_yo_inquilino_agencia_administrador_en_personas",
      T14P + "test_yo_nunca_es_inquilino_agencia_ni_administrador_pero_si_propietario_o_gestor"], None, 1),
    ("M-CON-14b", "YO aceptado como AGENCIA (O-22)",
     [(MOD, '                            "AGENCIA": e.ROL_NO_ADMITIDO_PARA_YO, "ADMINISTRADOR": e.ROL_NO_ADMITIDO_PARA_YO}\n',
       '                            "ADMINISTRADOR": e.ROL_NO_ADMITIDO_PARA_YO}\n')],
     [T300 + "test_o_22_yo_no_es_inquilino_ni_agencia_ni_administrador", T302 + "test_o_22_yo_inquilino_agencia_administrador_en_personas",
      T14P + "test_yo_nunca_es_inquilino_agencia_ni_administrador_pero_si_propietario_o_gestor"], None, 1),
    ("M-CON-14c", "YO aceptado como ADMINISTRADOR (O-22)",
     [(MOD, '                            "AGENCIA": e.ROL_NO_ADMITIDO_PARA_YO, "ADMINISTRADOR": e.ROL_NO_ADMITIDO_PARA_YO}\n',
       '                            "AGENCIA": e.ROL_NO_ADMITIDO_PARA_YO}\n')],
     [T300 + "test_o_22_yo_no_es_inquilino_ni_agencia_ni_administrador", T302 + "test_o_22_yo_inquilino_agencia_administrador_en_personas",
      T14P + "test_yo_nunca_es_inquilino_agencia_ni_administrador_pero_si_propietario_o_gestor"], None, 1),
    # ---------------------------------------------------------------- renta fuera (O-14, INV-ALQ-02)
    ("M-CON-15", "`renta` o `fianza` aceptadas en el alta (sin RENTA_NO_DISPONIBLE)",
     [(SRV, L('    if d.renta_presente:                                                                    # 2 (R-E-01)',
              '        return Rechazo(e.RENTA_NO_DISPONIBLE)'), '')],
     [T300 + "test_renta_o_fianza_son_renta_no_disponible_con_cero_filas", T300 + "test_la_propiedad_se_valida_antes_que_la_renta"], None, 1),
    ("M-CON-16", "terminar (y cambiar inicio, corregir, sucesor) un contrato con regla_renta_id aceptado (O-14)",
     [(SRV, '    if c["regla_renta_id"] is not None:\n        return Rechazo(e.NO_PERMITIDA_EN_ESTADO, {"motivo": e.RENTA_PENDIENTE})\n',
       '    if False:\n        return Rechazo(e.NO_PERMITIDA_EN_ESTADO, {"motivo": e.RENTA_PENDIENTE})\n')],
     [T301 + "test_o_12_terminar_un_contrato_con_regla_renta_es_409_con_estado_identico",
      T301 + "test_el_motivo_de_renta_es_lo_primero_tras_el_replay_y_la_version"], None, 1),
    # ---------------------------------------------------------------- edicion y terminacion
    ("M-CON-17", "prorroga (fin previsto) sin motivo aceptada",
     [(SRV, '    if "fecha_fin_prevista" in cambios:\n        motivo_ok = exigir_motivo(motivo)\n',
       '    if False:\n        motivo_ok = exigir_motivo(motivo)\n')],
     [T301 + "test_prorroga_con_motivo_y_correccion_libre_de_nombre_y_notas"], None, 1),
    ("M-CON-18a", "cambio de propiedad o de tipo aceptado (CAMPO_INMUTABLE eliminada en el servicio)",
     [(SRV, L('    if inmutables_presentes:', '        return Rechazo(e.CAMPO_INMUTABLE)'), '')],
     [T301 + "test_propiedad_y_tipo_son_inmutables_y_un_cancelado_no_se_edita"], None, 1),
    ("M-CON-18b", "cambio de propiedad o de tipo aceptado (la ruta no detecta los campos inmutables)",
     [(RUT, 'inmutables_presentes=any(n in c.model_fields_set for n in dto.CAMPOS_INMUTABLES)', 'inmutables_presentes=False')],
     [T301 + "test_propiedad_y_tipo_son_inmutables_y_un_cancelado_no_se_edita"], None, 1),
    ("M-CON-19", "fecha de inicio movida sin mover las vigencias que empezaban con el contrato",
     [(SRV, L('        for tabla, ids in mover.items():',
              '            repo.mover_vigencia(sesion, tabla, ids, "vigente_desde", inicio)'), '')],
     [T301 + "test_cambio_de_inicio_mueve_las_vigencias_que_empezaban_con_el_contrato"], None, 1),
    ("M-CON-20", "terminar un borrador aceptado (CONTRATO_NO_VIGENTE solo si ya tiene fin real)",
     [(SRV, L('    if c["estado_documental"] != "FORMALIZADO" or c["fecha_fin_real"] is not None:',
              '        return Rechazo(e.CONTRATO_NO_VIGENTE)',
              '    filas = _filas_vigencia(sesion, contrato_id)'),
       L('    if c["fecha_fin_real"] is not None:',
         '        return Rechazo(e.CONTRATO_NO_VIGENTE)',
         '    filas = _filas_vigencia(sesion, contrato_id)'))],
     [T301 + "test_terminar_requisitos_estado_y_fechas"], None, 1),
    ("M-CON-21", "cierre de una vigencia de persona ya cerrada aceptado",
     [(SRV, '    if p["vigente_hasta"] is not None:                        # nunca se cierra una vigencia ya cerrada\n',
       '    if False:                                                 # nunca se cierra una vigencia ya cerrada\n')],
     [T302 + "test_o_4_uno_se_va_y_el_contrato_sigue_cerrar_al_ultimo_es_contrato_sin_inquilino",
      T302 + "test_cerrar_al_principal_exige_nombrar_otro_si_quedan_personas_en_el_rol"], None, 1),
    # ---------------------------------------------------------------- sucesor
    ("M-CON-22", "sucesor que empieza el ultimo dia del anterior aceptado (`<=` -> `<`)",
     [(SRV, 'nuevo.fecha_inicio <= fecha_fin_real:', 'nuevo.fecha_inicio < fecha_fin_real:')],
     [T302 + "test_sucesor_requisitos"], None, 1),
    ("M-CON-23", "sucesor en VIVIENDA_COMPLETA u OTRO aceptado (solo HABITACION)",
     [(SRV, ' or c["fecha_fin_real"] is not None or c["tipo_contrato"] != m.TIPO_HABITACION:', ' or c["fecha_fin_real"] is not None:')],
     [T302 + "test_sucesor_requisitos"], None, 1),
    # ---------------------------------------------------------------- personas por vigencias (O-4, O-27, INV-ALQ-07)
    ("M-CON-24", "cerrar al principal sin nombrar otro aceptado (PRINCIPAL_REQUERIDO eliminada)",
     [(SRV, '    if p["principal"] and p["rol"] in m.ROLES_PRINCIPAL_OBLIGATORIO and quedan:\n',
       '    if False:\n')],
     [T302 + "test_cerrar_al_principal_exige_nombrar_otro_si_quedan_personas_en_el_rol"], None, 1),
    ("M-CON-25", "dejar el contrato sin inquilino aceptado (cobertura de INQUILINO no comprobada)",
     [(SRV, L('    if not m.cubre(inquilinos, c["fecha_inicio"], c["fecha_fin_real"]):',
              '        return Rechazo(e.CONTRATO_SIN_INQUILINO)'), '')],
     [T302 + "test_o_4_uno_se_va_y_el_contrato_sigue_cerrar_al_ultimo_es_contrato_sin_inquilino"], None, 1),
    ("M-CON-26", "cierre del ultimo arrendador aceptado (O-27: cobertura de PROPIETARIO o GESTOR no comprobada)",
     [(SRV, L('    if not m.cubre(arrendadores, c["fecha_inicio"], c["fecha_fin_real"]):',
              '        return Rechazo(e.CONTRATO_SIN_ARRENDADOR)'), '')],
     [T302 + "test_o_27_cerrar_al_ultimo_arrendador", T302 + "test_o_27_corregir_fechas_de_personas_que_dejan_un_hueco"], None, 1),
    # ---------------------------------------------------------------- clausula y servicios (O-6, O-7)
    ("M-CON-27", "«No lo sé» (sin clausula) guardado como NINGUNA en el alta",
     [(SRV, L('    if d.clausula is not None:',
              '        columnas = m.validar_clausula(d.clausula)',
              '        assert isinstance(columnas, dict)'),
       L('    if True:',
         '        columnas = m.validar_clausula(d.clausula or Clausula(tipo="NINGUNA"))',
         '        assert isinstance(columnas, dict)'))],
     [T303 + "test_o_6_ninguna_frente_a_no_lo_se", T300 + "test_alta_habitacion_firmada_con_personas_y_sin_renta"], None, 1),
    ("M-CON-28", "NINGUNA con periodicidad aceptada",
     [(MOD, L('    if c.tipo == "NINGUNA" and (c.indice_referencia or c.periodicidad_meses is not None',
              '                                or c.porcentaje_fijo is not None or c.fecha_primera_revision is not None):'),
       L('    if c.tipo == "NINGUNA" and (c.indice_referencia',
         '                                or c.porcentaje_fijo is not None or c.fecha_primera_revision is not None):'))],
     [T14P + "test_clausula_ninguna_frente_a_no_lo_se_y_porcentaje_fijo", T303 + "test_o_6_ninguna_frente_a_no_lo_se"], None, 1),
    ("M-CON-29", "version de clausula nueva sin cerrar la anterior",
     [(SRV, L('        if abierta is not None:',
              '            repo.cerrar_vigencia(sesion, "contrato_revision_renta_versiones", [abierta["id"]],',
              '                                 desde - dt.timedelta(days=1))'), '')],
     [T303 + "test_o_6_version_nueva_cierra_la_anterior_y_nunca_invierte"], None, 1),
    ("M-CON-30", "`modo_reparto` NULL con repercutible = true (modo FIJO)",
     [(MOD, '"repercutible": True, "modo_reparto": "FIJO",', '"repercutible": True, "modo_reparto": None,')],
     [T303 + "test_o_7_tratamiento_en_el_alta_incluido_fijo_y_por_factura", T14P + "test_tratamiento_modos_y_su_fila"], None, 1),
    ("M-CON-31", "POR_FACTURA con porcentaje aceptado",
     [(MOD, L('    if modo == "POR_FACTURA":',
              '        if porcentaje is not None:',
              '            return Rechazo(e.TRATAMIENTO_INCOMPATIBLE)'),
       L('    if modo == "POR_FACTURA":'))],
     [T303 + "test_o_7_negativos_del_tratamiento", T14P + "test_tratamiento_incoherente_es_tratamiento_incompatible"], None, 1),
    ("M-CON-32", "SIN_INDICAR / cambio de tratamiento borra la fila abierta con DELETE (42501 sin DELETE para gapto_runtime)",
     [(SVS, '                repo.cerrar_vigencia(sesion, "contrato_servicios", [actual["id"]], fecha - dt.timedelta(days=1))\n',
       '                sesion.ejecutar("DELETE FROM gapto.contrato_servicios WHERE id = %s", (actual["id"],))\n')],
     [T303 + "test_o_7_cambio_de_tratamiento_sin_indicar_y_errata", T308 + "test_sin_delete_ddl_ni_grants_en_el_paquete"], None, 1),
    ("M-CON-33", "FIJO con 0 % aceptado (`<= 0` -> `< 0`)",
     [(MOD, 'if porcentaje is None or porcentaje <= 0 or porcentaje > CIEN', 'if porcentaje is None or porcentaje < 0 or porcentaje > CIEN')],
     [T303 + "test_o_7_negativos_del_tratamiento", T14P + "test_tratamiento_incoherente_es_tratamiento_incompatible"], None, 1),
    # ---------------------------------------------------------------- roles de tercero y de participante
    ("M-CON-34a", "rol de participante fuera de catalogo aceptado por la validacion del alta",
     [(MOD, L('    if any(p.rol not in ROLES for p in personas):', '        return Rechazo(e.ROL_DESCONOCIDO)'), '')],
     [T300 + "test_alta_habitacion_firmada_con_personas_y_sin_renta", T300 + "test_cuerpo_invalido_es_422_entrada_invalida",
      T14P + "test_actor_repetido_en_el_mismo_rol"], None, 1),
    ("M-CON-34b", "rol de participante fuera de catalogo aceptado al anadir una persona",
     [(SRV, L('    if persona.rol not in m.ROLES:', '        return Rechazo(e.ROL_DESCONOCIDO)'), '')],
     [T306 + "test_check_rol_de_participante_fuera_de_catalogo", T302 + "test_anadir_persona_reglas_de_fechas_duplicados_y_principal"],
     'la CHECK ck_contrato_participantes__rol (fila del mapa §1.5) devuelve el MISMO codigo ROL_DESCONOCIDO; la ruta fisica la mata M-FIS-08 en test_306 y la CHECK, MS-01/MS-02 de 0355', 1),
    ("M-CON-34c", "rol de tercero fuera de catalogo (AGENCIA, ADMINISTRADOR) aceptado al anadir roles",
     [(TER, L('    if any(r not in m.ROLES_TERCERO for r in anadir):',
              '        return Rechazo(e.ROL_DESCONOCIDO)                    # AGENCIA/ADMINISTRADOR no son roles de tercero'), '')],
     [T304 + "test_roles_agencia_y_administrador_no_son_roles_de_tercero"], 'la CHECK ck_tercero_roles__rol_codigo (fila del mapa §1.5) devuelve el MISMO codigo ROL_DESCONOCIDO; la ruta fisica la mata M-FIS-09 en test_306', 1),
    ("M-CON-35a", "retirada de rol de tercero aceptada (quitar se ignora en lugar de RETIRADA_NO_ADMITIDA)",
     [(TER, L('    if quitar:', '        return Rechazo(e.RETIRADA_NO_ADMITIDA)',
              '    antes = repo.snapshot_tercero_con_hijas(sesion, tercero_id)', '    nuevos: list[str] = []'),
       L('    antes = repo.snapshot_tercero_con_hijas(sesion, tercero_id)', '    nuevos: list[str] = []'))],
     [T304 + "test_quitar_un_rol_es_retirada_no_admitida_sin_escritura"], None, 1),
    ("M-CON-35b", "desasignacion de clasificacion aceptada (quitar se ignora en lugar de RETIRADA_NO_ADMITIDA)",
     [(TER, L('    if quitar:', '        return Rechazo(e.RETIRADA_NO_ADMITIDA)',
              '    for cid in sorted(set(anadir), key=str):', '        c = repo.clasificacion(sesion, cid)'),
       L('    for cid in sorted(set(anadir), key=str):', '        c = repo.clasificacion(sesion, cid)'))],
     [T304 + "test_desasignar_es_retirada_no_admitida_y_principal_debe_estar_asignada"], None, 1),
    # ---------------------------------------------------------------- 0P de intencion (O-17, INV-ALQ-11)
    ("M-CON-36a", "alta sin 0P de intencion (el primer recurso deja de ser el 0P)",
     [(SRV, '    bloquear_intencion_propiedad(sesion, contrato_id)                                        # 0P, primer recurso\n', '')],
     [T308 + "test_el_primer_recurso_de_cada_writer_es_el_0p_o_su_preludio", T308 + "test_orden_alta_0p_propiedad_terceros_replay",
      T307 + "test_k4_misma_intencion_en_dos_propiedades_espera_en_el_0p"], None, 3),
    ("M-CON-36b", "preludio abrir() sin 0P de intencion",
     [(SRV, L('    bloquear_intencion_propiedad(sesion, intencion_id)                                       # 0P',
              '    hoy = hoy_owner(sesion, reloj)',
              '    previo = repo.contrato(sesion, contrato_id)'),
       L('    hoy = hoy_owner(sesion, reloj)', '    previo = repo.contrato(sesion, contrato_id)'))],
     [T308 + "test_los_preludios_comunes_empiezan_por_el_0p", T308 + "test_orden_abrir_0p_propiedad_terceros_contrato"], None, 1),
    ("M-CON-36c", "alta de servicio sin 0P de intencion",
     [(SVS, '    bloquear_intencion_propiedad(sesion, servicio_id)                                       # 0P\n', '')],
     [T308 + "test_el_primer_recurso_de_cada_writer_es_el_0p_o_su_preludio"], None, 1),
    ("M-CON-36d", "preludio de tercero sin 0P de intencion",
     [(TER, L('    bloquear_intencion_propiedad(sesion, intencion_id)', '    repo_ter.tomar_advisory(sesion)',
              '    t = repo_ter.leer(sesion, tercero_id, bloquear=True)'),
       L('    repo_ter.tomar_advisory(sesion)', '    t = repo_ter.leer(sesion, tercero_id, bloquear=True)'))],
     [T308 + "test_los_preludios_comunes_empiezan_por_el_0p"], None, 1),
    # ---------------------------------------------------------------- guarda §VII.1 y OP-21 (INV-ALQ-02, INV-ALQ-10)
    ("M-CON-37a", "un servicio del bloque importa y llama a un escritor de reglas (crear_regla)",
     [(SRV, 'from app.propiedades import repositorio as repo_prop\n',
       L('from app.propiedades import repositorio as repo_prop',
         'from app.services.reglas_service import ReglasService',
         '',
         '',
         'def _crea_renta(sesion):',
         '    return ReglasService().crear_regla(sesion)',
         ''))],
     [T299 + "test_el_bloque_no_alcanza_escritores_de_reglas_ni_de_previsiones",
      T299 + "test_ningun_modulo_del_bloque_importa_los_servicios_ni_repositorios_de_reglas_y_previsiones"], None, 1),
    ("M-CON-37b", "un servicio del bloque llama a un escritor de previsiones (insertar_prevision)",
     [(SVS, 'from app.propiedades import repositorio as repo_prop\n',
       L('from app.propiedades import repositorio as repo_prop',
         'from app.repositories import previsiones_repository as _prev',
         '',
         '',
         'def _crea_cuota(sesion):',
         '    return _prev.insertar_prevision(sesion)',
         ''))],
     [T299 + "test_el_bloque_no_alcanza_escritores_de_reglas_ni_de_previsiones",
      T299 + "test_ningun_modulo_del_bloque_importa_los_servicios_ni_repositorios_de_reglas_y_previsiones"], None, 1),
    ("M-CON-38", "adaptador del bloque con retiradas a OP-21 (efectos_a_eliminar / entidades_a_eliminar)",
     [(SRV, 'TABLAS_VIGENCIA = ("contrato_participantes", "contrato_servicios", "contrato_revision_renta_versiones")\n',
       L('TABLAS_VIGENCIA = ("contrato_participantes", "contrato_servicios", "contrato_revision_renta_versiones")',
         'RETIRADAS_OP21 = {"efectos_a_eliminar": [], "entidades_a_eliminar": []}'))],
     [T308 + "test_o_20_ningun_adaptador_envia_retiradas_a_op21"], None, 1),
    # ---------------------------------------------------------------- vigencias (O-28, INV-ALQ-17)
    ("M-CON-39a", "vigencia invertida aceptada: fin real anterior al inicio del contrato no se comprueba",
     [(SRV, L('    if c["fecha_inicio"] is not None and fecha < c["fecha_inicio"]:', '        return True'),
       L('    if False:', '        return True'))],
     [T301 + "test_terminar_requisitos_estado_y_fechas", T301 + "test_o_28_inicio_que_dejaria_una_vigencia_invertida"], 'con el contrato FORMALIZADO y sin fin real siempre hay vigencias abiertas (arrendador e inquilino, cobertura C-CON-06) con desde >= inicio; si fecha < inicio, la segunda clausula del mismo predicado da True y el codigo es identico (FECHA_FIN_ANTERIOR_A_VIGENCIA)', 1),
    ("M-CON-39b", "vigencia invertida aceptada: fin real anterior al inicio de una vigencia ABIERTA no se comprueba",
     [(SRV, '    return any(f["vigente_hasta"] is None and f["vigente_desde"] is not None and f["vigente_desde"] > fecha\n',
       '    return False and any(f["vigente_hasta"] is None and f["vigente_desde"] is not None and f["vigente_desde"] > fecha\n')],
     [T301 + "test_terminar_requisitos_estado_y_fechas", T302 + "test_o_27_corregir_fechas_de_personas_que_dejan_un_hueco", T302 + "test_vigencias_invertidas_al_terminar_cerrar_o_corregir_una_persona"], None, 1),
    ("M-CON-39c", "vigencia invertida aceptada al cerrar una persona (`hasta < vigente_desde`)",
     [(SRV, L('    if hasta < p["vigente_desde"]:', '        return Rechazo(e.FECHA_FIN_ANTERIOR_A_VIGENCIA)'),
       L('    if False:', '        return Rechazo(e.FECHA_FIN_ANTERIOR_A_VIGENCIA)'))],
     [T302 + "test_anadir_persona_reglas_de_fechas_duplicados_y_principal", T302 + "test_o_4_uno_se_va_y_el_contrato_sigue_cerrar_al_ultimo_es_contrato_sin_inquilino", T302 + "test_vigencias_invertidas_al_terminar_cerrar_o_corregir_una_persona"],
     None, 1),
    ("M-CON-39d", "vigencia invertida aceptada al corregir la terminacion",
     [(SRV, L('    if fecha_fin_real < c["fecha_inicio"] or any(',
              '            f["id"] in ids_mover and f["vigente_desde"] > fecha_fin_real for fs in filas.values() for f in fs):',
              '        return Rechazo(e.FECHA_FIN_ANTERIOR_A_VIGENCIA)'), '')],
     [T301 + "test_corregir_terminacion_mueve_juntos_fin_y_cierres_sin_reabrir"], None, 1),
    ("M-CON-39e", "vigencia invertida aceptada al mover la fecha de inicio (VIGENCIA_INVERTIDA)",
     [(SRV, '                    if f["vigente_hasta"] is not None and f["vigente_hasta"] < inicio:\n',
       '                    if False:\n')],
     [T301 + "test_o_28_inicio_que_dejaria_una_vigencia_invertida", T301 + "test_o_28_mover_el_inicio_detras_de_una_vigencia_ya_cerrada"], None, 1),
    ("M-CON-39f", "vigencia invertida aceptada al corregir una persona (`vigente_hasta < vigente_desde`)",
     [(SRV, '    if nuevo["vigente_hasta"] is not None and nuevo["vigente_hasta"] < nuevo["vigente_desde"]:\n',
       '    if False:\n')],
     [T302 + "test_o_27_corregir_fechas_de_personas_que_dejan_un_hueco", T302 + "test_anadir_persona_reglas_de_fechas_duplicados_y_principal", T302 + "test_vigencias_invertidas_al_terminar_cerrar_o_corregir_una_persona"],
     None, 1),
    ("M-CON-40a", "`desde` igual al de la clausula abierta aceptado (DESDE_IGUAL_A_VERSION_ABIERTA eliminada)",
     [(SRV, L('        if desde == abierta["vigente_desde"]:', '            return Rechazo(e.DESDE_IGUAL_A_VERSION_ABIERTA)'), '')],
     [T303 + "test_o_6_version_nueva_cierra_la_anterior_y_nunca_invierte"], None, 1),
    ("M-CON-40b", "`desde` igual al del tratamiento abierto aceptado (DESDE_IGUAL_A_VERSION_ABIERTA eliminada)",
     [(SVS, L('            if fecha == actual["vigente_desde"]:', '                return Rechazo(e.DESDE_IGUAL_A_VERSION_ABIERTA)'), '')],
     [T303 + "test_o_7_cambio_de_tratamiento_sin_indicar_y_errata", T303 + "test_o_7_negativos_del_tratamiento"], None, 1),
    # ---------------------------------------------------------------- advisory, inactivos, baja de servicio (O-29, O-30, O-31)
    ("M-CON-41", "sucesor o alta con tercero nuevo sin advisory de terceros (O-29)",
     [(BAS, L('    if nuevos:', '        repo_ter.tomar_advisory(sesion)'), '')],
     [T308 + "test_orden_bloquear_terceros_advisory_solo_si_se_crea_y_despues_fs", T307 + "test_k5_sucesor_con_tercero_nuevo_frente_a_alta_de_tercero",
      T307 + "test_k6_la_propiedad_se_bloquea_antes_que_los_terceros"], None, 3),
    ("M-CON-42a", "tercero inactivo aceptado como participante en el alta (O-30)",
     [(SRV, 'if tid is not None and (terceros.get(tid) is None or not terceros[tid]["enabled"]):',
       'if tid is not None and (terceros.get(tid) is None):')],
     [T300 + "test_tercero_ajeno_inexistente_o_inactivo_es_tercero_no_disponible"], None, 1),
    ("M-CON-42b", "tercero inactivo aceptado al anadir una persona (O-30)",
     [(SRV, 'if tid is not None and (abierto.terceros.get(tid) is None or not abierto.terceros[tid]["enabled"]):',
       'if tid is not None and (abierto.terceros.get(tid) is None):')],
     [T302 + "test_anadir_persona_reglas_de_fechas_duplicados_y_principal", T300 + "test_tercero_ajeno_inexistente_o_inactivo_es_tercero_no_disponible", T302 + "test_o_30_tercero_inactivo_no_se_anade_como_persona"],
     None, 1),
    ("M-CON-43", "motivo de renta en la baja de un servicio con regla (O-31)",
     [(SVS, '{"motivo": e.REGLA_SERVICIO_PENDIENTE}', '{"motivo": e.RENTA_PENDIENTE}')],
     [T303 + "test_o_31_baja_de_servicio_con_regla_financiera"], None, 1),
    ("M-CON-44", "la lectura del selector deja de calcular el uso (siempre SIN_USO) (O-32)",
     [(LEC, '        if f["contrato_id"] is not None:\n            uso: dict[str, Any]', '        if False:\n            uso: dict[str, Any]')],
     [T305 + "test_o_32_homonimos_distinguibles_por_naturaleza_y_uso", T305 + "test_o_32_con_dos_contratos_se_muestra_el_de_inicio_mas_reciente"],
     None, 1),
    ("M-CON-45", "el uso del selector se calcula sin filtro de owner (O-33; bajo RLS)",
     [(LEC, '    f" WHERE a.tercero_id = t.id AND a.owner_user_id = {repo.OWNER} AND ce.owner_user_id = {repo.OWNER} "\n',
       '    " WHERE a.tercero_id = t.id "\n')],
     [T305 + "test_o_33_aislamiento_del_uso_y_una_sola_consulta"], 'bajo gapto_runtime con FORCE RLS en terceros, actores, contratos y participantes, las filas de otro owner no son visibles: el filtro explicito de owner es defensa en profundidad y no cambia el resultado (O-33 lo comprueba en verde con dos owners)', 1),
    # ---------------------------------------------------------------- RK-ARN-03: instrumento de advisory aislado
    ("MK6-01", "medida de advisory sin filtro de base (cuenta locks de otra base del cluster)",
     [(T307F, "        \"database = (SELECT oid FROM pg_database WHERE datname = current_database()) AND \"\n", "")],
     [T307 + "test_k6_ais_la_medida_ignora_advisory_de_otra_base_y_de_otro_backend"], None, 1),
    ("MK6-02", "medida de advisory de K6 sin filtro de backend (cuenta locks de otro backend de la base)",
     [(T307F, "        \"(%s::int IS NULL OR pid = %s::int) AND \"\n",
       "        \"(%s::int IS NULL OR %s::int IS NOT NULL) AND \"\n")],
     [T307 + "test_k6_ais_la_medida_ignora_advisory_de_otra_base_y_de_otro_backend"], None, 1),
    ("M-CON-46a", "C-CON-01 con terceros antes que la propiedad (O-29)",
     [(SRV, L('    if repo_prop.bloquear(sesion, propiedad_id) is None:                                     # nivel 3',
              '        return Rechazo(e.AGREGADO_NO_ENCONTRADO)',
              '    existentes, nuevos = _ids_terceros(datos.personas)',
              '    terceros = bloquear_terceros(sesion, existentes=existentes, nuevos=nuevos)               # niveles 4 y 5'),
       L('    existentes, nuevos = _ids_terceros(datos.personas)',
         '    terceros = bloquear_terceros(sesion, existentes=existentes, nuevos=nuevos)               # niveles 4 y 5',
         '    if repo_prop.bloquear(sesion, propiedad_id) is None:',
         '        return Rechazo(e.AGREGADO_NO_ENCONTRADO)'))],
     [T308 + "test_orden_alta_0p_propiedad_terceros_replay", T307 + "test_k6_la_propiedad_se_bloquea_antes_que_los_terceros"], None, 3),
    ("M-CON-46b", "C-CON-05 (preludio abrir) con terceros antes que la propiedad (O-29)",
     [(SRV, L('    if repo_prop.bloquear(sesion, previo["propiedad_id"]) is None:',
              '        return Rechazo(e.AGREGADO_NO_ENCONTRADO)',
              '    terceros = bloquear_terceros(sesion, existentes=existentes or [], nuevos=nuevos or [])'),
       L('    terceros = bloquear_terceros(sesion, existentes=existentes or [], nuevos=nuevos or [])',
         '    if repo_prop.bloquear(sesion, previo["propiedad_id"]) is None:',
         '        return Rechazo(e.AGREGADO_NO_ENCONTRADO)'))],
     [T308 + "test_mutante_terceros_antes_que_la_propiedad_falla", T308 + "test_orden_abrir_0p_propiedad_terceros_contrato",
      T308 + "test_orden_sucesor_0p_propiedad_terceros_contrato_actual_y_despues_el_writer_de_f05",
      T307 + "test_k5_sucesor_con_tercero_nuevo_frente_a_alta_de_tercero"], None, 3),
]

# ---------------------------------------------------------------- mapa §1.5 (O-15): una fila por mutante (M-FIS-01..16) + C-31 (M-FIS-17)
_MAPA = [
    ("M-FIS-01", "ex_contrato_participantes__contrato_actor_rol", "PARTICIPANTE_DUPLICADO 23P01",
     [T306 + "test_exclude_personas_por_contrato_actor_y_rol"]),
    ("M-FIS-02", "ex_contrato_participantes__principal_por_rol", "PRINCIPAL_DUPLICADO 23P01",
     [T306 + "test_exclude_un_principal_por_contrato_y_rol", T306 + "test_exclude_principal_tambien_para_agencia_tras_0355"]),
    ("M-FIS-03", "ex_contrato_servicios__contrato_servicio", "TRATAMIENTO_SOLAPADO 23P01",
     [T306 + "test_exclude_tratamiento_por_contrato_y_servicio"]),
    ("M-FIS-04", "ex_propiedad_servicios__propiedad_servicio", "SERVICIO_YA_VINCULADO 23P01",
     [T306 + "test_exclude_servicio_vinculado_a_la_propiedad_sin_ruta_http"]),
    ("M-FIS-05", "ex_contrato_revision_renta_versiones__contrato", "CLAUSULA_SOLAPADA 23P01",
     [T306 + "test_exclude_clausula_sin_solape"]),
    ("M-FIS-06", "ck_contratos__habitacion", "HABITACION_NO_ADMITIDA 23514",
     [T306 + "test_check_habitacion_solo_en_habitacion"]),
    ("M-FIS-07", "ck_contrato_servicios__repercusion_coherente", "TRATAMIENTO_INCOMPATIBLE 23514",
     [T306 + "test_check_tratamiento_incompatible[columnas0-ck_contrato_servicios__repercusion_coherente]"]),
    ("M-FIS-08", "ck_contrato_participantes__rol", "ROL_DESCONOCIDO 23514",
     [T306 + "test_check_rol_de_participante_fuera_de_catalogo"]),
    ("M-FIS-09", "ck_tercero_roles__rol_codigo", "ROL_DESCONOCIDO 23514",
     [T306 + "test_check_rol_de_tercero_agencia_no_es_rol_de_tercero"]),
    ("M-FIS-10", "ck_contrato_servicios__renta_repercutible_excl", "TRATAMIENTO_INCOMPATIBLE 23514",
     [T306 + "test_check_tratamiento_incompatible[columnas1-ck_contrato_servicios__renta_repercutible_excl]"]),
    ("M-FIS-11", "ck_contrato_servicios__porcentaje", "TRATAMIENTO_INCOMPATIBLE 23514",
     [T306 + "test_check_tratamiento_incompatible[columnas2-ck_contrato_servicios__porcentaje]"]),
    ("M-FIS-12", "ck_contrato_revision_renta_versiones__porcentaje_fijo_exigido", "CLAUSULA_INCOMPLETA 23514",
     [T306 + "test_check_clausula_incompleta[fila0]"]),
    ("M-FIS-13", "ck_contrato_revision_renta_versiones__ninguna_sin_parametros", "CLAUSULA_INCOMPLETA 23514",
     [T306 + "test_check_clausula_incompleta[fila1]"]),
    ("M-FIS-14", "ck_contratos__fin_prevista_no_anterior", "FECHA_ANTERIOR_INICIO 23514",
     [T306 + "test_check_fechas_del_contrato"]),
    ("M-FIS-15", "ck_contratos__fin_real_no_anterior", "FECHA_ANTERIOR_INICIO 23514",
     [T306 + "test_check_fechas_del_contrato"]),
    ("M-FIS-16", "uq_clasificaciones_tercero__owner_parent_nombre", "CLASIFICACION_NOMBRE_REPETIDO 23505",
     [T306 + "test_unique_nombre_de_clasificacion_entre_hermanos_activos"]),
]
_LINEA_MAPA = {
    "ex_contrato_participantes__contrato_actor_rol": '    "ex_contrato_participantes__contrato_actor_rol": ("23P01", PARTICIPANTE_DUPLICADO),\n',
    "ex_contrato_participantes__principal_por_rol": '    "ex_contrato_participantes__principal_por_rol": ("23P01", PRINCIPAL_DUPLICADO),\n',
    "ex_contrato_servicios__contrato_servicio": '    "ex_contrato_servicios__contrato_servicio": ("23P01", TRATAMIENTO_SOLAPADO),\n',
    "ex_propiedad_servicios__propiedad_servicio": '    "ex_propiedad_servicios__propiedad_servicio": ("23P01", SERVICIO_YA_VINCULADO),\n',
    "ex_contrato_revision_renta_versiones__contrato": '    "ex_contrato_revision_renta_versiones__contrato": ("23P01", CLAUSULA_SOLAPADA),\n',
    "ck_contratos__habitacion": '    "ck_contratos__habitacion": ("23514", HABITACION_NO_ADMITIDA),\n',
    "ck_contrato_servicios__repercusion_coherente": '    "ck_contrato_servicios__repercusion_coherente": ("23514", TRATAMIENTO_INCOMPATIBLE),\n',
    "ck_contrato_participantes__rol": '    "ck_contrato_participantes__rol": ("23514", ROL_DESCONOCIDO),\n',
    "ck_tercero_roles__rol_codigo": '    "ck_tercero_roles__rol_codigo": ("23514", ROL_DESCONOCIDO),\n',
    "ck_contrato_servicios__renta_repercutible_excl": '    "ck_contrato_servicios__renta_repercutible_excl": ("23514", TRATAMIENTO_INCOMPATIBLE),\n',
    "ck_contrato_servicios__porcentaje": '    "ck_contrato_servicios__porcentaje": ("23514", TRATAMIENTO_INCOMPATIBLE),\n',
    "ck_contrato_revision_renta_versiones__porcentaje_fijo_exigido":
        '    "ck_contrato_revision_renta_versiones__porcentaje_fijo_exigido": ("23514", CLAUSULA_INCOMPLETA),\n',
    "ck_contrato_revision_renta_versiones__ninguna_sin_parametros":
        '    "ck_contrato_revision_renta_versiones__ninguna_sin_parametros": ("23514", CLAUSULA_INCOMPLETA),\n',
    "ck_contratos__fin_prevista_no_anterior": '    "ck_contratos__fin_prevista_no_anterior": ("23514", FECHA_ANTERIOR_INICIO),\n',
    "ck_contratos__fin_real_no_anterior": '    "ck_contratos__fin_real_no_anterior": ("23514", FECHA_ANTERIOR_INICIO),\n',
    "uq_clasificaciones_tercero__owner_parent_nombre": '    "uq_clasificaciones_tercero__owner_parent_nombre": ("23505", CLASIFICACION_NOMBRE_REPETIDO),\n',
}
for _id, _constraint, _efecto, _tests in _MAPA:
    MUTANTES.append((_id, f"mapa §1.5 (O-15): sin la fila {_constraint} la violacion fisica ({_efecto}) deja de traducirse",
                     [(ERR, _LINEA_MAPA[_constraint], "")], _tests, None, 1))
MUTANTES.append(
    ("M-FIS-17", "C-31: FUNCIONES_TRIGGER sin la firma gapto.fn_check_jerarquia_aciclica() (el P0001 del ciclo no se traduce)",
     [(ERR, 'FUNCIONES_TRIGGER: dict[str, str] = {"gapto.fn_check_jerarquia_aciclica()": CLASIFICACION_CICLO}\n',
       'FUNCIONES_TRIGGER: dict[str, str] = {}\n')],
     [T306 + "test_trigger_aciclico_se_traduce_por_la_firma_de_la_funcion"], None, 1))

#: Guardas de §XII.3 que viven solo en la base: no hay codigo del servidor que mutar. (id, guarda, motivo, cubierto por)
NO_APLICA = [
    ("NA-01", "SIN_INDICAR con DELETE (42501): la REVOCACION de DELETE para gapto_runtime",
     "el privilegio esta en las migrations 0230/0351, no en codigo del servidor",
     "scripts/mutantes/f06_02_03_0355.py (familia MS) y test_304::test_el_runtime_no_puede_borrar_roles_ni_clasificaciones; "
     "la parte de codigo (el writer que borra en lugar de cerrar) es M-CON-32"),
    ("NA-02", "rol fuera de catalogo: el CHECK ck_contrato_participantes__rol que rechaza un rol inventado",
     "CHECK de 0050 ampliado en 0355; el codigo solo lo traduce (M-FIS-08) y valida antes (M-CON-34a/b)",
     "scripts/mutantes/f06_02_03_0355.py MS-02 (CHECK que admite un rol inventado)"),
    ("NA-03", "AGENCIA y ADMINISTRADOR admitidos por el CHECK de roles de participante",
     "alcance de 0355 (migration), sin codigo del servidor que mutar",
     "scripts/mutantes/f06_02_03_0355.py MS-01 (CHECK sin AGENCIA)"),
    ("NA-04", "FORCE RLS restaurado y precheck de la definicion en 0355",
     "garantia de la migration, sin codigo del servidor",
     "scripts/mutantes/f06_02_03_0355.py MS-03 y MS-04"),
]

# ------------------------------------------------------------------ cliente (mobile/)
DOMC = "mobile/src/domain/contratos.ts"
PALT = "mobile/src/screens/ContratoAltaScreen.tsx"
PCON = "mobile/src/screens/ContratosScreen.tsx"
JDOM = "jest:__tests__/contratos_dominio.test.ts::"
JALT = "jest:__tests__/contratos_alta.test.tsx::"
JLIS = "jest:__tests__/contratos_lista.test.tsx::"
JSRV = "jest:__tests__/contratos_servicios.test.tsx::"
JTER = "jest:__tests__/contratos_terceros.test.tsx::"
JREN = "jest:__tests__/contratos_sin_renta.test.tsx::"

MUTANTES_CLIENTE: list[tuple] = [
    ("MC-CON-01", "B2b: el cliente no compara el solape antes de avanzar (decision 3): firma sin aviso de «Ya esta alquilada»",
     [(PALT, '      if (s.length > 0) {\n        setSolapeTipo(s[0].tipo);', '      if (false) {\n        setSolapeTipo(s[0].tipo);')],
     [JALT + "B2b: si la habitaci"], None, 1),
    ("MC-CON-02", "solape cliente: el fin PREVISTO libera la habitacion (decision 6)",
     [(DOMC, "    if (e.fecha_fin_real !== null && e.fecha_fin_real < n.inicio) return false;\n",
       "    if ((e.fecha_fin_real ?? e.fecha_fin_prevista) !== null && (e.fecha_fin_real ?? e.fecha_fin_prevista)! < n.inicio) return false;\n")],
     [JDOM + "el fin PREVISTO vencido no libera", JALT + "el fin previsto vencido NO libera"], None, 1),
    ("MC-CON-03", "solape cliente: un borrador cuenta (INV-ALQ-09)",
     [(DOMC, "e.estado_documental !== 'FORMALIZADO' || e.tipo === 'OTRO') return false;",
       "e.estado_documental === 'CANCELADO' || e.tipo === 'OTRO') return false;")],
     [JDOM + "un borrador y un cancelado no cuentan", JALT + "el borrador no se compara"], None, 1),
    ("MC-CON-04", "solape cliente en un solo sentido: una vivienda completa nueva no choca con una habitacion",
     [(DOMC, "    if (n.tipo === 'VIVIENDA_COMPLETA') return true;\n", "    if (n.tipo === 'VIVIENDA_COMPLETA') return e.tipo === 'VIVIENDA_COMPLETA';\n")],
     [JDOM + "habitaci.n contra vivienda completa firmada y al rev", JALT + "vivienda completa choca con una habitaci"], None, 1),
    ("MC-CON-05", "solape cliente en un solo sentido: una habitacion nueva no choca con una vivienda completa",
     [(DOMC, "    return e.tipo === 'VIVIENDA_COMPLETA' || (e.tipo === 'HABITACION' && e.habitacion === n.habitacion);",
       "    return e.tipo === 'HABITACION' && e.habitacion === n.habitacion;")],
     [JDOM + "habitaci.n contra vivienda completa firmada y al rev"], None, 1),
    ("MC-CON-06", "solape cliente: OTRO choca con todo",
     [(DOMC, "  if (n.tipo === 'OTRO' || !esFechaIso(n.inicio)) return [];", "  if (!esFechaIso(n.inicio)) return [];")],
     [JDOM + "habitaci.n solo choca con la misma habitaci", JALT + "OTRO no solapa con nada"], None, 1),
    ("MC-CON-07", "D25 cliente: «Tu» aceptado como inquilino (YO no puede ser INQUILINO)",
     [(DOMC, "    if (p.terceroId === null && p.rol === 'INQUILINO') f.push(TEXTO_INQUILINO_NO_YO);\n", "")],
     [JDOM + "no puede ser inquilino ni agencia", JALT + "D25 en pantalla"], None, 1),
    ("MC-CON-08", "D25 cliente: «Tu» aceptado como agencia o administrador",
     [(DOMC, "    if (p.terceroId === null && ROLES_INTERMEDIARIO.includes(p.rol)) f.push('La agencia o el administrador son solo terceros: «Tú» no puede serlo.');\n", "")],
     [JDOM + "no puede ser inquilino ni agencia", JALT + "D25 en pantalla"], None, 1),
    ("MC-CON-09", "D25 cliente: la AGENCIA cuenta como arrendador para firmar",
     [(DOMC, "export const ROLES_ARRENDADOR: RolParticipante[] = ['PROPIETARIO', 'GESTOR'];", "export const ROLES_ARRENDADOR: RolParticipante[] = ['PROPIETARIO', 'GESTOR', 'AGENCIA'];")],
     [JDOM + "para firmar hacen falta arrendador", JALT + "D25 en pantalla"], None, 1),
    ("MC-CON-10", "D25 cliente: firmar sin inquilino",
     [(DOMC, "    if (!b.personas.some((p) => p.rol === 'INQUILINO')) f.push('Para firmar hace falta un inquilino.');\n", "")],
     [JDOM + "para firmar hacen falta arrendador"], None, 1),
    ("MC-CON-11", "D25 cliente: principal exigido tambien al avalista",
     [(DOMC, "export const ROLES_CON_PRINCIPAL: RolParticipante[] = ['PROPIETARIO', 'GESTOR', 'INQUILINO'];",
       "export const ROLES_CON_PRINCIPAL: RolParticipante[] = ['PROPIETARIO', 'GESTOR', 'INQUILINO', 'AVALISTA'];")],
     [JDOM + "principal: obligatorio solo en arrendador"], None, 1),
    ("MC-CON-12", "clausula cliente: «No lo se» viaja como NINGUNA",
     [(DOMC, "  if (c.eleccion === null || c.eleccion === 'NO_SE') return null; // «No lo sé»: sin fila (nunca NINGUNA)\n",
       "  if (c.eleccion === null) return null;\n  if (c.eleccion === 'NO_SE') return { tipo: 'NINGUNA' };\n")],
     [JDOM + "IPC con par.metros desconocidos"], None, 1),
    ("MC-CON-13", "servicios cliente: POR_FACTURA viaja con porcentaje",
     [(DOMC, "      if (modo === 'REPERCUTIDO_FIJO') w.porcentaje = parsearPorcentaje(t.porcentaje);",
       "      if (modo === 'REPERCUTIDO_FIJO' || modo === 'POR_FACTURA') w.porcentaje = parsearPorcentaje(t.porcentaje);")],
     [JDOM + "SIN_INDICAR y sin elegir no viajan"], None, 1),
    ("MC-CON-14", "servicios cliente: SIN_INDICAR viaja en el alta",
     [(DOMC, ".filter(([, t]) => t.modo !== null && t.modo !== 'SIN_INDICAR')", ".filter(([, t]) => t.modo !== null)")],
     [JDOM + "SIN_INDICAR y sin elegir no viajan"], None, 1),
    ("MC-CON-15", "servicios cliente: % fijo 0 aceptado (`> 0` -> `>= 0`)",
     [(DOMC, "  return v > 0 && v <= 100 ? x : null;", "  return v >= 0 && v <= 100 ? x : null;")],
     [JDOM + "porcentajes: ", JALT + "B5: % fijo exige porcentaje"], None, 1),
    ("MC-CON-16", "servicios cliente: repercutir sin inquilino principal aceptado",
     [(DOMC, "    if ((t.modo === 'REPERCUTIDO_FIJO' || t.modo === 'POR_FACTURA') && !inquilinoPrincipal(b)) f.push('Para repercutir un servicio hace falta un inquilino principal (tercero).');\n", "")],
     [JDOM + "B5: repercutir exige inquilino principal", JALT + "B5: % fijo exige porcentaje"], None, 1),
    ("MC-CON-17", "clausula cliente: PORCENTAJE_FIJO sin porcentaje aceptado",
     [(DOMC, "  if (c.eleccion === 'PORCENTAJE_FIJO' && parsearPorcentaje(c.porcentaje) === null) f.push('Indica el porcentaje fijo (mayor que 0).');\n", "")],
     [JDOM + "B4: nada viene elegido"], None, 1),
    ("MC-CON-18", "alta cliente: el payload lleva renta (R-E-01 / O-14)",
     [(DOMC, "    servicios: tratamientosWire(b),\n  };\n  if (b.tipo === 'HABITACION') p.habitacion = b.habitacion;",
       "    servicios: tratamientosWire(b),\n    renta: null,\n  } as unknown as PayloadAltaContrato;\n  if (b.tipo === 'HABITACION') p.habitacion = b.habitacion;")],
     [JDOM + "nunca lleva renta ni fianza", JALT + "B1 . B6"], None, 1),
    ("MC-CON-19", "terminacion cliente: el boton «Terminar» siempre activo aunque el contrato tenga renta de V3 (terminable = false)",
     [(PCON, "                {ct.terminable.terminable ? (", "                {true ? (")],
     [JLIS + "la explicaci.n va antes del bot.n"], None, 1),
    ("MC-CON-20", "terminacion cliente: no se muestra la marca de renta registrada (V3) en la fila",
     [(PCON, "f.renta_registrada ? TEXTO_RENTA_REGISTRADA : null", "null")],
     [JLIS + "un contrato migrado con renta se marca"], None, 1),
    ("MC-CON-21", "V-bis cliente: los homonimos no muestran naturaleza y uso (segunda linea)",
     [(DOMC, "export const detalleHomonimo = (t: TerceroParaContrato): string => `${textoNaturaleza(t.naturaleza)} · ${textoUso(t.uso)}`;",
       "export const detalleHomonimo = (t: TerceroParaContrato): string => `${textoNaturaleza(t.naturaleza)}`;")],
     [JDOM + "dos .Empresa SL. activas", JTER + "B3c: hom.nimos con naturaleza y uso"], None, 1),
    ("MC-CON-22", "V-bis cliente: se muestra naturaleza y uso tambien a quien no es homonimo",
     [(DOMC, "    const homonimo = grupo.length > 1;", "    const homonimo = grupo.length > 0;")],
     [JDOM + "dos .Empresa SL. activas", JTER + "B3c: hom.nimos con naturaleza y uso"], None, 1),
    ("MC-CON-23", "O-30 cliente: los inactivos se listan en el selector de participantes",
     [(DOMC, "  const activos: TerceroDelSelector[] = lista.filter((t) => t.enabled !== false).map((t) => ({ ...t, enabled: true })); // el servidor solo manda activos y sin `enabled`", "  const activos: TerceroDelSelector[] = lista.map((t) => ({ ...t, enabled: true }));")],
     [JDOM + "los inactivos no se listan", JTER + "los inactivos no aparecen"], None, 1),
    ("MC-CON-23b", "V-bis cliente: el selector vuelve a exigir `enabled` (lista vacia con la respuesta real del servidor)",
     [(DOMC, "  const activos: TerceroDelSelector[] = lista.filter((t) => t.enabled !== false).map((t) => ({ ...t, enabled: true })); // el servidor solo manda activos y sin `enabled`", "  const activos: TerceroDelSelector[] = lista.filter((t) => t.enabled).map((t) => ({ ...t, enabled: true }));")],
     [JDOM + "forma REAL del servidor"], None, 1),
    ("MC-CON-24", "O-30 cliente: dos filas identicas se eligen directamente (sin pasar por la ficha)",
     [(DOMC, "    const identica = homonimo && grupo.some(", "    const identica = false && grupo.some(")],
     [JDOM + "filas a.n id.nticas", JTER + "O-30: dos filas id.nticas"], None, 1),
    ("MC-CON-25", "E3 cliente: la agencia propone un rol de tercero",
     [(DOMC, "const ROL_TERCERO_DE: Partial<Record<RolParticipante, RolTercero>> = { INQUILINO: 'INQUILINO', AVALISTA: 'AVALISTA', GESTOR: 'GESTOR' };",
       "const ROL_TERCERO_DE: Partial<Record<RolParticipante, RolTercero>> = { INQUILINO: 'INQUILINO', AVALISTA: 'AVALISTA', GESTOR: 'GESTOR', AGENCIA: 'GESTOR' };")],
     [JDOM + "inquilino, avalista y gestor proponen su rol", JALT + "B3b: agencia o administrador"], None, 1),
    ("MC-CON-26", "O-31 cliente: el motivo de regla de servicio muestra el texto de la renta del contrato",
     [(DOMC, "    if (motivo === MOTIVO_REGLA_SERVICIO_PENDIENTE) return TEXTO_SERVICIO_BAJA_REGLA;", "    if (motivo === MOTIVO_REGLA_SERVICIO_PENDIENTE) return TEXTO_RENTA_PENDIENTE;")],
     [JDOM + "O-31: el motivo de regla de servicio", JSRV + "O-31: con regla financiera"], None, 1),
]

GRUPOS = {"servidor": MUTANTES, "cliente": MUTANTES_CLIENTE}


def normalizar(mu: tuple) -> tuple:
    """(id, desc, cambios, tests, equivalencia, repeticiones); admite la forma de 5 campos (repeticiones = 1)."""
    if len(mu) == 5:
        return (*mu, 1)
    if len(mu) != 6 or not isinstance(mu[5], int) or mu[5] < 1:
        sys.exit(f"Mutante mal formado: {mu[0] if mu else mu!r}")
    return tuple(mu)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


_OMITIDOS = re.compile(r"\b\d+ (skipped|xfailed|xpassed)\b")


@base_limpia_mutante.por_llamada
def correr(tests: list[str]) -> tuple[int, bool]:
    """pytest por grupo (tests/api con su rootdir; test_307 aparte con GAPTO_F060203_CONCURRENCIA=1; el resto de
    tests/ sin rootdir) y Jest en mobile/. Devuelve (rc, hubo_omitidos): rc != 0 si alguno falla."""
    conc = [t for t in tests if t.startswith(CONCURRENCIA)]
    api = [t for t in tests if t.startswith("tests/api/") and t not in conc]
    resto = [t for t in tests if t.startswith("tests/") and not t.startswith("tests/api/")]
    jest = [t[len("jest:"):] for t in tests if t.startswith("jest:")]
    rc, omitidos = 0, False
    base = dict(os.environ)
    for grupo, extra, entorno in ((api, ["--rootdir=tests/api"], base),
                                  (conc, ["--rootdir=tests/api"], {**base, "GAPTO_F060203_CONCURRENCIA": "1"}),
                                  (resto, [], base)):
        if not grupo:
            continue
        cmd = [sys.executable, "-m", "pytest", *grupo, "-q", "-x", "-p", "no:cacheprovider", "-rsx", *extra]
        p = subprocess.run(cmd, cwd=RAIZ, capture_output=True, env=entorno)
        salida = p.stdout.decode("utf-8", "replace")
        omitidos = omitidos or bool(_OMITIDOS.search(salida))
        rc = rc or p.returncode
    npx = "npx.cmd" if os.name == "nt" else "npx"
    for t in jest:
        fichero, patron = t.split("::", 1)
        cmd = [npx, "jest", fichero, "-t", patron, "--silent"]
        p = subprocess.run(cmd, cwd=RAIZ / "mobile", capture_output=True)
        texto = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
        # con -t, un patron que no selecciona nada termina con rc 0 y sin «N passed»: eso no es verde
        omitidos = omitidos or (p.returncode == 0 and not re.search(r"Tests:.*\b[1-9]\d* passed", texto))
        rc = rc or p.returncode
    return rc, omitidos


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


def escribir_journal(datos: dict) -> None:
    with JOURNAL.open("w", encoding="utf-8") as f:
        f.write(json.dumps(datos))
        f.flush()
        os.fsync(f.fileno())


def anotar(salida: pathlib.Path | None, linea: str) -> None:
    print(linea, flush=True)
    if salida is not None:
        with salida.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")
            f.flush()
            os.fsync(f.fileno())


def aplicar(cambios: list[tuple[str, str, str]]) -> tuple[dict[str, bytes], dict[str, str]] | None:
    """Sustitucion secuencial; None si algun texto viejo no aparece exactamente una vez."""
    ficheros = sorted({c[0] for c in cambios})
    originales = {f: (RAIZ / f).read_bytes() for f in ficheros}
    textos = {f: b.decode("utf-8") for f, b in originales.items()}
    for f, texto, sustituto in cambios:
        if textos[f].count(texto) != 1:
            return None
        textos[f] = textos[f].replace(texto, sustituto)
    return originales, textos


def comprobar(lista: list[tuple]) -> int:
    """--check: sin base ni tests. Cada `viejo` una sola vez, ficheros existentes, ids unicos, catalogo impreso."""
    malos = 0
    for mid, desc, cambios, tests, _eq, rep in lista:
        if aplicar(cambios) is None:
            malos += 1
            for f, viejo, _ in cambios:
                n = (RAIZ / f).read_bytes().decode("utf-8").count(viejo)
                if n != 1:
                    print(f"  MAL {mid}: {f} -> el texto viejo aparece {n} veces: {viejo[:90]!r}")
        for t in tests:
            ruta = t.split("::")[0].replace("jest:", "")
            ruta = ruta if ruta.startswith("tests/") else f"mobile/{ruta}"
            if not (RAIZ / ruta).exists():
                malos += 1
                print(f"  MAL {mid}: no existe el fichero de test {ruta}")
        print(f"{mid} | x{rep} | {len(tests)} tests | {desc}")
    for nid, guarda, motivo, cubre in NO_APLICA:
        print(f"{nid} | NO_APLICA_SERVIDOR | {guarda} | {motivo} | cubierto por: {cubre}")
    print(f"CHECK: {len(lista)} mutantes, {malos} problemas, {len(NO_APLICA)} NO_APLICA")
    return malos


def main() -> None:
    grupo = sys.argv[sys.argv.index("--grupo") + 1] if "--grupo" in sys.argv else "todos"
    if grupo not in ("servidor", "cliente", "todos"):
        sys.exit("--grupo servidor|cliente|todos")
    lista = [normalizar(mu) for mu in (MUTANTES + MUTANTES_CLIENTE if grupo == "todos" else GRUPOS[grupo])]
    ids = [mu[0] for mu in lista]
    if len(set(ids)) != len(ids):
        sys.exit("IDs de mutante repetidos.")
    if "--check" in sys.argv:
        sys.exit(1 if comprobar(lista) else 0)
    if not os.getenv("GAPTO_TEST_DATABASE_URL"):
        sys.exit("Falta GAPTO_TEST_DATABASE_URL (base local desechable).")
    if recuperar_si_pendiente():
        sys.exit("Habia un mutante pendiente: restaurado y verificado. Resultado NO-PASS; relanzar.")
    solo = None
    if "--solo" in sys.argv:
        solo = set(sys.argv[sys.argv.index("--solo") + 1].split(","))
        desconocidos = solo - set(ids)
        if desconocidos:
            sys.exit(f"--solo con IDs fuera del grupo {grupo}: {sorted(desconocidos)}")
    salida = pathlib.Path(sys.argv[sys.argv.index("--salida") + 1]) if "--salida" in sys.argv else None
    elegidos = [mu for mu in lista if solo is None or mu[0] in solo]
    if not elegidos:
        sys.exit("Ningun mutante elegido.")
    preflight = sorted({t for mu in elegidos for t in mu[3]})
    rc, omitidos = correr(preflight)
    if rc != 0 or omitidos:
        sys.exit("PREFLIGHT ROJO" + (" (tests omitidos: no son verdes)" if omitidos else "") + ": no se muta nada.")
    anotar(salida, f"PREFLIGHT VERDE grupo={grupo} mutantes={len(elegidos)} tests={len(preflight)}")
    if solo is None and grupo in ("servidor", "todos"):
        for nid, guarda, motivo, cubre in NO_APLICA:
            anotar(salida, f"{nid} | NO_APLICA_SERVIDOR | {guarda} | {motivo} | cubierto por: {cubre}")
    veredictos = []
    for mid, desc, cambios, tests, equivalencia, repeticiones in elegidos:
        aplicado = aplicar(cambios)
        if aplicado is None:
            v = (mid, "NO_CLASIFICABLE", "transformacion no aplicable", desc)
            veredictos.append(v)
            anotar(salida, " | ".join(v))
            continue
        originales, textos = aplicado
        ficheros = sorted(originales)
        escribir_journal({"mutante": mid, "ficheros": [
            {"fichero": f, "original_hex": originales[f].hex(), "sha256": sha(originales[f])} for f in ficheros]})
        resultado = "NO_CLASIFICABLE"
        motivo_nc = ""
        try:
            for f in ficheros:
                (RAIZ / f).write_bytes(textos[f].encode("utf-8"))
            muertes = 0
            for k in range(1, repeticiones + 1):
                rc, omitidos = correr(tests)
                pasada = "OMITIDO" if (rc == 0 and omitidos) else ("MUERTO" if rc != 0 else "VIVO")
                anotar(salida, f"  PASADA {mid} {k}/{repeticiones}: {pasada} (rc={rc})")
                if pasada == "OMITIDO":
                    motivo_nc = "tests omitidos en la pasada"
                    break
                muertes += pasada == "MUERTO"
            else:
                resultado = "MUERTO" if muertes == repeticiones else (
                    "VIVO" if muertes == 0 else f"INESTABLE_{muertes}de{repeticiones}")
        finally:
            ok = True
            for f in ficheros:
                (RAIZ / f).write_bytes(originales[f])
                ok = ok and sha((RAIZ / f).read_bytes()) == sha(originales[f])
            JOURNAL.unlink(missing_ok=True)
        if resultado == "VIVO" and equivalencia:
            resultado = "EQUIVALENTE"
        nota = f"{desc} [equivalente: {equivalencia}]" if resultado == "EQUIVALENTE" else desc
        if motivo_nc:
            nota = f"{desc} [{motivo_nc}]"
        if not ok:
            resultado, nota = "NO_CLASIFICABLE", f"{desc} [restauracion no verificada]"
        v = (mid, resultado, f"x{repeticiones}",
             ",".join(sorted({pathlib.Path(t.split("::")[0].replace("jest:", "")).name for t in tests})), nota)
        veredictos.append(v)
        anotar(salida, " | ".join(v))
        if not ok:
            sys.exit(f"RESTAURACION NO VERIFICADA en {mid}: se detiene el arnes. Resultado NO-PASS.")
    muertos = sum(1 for v in veredictos if v[1] == "MUERTO")
    equivalentes = sum(1 for v in veredictos if v[1] == "EQUIVALENTE")
    anotar(salida, f"RESUMEN grupo={grupo}: {muertos} muertos, {equivalentes} equivalentes documentados, "
                   f"{len(veredictos) - muertos - equivalentes} otros / {len(veredictos)}"
                   + (f"; {len(NO_APLICA)} NO_APLICA_SERVIDOR" if solo is None and grupo in ("servidor", "todos") else ""))
    sys.exit(0 if muertos + equivalentes == len(veredictos) else 1)


if __name__ == "__main__":
    main()
