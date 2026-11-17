# ============================================================
# GAPTO MOBILE 2027
# Fichero: comparador.py
# Ruta: backend/app/hipotecas/comparador.py
# Descripcion: Comparador de identidad AMPLIADO de la compra con hipoteca (F06-01H; literal de reapertura de B2
#   v1.1, B2 y tabla MB2-01..14; contrato v0.4 §1.2 y §3.2.5; mandato v1.1 §2.1-6 y §11.3). Modulo de
#   comparacion de hipoteca que declara el N1: lo invoca `patrimonio/compra.py` en la rama de replay, bajo los
#   locks de nivel 0..2, despues de las comprobaciones (i)..(vi) de B2.
#   Estructura (para que cada mutante MB2-NN elimine SOLO la comparacion de campos de su pieza):
#     1. `_pertenencia`: conjuntos de identidades (Hd por tabla del agregado, con aportaciones, vinculo y
#        PARTE_DE; participaciones y cuotas de la financiacion; existencia de las filas unicas). NO es una pieza:
#        un replay exacto sigue siendo idempotente aunque se mutile una pieza.
#     2. Una funcion por pieza, `_p01_financiacion` .. `_p14_atribucion`, que compara por igualdad exacta los
#        campos de la tabla MB2 (contrato §1.2) con lo que la peticion sellada produce.
#   Igualdad -> idempotente (0 escrituras); cualquier diferencia -> IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION.
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 5)
# Version: 0.2.0 (F06 T3-F06 bloque 2 F06-01H, paso 6; firma de Moises STOP n.º 2 / Q3, 5f3f5f8e…, y enmienda
#   e28be7c6… del contrato v0.4 y del literal B2 v1.1): la pieza 13 (MB2-13) pasa a «pertenencia: Hd sin
#   aportaciones» y se comprueba SOLO en `_p13_aportacion` (fuera de `_pertenencia`), para que su mutante propio
#   la elimine sin que otra comprobacion la cubra.
# ============================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.core.modelos_compuesto import DatosHechoCompuesto
from app.core.unidad_trabajo import SesionMotor
from app.hipotecas.alta import Plan
from app.repositories import compuesto_repository as repo_comp


@dataclass(frozen=True)
class Esperado:
    plan: Plan
    hd: DatosHechoCompuesto
    financiador_actor: uuid.UUID | None
    prestamo: list[tuple[uuid.UUID, Decimal]] | None
    nombre_propiedad: str


def _igual(persistido: Any, esperado: Any) -> bool:
    from app.patrimonio.compra import _iguales   # misma igualdad exacta que B2 (F04-D050)
    return _iguales(persistido, esperado)


def _fila(sesion: SesionMotor, sql: str, ident: Any, esperado: dict[str, Any]) -> bool:
    with sesion.conexion.cursor() as cur:
        cur.execute(sql, (ident,))
        fila = cur.fetchone()
        if fila is None:
            return False
        datos = dict(zip([d.name for d in cur.description], fila))
    return all(_igual(datos.get(k), v) for k, v in esperado.items())


def _ids(sesion: SesionMotor, sql: str, ident: uuid.UUID) -> set[uuid.UUID]:
    with sesion.conexion.cursor() as cur:
        cur.execute(sql, (ident,))
        return {f[0] for f in cur.fetchall()}


# ------------------------------------------------------------------ pertenencia (no es pieza)
def _pertenencia(sesion: SesionMotor, e: Esperado) -> bool:
    pl, d = e.plan, e.hd
    declaradas: dict[str, set[uuid.UUID]] = {t: set() for t in repo_comp.FILTROS_AGREGADO}
    declaradas["hecho_efectos"] = {x.efecto_id for x in d.efectos}
    declaradas["efecto_atribuciones"] = {a.atribucion_id for x in d.efectos for a in x.atribuciones}
    declaradas["hecho_movimientos_tesoreria"] = {p.conciliacion.conciliacion_id for p in d.pagos}
    declaradas["hecho_entidades"] = {pl.vinculo_id}
    declaradas["hecho_relaciones"] = {pl.parte_de}
    persistidas = repo_comp.identidades_del_agregado(sesion, pl.hd)
    persistidas.pop("hecho_aportaciones_pago", None)          # pieza 13: la comprueba _p13_aportacion
    declaradas.pop("hecho_aportaciones_pago", None)
    if persistidas != declaradas:
        return False
    if _ids(sesion, "SELECT id FROM gapto.entidad_participaciones WHERE entidad_id = %s", pl.financiacion_id) != {
            pl.participacion_id(a) for a, _ in e.prestamo or []}:
        return False
    if _ids(sesion, "SELECT id FROM gapto.financiacion_cuotas WHERE financiacion_entidad_id = %s",
            pl.financiacion_id) != {pl.cuota_id(q.numero) for q in pl.cuadro}:
        return False
    unicas = (("SELECT 1 FROM gapto.financiaciones WHERE entidad_id = %s", pl.financiacion_id),
              ("SELECT 1 FROM gapto.entidades WHERE id = %s", pl.financiacion_id),
              ("SELECT 1 FROM gapto.entidad_relaciones WHERE id = %s", pl.relacion),
              ("SELECT 1 FROM gapto.financiacion_condiciones_versiones WHERE id = %s", pl.version),
              ("SELECT 1 FROM gapto.movimientos_tesoreria WHERE id = %s", pl.movimiento))
    if any(sesion.uno(sql, (i,)) is None for sql, i in unicas):
        return False
    return all(sesion.uno("SELECT 1 FROM gapto.previsiones WHERE id = %s", (pl.prevision_id(q.numero),)) is not None
               for q in pl.cuadro)


# ------------------------------------------------------------------ piezas (tabla MB2, 1:1)
def _p01_financiacion(sesion: SesionMotor, e: Esperado) -> bool:
    pl = e.plan
    return _fila(sesion, "SELECT * FROM gapto.financiaciones WHERE entidad_id = %s", pl.financiacion_id, {
        "financiador_actor_id": e.financiador_actor, "capital_original_contratado": pl.p,
        "tipo_financiacion": "HIPOTECA", "moneda": "EUR", "saldo_principal_apertura": Decimal(0),
        "fecha_inicio_seguimiento": pl.escritura, "fecha_inicio": pl.escritura,
        "fecha_vencimiento_final_prevista": pl.cuadro[-1].vencimiento, "estado": "ACTIVA"})


def _p02_entidad(sesion: SesionMotor, e: Esperado) -> bool:
    return _fila(sesion, "SELECT * FROM gapto.entidades WHERE id = %s", e.plan.financiacion_id, {
        "tipo_entidad": "FINANCIACION", "nombre": f"Hipoteca · {e.nombre_propiedad}"[:200], "enabled": True})


def _p03_participaciones(sesion: SesionMotor, e: Esperado) -> bool:
    pl = e.plan
    return all(_fila(sesion, "SELECT * FROM gapto.entidad_participaciones WHERE id = %s", pl.participacion_id(a), {
        "entidad_id": pl.financiacion_id, "actor_id": a, "porcentaje": p, "vigente_desde": pl.escritura,
        "vigente_hasta": None}) for a, p in e.prestamo or [])


def _p04_garantizada_por(sesion: SesionMotor, e: Esperado) -> bool:
    pl = e.plan
    return _fila(sesion, "SELECT * FROM gapto.entidad_relaciones WHERE id = %s", pl.relacion, {
        "entidad_origen_id": pl.financiacion_id, "entidad_destino_id": pl.propiedad_id,
        "tipo_relacion": "GARANTIZADA_POR", "vigente_desde": pl.escritura})


def _p05_version_alta(sesion: SesionMotor, e: Esperado) -> bool:
    pl, c = e.plan, e.plan.canon
    return _fila(sesion, "SELECT * FROM gapto.financiacion_condiciones_versiones WHERE id = %s", pl.version, {
        "financiacion_entidad_id": pl.financiacion_id, "motivo_version": "ALTA", "hecho_causa_id": pl.hd,
        "vigente_desde": pl.escritura, "tipo_interes": c["tipo_interes"], "tasa_anual_pct": Decimal(c["tasa_anual_pct"]),
        "indice_referencia": c["indice_referencia"],
        "diferencial_pct": None if c["diferencial_pct"] is None else Decimal(c["diferencial_pct"]),
        "importe_cuota_referencia": pl.cuadro[0].cuota, "numero_cuotas_referencia": len(pl.cuadro),
        "sistema_amortizacion": "FRANCES", "periodicidad": "MENSUAL", "intervalo": 1})


def _p06_cuotas(sesion: SesionMotor, e: Esperado) -> bool:
    pl = e.plan
    return all(_fila(sesion, "SELECT * FROM gapto.financiacion_cuotas WHERE id = %s", pl.cuota_id(q.numero), {
        "financiacion_entidad_id": pl.financiacion_id, "numero_cuota": q.numero, "fecha_vencimiento": q.vencimiento,
        "capital_previsto": q.capital, "interes_previsto": q.interes, "comisiones_previstas": Decimal(0),
        "importe_total_previsto": q.cuota, "condicion_version_id": pl.version,
        "prevision_id": pl.prevision_id(q.numero)}) for q in pl.cuadro)


def _p07_previsiones(sesion: SesionMotor, e: Esperado) -> bool:
    pl = e.plan
    gasto = sesion.uno("SELECT id FROM gapto.tipos_hecho WHERE codigo = 'GASTO'")[0]
    return all(_fila(sesion, "SELECT * FROM gapto.previsiones WHERE id = %s", pl.prevision_id(q.numero), {
        "tipo_hecho_id": gasto, "flujo_tesoreria_esperado": "SALIDA", "cuenta_salida_esperada_id": pl.cuenta_cargo,
        "entidad_id": pl.financiacion_id, "importe_esperado": q.cuota, "estado": "ABIERTA",
        "regla_version_id": None, "recalculo_automatico": False, "fecha_esperada_desde": q.vencimiento})
        for q in pl.cuadro)


def _p08_hd(sesion: SesionMotor, e: Esperado) -> bool:
    h = e.hd.hecho
    fila = repo_comp.leer(sesion, "hechos_financieros", e.plan.hd)
    if fila is None or repo_comp.codigo_tipo_hecho(sesion, fila["tipo_hecho_id"]) != h.tipo_hecho_codigo:
        return False
    return all(_igual(fila.get(k), v) for k, v in {
        "fecha_hecho": h.fecha_hecho, "moneda": h.moneda, "concepto": h.concepto, "importe_total": h.importe_total,
        "presupuestable": h.presupuestable, "estado_localizacion": h.estado_localizacion}.items())


def _p09_efecto_deuda(sesion: SesionMotor, e: Esperado) -> bool:
    x = e.hd.efectos[0]
    return _fila(sesion, "SELECT * FROM gapto.hecho_efectos WHERE id = %s", x.efecto_id, {
        "hecho_id": e.plan.hd, "tipo_efecto": "DEUDA", "importe_delta": x.importe_delta,
        "estado_atribucion": x.estado_atribucion, "categoria_id": None, "causa_valor_activo": None})


def _p10_vinculo_nivel_efecto(sesion: SesionMotor, e: Esperado) -> bool:
    pl = e.plan
    return _fila(sesion, "SELECT * FROM gapto.hecho_entidades WHERE id = %s", pl.vinculo_id, {
        "hecho_id": pl.hd, "entidad_id": pl.financiacion_id, "tipo_relacion": "AFECTA_A", "principal": False,
        "efecto_id": pl.efecto_deuda})


def _p11_movimiento_p(sesion: SesionMotor, e: Esperado) -> bool:
    m = e.hd.pagos[0].movimiento
    return _fila(sesion, "SELECT * FROM gapto.movimientos_tesoreria WHERE id = %s", m.movimiento_id, {
        "cuenta_id": m.cuenta_id, "fecha_movimiento": m.fecha_movimiento, "importe": m.importe,
        "clase_movimiento": m.clase_movimiento})


def _p12_conciliacion(sesion: SesionMotor, e: Esperado) -> bool:
    c = e.hd.pagos[0].conciliacion
    return _fila(sesion, "SELECT * FROM gapto.hecho_movimientos_tesoreria WHERE id = %s", c.conciliacion_id, {
        "hecho_id": e.plan.hd, "movimiento_tesoreria_id": c.movimiento_tesoreria_id,
        "importe_asignado": c.importe_asignado})


def _p13_aportacion(sesion: SesionMotor, e: Esperado) -> bool:
    """Firma STOP n.º 2 (opcion A): para una entrada la regla vigente es «ninguna aportacion»; la pieza 13 es la
    pertenencia exacta: el conjunto de aportaciones de Hd es el declarado (vacio)."""
    if _ids(sesion, "SELECT id FROM gapto.hecho_aportaciones_pago WHERE hecho_id = %s", e.plan.hd) != {
            a.aportacion_id for a in e.hd.aportaciones}:
        return False
    return all(_fila(sesion, "SELECT * FROM gapto.hecho_aportaciones_pago WHERE id = %s", a.aportacion_id, {
        "hecho_id": e.plan.hd, "actor_id": a.actor_id, "importe": a.importe, "porcentaje_aplicado": a.porcentaje_aplicado,
        "criterio_aportacion": a.criterio_aportacion, "hecho_movimiento_tesoreria_id": a.hecho_movimiento_tesoreria_id})
        for a in e.hd.aportaciones)


def _p14_atribucion(sesion: SesionMotor, e: Esperado) -> bool:
    x = e.hd.efectos[0]
    return all(_fila(sesion, "SELECT * FROM gapto.efecto_atribuciones WHERE id = %s", a.atribucion_id, {
        "efecto_id": x.efecto_id, "actor_id": a.actor_id, "importe_atribuido": a.importe_atribuido,
        "criterio_atribucion": a.criterio_atribucion, "porcentaje_aplicado": a.porcentaje_aplicado})
        for a in x.atribuciones)


def coincide(sesion: SesionMotor, e: Esperado) -> bool:
    """Replay de la compra con hipoteca: pertenencia y las 14 piezas por igualdad exacta (orden de la tabla)."""
    if not _pertenencia(sesion, e):
        return False
    if not _p01_financiacion(sesion, e):
        return False
    if not _p02_entidad(sesion, e):
        return False
    if not _p03_participaciones(sesion, e):
        return False
    if not _p04_garantizada_por(sesion, e):
        return False
    if not _p05_version_alta(sesion, e):
        return False
    if not _p06_cuotas(sesion, e):
        return False
    if not _p07_previsiones(sesion, e):
        return False
    if not _p08_hd(sesion, e):
        return False
    if not _p09_efecto_deuda(sesion, e):
        return False
    if not _p10_vinculo_nivel_efecto(sesion, e):
        return False
    if not _p11_movimiento_p(sesion, e):
        return False
    if not _p12_conciliacion(sesion, e):
        return False
    if not _p13_aportacion(sesion, e):
        return False
    if not _p14_atribucion(sesion, e):
        return False
    return True
