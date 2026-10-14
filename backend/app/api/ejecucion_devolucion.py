# ============================================================
# GAPTO MOBILE 2027
# Fichero: ejecucion_devolucion.py
# Ruta: backend/app/api/ejecucion_devolucion.py
# Descripcion: Devolucion contextual D-194 desde el hecho origen y «Registrar
#   abono» posterior (F05-06 M2; F05 §14, §51.2, §51.4; lamina DEV v0.1 con
#   D-DEV-01..08 y P-DEV-01..06, F09 §12.105). API DE INTEGRACION F05,
#   PENDIENTE DE CONSOLIDACION F10. Compone servicios certificados del motor
#   (OP-13, OP-05, OP-08, OP-09) ADSCRITOS a UNA transaccion del adaptador
#   (UnidadDeTrabajoAdscrita); no cambia ninguno.
#
#   DEVOLUCION (POST /v1/hechos/{origen_id}/devoluciones), en una transaccion
#   (retry completo ante 40P01/40001 en UnidadDeTrabajo), ORDEN DE LOCKS:
#     cuenta del abono FOR NO KEY UPDATE (solo con «Ya cobrado»; como en el
#     registro, la cuenta va antes que los hechos) -> capacidad FOR SHARE
#     (motivo_cuenta) -> hecho ORIGEN FOR NO KEY UPDATE (el mismo lock con que
#     OP-13 serializa dos devoluciones; tomarlo aqui hace que TODAS las
#     guardas F05 lean el origen ya bloqueado) -> OP-13 -> OP-05 -> OP-08 ->
#     OP-09 (raiz del hecho de devolucion recien creado).
#     OP-03 (anular) toma hecho -> posiciones y nunca cuentas: sin ciclo.
#   Identidad ANTES que revalidacion: si el hecho de la intencion ya existe, la
#   guarda de replay propia compara lo persistido con la intencion (origen,
#   importe, fecha, nota, categoria, atribucion, abono) -> idempotente o
#   IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION, sin efectos. No se repite OP-05
#   (rechaza COMPLETA -> COMPLETA) ni se revalida el estado actual.
#   Intencion nueva, bajo los locks, en orden fijo (rechazos de capa F05 como
#   valor, sin escritura previa):
#     FECHA_FUTURA (devolucion y abono) -> origen ACTIVO
#     (DEVOLUCION_ORIGEN_NO_ACTIVO) -> solo devoluciones de gastos: algun
#     efecto GASTO y todos los GASTO positivos (P-DEV-06,
#     DEVOLUCION_ORIGEN_NO_GASTO; tambien excluye devolver una devolucion) ->
#     origen de V3 solo con un unico efecto GASTO (P-DEV-05, guarda F05,
#     DEVOLUCION_ORIGEN_V3_VARIOS_EFECTOS) -> una sola categoria entre los
#     efectos GASTO (R15 multicategoria fuera, DEVOLUCION_ORIGEN_MULTICATEGORIA)
#     -> atribucion SOLO_MIO solo si cada efecto GASTO del origen es COMPLETA
#     con una unica fila, del actor propio (P-DEV-01;
#     DEVOLUCION_ATRIBUCION_NO_DEMOSTRABLE) -> cuenta del abono (capacidad
#     PAGAR_GASTO: el abono de una devolucion vuelve al medio con que se paga
#     el gasto; P-DEV-02 propone la cuenta de la compra, que la tenia.
#     CUENTA_SIN_CAPACIDAD con operacion ABONO_DEVOLUCION).
#     Decision de adaptador anotada para la revisora: RECIBIR_INGRESO dejaria
#     fuera la tarjeta de credito (CREDITO no recibe ingresos), justo la
#     cuenta propuesta en la lamina A1, y llamaria «ingreso» a lo que no lo
#     es (D-DEV-04).
#   Composicion:
#     OP-13: hecho GASTO de signo contrario + relacion DEVOLUCION_DE, con la
#       categoria del efecto del origen («De la compra», conservada aunque hoy
#       este deshabilitada: F05 §25 / D-194), estado_atribucion NO_DISPONIBLE,
#       sin caja, `presupuestable` = la decision del origen (la declara el
#       adaptador; OP-13 no hereda nada), localizacion DESCONOCIDA. El limite
#       acumulado es el de OP-13: su EXCEDE_CAPACIDAD_REVERSIBLE se devuelve
#       con «lo que queda» leido bajo el mismo lock.
#     OP-05 (solo SOLO_MIO): una atribucion del actor propio por el importe
#       del efecto (negativo), NO_DISPONIBLE -> COMPLETA.
#     «Ya cobrado»: OP-08 movimiento de entrada (+importe, cuenta y fecha del
#       abono) + OP-09 conciliacion con el hecho de la devolucion.
#     «Todavía no»: nada mas. Sin movimiento no hay liquidez (D-DEV-03).
#   Identidades: hecho = intencion_id; el resto uuid5(intencion_id,
#   «gapto.f05.devolucion.<rol>»).
#
#   ABONO (POST /v1/hechos/{devolucion_id}/abono): cuenta -> capacidad ->
#   hecho de la devolucion FOR NO KEY UPDATE. Replay: el movimiento de la
#   intencion ya existe -> se compara (cuenta, fecha, importe, conciliado con
#   esta devolucion). Nueva: FECHA_FUTURA -> es devolucion
#   (HECHO_NO_ES_DEVOLUCION) -> ACTIVA (DEVOLUCION_NO_ACTIVA) -> sin abono
#   previo: cualquier conciliacion existente del hecho bloquea (YA_CONCILIADO,
#   no hay abono doble) -> cuenta -> OP-08 + OP-09 por el importe de la
#   devolucion. La devolucion no cambia.
# Version: 0.1.0 (F05-06 M2-A §A2-§A3)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from dataclasses import dataclass
from typing import Any

from app.api.dto_devolucion import AbonoCobrado, IntencionAbono, IntencionDevolucion
from app.api.ejecucion_registro import RechazoRegistro, bloquear_cuentas
from app.api.traductor_gasto_pagado import leer_actor_self
from app.comun.elegibilidad_cuentas import MONEDA, SIN_CAPACIDAD, motivo_cuenta
from app.comun.fecha_funcional import CODIGO_FECHA_FUTURA, Reloj, es_futura, reloj_sistema
from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_devolucion import DatosDevolucion
from app.core.modelos_efectos import DatosAtribucion
from app.core.modelos_tesoreria import DatosConciliacion, DatosMovimiento
from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
from app.core.unidad_trabajo import SesionMotor, UnidadDeTrabajo
from app.repositories import relaciones_repository as repo_rel
from app.services.devoluciones_service import DevolucionesService
from app.services.efectos_service import EfectosService
from app.services.tesoreria_service import TesoreriaService

ESCALA = decimal.Decimal("0.0001")
CENT = decimal.Decimal("0.01")
CERO = decimal.Decimal(0)

ORIGEN_NO_ACTIVO = "DEVOLUCION_ORIGEN_NO_ACTIVO"
ORIGEN_NO_GASTO = "DEVOLUCION_ORIGEN_NO_GASTO"
ORIGEN_V3_VARIOS_EFECTOS = "DEVOLUCION_ORIGEN_V3_VARIOS_EFECTOS"
ORIGEN_MULTICATEGORIA = "DEVOLUCION_ORIGEN_MULTICATEGORIA"
ATRIBUCION_NO_DEMOSTRABLE = "DEVOLUCION_ATRIBUCION_NO_DEMOSTRABLE"
EXCEDE = "EXCEDE_CAPACIDAD_REVERSIBLE"
NO_ES_DEVOLUCION = "HECHO_NO_ES_DEVOLUCION"
DEVOLUCION_NO_ACTIVA = "DEVOLUCION_NO_ACTIVA"
CUENTA_SIN_CAPACIDAD = "CUENTA_SIN_CAPACIDAD"
#: Operacion del abono para el texto de CUENTA_SIN_CAPACIDAD. Exige la
#: capacidad del medio de pago del gasto (PAGAR_GASTO; ver cabecera).
OPERACION_ABONO = "ABONO_DEVOLUCION"
OPERACION_CUENTA_ABONO = "GASTO"
CAPACIDAD_ABONO = "PAGAR_GASTO"


def _id(intencion: uuid.UUID, rol: str) -> uuid.UUID:
    return uuid.uuid5(intencion, f"gapto.f05.devolucion.{rol}")


def _texto(valor: decimal.Decimal) -> str:
    return str(decimal.Decimal(valor).quantize(CENT))


@dataclass(frozen=True, slots=True)
class Devuelta:
    hecho_id: uuid.UUID
    idempotente: bool
    estado_atribucion: str
    abono: str
    devuelto: decimal.Decimal
    queda: decimal.Decimal


@dataclass(frozen=True, slots=True)
class Abonada:
    hecho_id: uuid.UUID
    movimiento_id: uuid.UUID
    idempotente: bool
    importe: decimal.Decimal


class _Rechazo(Exception):
    """Rechazo de capa F05 detectado ANTES de cualquier escritura."""

    def __init__(self, codigo: str, detalle: dict[str, Any] | None = None) -> None:
        super().__init__(codigo)
        self.rechazo = RechazoRegistro(codigo, detalle)


def _como_valor(operacion):
    def envuelta(sesion: SesionMotor):
        try:
            return operacion(sesion)
        except _Rechazo as exc:
            return exc.rechazo
    return envuelta


# ------------------------------------------------------------------ lecturas del origen bajo lock
_ORIGEN = (
    "SELECT h.estado, h.moneda, h.presupuestable, h.importe_total, "
    "EXISTS (SELECT 1 FROM gapto.mapeos_importacion m WHERE m.tabla_destino = 'hechos_financieros' "
    "AND m.registro_destino_id = h.id) "
    "FROM gapto.hechos_financieros h WHERE h.id = %s FOR NO KEY UPDATE OF h"
)
_EFECTOS = (
    "SELECT e.id, e.tipo_efecto, e.importe_delta, e.estado_atribucion, e.categoria_id, "
    "(SELECT count(*) FROM gapto.efecto_atribuciones a WHERE a.efecto_id = e.id), "
    "(SELECT count(*) FROM gapto.efecto_atribuciones a JOIN gapto.actores_financieros af ON af.id = a.actor_id "
    " WHERE a.efecto_id = e.id AND af.tercero_id IS NULL) "
    "FROM gapto.hecho_efectos e WHERE e.hecho_id = %s ORDER BY e.id"
)


def efectos_gasto(sesion: SesionMotor, hecho_id: uuid.UUID) -> list[tuple]:
    with sesion.conexion.cursor() as cur:
        cur.execute(_EFECTOS, (hecho_id,))
        return [f for f in cur.fetchall() if f[1] == "GASTO"]


def motivo_origen(gastos: list[tuple], es_v3: bool) -> str | None:
    """P-DEV-06, P-DEV-05 y R15, en este orden (primer motivo que aplica)."""
    if not gastos or any(decimal.Decimal(f[2]) <= CERO for f in gastos):
        return ORIGEN_NO_GASTO
    if es_v3 and len(gastos) != 1:
        return ORIGEN_V3_VARIOS_EFECTOS
    if len({f[4] for f in gastos}) > 1:
        return ORIGEN_MULTICATEGORIA
    return None


def tuya_demostrable(gastos: list[tuple]) -> bool:
    """P-DEV-01: cada efecto GASTO del origen es COMPLETA con UNA unica fila de
    atribucion y esa fila es del actor propio."""
    return bool(gastos) and all(f[3] == "COMPLETA" and f[5] == 1 and f[6] == 1 for f in gastos)


def devuelto_y_queda(sesion: SesionMotor, origen_id: uuid.UUID) -> tuple[decimal.Decimal, decimal.Decimal]:
    """Lo ya devuelto (devoluciones ACTIVAS) y lo que queda, con las mismas
    lecturas de OP-13 (F04-D030). Solo lectura."""
    resumen = repo_rel.capacidad_por_naturaleza(sesion, origen_id, "GASTO")
    capacidad = abs(decimal.Decimal(resumen["neto"])) if resumen else CERO
    devuelto = decimal.Decimal(repo_rel.devuelto_acumulado(sesion, origen_id, "GASTO"))
    return devuelto, capacidad - devuelto


def _rechazo_cuenta_abono(sesion: SesionMotor, cuenta_id: uuid.UUID, fecha: dt.date) -> None:
    motivo = motivo_cuenta(sesion, cuenta_id, OPERACION_CUENTA_ABONO, fecha, bloquear=True)
    if motivo == MONEDA:
        raise ErrorMotor(CodigoError.MONEDA_INVALIDA, "Solo se admite una cuenta en EUR.")
    if motivo == SIN_CAPACIDAD:
        fila = sesion.uno("SELECT nombre FROM gapto.cuentas WHERE id = %s", (cuenta_id,))
        raise _Rechazo(CUENTA_SIN_CAPACIDAD, {"cuenta_id": str(cuenta_id), "cuenta": fila[0],
                                              "operacion": OPERACION_ABONO, "capacidad": CAPACIDAD_ABONO})
    if motivo is not None:
        raise ErrorMotor(CodigoError.CUENTA_DESCONOCIDA, "La cuenta no existe o no esta disponible.")


def _abonar(sesion: SesionMotor, contexto: ContextoOperacion, hecho_id: uuid.UUID, intencion_id: uuid.UUID,
            cuenta_id: uuid.UUID, fecha: dt.date, importe: decimal.Decimal, descripcion: str | None) -> None:
    """OP-08 (entrada real) + OP-09 (conciliacion con la devolucion)."""
    tesoreria = TesoreriaService(UnidadDeTrabajoAdscrita(sesion))
    movimiento = tesoreria.registrar_movimiento(contexto, DatosMovimiento(
        movimiento_id=_id(intencion_id, "movimiento"), cuenta_id=cuenta_id, fecha_movimiento=fecha,
        importe=importe, clase_movimiento="OPERACION", descripcion=descripcion,
        confirmado_at=dt.datetime.now(dt.timezone.utc)))
    version_hecho = sesion.uno("SELECT row_version FROM gapto.hechos_financieros WHERE id = %s", (hecho_id,))[0]
    tesoreria.conciliar(contexto, DatosConciliacion(
        conciliacion_id=_id(intencion_id, "conciliacion"), hecho_id=hecho_id,
        movimiento_tesoreria_id=movimiento.movimiento_id, importe_asignado=importe),
        hecho_row_version_esperada=version_hecho, movimiento_row_version_esperada=movimiento.row_version)


def _movimiento_de(sesion: SesionMotor, movimiento_id: uuid.UUID, hecho_id: uuid.UUID) -> tuple | None:
    """(cuenta_id, fecha, importe) del movimiento si esta conciliado con el hecho."""
    return sesion.uno(
        "SELECT m.cuenta_id, m.fecha_movimiento, m.importe FROM gapto.movimientos_tesoreria m "
        "JOIN gapto.hecho_movimientos_tesoreria hm ON hm.movimiento_tesoreria_id = m.id "
        "WHERE m.id = %s AND hm.hecho_id = %s", (movimiento_id, hecho_id))


# ------------------------------------------------------------------ devolucion
def _replay_devolucion(sesion: SesionMotor, origen_id: uuid.UUID, i: IntencionDevolucion) -> Devuelta:
    """Guarda propia: lo persistido para la intencion describe EXACTAMENTE esta
    devolucion; si no, IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION sin efectos."""
    x = i.importe.quantize(ESCALA)
    fila = sesion.uno(
        "SELECT h.fecha_hecho, h.concepto, h.moneda, h.importe_total, r.hecho_destino_id, r.importe_relacionado, "
        "e.importe_delta, e.estado_atribucion, e.tipo_efecto "
        "FROM gapto.hechos_financieros h "
        "JOIN gapto.hecho_relaciones r ON r.id = %s AND r.hecho_origen_id = h.id AND r.tipo_relacion = 'DEVOLUCION_DE' "
        "JOIN gapto.hecho_efectos e ON e.id = %s AND e.hecho_id = h.id WHERE h.id = %s",
        (_id(i.intencion_id, "relacion"), _id(i.intencion_id, "efecto"), i.intencion_id))
    estado_atribucion = "COMPLETA" if i.atribucion == "SOLO_MIO" else "NO_DISPONIBLE"
    mov = _movimiento_de(sesion, _id(i.intencion_id, "movimiento"), i.intencion_id)
    if isinstance(i.abono, AbonoCobrado):
        abono_coincide = mov is not None and (mov[0], mov[1], mov[2]) == (i.abono.cuenta_id, i.abono.fecha, x)
    else:
        abono_coincide = sesion.uno("SELECT 1 FROM gapto.movimientos_tesoreria WHERE id = %s",
                                    (_id(i.intencion_id, "movimiento"),)) is None
    if (fila is None or fila[0] != i.fecha_hecho or fila[1] != i.nota or fila[2] != i.moneda or fila[3] != x
            or fila[4] != origen_id or fila[5] != x or fila[6] != -x or fila[7] != estado_atribucion
            or fila[8] != "GASTO" or not abono_coincide):
        raise ErrorMotor(CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                         "Esta devolucion ya existe con otros datos.")
    devuelto, queda = devuelto_y_queda(sesion, origen_id)
    return Devuelta(hecho_id=i.intencion_id, idempotente=True, estado_atribucion=estado_atribucion,
                    abono="COBRADO" if isinstance(i.abono, AbonoCobrado) else "PENDIENTE",
                    devuelto=devuelto, queda=queda)


def registrar_devolucion(unidad: UnidadDeTrabajo, contexto: ContextoOperacion, origen_id: uuid.UUID,
                         i: IntencionDevolucion, reloj: Reloj = reloj_sistema) -> Devuelta | RechazoRegistro:
    cobrado = isinstance(i.abono, AbonoCobrado)

    def operacion(sesion: SesionMotor) -> Devuelta | RechazoRegistro:
        if cobrado:
            bloquear_cuentas(sesion, i.abono.cuenta_id)
        origen = sesion.uno(_ORIGEN, (origen_id,))
        if origen is None:
            raise ErrorMotor(CodigoError.AGREGADO_NO_ENCONTRADO, "El hecho origen no existe o no es accesible.")
        estado, _moneda, presupuestable, _total, es_v3 = origen
        if sesion.uno("SELECT 1 FROM gapto.hechos_financieros WHERE id = %s", (i.intencion_id,)) is not None:
            return _replay_devolucion(sesion, origen_id, i)
        if es_futura(sesion, i.fecha_hecho, reloj) or (cobrado and es_futura(sesion, i.abono.fecha, reloj)):
            return RechazoRegistro(CODIGO_FECHA_FUTURA)
        if estado != "ACTIVO":
            raise _Rechazo(ORIGEN_NO_ACTIVO)
        gastos = efectos_gasto(sesion, origen_id)
        motivo = motivo_origen(gastos, es_v3)
        if motivo is not None:
            raise _Rechazo(motivo)
        if i.atribucion == "SOLO_MIO" and not tuya_demostrable(gastos):
            raise _Rechazo(ATRIBUCION_NO_DEMOSTRABLE)
        if cobrado:
            _rechazo_cuenta_abono(sesion, i.abono.cuenta_id, i.abono.fecha)
        x = i.importe.quantize(ESCALA)
        datos = DatosDevolucion(
            hecho_id=i.intencion_id, efecto_id=_id(i.intencion_id, "efecto"),
            relacion_id=_id(i.intencion_id, "relacion"), hecho_original_id=origen_id, tipo_efecto="GASTO",
            importe=x, fecha_hecho=i.fecha_hecho, moneda=i.moneda, concepto=i.nota, categoria_id=gastos[0][4],
            estado_atribucion="NO_DISPONIBLE", presupuestable=presupuestable)
        try:
            r = DevolucionesService(UnidadDeTrabajoAdscrita(sesion)).devolver(contexto, datos)
        except ErrorMotor as exc:
            if exc.codigo is CodigoError.EXCEDE_CAPACIDAD_REVERSIBLE:
                _, queda = devuelto_y_queda(sesion, origen_id)
                raise _Rechazo(EXCEDE, {"queda": _texto(queda)}) from exc
            raise
        estado_atribucion = "NO_DISPONIBLE"
        if i.atribucion == "SOLO_MIO":
            EfectosService(UnidadDeTrabajoAdscrita(sesion)).atribuir_efecto(
                contexto, hecho_id=r.hecho_id, row_version_esperada=r.hecho_row_version, efecto_id=r.efecto_id,
                atribuciones=[DatosAtribucion(atribucion_id=_id(i.intencion_id, "atribucion"),
                                              actor_id=leer_actor_self(sesion), importe_atribuido=r.importe_delta,
                                              criterio_atribucion="MANUAL")],
                estado_resultante="COMPLETA")
            estado_atribucion = "COMPLETA"
        if cobrado:
            _abonar(sesion, contexto, r.hecho_id, i.intencion_id, i.abono.cuenta_id, i.abono.fecha, x, i.nota)
        return Devuelta(hecho_id=r.hecho_id, idempotente=False, estado_atribucion=estado_atribucion,
                        abono="COBRADO" if cobrado else "PENDIENTE", devuelto=r.devuelto_acumulado,
                        queda=r.pendiente)

    return unidad.ejecutar(contexto, _como_valor(operacion),
                           nombre="F05-06 M2 devolucion (locks + OP-13 + OP-05 [+ OP-08 + OP-09])")


# ------------------------------------------------------------------ abono posterior
def registrar_abono(unidad: UnidadDeTrabajo, contexto: ContextoOperacion, devolucion_id: uuid.UUID,
                    i: IntencionAbono, reloj: Reloj = reloj_sistema) -> Abonada | RechazoRegistro:
    def operacion(sesion: SesionMotor) -> Abonada | RechazoRegistro:
        bloquear_cuentas(sesion, i.cuenta_id)
        hecho = sesion.uno("SELECT estado FROM gapto.hechos_financieros WHERE id = %s FOR NO KEY UPDATE",
                           (devolucion_id,))
        if hecho is None:
            raise ErrorMotor(CodigoError.AGREGADO_NO_ENCONTRADO, "La devolucion no existe o no es accesible.")
        relacion = sesion.uno("SELECT importe_relacionado FROM gapto.hecho_relaciones "
                              "WHERE hecho_origen_id = %s AND tipo_relacion = 'DEVOLUCION_DE'", (devolucion_id,))
        movimiento_id = _id(i.intencion_id, "movimiento")
        if sesion.uno("SELECT 1 FROM gapto.movimientos_tesoreria WHERE id = %s", (movimiento_id,)) is not None:
            mov = _movimiento_de(sesion, movimiento_id, devolucion_id)
            if relacion is None or mov is None or (mov[0], mov[1], mov[2]) != (
                    i.cuenta_id, i.fecha, decimal.Decimal(relacion[0])):
                raise ErrorMotor(CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                                 "Este abono ya existe con otros datos.")
            return Abonada(hecho_id=devolucion_id, movimiento_id=movimiento_id, idempotente=True,
                           importe=decimal.Decimal(relacion[0]))
        if es_futura(sesion, i.fecha, reloj):
            return RechazoRegistro(CODIGO_FECHA_FUTURA)
        if relacion is None:
            raise _Rechazo(NO_ES_DEVOLUCION)
        if hecho[0] != "ACTIVO":
            raise _Rechazo(DEVOLUCION_NO_ACTIVA)
        if sesion.uno("SELECT 1 FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id = %s LIMIT 1",
                      (devolucion_id,)) is not None:
            raise ErrorMotor(CodigoError.YA_CONCILIADO, "La devolucion ya tiene su abono registrado.")
        _rechazo_cuenta_abono(sesion, i.cuenta_id, i.fecha)
        importe = decimal.Decimal(relacion[0])
        concepto = sesion.uno("SELECT concepto FROM gapto.hechos_financieros WHERE id = %s", (devolucion_id,))[0]
        _abonar(sesion, contexto, devolucion_id, i.intencion_id, i.cuenta_id, i.fecha, importe, concepto)
        return Abonada(hecho_id=devolucion_id, movimiento_id=movimiento_id, idempotente=False, importe=importe)

    return unidad.ejecutar(contexto, _como_valor(operacion), nombre="F05-06 M2 abono (locks + OP-08 + OP-09)")


# ------------------------------------------------------------------ lectura del contexto (A4)
def contexto_devolucion(sesion: SesionMotor, origen_id: uuid.UUID) -> dict[str, Any] | None:
    """Lo que el formulario muestra del origen (D-DEV-02) y si admite una
    devolucion, con las MISMAS guardas que la escritura (motivo_origen,
    tuya_demostrable). Solo lectura, sin locks: la escritura revalida todo bajo
    el lock del origen. None si el hecho no existe o es de otro owner."""
    fila = sesion.uno(
        "SELECT h.estado, h.fecha_hecho, h.concepto, h.importe_total, "
        "EXISTS (SELECT 1 FROM gapto.mapeos_importacion m WHERE m.tabla_destino = 'hechos_financieros' "
        "AND m.registro_destino_id = h.id), "
        "(SELECT t.nombre FROM gapto.hecho_terceros ht JOIN gapto.terceros t ON t.id = ht.tercero_id "
        " WHERE ht.hecho_id = h.id ORDER BY ht.principal DESC, t.id LIMIT 1) "
        "FROM gapto.hechos_financieros h WHERE h.id = %s", (origen_id,))
    if fila is None:
        return None
    estado, fecha, nota, total, es_v3, tercero = fila
    gastos = efectos_gasto(sesion, origen_id)
    motivo = ORIGEN_NO_ACTIVO if estado != "ACTIVO" else motivo_origen(gastos, es_v3)
    categoria_id = gastos[0][4] if gastos and motivo is None else None
    categoria = None
    if categoria_id is not None:
        categoria = sesion.uno("SELECT nombre FROM gapto.categorias_financieras WHERE id = %s", (categoria_id,))[0]
    devuelto, queda = devuelto_y_queda(sesion, origen_id) if gastos else (CERO, CERO)
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT d.id, d.fecha_hecho, r.importe_relacionado, "
            "EXISTS (SELECT 1 FROM gapto.hecho_movimientos_tesoreria hm WHERE hm.hecho_id = d.id) "
            "FROM gapto.hecho_relaciones r JOIN gapto.hechos_financieros d ON d.id = r.hecho_origen_id "
            "WHERE r.hecho_destino_id = %s AND r.tipo_relacion = 'DEVOLUCION_DE' AND d.estado = 'ACTIVO' "
            "ORDER BY d.fecha_hecho, d.id", (origen_id,))
        devoluciones = [{"hecho_id": d[0], "fecha_hecho": d[1], "importe": _texto(d[2]),
                         "abono": "COBRADO" if d[3] else "PENDIENTE"} for d in cur.fetchall()]
        # P-DEV-02: la cuenta con la que se pago la compra (movimiento de salida).
        cur.execute(
            "SELECT c.id, c.nombre FROM gapto.hecho_movimientos_tesoreria hm "
            "JOIN gapto.movimientos_tesoreria m ON m.id = hm.movimiento_tesoreria_id "
            "JOIN gapto.cuentas c ON c.id = m.cuenta_id WHERE hm.hecho_id = %s AND m.importe < 0 "
            "ORDER BY m.fecha_movimiento, m.id LIMIT 1", (origen_id,))
        compra = cur.fetchone()
    tuya = motivo is None and tuya_demostrable(gastos)
    if motivo is None and queda <= CERO:
        motivo = EXCEDE
    return {
        "origen_id": origen_id, "fecha_hecho": fecha, "nota": nota, "tercero": tercero,
        "categoria_id": categoria_id, "categoria": categoria, "importe_total": _texto(total or CERO),
        "devuelto": _texto(devuelto), "queda": _texto(queda), "neto": _texto((total or CERO) - devuelto),
        "devoluciones": devoluciones, "disponible": motivo is None, "motivo": motivo,
        "atribucion_propuesta": "SOLO_MIO" if tuya else "SIN_INDICAR", "tuya_disponible": tuya,
        "cuenta_compra": None if compra is None else {"cuenta_id": compra[0], "nombre": compra[1]},
    }
