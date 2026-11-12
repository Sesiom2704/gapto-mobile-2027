#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f06_01_b2.py
# Ruta: scripts/mutantes/f06_01_b2.py
# Descripcion: Arnes de mutacion de F06-01 B2 · Compra (N1; mandato B2 N1 v1.0 §7.3; contratos R1 v0.9.5
#   Parte II y §I.5; oraculos v0.7 §A.9-§A.10). Mismo motor que scripts/mutantes/f06_01_b1.py:
#   - sustitucion de texto EXACTO que aparece una sola vez (0 o mas de 1 -> NO_CLASIFICABLE y el arnes PARA);
#   - journal (marcador con el contenido original) ANTES del primer byte mutado; si una ejecucion anterior se
#     corto, restaura y aborta;
#   - restauracion verificada por SHA-256 tras cada mutante (tambien si pytest aborta);
#   - preflight: todos los discriminantes verdes antes de mutar;
#   - veredicto escrito a disco en cuanto se conoce (GAPTO_B2_MUTANTES_VEREDICTOS, una linea JSON por mutante)
#     y salida de pytest de cada mutante (GAPTO_B2_MUTANTES_SALIDA).
#   Un mutante solo se da por MUERTO si cae al menos uno de SUS discriminantes.
#   Mutantes: M-ID-14..18, M-FE-01..05, M-CO-01..12, M-IP-01..07, M-IP-10, M-IP-11, M-Q16-01/02, M-AC-01,
#   M-O10-28 (writer fuera de la lista), M-O10-29 (habilitacion activada) y los de la v0.2 §M de la compra
#   (M-V02-*). M-AC-02 (cliente) va en el arnes de Jest de B2 (scripts/dev/mutantes_f06_t1_b2_cliente.py).
#   Requiere GAPTO_TEST_DATABASE_URL (base desechable, formato postgresql://), GAPTO_B1_CONCURRENCIA=1 y
#   GAPTO_B2_CONCURRENCIA=1 (discriminantes de las baterias serie).
# Uso:
#   python scripts/mutantes/f06_01_b2.py              # todos
#   python scripts/mutantes/f06_01_b2.py M-ID-14      # subconjunto
# Version: 0.1.0 (F06 T1-F06 B2 N1)
# Version: 0.1.1 (F06 T1-F06 B2 N1, tirada del paso 12): el resumen de pytest incluye los ERROR (-rfE); con -rf un
#   discriminante que cae en su fixture (ERROR, no FAILED) se clasificaba NO_CLASIFICABLE (M-CO-09) y paraba el arnes.
# Version: 0.1.2 (tirada 2 del paso 12): M-Q16-02 quedo VIVO porque mutaba la guarda de tipo de `_comun` y las guardas
#   siguientes de la lectura (dependencias del H0 y tipo en «corregir») seguian negando las acciones: no era el defecto
#   que describe el oraculo. Ahora la lectura OFRECE «anular por duplicado» sobre ADQUISICION_PATRIMONIAL (defecto
#   literal de M-Q16-02, oraculos v0.7 §A.10.3); discriminantes O10.23 (c) en H0 y Hk.
# ============================================================
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass

RAIZ = pathlib.Path(__file__).resolve().parents[2]
COMPRA = "backend/app/patrimonio/compra.py"
COMPL = "backend/app/patrimonio/completitud.py"
COSTE = "backend/app/patrimonio/coste.py"
ATR = "backend/app/patrimonio/atribucion.py"
HAB = "backend/app/patrimonio/habilitacion.py"
RUTAS = "backend/app/patrimonio/rutas.py"
REPO = "backend/app/propiedades/repositorio.py"
SRV = "backend/app/propiedades/servicio.py"
EDICION = "backend/app/actividad/edicion.py"
ACTIVIDAD = "backend/app/actividad/lecturas.py"
T250 = "tests/api/test_250_f06_01_b2_compra.py"
T251 = "tests/api/test_251_f06_01_b2_compra03.py"
T252 = "tests/api/test_252_f06_01_b2_coste_completitud.py"
T253 = "tests/api/test_253_f06_01_b2_reserva_h0hk_pb005.py"
T254 = "tests/api/test_254_f06_01_b2_concurrencia_serial.py"
T233 = "tests/api/test_233_f06_01_b1_rls_acl.py"
T235 = "tests/api/test_235_f06_01_0352_guarda_c_prop_02.py"
T237 = "tests/api/test_237_f06_01_b1r_intencion_concurrente_serial.py"
MARCADOR = RAIZ / ".mutante_f06_01_b2_en_curso"


def n(fichero: str, nombre: str) -> str:
    return f"{fichero}::{nombre}"


@dataclass(frozen=True)
class Mutante:
    ident: str
    invariante: str
    fichero: str
    viejo: str
    nuevo: str
    discriminantes: tuple[str, ...]


MUTANTES = (
    # ------------------------------------------------------------------ identidad de la compra (§II.1, AJ-TR1-09)
    Mutante("M-ID-14", "El replay de la compra lo reconoce el comparador propio, no OP-22 (HF-01)", COMPRA,
            "        for r, d in declaradas.items():                                                 # (i) y (iii)\n"
            "            if not agregado_coincide(sesion, d, parte_de.get(r)):\n"
            "                return Rechazo(IDENTIDAD_REUTILIZADA)\n",
            "        for r, d in declaradas.items():                                                 # (i) y (iii)\n"
            "            _op22(sesion).registrar_hecho_compuesto(sesion.contexto, d)\n",
            (n(T250, "test_o6_1_replay_reordenado_es_idempotente_sin_escribir_ni_invocar_op22"),)),
    Mutante("M-ID-15", "El comparador exige la pertenencia exacta al lote: ninguna PARTE_DE ajena hacia H0", COMPRA,
            "        if _relaciones_hacia(sesion, h0) - compra03 != {(i, hk) for hk, (i, _) in parte_de.items()}:\n",
            "        if False:\n",
            (n(T250, "test_o6_9_o6_16_o6_21_parte_de_ajena_hacia_h0"),)),
    Mutante("M-ID-16", "El comparador compara los CAMPOS de cada fila, no solo las identidades", COMPRA,
            "    hecho = repo_comp.leer(sesion, \"hechos_financieros\", raiz)\n    if hecho is None or",
            "    return True\n    hecho = repo_comp.leer(sesion, \"hechos_financieros\", raiz)\n    if hecho is None or",
            (n(T250, "test_o6_15_campo_cambiado_en_un_hk_rompe_el_replay"),)),
    Mutante("M-ID-17", "El replay no es solo por el sello: compara el agregado de cada raiz", COMPRA,
            "        for r, d in declaradas.items():                                                 # (i) y (iii)\n"
            "            if not agregado_coincide(sesion, d, parte_de.get(r)):\n"
            "                return Rechazo(IDENTIDAD_REUTILIZADA)\n",
            "",
            (n(T250, "test_o6_15_campo_cambiado_en_un_hk_rompe_el_replay"),)),
    Mutante("M-ID-18", "Un lote parcial nunca se completa con OP-22", COMPRA,
            "    if existentes:\n        if len(existentes) != len(raices):",
            "    if len(existentes) == len(raices):\n        if len(existentes) != len(raices):",
            (n(T250, "test_o6_19_lote_parcial_no_se_completa"),)),
    # ------------------------------------------------------------------ fecha de escritura (AJ-TR1-10)
    Mutante("M-FE-01", "La propuesta de C-COMPRA-01 se lee en la fecha de ESCRITURA, no en la de cada efecto", COMPRA,
            "    partes = m2.resolver(sesion, propiedad_id, peticion[\"atribucion\"])\n    if isinstance(partes, str):\n"
            "        return Rechazo(partes)\n    datos = composiciones(partes)\n",
            "    atr = peticion[\"atribucion\"]\n"
            "    if atr[\"modo\"] == m2.SEGUN_TITULARIDAD and canon[\"gastos\"]:\n"
            "        atr = {**atr, \"propuesta_vista\": {**atr[\"propuesta_vista\"], \"fecha_referencia\": min(\n"
            "            dt.date.fromisoformat(g[\"fecha_economica\"]) for g in canon[\"gastos\"])}}\n"
            "    partes = m2.resolver(sesion, propiedad_id, atr)\n    if isinstance(partes, str):\n"
            "        return Rechazo(partes)\n    datos = composiciones(partes)\n",
            (n(T250, "test_o6_22_propuesta_en_la_fecha_de_escritura_para_todas_las_raices"),
             n(T250, "test_o2_compra_completa_composicion_y_respuesta"))),
    Mutante("M-FE-02", "La fecha economica de cada Hk no se reescribe con la de escritura", COMPRA,
            "            datos[hk] = _raiz(hecho_id=hk, fecha=dt.date.fromisoformat(g[\"fecha_economica\"]),",
            "            datos[hk] = _raiz(hecho_id=hk, fecha=escritura,",
            (n(T250, "test_o6_22_propuesta_en_la_fecha_de_escritura_para_todas_las_raices"),)),
    Mutante("M-FE-03", "Sin titularidad en la fecha no se infiere ninguna participacion", ATR,
            "    if not vigente:\n        return TITULARIDAD_NO_DISPONIBLE\n",
            "    if not vigente:\n        return _partes(propuesta[\"partes\"])\n",
            (n(T250, "test_o6_23_sin_titularidad_en_la_escritura_y_fecha_referencia_distinta"),)),
    Mutante("M-FE-04", "C-COMPRA-03 usa la fecha economica de su efecto, no la de escritura", COMPRA,
            "    forma = m2.validar_forma(peticion[\"atribucion\"], criterio=m2.CRITERIO_EFECTO,\n"
            "                             fecha_referencia=g0[\"fecha_economica\"])\n",
            "    forma = None if (peticion[\"atribucion\"].get(\"propuesta_vista\") or {}).get(\"criterio\") == "
            "m2.CRITERIO_ESCRITURA else m2.validar_forma(peticion[\"atribucion\"], criterio=m2.CRITERIO_EFECTO,\n"
            "                             fecha_referencia=g0[\"fecha_economica\"])\n",
            (n(T251, "test_o6_24_propuesta_en_la_fecha_economica_de_su_efecto"),)),
    Mutante("M-FE-05", "La compra no modifica la titularidad historica de B1 ni reatribuye", COMPRA,
            "            for hk in hks.values():\n                _insertar_parte_de(sesion, hk, h0, MARCA_LOTE)\n",
            "            for hk in hks.values():\n                _insertar_parte_de(sesion, hk, h0, MARCA_LOTE)\n"
            "            sesion.ejecutar(\"UPDATE gapto.entidad_participaciones SET vigente_desde = vigente_desde - 1 \"\n"
            "                            \"WHERE entidad_id = %s AND vigente_hasta IS NULL\", (propiedad_id,))\n",
            (n(T250, "test_o6_25_no_reatribuye_hechos_previos_ni_cambia_la_titularidad"),)),
    # ------------------------------------------------------------------ completitud y L-COSTE (§II.6)
    Mutante("M-CO-01", "Regla de lectura: conjunto vigente distinto del declarado -> DECLARACION_DESACTUALIZADA", COSTE,
            "    if igual is not True:\n        return \"PARCIAL\", \"DECLARACION_DESACTUALIZADA\"\n", "",
            (n(T252, "test_o10_12_gasto_omitido_anterior_al_corte"),)),
    Mutante("M-CO-02", "El conjunto incluye el importe", REPO,
            "        \"'importe', round(c.importe, 4)::numeric(20,4)::text, 'fecha', to_char(c.fecha, 'YYYY-MM-DD'), \"\n",
            "        \"'fecha', to_char(c.fecha, 'YYYY-MM-DD'), \"\n",
            (n(T252, "test_o10_20_aba_en_mejoras_con_op21"),)),
    Mutante("M-CO-03", "Solo cuentan los hechos ACTIVOS", REPO,
            "    \"JOIN gapto.hechos_financieros h ON h.id = e.hecho_id AND h.estado = 'ACTIVO' \"\n",
            "    \"JOIN gapto.hechos_financieros h ON h.id = e.hecho_id \"\n",
            (n(T252, "test_o10_7p_o10_13_op03p_anulacion_de_un_componente_de_mejoras"),)),
    Mutante("M-CO-04", "El ambito lo define la causa del efecto, no el tipo del hecho", REPO,
            "    \"WHERE e.tipo_efecto = 'VALOR_ACTIVO' AND e.causa_valor_activo IN ('ADQUISICION', 'TRANSFORMACION_CAPITALIZABLE') \"\n",
            "    \"WHERE e.tipo_efecto = 'VALOR_ACTIVO' AND e.causa_valor_activo IN ('ADQUISICION', 'TRANSFORMACION_CAPITALIZABLE') \"\n"
            "    \"AND (e.causa_valor_activo = 'ADQUISICION' OR h.tipo_hecho_id = (SELECT id FROM gapto.tipos_hecho \"\n"
            "    \"WHERE codigo = 'MEJORA_PATRIMONIAL')) \"\n",
            (n(T252, "test_componente_de_mejora_en_un_hecho_de_otro_tipo_cuenta"),)),
    Mutante("M-CO-05", "Lectura anterior al corte -> PARCIAL (fila 3)", COSTE,
            "    if a_fecha < corte:\n        return \"PARCIAL\", \"LECTURA_ANTERIOR_AL_CORTE\"\n", "",
            (n(T252, "test_o10_4_lectura_anterior_al_corte"),)),
    Mutante("M-CO-06", "La fila 5 (componente posterior al corte) respeta a_fecha", REPO,
            "                       f\"(SELECT count(*) FROM comp c WHERE c.causa = '{causa}' AND c.fecha > p.{en} \"\n"
            "                       \"AND c.fecha <= %(a)s::date)\")\n",
            "                       f\"(SELECT count(*) FROM comp c WHERE c.causa = '{causa}' AND c.fecha > p.{en})\")\n",
            (n(T252, "test_o10_15_componente_posterior_segun_a_fecha"),)),
    Mutante("M-CO-07", "C-PROP-05 bloquea la propiedad (NK) antes de identidad, version y relectura", COMPL,
            "    raiz = repo.bloquear(sesion, propiedad_id)\n",
            "    raiz = (lambda f: None if f is None else {\"row_version\": f[0], \"enabled\": f[1], \"fecha_adquisicion\": f[2]})(\n"
            "        sesion.uno(\"SELECT e.row_version, e.enabled, p.fecha_adquisicion FROM gapto.entidades e JOIN gapto.propiedades p \"\n"
            "                   \"ON p.entidad_id = e.id WHERE e.id = %s\", (propiedad_id,)))\n",
            (n(T254, "test_o7_8_gasto_posterior_frente_a_c_prop_05[A-primero]"),
             n(T254, "test_caso11_doble_declaracion_concurrente[intenciones_distintas_mismo_ambito]"),
             n(T254, "test_caso11_doble_declaracion_concurrente[intenciones_distintas_otro_ambito]"))),
    Mutante("M-CO-08", "C-PROP-05 compara la huella vista con el conjunto releido", COMPL,
            "        if huella != huella_vista:\n            return Rechazo(VISTA_DESFASADA)\n", "",
            (n(T252, "test_o10_17_c_prop_05_con_huella_antigua"),)),
    Mutante("M-CO-09", "El conjunto incluye efecto_id", REPO,
            "        \"coalesce((SELECT jsonb_agg(jsonb_build_object('efecto_id', c.efecto_id::text, 'hecho_id', c.hecho_id::text, \"\n",
            "        \"coalesce((SELECT jsonb_agg(jsonb_build_object('hecho_id', c.hecho_id::text, \"\n",
            (n(T252, "test_o10_20_bis_b2_sustitucion_con_efecto_nuevo_no_recupera"),)),
    Mutante("M-CO-10", "El importe del conjunto usa la escala de la columna (4 decimales)", REPO,
            "round(c.importe, 4)::numeric(20,4)::text", "round(c.importe, 2)::numeric(20,2)::text",
            (n(T252, "test_o10_21_escala_de_4_decimales"),)),
    Mutante("M-CO-11", "La declaracion de la compra es exactamente el conjunto de sus raices (HF-07)", COMPRA,
            "    if efectos_esperados is not None and {c[\"efecto_id\"] for c in vigente} != efectos_esperados:\n"
            "        raise _Deshacer(VISTA_DESFASADA)\n", "",
            (n(T252, "test_o10_22_hf07_componente_ajeno_a_las_raices"),)),
    Mutante("M-CO-12", "Solo el AFECTA_A de nivel efecto hace componente (HF-08)", REPO,
            "    \"AND x.tipo_relacion = 'AFECTA_A' AND x.principal AND x.efecto_id = e.id \"\n",
            "    \"AND x.tipo_relacion = 'AFECTA_A' AND x.principal AND (x.efecto_id IS NULL OR x.efecto_id = e.id) \"\n",
            (n(T252, "test_o10_24_hf08_vinculo_de_nivel_hecho_no_es_componente"),)),
    # ------------------------------------------------------------------ C-PROP-05: identidad y 0P (§I.5.1-§I.5.4)
    Mutante("M-IP-01", "Replay reconocido por contenido, nunca solo por el UUID", COMPL,
            "    return Rechazo(IDENTIDAD_REUTILIZADA)\n\n\ndef _vista", "    return True\n\n\ndef _vista",
            (n(T252, "test_o11_1_a_o11_5_replay_reutilizacion_y_estado_vigente"),)),
    Mutante("M-IP-02", "Identidad antes que version", COMPL,
            "    replay = identidad(sesion, intencion_id, propiedad_id, sellado)\n",
            "    if raiz[\"row_version\"] != row_version:\n        return Rechazo(VERSION_DESFASADA)\n"
            "    replay = identidad(sesion, intencion_id, propiedad_id, sellado)\n",
            (n(T252, "test_o11_1_a_o11_5_replay_reutilizacion_y_estado_vigente"),)),
    Mutante("M-IP-03", "El replay se compara con el contenido sellado, no con la terna vigente", COMPL,
            "        if sellada == {\"operacion\": OPERACION, \"contenido\": contenido_}:\n",
            "        if sellada is not None and sellada.get(\"operacion\") == OPERACION and repo.declaracion_completitud(\n"
            "                sesion, propiedad_id, contenido_[\"ambito\"])[1] == (None if contenido_[\"fecha_corte\"] is None\n"
            "                else dt.date.fromisoformat(contenido_[\"fecha_corte\"])):\n",
            (n(T252, "test_o11_1_a_o11_5_replay_reutilizacion_y_estado_vigente"),)),
    Mutante("M-IP-04", "El contenido sellado incluye row_version_esperada", COMPL,
            "            \"huella_conjunto_vista\": huella_vista, \"row_version_esperada\": row_version}\n",
            "            \"huella_conjunto_vista\": huella_vista}\n",
            (n(T252, "test_o11_1_a_o11_5_replay_reutilizacion_y_estado_vigente"),
             n(T252, "test_o11_13_auditoria_con_las_siete_claves"))),
    Mutante("M-IP-05", "El contenido sellado incluye huella_conjunto_vista", COMPL,
            "            \"huella_conjunto_vista\": huella_vista, \"row_version_esperada\": row_version}\n",
            "            \"row_version_esperada\": row_version}\n",
            (n(T252, "test_o11_1_a_o11_5_replay_reutilizacion_y_estado_vigente"),
             n(T252, "test_o11_13_auditoria_con_las_siete_claves"))),
    Mutante("M-IP-06", "C-PROP-05 serializa la intencion entre propiedades (0P)", COMPL,
            "    bloquear_intencion_propiedad(sesion, intencion_id)\n    hoy = hoy_owner(sesion, reloj)\n",
            "    hoy = hoy_owner(sesion, reloj)\n",
            (n(T254, "test_s18_o11_14_misma_intencion_en_dos_propiedades[A-primero]"),
             n(T252, "test_o11_22_cinco_llamadas_a_la_funcion_unica_del_0p"))),
    Mutante("M-IP-07", "El 0P va ANTES de leer la auditoria", COMPL,
            "    bloquear_intencion_propiedad(sesion, intencion_id)\n    hoy = hoy_owner(sesion, reloj)\n"
            "    if completo and fecha_corte > hoy:          # capa (O8.6): antes que el lock y que la version\n"
            "        return Rechazo(SIN_FECHA_DE_CORTE)\n    raiz = repo.bloquear(sesion, propiedad_id)\n"
            "    if raiz is None:\n        return Rechazo(NO_ENCONTRADA)\n"
            "    replay = identidad(sesion, intencion_id, propiedad_id, sellado)\n",
            "    hoy = hoy_owner(sesion, reloj)\n"
            "    if completo and fecha_corte > hoy:          # capa (O8.6): antes que el lock y que la version\n"
            "        return Rechazo(SIN_FECHA_DE_CORTE)\n    raiz = repo.bloquear(sesion, propiedad_id)\n"
            "    if raiz is None:\n        return Rechazo(NO_ENCONTRADA)\n"
            "    replay = identidad(sesion, intencion_id, propiedad_id, sellado)\n"
            "    bloquear_intencion_propiedad(sesion, intencion_id)\n",
            (n(T254, "test_s18_o11_14_misma_intencion_en_dos_propiedades[A-primero]"),
             n(T254, "test_s18_o11_14_misma_intencion_en_dos_propiedades[B-primero]"))),
    Mutante("M-IP-10", "C-PROP-05 usa la funcion UNICA del 0P, no una propia con otro espacio", COMPL,
            "    bloquear_intencion_propiedad(sesion, intencion_id)\n    hoy = hoy_owner(sesion, reloj)\n",
            "    sesion.uno(\"SELECT pg_advisory_xact_lock(hashtext('gapto:CPROP05'), hashtext(%s::text))\", "
            "(str(intencion_id),))\n    hoy = hoy_owner(sesion, reloj)\n",
            (n(T254, "test_s20_par_9_c_prop_02_frente_a_c_prop_05_real"),
             n(T252, "test_o11_22_cinco_llamadas_a_la_funcion_unica_del_0p"))),
    Mutante("M-IP-11", "C-PROP-01 toma el 0P con la clave entidad_id", SRV,
            "    bloquear_intencion_propiedad(sesion, entidad_id)  # 0P, primer recurso (F06-D009)\n",
            "    bloquear_intencion_propiedad(sesion, uuid.uuid5(entidad_id, \"alta\"))  # 0P, primer recurso (F06-D009)\n",
            (n(T237, "test_s20_o11_19_misma_intencion_en_dos_propiedades[C-PROP-01__C-PROP-02]"),
             n(T237, "test_s20_o11_19_misma_intencion_en_dos_propiedades[C-PROP-01__C-PROP-04]"),
             n(T233, "test_o11_22_funcion_unica_del_0p_y_cuatro_llamadas_en_primer_lugar"))),
    # ------------------------------------------------------------------ reserva H0/Hk (§II.7) y Actividad
    Mutante("M-Q16-01", "Ninguna ruta de B2 expone OP-21/OP-03 sobre H0/Hk", RUTAS,
            "from app.patrimonio import compra, completitud, coste, habilitacion\n",
            "from app.patrimonio import compra, completitud, coste, habilitacion\n"
            "from app.services.correcciones_service import CorreccionesService  # noqa: F401\n",
            (n(T253, "test_o10_23_d_inventario_b2_no_expone_op21_op02_op03"),)),
    Mutante("M-Q16-02", "La lectura de edicion no ofrece corregir ni anular sobre H0/Hk", EDICION,
            "            \"anular_duplicado\": _accion(_motivo_anular(sesion, hecho_id, hecho, movimientos, comun)),\n",
            "            \"anular_duplicado\": _accion(None if hecho[\"tipo\"] == \"ADQUISICION_PATRIMONIAL\" else\n"
            "                                      _motivo_anular(sesion, hecho_id, hecho, movimientos, comun)),\n",
            (n(T253, "test_o10_23_superficies_existentes_rechazan_p1_a_p4[H0]"),
             n(T253, "test_o10_23_superficies_existentes_rechazan_p1_a_p4[Hk]"))),
    Mutante("M-AC-01", "Actividad filtra el periodo [desde, hasta)", ACTIVIDAD,
            "        cond.append(\"h.fecha_hecho < %(hasta)s\")\n", "        cond.append(\"h.fecha_hecho <= %(hasta)s\")\n",
            (n(T253, "test_o10_19_periodo_semiabierto"),)),
    # ------------------------------------------------------------------ inventario O10.28 y habilitacion O10.29
    Mutante("M-O10-28", "Solo C-PROP-05 y C-COMPRA-01/03 escriben las columnas de 0352", COSTE,
            "    filas = repo.leer_coste(sesion, propiedad_id, a_fecha, habilitada)\n",
            "    if a_fecha is None:\n        repo.escribir_declaracion_completitud(sesion, propiedad_id, \"ADQUISICION\", (None, None, None))\n"
            "    filas = repo.leer_coste(sesion, propiedad_id, a_fecha, habilitada)\n",
            (n(T252, "test_o10_28_writers_de_las_columnas_de_0352"),)),
    Mutante("M-O10-29", "Los consumidores de 0352 no estan habilitados antes de su certificacion", HAB,
            "CONSUMIDORES_0352_HABILITADOS = False\n", "CONSUMIDORES_0352_HABILITADOS = True\n",
            (n(T252, "test_o10_29_constante_de_codigo_desactivada"),
             n(T252, "test_o10_29_ruta_c_prop_05_inaccesible_y_servicio_rechaza"),
             n(T252, "test_o10_29_declaracion_en_la_compra_y_en_el_gasto_posterior_es_422"))),
    # ------------------------------------------------------------------ v0.2 §M que corresponden a la compra
    Mutante("M-V02-01", "AJ-04: la marca del lote distingue el origen (C-COMPRA-03 no entra en el lote sellado)", COMPRA,
            "        compra03 = {(i, o) for i, o in _relaciones_hacia(sesion, h0) if i == uuid.uuid5(o, MARCA_LOTE03)}\n",
            "        compra03 = set()\n",
            (n(T250, "test_o6_8_gasto_posterior_no_entra_en_el_lote_sellado"),)),
    Mutante("M-V02-02", "AJ-02: L-COSTE nunca COMPLETO sin declaracion", COSTE,
            "        return (\"NO_DISPONIBLE\" if n == 0 else \"PARCIAL\"), \"SIN_DECLARACION\"\n",
            "        return (\"NO_DISPONIBLE\" if n == 0 else \"COMPLETO\"), \"SIN_DECLARACION\"\n",
            (n(T252, "test_o10_29_o10_10_l_coste_sin_declaracion_nunca_completo"),
             n(T252, "test_o2_completo_y_no_completo"))),
    Mutante("M-V02-03", "AJ-03: el coste que permanece nunca es COMPLETO (bajas no representadas)", COSTE,
            "        \"estado\": \"NO_DISPONIBLE\" if adq[\"estado\"] == \"NO_DISPONIBLE\" else \"PARCIAL\",\n",
            "        \"estado\": \"NO_DISPONIBLE\" if adq[\"estado\"] == \"NO_DISPONIBLE\" else (\"COMPLETO\" if adq[\"estado\"] == "
            "mej[\"estado\"] == \"COMPLETO\" else \"PARCIAL\"),\n",
            (n(T252, "test_o10_6_permanece_nunca_completo"),)),
    Mutante("M-V02-04", "AJ-04: compra ya registrada antes que la suma (O8.4)", COMPRA,
            "    if compra_registrada(sesion, propiedad_id):\n        return Rechazo(COMPRA_YA_REGISTRADA)\n", "",
            (n(T250, "test_o8_4_compra_ya_registrada_antes_que_la_suma"),)),
    Mutante("M-V02-05", "PB0-05: la operacion de pago explicita es GASTO (PAGAR_GASTO)", COMPRA,
            "        if motivo_cuenta(sesion, cuenta, \"GASTO\", fecha, bloquear=True) is not None:\n",
            "        if motivo_cuenta(sesion, cuenta, \"INGRESO\", fecha, bloquear=True) is not None:\n",
            (n(T250, "test_elegibilidad_por_la_operacion_de_pago_explicita"),)),
)


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _recuperar_si_aborto_previo() -> None:
    if MARCADOR.exists():
        ruta_rel, original_hex = MARCADOR.read_text("ascii").split("\n", 1)
        (RAIZ / ruta_rel).write_bytes(bytes.fromhex(original_hex.strip()))
        MARCADOR.unlink()
        raise SystemExit(f"ABORTADO: habia una mutacion a medias en {ruta_rel}; restaurada. "
                         "Revisa el arbol y vuelve a ejecutar.")


def _estado_arbol() -> str:
    return subprocess.run(["git", "status", "--porcelain"], cwd=RAIZ, capture_output=True, text=True).stdout


def _pytest(nodos: tuple[str, ...]) -> tuple[int, str]:
    proceso = subprocess.run(
        [sys.executable, "-m", "pytest", *nodos, "-q", "-p", "no:cacheprovider", "--rootdir=tests/api", "-rfE"],
        cwd=RAIZ, capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    return proceso.returncode, proceso.stdout + proceso.stderr


def _a_disco(registro: dict) -> None:
    destino = os.environ.get("GAPTO_B2_MUTANTES_VEREDICTOS")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def _guardar_salida(m: Mutante, salida: str) -> None:
    carpeta = os.environ.get("GAPTO_B2_MUTANTES_SALIDA")
    if carpeta:
        pathlib.Path(carpeta).mkdir(parents=True, exist_ok=True)
        (pathlib.Path(carpeta) / f"{m.ident}.log").write_text(salida, encoding="utf-8")


def comprobar_patrones(seleccion) -> list[str]:
    malos = []
    for m in seleccion:
        apariciones = (RAIZ / m.fichero).read_bytes().decode("utf-8").count(m.viejo)
        if apariciones != 1:
            malos.append(f"{m.ident}: patron encontrado {apariciones} veces en {m.fichero}")
    return malos


def ejecutar(m: Mutante) -> str:
    ruta = RAIZ / m.fichero
    original = ruta.read_bytes()
    sha_original = _sha(original)
    texto = original.decode("utf-8")
    MARCADOR.write_text(f"{m.fichero}\n{original.hex()}", "ascii")          # journal antes del primer byte
    try:
        ruta.write_bytes(texto.replace(m.viejo, m.nuevo, 1).encode("utf-8"))
        codigo, salida = _pytest(m.discriminantes)
        _guardar_salida(m, salida)
    finally:
        ruta.write_bytes(original)
        if _sha(ruta.read_bytes()) != sha_original:
            raise SystemExit(f"ABORTADO: restauracion fallida en {m.fichero}")
        MARCADOR.unlink()
    if "passed" not in salida and "failed" not in salida and "error" not in salida:
        return "NO_CLASIFICABLE pytest no llego a ejecutarse"
    fallos = [linea for linea in salida.splitlines() if linea.startswith(("FAILED", "ERROR"))]
    if codigo == 0:
        return "VIVO      ningun discriminante cae"
    nombres = [d.split("::", 1)[1] for d in m.discriminantes]
    if not any(nm in linea for nm in nombres for linea in fallos):
        return f"NO_CLASIFICABLE caen {len(fallos)} tests pero no un discriminante"
    return f"MUERTO    fallos={len(fallos)}"


def main(argv: list[str]) -> int:
    _recuperar_si_aborto_previo()
    seleccion = [m for m in MUTANTES if not argv or m.ident in argv]
    malos = comprobar_patrones(seleccion)
    if malos:
        print("\n".join(malos))
        raise SystemExit("ABORTADO (NO_CLASIFICABLE): patron con 0 o mas de 1 apariciones; no se muta nada.")
    arbol = _estado_arbol()
    nodos = tuple(dict.fromkeys(d for m in seleccion for d in m.discriminantes))
    codigo, salida = _pytest(nodos)
    if codigo != 0:
        print(salida[-4000:])
        raise SystemExit("ABORTADO: los discriminantes no estan verdes antes de mutar.")
    print(f"PREFLIGHT VERDE: {len(nodos)} discriminantes", flush=True)
    print("=== F06-01 B2 · MUTANTES ===", flush=True)
    muertos = 0
    for m in seleccion:
        veredicto = ejecutar(m)
        muertos += veredicto.startswith("MUERTO")
        _a_disco({"id": m.ident, "invariante": m.invariante, "fichero": m.fichero, "veredicto": veredicto.split()[0],
                  "detalle": veredicto, "discriminantes": list(m.discriminantes)})
        print(f"  {m.ident:9}  {veredicto}   [{m.invariante}]", flush=True)
        if veredicto.startswith("NO_CLASIFICABLE"):
            raise SystemExit(f"ABORTADO: {m.ident} NO_CLASIFICABLE")
    if _estado_arbol() != arbol:
        raise SystemExit("ABORTADO: el estado del arbol cambio durante la tirada.")
    print(f"RESULTADO: {muertos}/{len(seleccion)} muertos")
    return 0 if muertos == len(seleccion) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
