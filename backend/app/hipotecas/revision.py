# ============================================================
# GAPTO MOBILE 2027
# Fichero: revision.py
# Ruta: backend/app/hipotecas/revision.py
# Descripcion: W-HIP-03/04 · revision del tipo con fecha y recalculo hacia delante por SERVICIO PROPIO
#   (F06-01H; contrato v0.4 §3.5; Q-H-11; Q-T3D-06/07; mandato T3-F06 bloque 2 v1.1 §2.4).
#   Guardas en el orden del contrato (§3.5.1): forma (periodicidad != MENSUAL -> CONDICIONES_INCOMPLETAS /
#   PERIODICIDAD_NO_SOPORTADA; tasa 0-30 con 4 decimales; tipo_interes FIJO/VARIABLE) -> 0P de la intencion
#   (advisory de raiz, raiz = intencion_id) -> financiacion FOR NO KEY UPDATE (AGREGADO_NO_ENCONTRADO) ->
#   identidad (version uuid5(intencion_id)) -> no ACTIVA -> legacy (SALDO_PRINCIPAL_INDETERMINADO) ->
#   VERSION_DESFASADA -> version vigente FOR UPDATE; vigente_desde <= su vigente_desde ->
#   FECHA_REVISION_INCOHERENTE -> cuotas FOR UPDATE por numero_cuota; afectadas = fecha_vencimiento >=
#   vigente_desde; alguna no ABIERTA -> REVISION_SOBRE_CUOTA_PAGADA; ninguna -> SIN_CUOTAS_FUTURAS ->
#   previsiones de las afectadas FOR UPDATE por numero_cuota.
#   Recalculo (§3.5.2): base = P - Σ capital_previsto de las anteriores (pagadas o no); tramo frances con el tipo
#   nuevo, mismos numeros y vencimientos (se mantiene el plazo; calculadora.tramo_desde); cierre de la version
#   vigente (vigente_hasta = vigente_desde - 1: unico UPDATE que admite G3) + INSERT CAMBIO_CONDICIONES; UPDATE de
#   cada afectada con auditoria POR CUOTA (datos_antes/datos_despues = fila completa, §3.5.3; M-H-34/35, O-H20);
#   PrevisionesService.ajustar_importe_cuota_hipoteca por previsión (I3; nunca recalcular_futuras); la financiacion
#   sube su row_version; auditoria ACTUALIZAR. CUADRO_NO_CUADRA se registra en el log y se eleva como ErrorMotor
#   VIOLACION_INVARIANTE_FISICA (500): la UnidadDeTrabajo hace ROLLBACK de todo lo escrito (O-H25).
#   Replay (§3.5.3): misma intencion y mismo contenido -> idempotente, 0 filas; otra tasa, fecha u otra
#   financiacion -> IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION. Sin desglose de bonificaciones (Q-T3D-07).
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 7)
# Version: 0.2.0 (F06 T3-F06 bloque 2 F06-01H, paso 11; IC-01 del contrato §6, indicacion de Moises del
#   2026-11-17): REVISION_SOBRE_CUOTA_PAGADA precede a VERSION_DESFASADA. El desfase se anota tras la financiacion
#   y se responde despues de mirar las cuotas afectadas (FECHA_REVISION_INCOHERENTE solo sin desfase). El orden de
#   locks no cambia (financiacion -> version vigente -> cuotas). Mutante M-H-44 (orden anterior).
# ============================================================

from __future__ import annotations

import datetime as dt
import json
import logging
import uuid
from decimal import Decimal
from typing import Any

from app.comun.fecha_funcional import Reloj, hoy_owner, reloj_sistema
from app.core.errores import CodigoError, ErrorMotor
from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
from app.core.unidad_trabajo import SesionMotor
from app.hipotecas import alta, lecturas
from app.hipotecas import calculadora as calc
from app.patrimonio.completitud import Rechazo
from app.repositories import auditoria_repository as auditoria
from app.repositories import compuesto_repository as repo_comp
from app.services.previsiones_service import PrevisionesService

_LOG = logging.getLogger(__name__)
NO_ENCONTRADA = "AGREGADO_NO_ENCONTRADO"
REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
NO_ACTIVA = "OPERACION_NO_PERMITIDA_EN_ESTADO"
INDETERMINADO = "SALDO_PRINCIPAL_INDETERMINADO"
VERSION_DESFASADA = "VERSION_DESFASADA"
FECHA_REVISION_INCOHERENTE = "FECHA_REVISION_INCOHERENTE"
SOBRE_CUOTA_PAGADA = "REVISION_SOBRE_CUOTA_PAGADA"
SIN_CUOTAS_FUTURAS = "SIN_CUOTAS_FUTURAS"
CONDICIONES_INCOMPLETAS = calc.CONDICIONES_INCOMPLETAS
MOTIVO = "F06-01H W-HIP-03/04: revision del tipo"
MARCA_VERSION = "gapto.f06.hipoteca.revision.version"


def version_id(intencion: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(intencion, MARCA_VERSION)


def forma(p: dict[str, Any]) -> str | None:
    """Motivo de CONDICIONES_INCOMPLETAS o None (antes de cualquier lock)."""
    try:
        calc.validar_condiciones(sistema=calc.SISTEMA, periodicidad=p.get("periodicidad") or calc.PERIODICIDAD)
    except calc.CondicionesIncompletas as exc:
        return exc.motivo
    tasa = alta._dec(p.get("tasa_anual"))
    if tasa is None or tasa < 0 or tasa > calc.MAX_TASA or tasa != tasa.quantize(alta.MAX_TASA_DECIMALES):
        return calc.VALORES_FUERA_DE_RANGO
    if p.get("tipo_interes") is not None and p["tipo_interes"] not in alta.TIPOS_INTERES:
        return calc.VALORES_FUERA_DE_RANGO
    if p.get("diferencial") is not None and alta._dec(p["diferencial"]) is None:
        return calc.VALORES_FUERA_DE_RANGO
    return None


def _condiciones(p: dict[str, Any], vigente: dict[str, Any]) -> dict[str, Any]:
    """Condiciones de la version nueva: lo no indicado se hereda de la vigente (forma, N-23)."""
    dif = p.get("diferencial")
    return {"tipo_interes": p.get("tipo_interes") or vigente["tipo_interes"],
            "tasa": alta._dec(p["tasa_anual"]).quantize(alta.MAX_TASA_DECIMALES),
            "indice": p["indice_referencia"] if p.get("indice_referencia") is not None else vigente["indice"],
            "diferencial": alta._dec(dif) if dif is not None else vigente["diferencial"]}


def _coincide(fila: tuple, fid: uuid.UUID, p: dict[str, Any]) -> bool:
    """Replay: misma financiacion, fecha, tasa y, si vienen en la peticion, tipo, indice y diferencial."""
    f, desde, motivo, tipo, tasa, indice, dif = fila
    if f != fid or motivo != "CAMBIO_CONDICIONES" or desde != p["vigente_desde"]:
        return False
    if Decimal(tasa) != alta._dec(p["tasa_anual"]):
        return False
    if p.get("tipo_interes") is not None and tipo != p["tipo_interes"]:
        return False
    if p.get("indice_referencia") is not None and indice != p["indice_referencia"]:
        return False
    return p.get("diferencial") is None or (dif is not None and Decimal(dif) == alta._dec(p["diferencial"]))


def _fila_cuota(sesion: SesionMotor, cuota_id: uuid.UUID) -> str:
    return sesion.uno("SELECT row_to_json(q)::text FROM gapto.financiacion_cuotas q WHERE q.id = %s", (cuota_id,))[0]


def revisar(sesion: SesionMotor, *, financiacion_id: uuid.UUID, peticion: dict[str, Any],
            reloj: Reloj = reloj_sistema) -> dict | Rechazo:
    """CUADRO_NO_CUADRA es un defecto: se registra en el log y sale como VIOLACION_INVARIANTE_FISICA (la
    UnidadDeTrabajo hace ROLLBACK de todo lo escrito; contrato §2 y §3.5.3, O-H25)."""
    try:
        return _revisar(sesion, financiacion_id=financiacion_id, peticion=peticion, reloj=reloj)
    except calc.CuadroNoCuadra as exc:
        _LOG.error("CUADRO_NO_CUADRA en W-HIP-04 (financiacion %s): %s", financiacion_id, exc.motivo)
        raise ErrorMotor(CodigoError.VIOLACION_INVARIANTE_FISICA, "El cuadro recalculado no cuadra.",
                         contexto_extra={"motivo": calc.CUADRO_NO_CUADRA}) from exc


def _revisar(sesion: SesionMotor, *, financiacion_id: uuid.UUID, peticion: dict[str, Any],
             reloj: Reloj) -> dict | Rechazo:
    motivo = forma(peticion)
    if motivo is not None:
        return Rechazo(CONDICIONES_INCOMPLETAS, {"motivo": motivo})
    intencion = uuid.UUID(str(peticion["intencion_id"]))
    desde: dt.date = peticion["vigente_desde"]
    repo_comp.tomar_advisory_raiz(sesion, intencion)                                   # 0P
    fin = sesion.uno("SELECT e.row_version, f.estado, f.saldo_principal_apertura, f.capital_original_contratado "
                     "FROM gapto.entidades e JOIN gapto.financiaciones f ON f.entidad_id = e.id WHERE e.id = %s AND "
                     "f.tipo_financiacion = 'HIPOTECA' FOR NO KEY UPDATE OF e, f", (financiacion_id,))
    if fin is None:
        return Rechazo(NO_ENCONTRADA)
    vid = version_id(intencion)
    previa = sesion.uno("SELECT financiacion_entidad_id, vigente_desde, motivo_version, tipo_interes, tasa_anual_pct, "
                        "indice_referencia, diferencial_pct FROM gapto.financiacion_condiciones_versiones "
                        "WHERE id = %s", (vid,))
    if previa is not None or repo_comp.leer(sesion, "hechos_financieros", intencion) is not None:   # identidad
        if previa is None or not _coincide(previa, financiacion_id, peticion):
            return Rechazo(REUTILIZADA)
        return {"idempotente": True, "hipoteca": lecturas.leer(sesion, financiacion_id, hoy_owner(sesion, reloj))}
    row_version, estado, apertura, capital = fin
    if estado != "ACTIVA":
        return Rechazo(NO_ACTIVA)
    if apertura is None:
        return Rechazo(INDETERMINADO)
    # IC-01 (contrato §6; indicacion de Moises del 2026-11-17): la cuota pagada se comprueba ANTES que
    # VERSION_DESFASADA; el desfase se anota aqui y se responde despues de mirar las cuotas afectadas.
    desfasada = row_version != peticion["row_version_esperada"]
    v = sesion.uno("SELECT id, vigente_desde, tipo_interes, indice_referencia, diferencial_pct "
                   "FROM gapto.financiacion_condiciones_versiones WHERE financiacion_entidad_id = %s "
                   "AND vigente_hasta IS NULL FOR UPDATE", (financiacion_id,))
    if v is None:
        return Rechazo(NO_ENCONTRADA)
    vigente = {"id": v[0], "desde": v[1], "tipo_interes": v[2], "indice": v[3], "diferencial": v[4]}
    if not desfasada and desde <= vigente["desde"]:
        return Rechazo(FECHA_REVISION_INCOHERENTE)
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT q.id, q.numero_cuota, q.fecha_vencimiento, q.capital_previsto, q.prevision_id "
                    "FROM gapto.financiacion_cuotas q WHERE q.financiacion_entidad_id = %s "
                    "ORDER BY q.numero_cuota FOR UPDATE", (financiacion_id,))
        cuotas = cur.fetchall()
    afectadas = [q for q in cuotas if q[2] >= desde]
    anteriores = [q for q in cuotas if q[2] < desde]
    estados: dict[uuid.UUID, tuple[str, int]] = {}
    for q in afectadas:
        if q[4] is not None:
            fila = sesion.uno("SELECT estado, row_version FROM gapto.previsiones WHERE id = %s", (q[4],))
            if fila is not None:
                estados[q[4]] = (fila[0], fila[1])
    if any(q[4] is None or estados.get(q[4], ("", 0))[0] != "ABIERTA" for q in afectadas):
        return Rechazo(SOBRE_CUOTA_PAGADA)
    if desfasada:
        return Rechazo(VERSION_DESFASADA)
    if not afectadas:
        return Rechazo(SIN_CUOTAS_FUTURAS)
    for q in afectadas:                                                                # previsiones FU por numero
        fila = sesion.uno("SELECT estado, row_version FROM gapto.previsiones WHERE id = %s FOR UPDATE", (q[4],))
        estados[q[4]] = (fila[0], fila[1])
    if any(estados[q[4]][0] != "ABIERTA" for q in afectadas):                          # relectura bajo lock
        return Rechazo(SOBRE_CUOTA_PAGADA)
    cond = _condiciones(peticion, vigente)
    pendiente = Decimal(capital) - sum((Decimal(q[3]) for q in anteriores), Decimal(0))
    tramo = calc.tramo_desde(pendiente, cond["tasa"], [q[1] for q in afectadas], [q[2] for q in afectadas])
    # --- escrituras
    sesion.ejecutar("UPDATE gapto.financiacion_condiciones_versiones SET vigente_hasta = %s WHERE id = %s",
                    (desde - dt.timedelta(days=1), vigente["id"]))
    sesion.ejecutar(
        "INSERT INTO gapto.financiacion_condiciones_versiones (id, financiacion_entidad_id, vigente_desde, "
        "motivo_version, hecho_causa_id, tipo_interes, tasa_anual_pct, indice_referencia, diferencial_pct, "
        "sistema_amortizacion, periodicidad, intervalo, importe_cuota_referencia, numero_cuotas_referencia) "
        "VALUES (%s, %s, %s, 'CAMBIO_CONDICIONES', NULL, %s, %s, %s, %s, 'FRANCES', 'MENSUAL', 1, %s, %s)",
        (vid, financiacion_id, desde, cond["tipo_interes"], cond["tasa"], cond["indice"], cond["diferencial"],
         tramo[0].cuota, len(tramo)))
    previsiones = PrevisionesService(UnidadDeTrabajoAdscrita(sesion))
    for q, c in zip(afectadas, tramo):
        antes = _fila_cuota(sesion, q[0])
        sesion.ejecutar("UPDATE gapto.financiacion_cuotas SET capital_previsto = %s, interes_previsto = %s, "
                        "importe_total_previsto = %s, condicion_version_id = %s WHERE id = %s",
                        (c.capital, c.interes, c.cuota, vid, q[0]))
        auditoria.registrar(sesion, tabla="financiacion_cuotas", registro_id=q[0], accion=auditoria.ACCION_ACTUALIZAR,
                            datos_antes_json=antes, datos_despues_json=_fila_cuota(sesion, q[0]),
                            motivo=f"{MOTIVO} (version {vid})")
        previsiones.ajustar_importe_cuota_hipoteca(
            sesion.contexto, prevision_id=q[4], financiacion_id=financiacion_id, importe_esperado=c.cuota,
            row_version_esperada=estados[q[4]][1], motivo_ajuste=f"{MOTIVO}: cuota {q[1]}")
    antes = sesion.uno("SELECT row_to_json(e)::text FROM gapto.entidades e WHERE id = %s", (financiacion_id,))[0]
    sesion.ejecutar("UPDATE gapto.entidades SET row_version = row_version + 1, updated_at = now() WHERE id = %s",
                    (financiacion_id,))
    despues = sesion.uno("SELECT row_to_json(e)::text FROM gapto.entidades e WHERE id = %s", (financiacion_id,))[0]
    auditoria.registrar(sesion, tabla="entidades", registro_id=financiacion_id, accion=auditoria.ACCION_ACTUALIZAR,
                        datos_antes_json=antes,
                        datos_despues_json=json.dumps({**json.loads(despues), "revision": {
                            "version_anterior_id": str(vigente["id"]), "version_nueva_id": str(vid),
                            "vigente_desde": desde.isoformat(), "cuotas_afectadas": len(afectadas)}},
                            ensure_ascii=False),
                        motivo=MOTIVO)
    return {"idempotente": False, "hipoteca": lecturas.leer(sesion, financiacion_id, hoy_owner(sesion, reloj))}
