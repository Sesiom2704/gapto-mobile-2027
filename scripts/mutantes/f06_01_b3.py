#!/usr/bin/env python3
# ============================================================
# GAPTO MOBILE 2027
# Fichero: f06_01_b3.py
# Ruta: scripts/mutantes/f06_01_b3.py
# Descripcion: Arnes de mutacion de F06-01 B3 · Obras y gastos de una propiedad (N1; mandato B3 N1 v1.0 §7.3;
#   contratos R1 v0.9.5 Parte III, Parte IV y §IV.1; oraculos v0.7 §A.5.1, §A.6, §A.8, §A.9.3, §A.10.6-§A.10.8 y
#   v0.2 §M). Mismo motor que scripts/mutantes/f06_01_b2.py (copiado sin cambios de logica):
#   - sustitucion de texto EXACTO que aparece una sola vez (0 o mas de 1 -> NO_CLASIFICABLE y el arnes PARA);
#   - journal (marcador con el contenido original) ANTES del primer byte mutado; si una ejecucion anterior se
#     corto, restaura y aborta;
#   - restauracion verificada por SHA-256 tras cada mutante (tambien si pytest aborta);
#   - preflight: todos los discriminantes verdes antes de mutar;
#   - veredicto escrito a disco en cuanto se conoce (GAPTO_B3_MUTANTES_VEREDICTOS, una linea JSON por mutante)
#     y salida de pytest de cada mutante (GAPTO_B3_MUTANTES_SALIDA).
#   Un mutante solo se da por MUERTO si cae al menos uno de SUS discriminantes.
#   Mutantes: M-ID-08, M-ID-09, M-ID-09b, M-ID-11, M-ID-12, M-ID-13, M-E1-01a/b/c, M-LOC-01/02, los de la v0.8 de
#   C-MEJ-03 (M-V08-01..06), M-CO-09, M-DM02-02/07/08/09/11/12/13/15/17 (servidor) y los de la v0.2 §M de C-MEJ-03
#   (M-V02-*). M-DM02-01/04/05/06/10/14/16 y la fila de Actividad son de cliente: van en el arnes de Jest
#   (scripts/dev/mutantes_f06_t1_b3_cliente.py). M-DM02-03 no tiene superficie mutable en B3 (ningun writer de B3
#   toca hechos previos; O9.11 lo vigila): se declara en el handoff.
#   Requiere GAPTO_TEST_DATABASE_URL (base desechable, formato postgresql://) y GAPTO_B3_CONCURRENCIA=1
#   (discriminantes de la bateria serie).
# Uso:
#   python scripts/mutantes/f06_01_b3.py              # todos
#   python scripts/mutantes/f06_01_b3.py M-ID-11      # subconjunto
# Version: 0.1.0 (F06 T1-F06 B3 N1)
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
GP = "backend/app/patrimonio/gasto_propiedad.py"
CC = "backend/app/patrimonio/correccion_clase.py"
REPO = "backend/app/propiedades/repositorio.py"
OP21 = "backend/app/services/correcciones_service.py"
T255 = "tests/api/test_255_f06_01_b3_gasto_propiedad.py"
T256 = "tests/api/test_256_f06_01_b3_correccion_clase.py"
T257 = "tests/api/test_257_f06_01_b3_concurrencia_serial.py"
T258 = "tests/api/test_258_f06_01_b3_inventarios.py"
MARCADOR = RAIZ / ".mutante_f06_01_b3_en_curso"


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


DELEGACION = (
    "    from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita\n"
    "    from app.services.correcciones_service import CorreccionesService, DatosCorreccion\n")
DELEGACION_2 = (
    "        from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita\n"
    "        from app.services.correcciones_service import CorreccionesService, DatosCorreccion\n")
DIS_E1 = ("tests/api/test_256_f06_01_b3_correccion_clase.py::test_o5_34_espia_cero_llamadas_a_correcciones_service",
          "tests/api/test_256_f06_01_b3_correccion_clase.py::test_o5_34_inventario_estatico_del_modulo_de_c_mej_03",
          "tests/api/test_256_f06_01_b3_correccion_clase.py::"
          "test_o5_1_mejora_a_reparacion_estado_final_y_auditoria_exactos")

MUTANTES = (
    # ------------------------------------------------------------------ identidad durable (§III.3.6, E-3, E-4)
    Mutante("M-ID-08", "Ningun writer actualiza el id de un vinculo: C-MEJ-03 reapunta conservando el id", CC,
            'sesion.ejecutar("UPDATE gapto.hecho_entidades SET efecto_id = %s WHERE id = %s AND efecto_id = %s",',
            'sesion.ejecutar("UPDATE gapto.hecho_entidades SET id = gen_random_uuid(), efecto_id = %s WHERE id = %s '
            'AND efecto_id = %s",',
            (n(T258, "test_m_id_08_ningun_writer_actualiza_el_id_de_vinculos_ni_efectos"),
             n(T256, "test_o5_24_ida_y_vuelta_conserva_el_vinculo_y_la_procedencia"))),
    Mutante("M-ID-09", "La version se compara DESPUES de la identidad (no entre 2bis y la identidad)", CC,
            "    # 3 identidad (§III.3.6)\n",
            '    if h["row_version"] != p["row_version_esperada"]:\n        return Rechazo(gp.VERSION_DESFASADA)\n'
            "    # 3 identidad (§III.3.6)\n",
            (n(T256, "test_o5_30_replay_tras_subir_solo_la_version"),)),
    Mutante("M-ID-09b", "La version no se compara antes de la guarda 2bis", CC,
            "    # 2bis: hecho ACTIVO con exactamente un efecto vigente (§III.3.3bis)\n",
            '    if h["row_version"] != p["row_version_esperada"]:\n        return Rechazo(gp.VERSION_DESFASADA)\n'
            "    # 2bis: hecho ACTIVO con exactamente un efecto vigente (§III.3.3bis)\n",
            (n(T256, "test_o5_30_replay_tras_subir_solo_la_version"),
             n(T256, "test_o5_36_replay_exacto_tras_anular_da_2bis"))),
    Mutante("M-ID-11", "Guarda 2bis: hecho ACTIVO con exactamente un efecto vigente, antes de la identidad", CC,
            '    if h["estado"] != "ACTIVO" or len(efectos) != 1:\n        return Rechazo(NO_ADMITIDA)\n',
            "    if not efectos:\n        return Rechazo(NO_VIGENTE)\n",
            (n(T256, "test_o5_11_o5_35_segundo_efecto_2bis_con_cualquier_intencion"),
             n(T256, "test_o5_14a_anulado_conservando_el_efecto_y_o5_33a"))),
    Mutante("M-ID-12", "La guarda 2bis exige el hecho ACTIVO (no solo contar efectos)", CC,
            '    if h["estado"] != "ACTIVO" or len(efectos) != 1:\n',
            "    if len(efectos) != 1:\n",
            (n(T256, "test_o5_14a_anulado_conservando_el_efecto_y_o5_33a"),
             n(T256, "test_o5_36_replay_exacto_tras_anular_da_2bis"))),
    Mutante("M-ID-13", "La lectura no ofrece intencion sin un efecto vigente unico (misma condicion que 2bis)", GP,
            '"intencion_correccion_id": intencion_vigente(efectos[0]) if unico else None,',
            '"intencion_correccion_id": intencion_vigente(efectos[0]) if efectos else None,',
            (n(T256, "test_o5_14a_anulado_conservando_el_efecto_y_o5_33a"),
             n(T256, "test_o5_11_o5_35_segundo_efecto_2bis_con_cualquier_intencion"),
             n(T256, "test_o5_33_d_y_o9_17_con_deuda_no_hay_intencion_ni_correccion"))),
    # ------------------------------------------------------------------ E-1 sin delegar en OP-21 (§IV.1)
    Mutante("M-E1-01a", "C-MEJ-03 no delega la correccion completa en CorreccionesService.corregir", CC,
            "    # 1: tipo_hecho_id y presupuestable, row_version + 1 exacto\n",
            DELEGACION +
            "    CorreccionesService(UnidadDeTrabajoAdscrita(sesion)).corregir(sesion.contexto, DatosCorreccion(\n"
            '        hecho_id=hecho_id, row_version_esperada=h["row_version"], motivo=motivo,\n'
            '        efectos_a_eliminar=(e0["id"],)))\n'
            "    # 1: tipo_hecho_id y presupuestable, row_version + 1 exacto\n",
            DIS_E1),
    Mutante("M-E1-01b", "C-MEJ-03 no delega la retirada de e0 en OP-21 (D1, D2, D5)", CC,
            '    sesion.ejecutar("DELETE FROM gapto.hecho_efectos WHERE id = %s AND hecho_id = %s", '
            '(e0["id"], hecho_id))\n',
            DELEGACION +
            "    CorreccionesService(UnidadDeTrabajoAdscrita(sesion))._eliminar_efectos(sesion, DatosCorreccion(\n"
            '        hecho_id=hecho_id, row_version_esperada=h["row_version"] + 1, motivo=motivo,\n'
            '        efectos_a_eliminar=(e0["id"],)))\n',
            DIS_E1),
    Mutante("M-E1-01c", "C-MEJ-03 no llama a los pasos internos de OP-21 (_eliminar_atribuciones)", CC,
            '        sesion.ejecutar("DELETE FROM gapto.efecto_atribuciones WHERE id = %s", (aid,))\n',
            DELEGACION_2 +
            "        CorreccionesService(UnidadDeTrabajoAdscrita(sesion))._eliminar_atribuciones(sesion, DatosCorreccion(\n"
            '            hecho_id=hecho_id, row_version_esperada=h["row_version"] + 1, motivo=motivo,\n'
            "            atribuciones_a_eliminar=(aid,)))\n",
            DIS_E1),
    # ------------------------------------------------------------------ localizacion (§III.1ter, HF-03)
    Mutante("M-LOC-01", "C-MEJ-01/02 crean el hecho con DESCONOCIDA en las tres clases", GP,
            'estado_localizacion="DESCONOCIDA", tipo_hecho_codigo=TIPO_MEJORA if mejora else TIPO_GASTO,',
            'estado_localizacion="NO_APLICA" if mejora else "DESCONOCIDA", '
            "tipo_hecho_codigo=TIPO_MEJORA if mejora else TIPO_GASTO,",
            (n(T255, "test_o5_39_desconocida_en_las_tres_clases_y_en_c_mej_02"),
             n(T256, "test_o5_37_mejora_a_reparacion_queda_desconocida_y_op21_posterior_se_acepta"))),
    Mutante("M-LOC-02", "Guarda de localizacion: destino GASTO con NO_APLICA -> CORRECCION_NATURALEZA_NO_ADMITIDA", CC,
            '    if not a_mejora and h["localizacion"] == "NO_APLICA":',
            "    if False:",
            (n(T256, "test_o5_38_mejora_legada_no_aplica_a_gasto_no_admitida"),)),
    # ------------------------------------------------------------------ v0.8 de C-MEJ-03
    Mutante("M-V08-01", "La causa se limpia al pasar a GASTO", CC,
            "        causa_valor_activo=gp.CAUSA_MEJORA if a_mejora else None)\n",
            "        causa_valor_activo=gp.CAUSA_MEJORA)\n",
            (n(T256, "test_o5_1_mejora_a_reparacion_estado_final_y_auditoria_exactos"),)),
    Mutante("M-V08-02", "Las atribuciones de e0 se copian a e1", CC,
            "    for _, actor, importe, criterio, pct, _snap in atribuciones:\n",
            "    for _, actor, importe, criterio, pct, _snap in []:\n",
            (n(T256, "test_o5_1_mejora_a_reparacion_estado_final_y_auditoria_exactos"),)),
    Mutante("M-V08-03", "Emparejamiento efecto a efecto, no por conjuntos: exactamente un efecto", CC,
            '    if h["estado"] != "ACTIVO" or len(efectos) != 1:\n',
            '    if h["estado"] != "ACTIVO" or len(efectos) < 1:\n',
            (n(T256, "test_o5_11_o5_35_segundo_efecto_2bis_con_cualquier_intencion"),)),
    Mutante("M-V08-04", "Guarda de periodo cerrado", CC,
            '    if periodo_cerrado(sesion, [h["fecha"]]):\n',
            "    if False:\n",
            (n(T256, "test_o5_3_periodo_cerrado"),)),
    Mutante("M-V08-05", "El arquetipo del hecho cambia (tipo_hecho_id)", CC,
            "SET tipo_hecho_id = (SELECT id FROM gapto.tipos_hecho WHERE codigo = %s), ",
            "SET tipo_hecho_id = coalesce(NULL::uuid, tipo_hecho_id), presupuestable = presupuestable OR %s IS NULL, ",
            (n(T256, "test_o5_1_mejora_a_reparacion_estado_final_y_auditoria_exactos"),)),
    Mutante("M-V08-06", "OP-21 generico conserva la restriccion de B0 (CC-R1-11)", OP21,
            "            self._exigir_sin_conversion_logica_valor_activo(sesion, datos)\n",
            "            pass\n",
            (n(T256, "test_o5_5_op21_generico_sigue_rechazando_la_conversion"),)),
    # ------------------------------------------------------------------ v0.2 §M de C-MEJ-03
    Mutante("M-V02-AJ05", "presupuestable nunca se copia del booleano previo", CC,
            '    presupuestable = False if a_mejora else bool(p["presupuestable"])\n',
            '    presupuestable = False if a_mejora else bool(h["presupuestable"])\n',
            (n(T256, "test_o5_1_mejora_a_reparacion_estado_final_y_auditoria_exactos"),)),
    Mutante("M-V02-AJ06a", "Predicado con la marca de procedencia persistida", CC,
            '    if not _procedencia(sesion, hecho_id, propiedad_id, e0["id"]):\n',
            "    if False:\n",
            (n(T256, "test_o5_10_gasto_con_forma_de_c_mej_01_sin_la_marca"),
             n(T256, "test_o5_15_ruta_de_otra_propiedad"))),
    Mutante("M-V02-AJ06b", "Predicado sin dependencias (relaciones, posiciones, previsiones, magnitudes)", CC,
            "    if _dependencias(sesion, hecho_id, a_mejora):\n",
            "    if False:\n",
            (n(T256, "test_o5_12_relacion_entre_hechos_no_admitida"),
             n(T256, "test_o5_13_magnitudes_hacia_mejora_no_admitidas"))),
    Mutante("M-V02-AJ07", "e0 no se borra antes de reapuntar el vinculo (FK RESTRICT)", CC,
            "    # 4: reapuntar los vinculos de nivel efecto de e0 (conservan id, entidad, tipo y principal)\n",
            '    sesion.ejecutar("DELETE FROM gapto.hecho_efectos WHERE id = %s", (e0["id"],))\n'
            "    # 4: reapuntar los vinculos de nivel efecto de e0 (conservan id, entidad, tipo y principal)\n",
            (n(T256, "test_o5_1_mejora_a_reparacion_estado_final_y_auditoria_exactos"),)),
    Mutante("M-V02-AJ07b", "Auditoria del cambio de tipo del hecho", CC,
            '    _auditar(sesion, "hechos_financieros", hecho_id, auditoria.ACCION_ACTUALIZAR, antes,\n'
            "             _json(sesion, hecho_json, (hecho_id,)), motivo)\n",
            "",
            (n(T256, "test_o5_1_mejora_a_reparacion_estado_final_y_auditoria_exactos"),)),
    Mutante("M-V02-AJ08", "Se compara el impacto bajo lock (comparacion_vista)", CC,
            '    if vista != {k: str(v) for k, v in p["comparacion_vista"].items()}:\n',
            "    if False:\n",
            (n(T256, "test_o5_16_impacto_desfasado"),)),
    Mutante("M-V02-AJ01", "C-MEJ-01/02/03 toman la propiedad FOR SHARE (lock de la entidad)", GP,
            "\"AND e.owner_user_id = current_setting('gapto.owner_user_id')::uuid FOR SHARE OF e\", (propiedad_id,))",
            "\"AND e.owner_user_id = current_setting('gapto.owner_user_id')::uuid\", (propiedad_id,))",
            (n(T257, "test_o7_5_cmej03_frente_a_deshabilitar_la_propiedad"),)),
    # ------------------------------------------------------------------ ABA de C-MEJ-03 (M-CO-09)
    Mutante("M-CO-09", "El conjunto de completitud incluye el efecto_id (ABA de C-MEJ-03 no recupera)", REPO,
            "\"coalesce((SELECT jsonb_agg(jsonb_build_object('efecto_id', c.efecto_id::text, "
            "'hecho_id', c.hecho_id::text, \"",
            "\"coalesce((SELECT jsonb_agg(jsonb_build_object('hecho_id', c.hecho_id::text, \"",
            (n(T256, "test_o10_20_bis_ida_y_vuelta_con_ids_nuevos_no_recupera"),)),
    # ------------------------------------------------------------------ deuda y reparto (servidor)
    Mutante("M-DM02-02", "La propuesta se lee en la fecha del hecho, no hoy", GP,
            "    partes = m2.titularidad_en_fecha(sesion, propiedad_id, fecha)\n",
            "    partes = m2.titularidad_en_fecha(sesion, propiedad_id, dt.date.today())\n",
            (n(T255, "test_o9_9_titularidad_en_la_fecha_del_hecho_no_la_de_hoy"),)),
    Mutante("M-DM02-07", "El servidor nunca infiere la deuda: valor explicito por parte de cotitular", GP,
            "    if set(vistos) != set(otros):                                          # O9.19: nada se infiere\n",
            "    if False:\n",
            (n(T255, "test_o9_19_sin_el_campo_me_debe_422"),)),
    Mutante("M-DM02-08", "Con cuenta compartida el derecho exige aportacion MANUAL", GP,
            '        if solo_mia == (p.get("aportacion_indicada") is not None):                # O9.16\n',
            "        if False:\n",
            (n(T255, "test_o9_16_cuenta_compartida_solo_con_aportacion_manual"),)),
    Mutante("M-DM02-09", "El derecho es por la parte del cotitular, no por el total", GP,
            "        if aportacion is None and valor != parte:\n",
            "        if aportacion is None and valor != importe:\n",
            (n(T255, "test_o9_14_deuda_por_defecto_confirmada_crea_derecho_por_su_parte"),)),
    Mutante("M-DM02-11", "EMPRESA no admite «Te debe su parte»", GP,
            '        if any(nat.get(a) != "PERSONA" for a in confirmados):                     # EMPRESA (O9.18)\n',
            "        if False:\n",
            (n(T255, "test_o9_18_empresa_no_admite_te_debe"),)),
    Mutante("M-DM02-12", "C-MEJ-02 (sin pago) no admite derecho", GP,
            "    if not con_pago:                                                       # C-MEJ-02 (8ter, exclusion 3)\n"
            "        return ENTRADA_INVALIDA if (si or derechos or aportacion is not None) else None\n",
            "    if not con_pago:                                                       # C-MEJ-02 (8ter, exclusion 3)\n"
            "        return None\n",
            (n(T255, "test_o9_20_c_mej_02_no_admite_derecho"),)),
    Mutante("M-DM02-13", "Sin importe determinado (NO_LO_SE) no hay posicion", GP,
            "    if not partes:                                                         # NO_LO_SE (exclusion 4)\n"
            "        return ENTRADA_INVALIDA if (si or derechos or aportacion is not None) else None\n",
            "    if not partes:                                                         # NO_LO_SE (exclusion 4)\n"
            "        return None\n",
            (n(T255, "test_o9_21_no_lo_se_no_admite_derecho"),)),
    Mutante("M-DM02-15", "El servidor no crea la posicion sin confirmacion (derechos_confirmados)", GP,
            "    if set(confirmados) != si:                                             # O9.22 (8bis)\n",
            "    if False:\n",
            (n(T255, "test_o9_22_sin_confirmacion_o_con_otro_importe_422"),)),
    Mutante("M-DM02-17", "La posicion no genera un movimiento (liquidez intacta)", GP,
            "    return DatosHechoCompuesto(\n        hecho=hecho, efectos=[efecto], pagos=pagos, posiciones=",
            "    if confirmados and cuenta_id is not None:\n"
            '        extra = DatosMovimiento(movimiento_id=ident(iid, prefijo, "mov_pos"), cuenta_id=cuenta_id,\n'
            "                                fecha_movimiento=fecha, importe=-sum(confirmados.values()),\n"
            '                                clase_movimiento="OPERACION", descripcion=nota)\n'
            "        pagos.append(DatosPagoCompuesto(movimiento=extra, conciliacion=DatosConciliacion(\n"
            '            conciliacion_id=ident(iid, prefijo, "conc_pos"), hecho_id=iid,\n'
            "            movimiento_tesoreria_id=extra.movimiento_id, importe_asignado=-sum(confirmados.values()))))\n"
            "    return DatosHechoCompuesto(\n        hecho=hecho, efectos=[efecto], pagos=pagos, posiciones=",
            (n(T255, "test_o9_24_la_posicion_no_es_un_movimiento"),
             n(T255, "test_o9_14_deuda_por_defecto_confirmada_crea_derecho_por_su_parte"))),
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
    destino = os.environ.get("GAPTO_B3_MUTANTES_VEREDICTOS")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def _guardar_salida(m: Mutante, salida: str) -> None:
    carpeta = os.environ.get("GAPTO_B3_MUTANTES_SALIDA")
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
    print("=== F06-01 B3 · MUTANTES ===", flush=True)
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
