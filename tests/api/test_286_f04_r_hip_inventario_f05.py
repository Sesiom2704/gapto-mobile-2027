# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_286_f04_r_hip_inventario_f05.py
# Ruta: tests/api/test_286_f04_r_hip_inventario_f05.py
# Descripcion: T3-F06 · F04-R-HIP, subhito F05 (literal F05 v1.2): inventario
#   DISCRIMINANTE de la frontera F05 sobre hechos y previsiones de
#   financiacion (MF05-INV). Estatico (AST y texto del codigo), sin base:
#     1. completitud: toda ruta POST de la API cuyo path recibe un hecho o una
#        prevision existentes ({hecho_id}, {origen_id}, {devolucion_id},
#        {prevision_id}) y las cuatro intenciones con bloque `prevision` (S10)
#        estan en INVENTARIO o en EXCLUIDAS con su motivo; una ruta nueva no
#        clasificada hace fallar el test (STOP 1 del mandato);
#     2. orden: en la `operacion` de cada writer inventariado, la guarda unica
#        (gf.es_hecho_de_financiacion / rechazo_hecho / rechazo_prevision /
#        rechazo_bloque_prevision) se llama ANTES del primer lock o del primer
#        servicio del motor (S10: antes de tomar_advisory_raiz o de
#        transferir_bajo_locks, F04-R3 il1b intacto);
#     3. S6: SuplementosService solo se construye en compuesto_service (sin
#        ruta HTTP propia; patron test_230);
#     4. B3 (F06, fuera de F05): `corregir-clase` exige un unico efecto y el
#        vinculo AFECTA_A principal a la propiedad sobre ese efecto: no alcanza
#        el pago de una cuota (dos efectos) ni Hd (sin vinculo a la propiedad).
# Version: 0.1.0 (F06 T3-F06 · F04-R-HIP, paso 4)
# ============================================================

from __future__ import annotations

import ast
import pathlib
import re

import pytest

APP = pathlib.Path(__file__).resolve().parents[2] / "backend" / "app"

GUARDAS = {"es_hecho_de_financiacion", "rechazo_hecho", "rechazo_prevision", "rechazo_bloque_prevision"}
#: Primer recurso de escritura o del motor que la guarda debe preceder.
LOCKS = {"tomar_advisory_raiz", "adquirir_raiz", "bloquear_cuentas", "bloquear_cuenta", "transferir_bajo_locks",
         "tomar_inversiones", "_capacidad_bajo_lock", "motor", "_motor", "_previsiones", "CorreccionesService",
         "corregir", "anular_registro", "vincular_realidad", "estado_persistido", "motivo_categoria_v3",
         "_estado_reparto"}

#: superficie -> [(fichero, funcion, ruta POST)]
INVENTARIO: dict[str, list[tuple[str, str, str]]] = {
    "S1": [("api/ejecucion_reparto.py", "corregir_reparto", "/v1/hechos/{hecho_id}/reparto")],
    "S2": [("api/ejecucion_devolucion.py", "registrar_devolucion", "/v1/hechos/{origen_id}/devoluciones"),
           ("api/ejecucion_devolucion.py", "registrar_abono", "/v1/hechos/{devolucion_id}/abono")],
    "S3": [("api/ejecucion_anulacion.py", "anular_duplicado_http", "/v1/hechos/{hecho_id}/anular-duplicado")],
    "S4": [("api/ejecucion_correccion.py", "corregir_pago", "/v1/hechos/{hecho_id}/corregir-pago"),
           ("api/ejecucion_correccion.py", "corregir_transferencia", "/v1/transferencias/{hecho_id}/corregir")],
    "S5": [("api/ejecucion_categoria_v3.py", "corregir_categoria_v3", "/v1/hechos/{hecho_id}/corregir-categoria")],
    "S7": [("api/ejecucion_prevision.py", "vincular", "/v1/previsiones/{prevision_id}/vincular"),
           ("api/ejecucion_prevision.py", "omitir", "/v1/previsiones/{prevision_id}/omitir"),
           ("api/ejecucion_prevision.py", "dar_por_cubierta", "/v1/previsiones/{prevision_id}/dar-por-realizada"),
           ("api/ejecucion_prevision.py", "reabrir", "/v1/previsiones/{prevision_id}/reabrir")],
    "S10": [("api/ejecucion_gasto_pagado.py", "registrar_gasto_pagado", "/v1/intenciones/gasto-pagado"),
            ("api/ejecucion_reparto.py", "registrar_gasto_compartido", "/v1/intenciones/gasto-compartido"),
            ("api/ejecucion_registro.py", "registrar_ingreso_cobrado", "/v1/intenciones/ingreso-cobrado"),
            ("api/ejecucion_prevision.py", "registrar_transferencia_prevista", "/v1/intenciones/transferencia")],
}

#: Rutas que reciben un hecho existente y NO son superficie F05 de este subhito, con su motivo.
EXCLUIDAS = {
    "/v1/propiedades/{propiedad_id}/gastos/{hecho_id}/corregir-clase":
        "B3 (F06): no alcanza cuota ni Hd (unico efecto y AFECTA_A principal a la propiedad); punto 4",
}

#: Intenciones con bloque `prevision` (S10).
S10_RUTAS = {"/v1/intenciones/gasto-pagado", "/v1/intenciones/gasto-compartido", "/v1/intenciones/ingreso-cobrado",
             "/v1/intenciones/transferencia"}


def _rutas_post() -> set[str]:
    rutas = set()
    for f in [APP / "api" / "app.py", *sorted((APP / "patrimonio").glob("rutas*.py"))]:
        texto = f.read_text(encoding="utf-8")
        for bloque in re.findall(r"@app\.post\(\s*\"([^\"]+)\"", texto):
            rutas.add(bloque)
    return rutas


def _sobre_existente(ruta: str) -> bool:
    return any(p in ruta for p in ("{hecho_id}", "{origen_id}", "{devolucion_id}", "{prevision_id}"))


def test_inventario_completo_de_writers_f05_sobre_hechos_y_previsiones() -> None:
    """MF05-INV: toda ruta POST sobre un hecho o prevision existente, y las de
    S10, esta inventariada o excluida con motivo."""
    rutas = _rutas_post()
    objetivo = {r for r in rutas if _sobre_existente(r)} | (S10_RUTAS & rutas)
    inventariadas = {ruta for filas in INVENTARIO.values() for _, _, ruta in filas}
    assert S10_RUTAS <= rutas
    faltan = objetivo - inventariadas - set(EXCLUIDAS)
    assert not faltan, f"superficie no inventariada (STOP 1): {sorted(faltan)}"
    assert inventariadas <= rutas, sorted(inventariadas - rutas)


def _operacion(fichero: str, funcion: str) -> ast.FunctionDef:
    arbol = ast.parse((APP / fichero).read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == funcion:
            for hijo in ast.walk(nodo):
                if isinstance(hijo, ast.FunctionDef) and hijo.name == "operacion":
                    return hijo
    raise AssertionError(f"{fichero}:{funcion} sin `operacion`")


def _nombre(llamada: ast.Call) -> str | None:
    f = llamada.func
    return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None


def _primeras(op: ast.FunctionDef) -> tuple[int | None, int | None]:
    guarda = lock = None
    for nodo in ast.walk(op):
        if isinstance(nodo, ast.Call):
            n = _nombre(nodo)
            if n in GUARDAS and (guarda is None or nodo.lineno < guarda):
                guarda = nodo.lineno
            if n in LOCKS and (lock is None or nodo.lineno < lock):
                lock = nodo.lineno
    return guarda, lock


CASOS = [(s, f, fn) for s, filas in INVENTARIO.items() for f, fn, _ in filas]


@pytest.mark.parametrize("superficie, fichero, funcion", CASOS, ids=[f"{s}-{fn}" for s, _, fn in CASOS])
def test_la_guarda_precede_al_primer_lock(superficie, fichero, funcion) -> None:
    guarda, lock = _primeras(_operacion(fichero, funcion))
    assert guarda is not None, f"{superficie} {fichero}:{funcion} no llama a la guarda"
    assert lock is None or guarda < lock, f"{superficie} {fichero}:{funcion}: guarda l.{guarda} tras lock l.{lock}"


def test_s6_suplementos_sin_ruta_propia() -> None:
    """S6: SuplementosService solo se construye en compuesto_service (patron test_230)."""
    usos = sorted(str(p.relative_to(APP)).replace("\\", "/") for p in APP.rglob("*.py")
                  if re.search(r"SuplementosService\(", p.read_text(encoding="utf-8"))
                  and "class SuplementosService" not in p.read_text(encoding="utf-8"))
    assert usos == ["services/compuesto_service.py"], usos


def test_b3_corregir_clase_no_alcanza_cuota_ni_hd() -> None:
    texto = (APP / "patrimonio" / "correccion_clase.py").read_text(encoding="utf-8")
    assert 'if h["estado"] != "ACTIVO" or len(efectos) != 1:' in texto
    assert "if not _procedencia(sesion, hecho_id, propiedad_id, e0[\"id\"]):" in texto
