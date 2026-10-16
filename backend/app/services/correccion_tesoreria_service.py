# ============================================================
# GAPTO MOBILE 2027
# Fichero: correccion_tesoreria_service.py
# Ruta: backend/app/services/correccion_tesoreria_service.py
# Descripcion: F04-R2 R2-B (contrato F04-R2 v0.8 §1.5, §2.1, §2.2, §2.5, §4,
#   §5, §6, §8.1). OP-21P «corregir el pago de un gasto simple» y OP-21T
#   «corregir una transferencia propia»: correccion EN SITIO de un dato que
#   NUNCA fue cierto (INV-07), con su tesoreria.
#
#   QUE NO ES. No es un acontecimiento posterior (OP-13, OP-11, OP-18): el
#   llamante declara `error_de_registro = true` («el dato nunca fue cierto»);
#   sin esa declaracion -> OPERACION_NO_PERMITIDA_EN_ESTADO /
#   ACONTECIMIENTO_POSTERIOR. Nunca crea filas, nunca borra, nunca anula: el
#   movimiento conserva su `id` (§2.1.3) y ningun movimiento real pasa a
#   ANULADO por esta via (§10.3). OP-03P es R2-C y no vive aqui.
#
#   ELEGIBILIDAD (todas bajo la raiz; si falla una, rechazo sin efectos):
#     OP-21P  E-1 hecho ACTIVO, GASTO, un efecto GASTO, no devolucion (§2.4),
#             no inversion; E-2 una conciliacion contra un movimiento ACTIVO;
#             E-2 bis cobertura completa; E-3 movimiento solo de este hecho;
#             E-4 sin reversiones (de ningun estado) y fuera de transferencias;
#             E-5 misma moneda; E-6 sin origen importado ni AJUSTE_SALDO
#             (§2.5); E-7 periodo cerrado y ledger (§5).
#     OP-21T  T-1 TRANSFERENCIA con su fila y dos conciliaciones, una por pata;
#             T-1 bis cobertura por pata; T-2 sin otros hechos ni reversiones;
#             T-3 misma moneda; T-4 MISMA_CUENTA; T-5 cuentas nuevas §2.1.5;
#             T-6 §5. Las dos patas SIEMPRE juntas.
#   La capacidad de la cuenta (PAGAR_GASTO / TRANSFERIR_*) NO es del motor: la
#   valida el adaptador F05 (api/ejecucion_correccion.py) bajo el mismo lock
#   (§2.1.5, decision de Moisés). El motor exige owner, enabled, fecha_cierre,
#   fecha_inicio_ledger y moneda de cada cuenta NUEVA; corregir importe o fecha
#   en una cuenta que HOY esta deshabilitada se admite (R-10).
#
#   ORDEN DE LOCKS (§6.1, §6.7.1; prohibido volver atras):
#     1 lecturas previas sin lock (conjunto: movimientos, cuentas nuevas,
#       vinculos, reglas y previsiones) -> 2 advisory INVERSIONES si cambia el
#       importe (OP-21P) -> 2 bis cuentas NUEVAS FOR NO KEY UPDATE por UUID ->
#       3 hecho -> 4 posiciones (adquirir_raiz) -> 5 reglas FU y previsiones
#       por UUID (solo con propagacion de fecha o vinculos_a_corregir) -> 6
#       movimientos por UUID -> 7 hijas (UPDATE directo). Tras adquirir se
#       relee el conjunto; si cambio -> ConjuntoCambiado (40001, reintento
#       COMPLETO, protocolo F04-D058).
#
#   AUDITORIA (§8.1): una fila por fila mutada, en la misma transaccion, con
#   foto anterior y posterior (hecho y movimientos con row_version), el mismo
#   motivo y el request_id del contexto (obligatorio: REQUEST_ID_AUSENTE).
#   Cada fila se escribe UNA vez: el estado final se compone antes de escribir.
#   Idempotencia (§6.4): con el mismo request_id, lo auditado decide; igual ->
#   idempotente sin escribir; distinto -> IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION.
#
#   PREVISIONES (§4.1, R1-OBS-01): bajar el importe no se bloquea por los
#   vinculos; si el estado final excede la porcion -> requiere_revision con
#   PORCION_EXCEDIDA y sin recortar vinculos. `vinculos_a_corregir` (opcional,
#   explicito) se aplica con G-R1-C sobre el estado final.
# Version: 0.1.0 (F04-R2 R2-B)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.unidad_trabajo import SesionMotor, Traza, UnidadDeTrabajo
from app.repositories import auditoria_repository as auditoria
from app.repositories import correccion_tesoreria_repository as repo
from app.repositories import correcciones_repository as repo_corr
from app.repositories import hechos_repository as repo_hechos
from app.repositories import previsiones_repository as repo_prev
from app.repositories import reglas_repository as repo_reglas
from app.services import integridad_posicion
from app.services.correcciones_service import exigir_devuelto_dentro_de_capacidad
from app.services.efectos_service import EfectosService
from app.services.previsiones_service import ConjuntoCambiado, exigir_porcion

D = decimal.Decimal
CUATRO = D("0.0001")
CIEN = D(100)

TIPO_GASTO = "GASTO"
TIPO_TRANSFERENCIA = "TRANSFERENCIA"
ESTADO_ACTIVO = "ACTIVO"
CLASE_AJUSTE = "AJUSTE_SALDO"
SIN_ATRIBUCION = "NO_DISPONIBLE"
PARTICIPACION_CUENTA = "PARTICIPACION_CUENTA"
TABLA_VINCULOS = repo_prev.TABLA_VINCULOS
TABLA_ATRIBUCIONES = "efecto_atribuciones"

#: Vias para lo que SI ocurrio y despues cambio (§1.2, §1.5).
VIAS_POSTERIORES = ("OP-13", "OP-11", "OP-18")


@dataclass(frozen=True, slots=True)
class DatosVinculoACorregir:
    """§4.1 ampliacion opcional: nuevo `importe_asignado` de un vinculo DEL
    PROPIO hecho, con la identidad y la version de su previsión (§7.4)."""

    vinculo_id: uuid.UUID
    prevision_id_esperada: uuid.UUID
    prevision_row_version_esperada: int
    importe_asignado: decimal.Decimal


@dataclass(frozen=True, slots=True)
class DatosCorreccionPago:
    """Entrada de OP-21P (§2.1). `importe` es el importe del gasto (positivo);
    `atribuciones_nuevas` y `aportaciones_nuevas` son la decision explicita
    (id existente -> importe final) cuando el recalculo no es determinista."""

    hecho_id: uuid.UUID
    row_version_esperada: int
    movimiento_row_version_esperada: int
    motivo: str | None
    error_de_registro: bool | None = None
    importe: decimal.Decimal | None = None
    fecha: dt.date | None = None
    cuenta_id: uuid.UUID | None = None
    atribuciones_nuevas: Mapping[uuid.UUID, decimal.Decimal] = field(default_factory=dict)
    aportaciones_nuevas: Mapping[uuid.UUID, decimal.Decimal] = field(default_factory=dict)
    vinculos_a_corregir: tuple[DatosVinculoACorregir, ...] = ()


@dataclass(frozen=True, slots=True)
class DatosCorreccionTransferencia:
    """Entrada de OP-21T (§2.2). `movimientos_row_version_esperadas`: version
    leida de CADA pata (las dos, aunque solo cambie una cuenta)."""

    hecho_id: uuid.UUID
    row_version_esperada: int
    movimientos_row_version_esperadas: Mapping[uuid.UUID, int]
    motivo: str | None
    error_de_registro: bool | None = None
    importe: decimal.Decimal | None = None
    fecha: dt.date | None = None
    cuenta_origen_id: uuid.UUID | None = None
    cuenta_destino_id: uuid.UUID | None = None
    vinculos_a_corregir: tuple[DatosVinculoACorregir, ...] = ()


@dataclass(frozen=True, slots=True)
class ResultadoCorreccionTesoreria:
    hecho_id: uuid.UUID
    hecho_row_version: int
    movimientos: dict[uuid.UUID, int]
    idempotente: bool = False
    filas_auditadas: int = 0
    requiere_revision: bool = False
    motivo_revision: str | None = None
    previsiones_afectadas: tuple[uuid.UUID, ...] = ()
    previsiones_propagadas: tuple[uuid.UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanCuentas:
    """Lectura previa SIN lock para preparar la adquisicion (§6.1 nivel 1).
    No autoriza nada: el adaptador F05 la usa para bloquear y validar la
    capacidad en el mismo orden que el motor (advisory -> cuentas)."""

    advisory: bool
    cuentas_nuevas: dict[uuid.UUID, str]  # cuenta -> operacion F05
    fecha: dt.date | None


# ------------------------------------------------------------------ rechazos
def _fuera(detalle: str) -> ErrorMotor:
    return ErrorMotor(
        CodigoError.CORRECCION_AGREGADA_REQUERIDA,
        "Esta correccion queda fuera del alcance de v1.",
        contexto_extra={"motivo": "FUERA_DE_ALCANCE_V1", "detalle": detalle},
    )


def _decision(motivo: str) -> ErrorMotor:
    return ErrorMotor(
        CodigoError.CORRECCION_AGREGADA_REQUERIDA,
        "La correccion exige una decision explicita sobre el reparto.",
        contexto_extra={"motivo": motivo},
    )


def _estado(motivo: str, mensaje: str, **extra: Any) -> ErrorMotor:
    return ErrorMotor(
        CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, mensaje,
        contexto_extra={"motivo": motivo, **extra},
    )


def _desfasada(que: str) -> ErrorMotor:
    return ErrorMotor(CodigoError.VERSION_DESFASADA, f"{que} ha cambiado desde la version que conoce el llamante.")


def _q(valor: Any) -> decimal.Decimal:
    return D(valor).quantize(CUATRO)


def _validar_comun(contexto: ContextoOperacion, motivo: str | None, error_de_registro: bool | None,
                   cambios: tuple[Any, ...], importe: decimal.Decimal | None) -> str:
    if getattr(contexto, "request_id", None) is None:
        raise ErrorMotor(CodigoError.ENTRADA_INVALIDA, "La correccion exige request_id de correlacion.",
                         contexto_extra={"motivo": "REQUEST_ID_AUSENTE"})
    if not (motivo or "").strip():
        raise ErrorMotor(CodigoError.MOTIVO_AUSENTE, "Toda correccion de tesoreria exige motivo explicito.")
    if error_de_registro is not True:
        raise _estado("ACONTECIMIENTO_POSTERIOR",
                      "Corregir es solo para datos que nunca fueron ciertos; lo que ocurrio y despues "
                      "cambio se registra con su operacion posterior.", vias=list(VIAS_POSTERIORES))
    if all(c is None for c in cambios):
        raise ErrorMotor(CodigoError.ENTRADA_INVALIDA, "La correccion debe cambiar importe, fecha o cuenta.")
    if importe is not None and D(importe) <= 0:
        raise ErrorMotor(CodigoError.IMPORTE_NO_POSITIVO, "El importe corregido debe ser mayor que cero.")
    return motivo.strip()


def _exigir_request_id_en_transaccion(sesion: SesionMotor) -> None:
    fila = sesion.uno("SELECT COALESCE(current_setting('gapto.request_id', true), '')")
    if not fila or not fila[0]:
        raise ErrorMotor(CodigoError.ENTRADA_INVALIDA, "La transaccion no tiene request_id de correlacion.",
                         contexto_extra={"motivo": "REQUEST_ID_AUSENTE"})


# ------------------------------------------------------------------ lecturas previas (sin lock)
def _movimientos_previos(sesion: SesionMotor, hecho_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID]:
    """movimiento -> cuenta actual, de las conciliaciones del hecho."""
    salida: dict[uuid.UUID, uuid.UUID] = {}
    for conciliacion in repo.conciliaciones(sesion, hecho_id):
        movimiento = repo.leer_movimiento(sesion, conciliacion["movimiento_id"])
        if movimiento is not None:
            salida[movimiento["id"]] = movimiento["cuenta_id"]
    return salida


def plan_cuentas_pago(sesion: SesionMotor, datos: DatosCorreccionPago) -> PlanCuentas:
    nuevas: dict[uuid.UUID, str] = {}
    movimientos = _movimientos_previos(sesion, datos.hecho_id)
    if datos.cuenta_id is not None and datos.cuenta_id not in set(movimientos.values()):
        nuevas[datos.cuenta_id] = "GASTO"
    return PlanCuentas(advisory=datos.importe is not None, cuentas_nuevas=nuevas, fecha=_fecha_previa(
        sesion, datos.hecho_id, datos.fecha))


def plan_cuentas_transferencia(sesion: SesionMotor, datos: DatosCorreccionTransferencia) -> PlanCuentas:
    nuevas: dict[uuid.UUID, str] = {}
    patas = _patas_previas(sesion, datos.hecho_id)
    if patas is not None:
        salida, entrada = patas
        if datos.cuenta_origen_id is not None and datos.cuenta_origen_id != salida["cuenta_id"]:
            nuevas[datos.cuenta_origen_id] = "TRANSFERENCIA_ORIGEN"
        if datos.cuenta_destino_id is not None and datos.cuenta_destino_id != entrada["cuenta_id"]:
            nuevas[datos.cuenta_destino_id] = "TRANSFERENCIA_DESTINO"
    return PlanCuentas(advisory=False, cuentas_nuevas=nuevas, fecha=_fecha_previa(
        sesion, datos.hecho_id, datos.fecha))


def _fecha_previa(sesion: SesionMotor, hecho_id: uuid.UUID, fecha: dt.date | None) -> dt.date | None:
    if fecha is not None:
        return fecha
    hecho = repo.leer_hecho(sesion, hecho_id)
    return None if hecho is None else hecho["fecha"]


def _patas_previas(sesion: SesionMotor, hecho_id: uuid.UUID) -> tuple[dict, dict] | None:
    for conciliacion in repo.conciliaciones(sesion, hecho_id):
        movimiento = repo.leer_movimiento(sesion, conciliacion["movimiento_id"])
        if movimiento is None or movimiento["transferencia_id"] is None:
            continue
        transferencia = repo.leer_transferencia(sesion, movimiento["transferencia_id"])
        if transferencia is None:
            continue
        salida = repo.leer_movimiento(sesion, transferencia["salida"])
        entrada = repo.leer_movimiento(sesion, transferencia["entrada"])
        if salida is not None and entrada is not None:
            return salida, entrada
    return None


class CorreccionTesoreriaService:
    """OP-21P y OP-21T. Colaboradores de previsiones INYECTADOS y obligatorios
    (como OP-02/OP-03, F04-D022): `impacto_ancla` propaga una correccion de
    fecha y `conjunto_impacto` da, sin lock, lo que bloqueara."""

    __slots__ = ("_unidad", "_impacto_ancla", "_conjunto_impacto", "ultima_traza")

    def __init__(
        self,
        unidad: UnidadDeTrabajo,
        *,
        impacto_ancla: Callable[[SesionMotor, uuid.UUID], dict[str, Any]],
        conjunto_impacto: Callable[[SesionMotor, uuid.UUID], tuple[list[uuid.UUID], list[uuid.UUID]]],
    ) -> None:
        self._unidad = unidad
        self._impacto_ancla = impacto_ancla
        self._conjunto_impacto = conjunto_impacto
        self.ultima_traza: Traza | None = None

    # ==================================================================
    # OP-21P
    # ==================================================================
    def corregir_pago(self, contexto: ContextoOperacion, datos: DatosCorreccionPago) -> ResultadoCorreccionTesoreria:
        motivo = _validar_comun(contexto, datos.motivo, datos.error_de_registro,
                                (datos.importe, datos.fecha, datos.cuenta_id), datos.importe)

        def operacion(sesion: SesionMotor) -> ResultadoCorreccionTesoreria:
            owner = repo_hechos.exigir_contexto(sesion)
            _exigir_request_id_en_transaccion(sesion)
            # 1. Conjunto previo, sin lock.
            plan = plan_cuentas_pago(sesion, datos)
            movimientos_previos = _movimientos_previos(sesion, datos.hecho_id)
            # 2-6. Adquisicion en el orden global.
            fotos, vinculos = self._adquirir(
                sesion, owner, datos.hecho_id, advisory=plan.advisory, cuentas=plan.cuentas_nuevas,
                vinculos=datos.vinculos_a_corregir, propaga=datos.fecha is not None,
                movimientos=movimientos_previos)
            # Relectura del conjunto bajo la raiz.
            if _movimientos_previos(sesion, datos.hecho_id) != movimientos_previos:
                raise ConjuntoCambiado()
            if plan_cuentas_pago(sesion, datos).cuentas_nuevas != plan.cuentas_nuevas:
                raise ConjuntoCambiado()

            estado = self._estado_pago(sesion, datos)
            idempotente = self._identidad(sesion, contexto, motivo, estado, datos)
            if idempotente is not None:
                return idempotente
            self._elegibilidad_pago(sesion, datos, estado)
            plan_escritura = self._componer_pago(sesion, datos, estado)

            filas = 0
            hecho = estado["hecho"]
            movimiento = estado["movimiento"]
            cambios_hecho: dict[str, Any] = {}
            if datos.importe is not None:
                cambios_hecho["importe_total"] = _q(datos.importe)
            if datos.fecha is not None:
                cambios_hecho["fecha_hecho"] = datos.fecha
            version_hecho = self._escribir_hecho(sesion, datos.hecho_id, hecho["row_version"], cambios_hecho, motivo)
            filas += 1
            if datos.importe is not None:
                efecto = estado["efecto"]
                par = repo_corr.actualizar_efecto(sesion, efecto["id"], datos.hecho_id,
                                                  {"importe_delta": _q(datos.importe)})
                if par is None:  # pragma: no cover - leido bajo la raiz
                    raise ErrorMotor(CodigoError.AGREGADO_NO_ENCONTRADO, "El efecto ya no es de este hecho.")
                auditoria.registrar(sesion, tabla=repo_corr.TABLA_EFECTOS, registro_id=efecto["id"],
                                    accion=auditoria.ACCION_ACTUALIZAR, datos_antes_json=par[0],
                                    datos_despues_json=par[1], motivo=motivo)
                filas += 1
                filas += self._escribir_atribuciones(sesion, plan_escritura["atribuciones"], motivo)
                # §3.2: no por debajo de lo ya devuelto (guarda de OP-21, mismo validador).
                exigir_devuelto_dentro_de_capacidad(sesion, datos.hecho_id)
            # Exceso de porcion (G-R1-C) sobre el estado final del hecho: el
            # tope ya es el corregido; los vinculos aun no.
            self._exigir_vinculos(sesion, datos.hecho_id, vinculos)

            cambios_mov: dict[str, Any] = {}
            if datos.importe is not None:
                cambios_mov["importe"] = -_q(datos.importe)
            if datos.fecha is not None:
                cambios_mov["fecha_movimiento"] = datos.fecha
            if datos.cuenta_id is not None and datos.cuenta_id != movimiento["cuenta_id"]:
                cambios_mov["cuenta_id"] = datos.cuenta_id
            if cambios_mov:
                versiones = {movimiento["id"]: self._escribir_movimiento(
                    sesion, movimiento["id"], movimiento["row_version"], cambios_mov, motivo)}
                filas += 1
            else:  # la cuenta pedida es la actual y nada mas cambia: el movimiento no muta
                versiones = {movimiento["id"]: movimiento["row_version"]}
            if datos.importe is not None:
                filas += self._escribir_conciliacion(sesion, estado["conciliacion"]["id"], datos.hecho_id,
                                                     -_q(datos.importe), motivo)
            filas += self._escribir_aportaciones(sesion, datos.hecho_id, plan_escritura["aportaciones"], motivo)
            filas += self._escribir_vinculos(sesion, vinculos, motivo)

            if datos.importe is not None:
                self._validar_atribuciones(sesion, datos.hecho_id, estado["efecto"]["id"])
            integridad_posicion.validar(sesion, fotos)
            return self._resultado(sesion, datos.hecho_id, version_hecho, versiones, filas,
                                   propaga=datos.fecha is not None)

        return self._ejecutar(contexto, operacion, "OP-21P corregir_pago")

    # ==================================================================
    # OP-21T
    # ==================================================================
    def corregir_transferencia(self, contexto: ContextoOperacion,
                               datos: DatosCorreccionTransferencia) -> ResultadoCorreccionTesoreria:
        motivo = _validar_comun(contexto, datos.motivo, datos.error_de_registro,
                                (datos.importe, datos.fecha, datos.cuenta_origen_id, datos.cuenta_destino_id),
                                datos.importe)

        def operacion(sesion: SesionMotor) -> ResultadoCorreccionTesoreria:
            owner = repo_hechos.exigir_contexto(sesion)
            _exigir_request_id_en_transaccion(sesion)
            plan = plan_cuentas_transferencia(sesion, datos)
            movimientos_previos = _movimientos_previos(sesion, datos.hecho_id)
            fotos, vinculos = self._adquirir(
                sesion, owner, datos.hecho_id, advisory=False, cuentas=plan.cuentas_nuevas,
                vinculos=datos.vinculos_a_corregir, propaga=datos.fecha is not None,
                movimientos=movimientos_previos)
            if _movimientos_previos(sesion, datos.hecho_id) != movimientos_previos:
                raise ConjuntoCambiado()
            if plan_cuentas_transferencia(sesion, datos).cuentas_nuevas != plan.cuentas_nuevas:
                raise ConjuntoCambiado()

            estado = self._estado_transferencia(sesion, datos)
            idempotente = self._identidad(sesion, contexto, motivo, estado, datos)
            if idempotente is not None:
                return idempotente
            self._elegibilidad_transferencia(sesion, datos, estado)

            filas = 0
            hecho = estado["hecho"]
            cambios_hecho: dict[str, Any] = {}
            if datos.importe is not None and hecho["importe_total"] is not None:
                cambios_hecho["importe_total"] = _q(datos.importe)
            if datos.fecha is not None:
                cambios_hecho["fecha_hecho"] = datos.fecha
            version_hecho = self._escribir_hecho(sesion, datos.hecho_id, hecho["row_version"], cambios_hecho, motivo)
            filas += 1
            self._exigir_vinculos(sesion, datos.hecho_id, vinculos)

            versiones: dict[uuid.UUID, int] = {}
            for pata, signo, cuenta_nueva in (("salida", -1, datos.cuenta_origen_id),
                                              ("entrada", 1, datos.cuenta_destino_id)):
                movimiento = estado[pata]
                cambios_mov: dict[str, Any] = {}
                if datos.importe is not None:
                    cambios_mov["importe"] = signo * _q(datos.importe)
                if datos.fecha is not None:
                    cambios_mov["fecha_movimiento"] = datos.fecha
                if cuenta_nueva is not None and cuenta_nueva != movimiento["cuenta_id"]:
                    cambios_mov["cuenta_id"] = cuenta_nueva
                if not cambios_mov:  # pata sin cambios (solo cambia la cuenta de la otra): no muta
                    versiones[movimiento["id"]] = movimiento["row_version"]
                    continue
                versiones[movimiento["id"]] = self._escribir_movimiento(
                    sesion, movimiento["id"], movimiento["row_version"], cambios_mov, motivo)
                filas += 1
                if datos.importe is not None:
                    filas += self._escribir_conciliacion(sesion, estado["conciliaciones"][pata]["id"],
                                                         datos.hecho_id, signo * _q(datos.importe), motivo)
            filas += self._escribir_vinculos(sesion, vinculos, motivo)
            integridad_posicion.validar(sesion, fotos)
            return self._resultado(sesion, datos.hecho_id, version_hecho, versiones, filas,
                                   propaga=datos.fecha is not None)

        return self._ejecutar(contexto, operacion, "OP-21T corregir_transferencia")

    # ==================================================================
    # Adquisicion (§6.1)
    # ==================================================================
    def _adquirir(self, sesion: SesionMotor, owner: uuid.UUID, hecho_id: uuid.UUID, *, advisory: bool,
                  cuentas: Mapping[uuid.UUID, str], vinculos: tuple[DatosVinculoACorregir, ...],
                  propaga: bool, movimientos: Mapping[uuid.UUID, uuid.UUID]):
        # 2. Advisory antes de cualquier fila (D-080, D-158).
        if advisory:
            repo_corr.tomar_advisory_inversiones(sesion, owner)
        # 2 bis. Cuentas NUEVAS, conjunto completo y por UUID (§6.7.1).
        repo.bloquear_cuentas(sesion, cuentas)
        # 3-4. Hecho y posiciones que alimenta (sin advisory: ya tomado).
        posiciones = integridad_posicion.adquirir_raiz(sesion, owner, hechos=[hecho_id])
        fotos = integridad_posicion.fotografiar(sesion, posiciones, hechos=[hecho_id])
        # 5. Reglas FU y previsiones por UUID: las de los vinculos a corregir y
        #    las que la propagacion de fecha bloqueara (antes que los movimientos).
        previos = {v.vinculo_id: repo_prev.leer_vinculo(sesion, v.vinculo_id) for v in vinculos}
        previsiones = {v["prevision_id"] for v in previos.values() if v is not None}
        reglas: set[uuid.UUID] = set()
        sucesores: list[uuid.UUID] = []
        if propaga:
            reglas_impacto, sucesores = self._conjunto_impacto(sesion, hecho_id)
            reglas.update(reglas_impacto)
        for prevision_id in previsiones:
            prevision = repo_prev.leer_prevision(sesion, prevision_id)
            if prevision is not None and prevision.get("regla_id") is not None:
                reglas.add(prevision["regla_id"])
        for regla_id in sorted(reglas, key=str):
            repo_reglas.bloquear_regla(sesion, regla_id)
        bloqueadas: dict[uuid.UUID, int | None] = {}
        for prevision_id in sorted(previsiones | set(sucesores), key=str):
            bloqueadas[prevision_id] = repo_prev.bloquear_prevision(sesion, prevision_id)
        # 6. Movimientos por UUID.
        repo.bloquear_movimientos(sesion, movimientos)
        # Relectura de los vinculos bajo los locks.
        for vinculo in vinculos:
            if repo_prev.leer_vinculo(sesion, vinculo.vinculo_id) != previos[vinculo.vinculo_id]:
                raise ConjuntoCambiado()
        return fotos, [(v, previos[v.vinculo_id], bloqueadas) for v in vinculos]

    # ==================================================================
    # Estado bajo la raiz
    # ==================================================================
    def _estado_comun(self, sesion: SesionMotor, hecho_id: uuid.UUID) -> dict[str, Any]:
        hecho = repo.leer_hecho(sesion, hecho_id)
        if hecho is None:
            raise ErrorMotor(CodigoError.AGREGADO_NO_ENCONTRADO, "El hecho indicado no existe o no es accesible.")
        return {
            "hecho": hecho,
            "efectos": repo.efectos(sesion, hecho_id),
            "conciliaciones_lista": repo.conciliaciones(sesion, hecho_id),
            "aportaciones": repo.aportaciones(sesion, hecho_id),
            "vinculos": repo_prev.vinculos_de_hecho(sesion, hecho_id),
        }

    def _estado_pago(self, sesion: SesionMotor, datos: DatosCorreccionPago) -> dict[str, Any]:
        estado = self._estado_comun(sesion, datos.hecho_id)
        lista = estado["conciliaciones_lista"]
        estado["conciliacion"] = lista[0] if len(lista) == 1 else None
        estado["movimiento"] = (
            repo.leer_movimiento(sesion, lista[0]["movimiento_id"]) if len(lista) == 1 else None
        )
        estado["efecto"] = estado["efectos"][0] if len(estado["efectos"]) == 1 else None
        estado["atribuciones"] = (
            repo.atribuciones(sesion, estado["efecto"]["id"]) if estado["efecto"] is not None else []
        )
        estado["movimientos"] = [estado["movimiento"]] if estado["movimiento"] is not None else []
        return estado

    def _estado_transferencia(self, sesion: SesionMotor, datos: DatosCorreccionTransferencia) -> dict[str, Any]:
        estado = self._estado_comun(sesion, datos.hecho_id)
        patas = _patas_previas(sesion, datos.hecho_id)
        estado["salida"], estado["entrada"] = patas if patas is not None else (None, None)
        estado["movimientos"] = [m for m in (estado["salida"], estado["entrada"]) if m is not None]
        por_movimiento = {c["movimiento_id"]: c for c in estado["conciliaciones_lista"]}
        estado["conciliaciones"] = {
            pata: por_movimiento.get(estado[pata]["id"]) if estado[pata] is not None else None
            for pata in ("salida", "entrada")
        }
        return estado

    # ==================================================================
    # Elegibilidad
    # ==================================================================
    @staticmethod
    def _hecho_activo(hecho: dict[str, Any]) -> None:
        if hecho["estado"] != ESTADO_ACTIVO:
            raise _estado("HECHO_ANULADO", "Un hecho anulado no se corrige.")

    def _evidencia_persistida(self, sesion: SesionMotor, hecho_id: uuid.UUID,
                              movimientos: list[dict[str, Any]]) -> None:
        """§2.5: la evidencia persistida prevalece sobre la declaracion."""
        destinos = [(repo.TABLA_HECHOS, hecho_id)] + [(repo.TABLA_MOVIMIENTOS, m["id"]) for m in movimientos]
        if repo.importado(sesion, destinos):
            raise _estado("ORIGEN_IMPORTADO", "Un registro importado no se corrige por esta via.")
        if any(m["clase"] == CLASE_AJUSTE for m in movimientos):
            raise _fuera("TIPO_NO_SOPORTADO")

    @staticmethod
    def _cobertura(conciliacion: dict[str, Any], movimiento: dict[str, Any], total: Any) -> None:
        asignado = abs(D(conciliacion["importe"]))
        if asignado != abs(D(movimiento["importe"])) or (total is not None and asignado != abs(D(total))):
            raise _fuera("CONCILIACION_PARCIAL")

    def _sin_compartir_ni_revertir(self, sesion: SesionMotor, hecho_id: uuid.UUID, movimiento: dict[str, Any],
                                   *, cambia_importe: bool, cambia_fecha: bool, cambia_cuenta: bool) -> None:
        if repo.hechos_conciliados(sesion, movimiento["id"]) != [hecho_id]:
            raise _fuera("MOVIMIENTO_COMPARTIDO")
        tiene_reversion = movimiento["reversiones"] > 0 or movimiento["reversion_de"] is not None
        # PRE M1 (fecha e importe: solo el motor lo impide) y PRE M2 (cuenta: la
        # BD responderia 23503): el motor se adelanta en las tres dimensiones.
        if tiene_reversion and (cambia_importe or cambia_fecha or cambia_cuenta):
            raise _estado("REVERSION_EXISTENTE", "El movimiento tiene reversiones: lo ocurrido despues se "
                          "registra con su operacion, no corrigiendo el original.")

    def _cuenta_nueva(self, sesion: SesionMotor, cuenta_id: uuid.UUID, moneda: str, fecha: dt.date) -> dict:
        """§2.1.5 en el motor, bajo el lock de la cuenta (nivel 2 bis)."""
        cuenta = repo.leer_cuenta(sesion, cuenta_id)
        if cuenta is None:
            raise ErrorMotor(CodigoError.CUENTA_DESCONOCIDA, "La cuenta indicada no existe o no es accesible.")
        if cuenta["moneda"] != moneda:
            raise ErrorMotor(CodigoError.MONEDA_INVALIDA, "La cuenta nueva debe estar en la moneda del hecho.")
        if not cuenta["enabled"]:
            raise _estado("CUENTA_DESACTIVADA", "No se puede mover un movimiento a una cuenta deshabilitada.")
        if cuenta["fecha_cierre"] is not None and cuenta["fecha_cierre"] < fecha:
            raise _estado("CUENTA_DESACTIVADA", "La cuenta nueva estaba cerrada en la fecha del movimiento.")
        return cuenta

    def _limites(self, sesion: SesionMotor, hecho: dict[str, Any], movimientos: list[dict[str, Any]],
                 fecha_nueva: dt.date | None, cuentas_finales: dict[uuid.UUID, uuid.UUID]) -> None:
        """§5.1 periodo cerrado (fechas anteriores y nuevas) y §5.2 ledger."""
        fechas = {hecho["fecha"]} | {m["fecha"] for m in movimientos}
        if fecha_nueva is not None:
            fechas.add(fecha_nueva)
        if repo.periodo_cerrado(sesion, fechas):
            raise ErrorMotor(CodigoError.PERIODO_CERRADO_SIN_POLITICA,
                             "La correccion atraviesa un periodo cerrado y no hay politica que lo permita.")
        for movimiento in movimientos:
            cuenta_final = cuentas_finales[movimiento["id"]]
            fecha_final = fecha_nueva or movimiento["fecha"]
            if fecha_nueva is None and cuenta_final == movimiento["cuenta_id"]:
                continue  # ni fecha ni cuenta cambian: un movimiento ya anterior se respeta
            cuenta = repo.leer_cuenta(sesion, cuenta_final)
            if cuenta is not None and cuenta["inicio_ledger"] is not None and fecha_final < cuenta["inicio_ledger"]:
                # §9 nombra FECHA_ANTERIOR_INICIO como codigo, pero en el catalogo solo existe como
                # motivo de INTEGRIDAD_POSICION_VIOLADA: sin codigos nuevos, va como motivo (§9 lo admite).
                raise _estado("FECHA_ANTERIOR_INICIO",
                              "La fecha del movimiento quedaria antes del inicio del ledger de su cuenta.")

    def _elegibilidad_pago(self, sesion: SesionMotor, datos: DatosCorreccionPago, estado: dict[str, Any]) -> None:
        hecho = estado["hecho"]
        self._hecho_activo(hecho)
        if hecho["tipo"] != TIPO_GASTO:
            raise _fuera("TIPO_NO_SOPORTADO")
        if repo.es_origen_de_devolucion(sesion, datos.hecho_id):
            raise _fuera("DEVOLUCION")  # §2.4: corregir no; anular si (R2-C)
        if repo.tiene_entidad_de_inversion(sesion, datos.hecho_id):
            raise _fuera("INVERSION")
        efecto = estado["efecto"]
        if efecto is None or efecto["tipo_efecto"] != TIPO_GASTO or D(efecto["importe_delta"]) <= 0:
            raise _fuera("TIPO_NO_SOPORTADO")
        lista = estado["conciliaciones_lista"]
        if not lista:
            raise _fuera("SIN_TESORERIA")
        if len(lista) > 1:
            raise _fuera("VARIOS_MOVIMIENTOS")
        movimiento = estado["movimiento"]
        if movimiento is None or movimiento["estado"] != ESTADO_ACTIVO:
            raise ErrorMotor(CodigoError.MOVIMIENTO_ANULADO, "El movimiento del pago no esta activo.")
        if D(movimiento["importe"]) >= 0:
            raise _fuera("TIPO_NO_SOPORTADO")
        self._evidencia_persistida(sesion, datos.hecho_id, [movimiento])
        if movimiento["transferencia_id"] is not None:
            raise _fuera("TIPO_NO_SOPORTADO")
        cambia_cuenta = datos.cuenta_id is not None and datos.cuenta_id != movimiento["cuenta_id"]
        self._sin_compartir_ni_revertir(sesion, datos.hecho_id, movimiento, cambia_importe=datos.importe is not None,
                                        cambia_fecha=datos.fecha is not None, cambia_cuenta=cambia_cuenta)
        self._cobertura(estado["conciliacion"], movimiento, hecho["importe_total"])
        if hecho["importe_total"] is None:
            raise _fuera("CONCILIACION_PARCIAL")
        cuenta_actual = repo.leer_cuenta(sesion, movimiento["cuenta_id"])
        if cuenta_actual is None or cuenta_actual["moneda"] != hecho["moneda"]:
            raise _fuera("MULTIDIVISA")
        if hecho["row_version"] != datos.row_version_esperada:
            raise _desfasada("El hecho")
        if movimiento["row_version"] != datos.movimiento_row_version_esperada:
            raise _desfasada("El movimiento")
        fecha_final = datos.fecha or movimiento["fecha"]
        if cambia_cuenta:
            self._cuenta_nueva(sesion, datos.cuenta_id, hecho["moneda"], fecha_final)
        self._limites(sesion, hecho, [movimiento], datos.fecha,
                      {movimiento["id"]: datos.cuenta_id if cambia_cuenta else movimiento["cuenta_id"]})

    def _elegibilidad_transferencia(self, sesion: SesionMotor, datos: DatosCorreccionTransferencia,
                                    estado: dict[str, Any]) -> None:
        hecho = estado["hecho"]
        self._hecho_activo(hecho)
        salida, entrada = estado["salida"], estado["entrada"]
        if hecho["tipo"] != TIPO_TRANSFERENCIA or salida is None or entrada is None:
            raise _fuera("TIPO_NO_SOPORTADO")
        if estado["efectos"]:
            raise _fuera("TIPO_NO_SOPORTADO")
        lista = estado["conciliaciones_lista"]
        conciliaciones = estado["conciliaciones"]
        if len(lista) != 2 or conciliaciones["salida"] is None or conciliaciones["entrada"] is None:
            raise _fuera("VARIOS_MOVIMIENTOS")
        for movimiento in (salida, entrada):
            if movimiento["estado"] != ESTADO_ACTIVO:
                raise ErrorMotor(CodigoError.MOVIMIENTO_ANULADO, "Una pata de la transferencia no esta activa.")
        self._evidencia_persistida(sesion, datos.hecho_id, [salida, entrada])
        cambia = {
            "salida": datos.cuenta_origen_id is not None and datos.cuenta_origen_id != salida["cuenta_id"],
            "entrada": datos.cuenta_destino_id is not None and datos.cuenta_destino_id != entrada["cuenta_id"],
        }
        for pata, movimiento in (("salida", salida), ("entrada", entrada)):
            self._sin_compartir_ni_revertir(sesion, datos.hecho_id, movimiento,
                                            cambia_importe=datos.importe is not None,
                                            cambia_fecha=datos.fecha is not None, cambia_cuenta=cambia[pata])
            self._cobertura(conciliaciones[pata], movimiento, hecho["importe_total"])
        finales = {
            salida["id"]: datos.cuenta_origen_id if cambia["salida"] else salida["cuenta_id"],
            entrada["id"]: datos.cuenta_destino_id if cambia["entrada"] else entrada["cuenta_id"],
        }
        if finales[salida["id"]] == finales[entrada["id"]]:
            raise ErrorMotor(CodigoError.MISMA_CUENTA, "Origen y destino deben ser cuentas distintas.")
        for movimiento in (salida, entrada):
            cuenta_actual = repo.leer_cuenta(sesion, movimiento["cuenta_id"])
            if cuenta_actual is None or cuenta_actual["moneda"] != hecho["moneda"]:
                raise _fuera("MULTIDIVISA")
        if hecho["row_version"] != datos.row_version_esperada:
            raise _desfasada("El hecho")
        for movimiento in (salida, entrada):
            if datos.movimientos_row_version_esperadas.get(movimiento["id"]) != movimiento["row_version"]:
                raise _desfasada("Una pata de la transferencia")
        for pata, movimiento in (("salida", salida), ("entrada", entrada)):
            if cambia[pata]:
                self._cuenta_nueva(sesion, finales[movimiento["id"]], hecho["moneda"],
                                   datos.fecha or movimiento["fecha"])
        self._limites(sesion, hecho, [salida, entrada], datos.fecha, finales)

    # ==================================================================
    # Composicion del estado final (antes de escribir nada)
    # ==================================================================
    def _componer_pago(self, sesion: SesionMotor, datos: DatosCorreccionPago,
                       estado: dict[str, Any]) -> dict[str, dict[uuid.UUID, decimal.Decimal]]:
        cambia_importe = datos.importe is not None
        cambia_cuenta = datos.cuenta_id is not None and datos.cuenta_id != estado["movimiento"]["cuenta_id"]
        return {
            "atribuciones": self._atribuciones_finales(datos, estado, cambia_importe),
            "aportaciones": self._aportaciones_finales(datos, estado, cambia_importe, cambia_cuenta),
        }

    @staticmethod
    def _atribuciones_finales(datos: DatosCorreccionPago, estado: dict[str, Any],
                              cambia_importe: bool) -> dict[uuid.UUID, decimal.Decimal]:
        """§2.1.4: un actor al 100 % se reescala; NO_DISPONIBLE no cambia; otro
        reparto exige `atribuciones_nuevas` sobre TODAS sus filas."""
        filas = estado["atribuciones"]
        explicitas = dict(datos.atribuciones_nuevas)
        if not cambia_importe:
            if explicitas:
                raise ErrorMotor(CodigoError.ENTRADA_INVALIDA,
                                 "Sin cambio de importe no hay reparto que decidir: el reparto se corrige con OP-21.")
            return {}
        if estado["efecto"]["estado_atribucion"] == SIN_ATRIBUCION and not filas:
            if explicitas:
                raise ErrorMotor(CodigoError.ENTRADA_INVALIDA, "El efecto no tiene reparto que corregir.")
            return {}
        if explicitas:
            if set(explicitas) != {f["id"] for f in filas}:
                raise ErrorMotor(CodigoError.ENTRADA_INVALIDA,
                                 "`atribuciones_nuevas` debe cubrir exactamente las atribuciones del efecto.")
            return {k: _q(v) for k, v in explicitas.items()}
        delta = D(estado["efecto"]["importe_delta"])
        if len(filas) == 1 and D(filas[0]["importe"]) == delta:
            return {filas[0]["id"]: _q(datos.importe)}
        raise _decision("REPARTO_REQUIERE_DECISION")

    @staticmethod
    def _aportaciones_finales(datos: DatosCorreccionPago, estado: dict[str, Any], cambia_importe: bool,
                              cambia_cuenta: bool) -> dict[uuid.UUID, decimal.Decimal]:
        """§2.1.4: PARTICIPACION_CUENTA con porcentaje congelado -> X' x p / 100
        a 4 decimales, residual en la de mayor porcentaje (a igualdad, menor
        id); otro criterio, o cambio de cuenta con PARTICIPACION_CUENTA ->
        `aportaciones_nuevas`; una aportacion no vinculada -> rechazo."""
        conciliacion_id = estado["conciliacion"]["id"]
        todas = estado["aportaciones"]
        vinculadas = [a for a in todas if a["conciliacion_id"] == conciliacion_id]
        explicitas = dict(datos.aportaciones_nuevas)
        if not (cambia_importe or cambia_cuenta):
            if explicitas:
                raise ErrorMotor(CodigoError.ENTRADA_INVALIDA, "Esta correccion no cambia las aportaciones.")
            return {}
        if len(vinculadas) != len(todas):
            raise _decision("APORTACION_NO_VINCULADA")
        if not vinculadas:
            if explicitas:
                raise ErrorMotor(CodigoError.ENTRADA_INVALIDA, "El pago no tiene aportaciones.")
            return {}
        if explicitas:
            if set(explicitas) != {a["id"] for a in vinculadas}:
                raise ErrorMotor(CodigoError.ENTRADA_INVALIDA,
                                 "`aportaciones_nuevas` debe cubrir exactamente las aportaciones del pago.")
            if any(D(v) <= 0 for v in explicitas.values()):
                raise ErrorMotor(CodigoError.IMPORTE_NO_POSITIVO, "Una aportacion debe ser mayor que cero.")
            return {k: _q(v) for k, v in explicitas.items()}
        if cambia_cuenta and any(a["criterio"] == PARTICIPACION_CUENTA for a in vinculadas):
            raise _decision("APORTACION_REQUIERE_DECISION")
        if not cambia_importe:
            return {}
        if any(a["criterio"] != PARTICIPACION_CUENTA or a["porcentaje"] is None for a in vinculadas):
            raise _decision("APORTACION_REQUIERE_DECISION")
        importe = _q(datos.importe)
        finales = {a["id"]: (importe * D(a["porcentaje"]) / CIEN).quantize(CUATRO) for a in vinculadas}
        objetivo = (importe * sum((D(a["porcentaje"]) for a in vinculadas), D(0)) / CIEN).quantize(CUATRO)
        residual = objetivo - sum(finales.values(), D(0))
        if residual:
            mayor = sorted(vinculadas, key=lambda a: (-D(a["porcentaje"]), str(a["id"])))[0]
            finales[mayor["id"]] += residual
        if any(v <= 0 for v in finales.values()):
            raise _decision("APORTACION_REQUIERE_DECISION")
        return finales

    # ==================================================================
    # Escrituras (una por fila) y auditoria
    # ==================================================================
    @staticmethod
    def _escribir_hecho(sesion: SesionMotor, hecho_id: uuid.UUID, version: int, cambios: dict[str, Any],
                        motivo: str) -> int:
        resultado = repo.actualizar_hecho(sesion, hecho_id, version, cambios)
        if resultado is None:
            raise _desfasada("El hecho")
        auditoria.registrar(sesion, tabla=repo.TABLA_HECHOS, registro_id=hecho_id,
                            accion=auditoria.ACCION_ACTUALIZAR, datos_antes_json=resultado[1],
                            datos_despues_json=resultado[2], motivo=motivo)
        return resultado[0]

    @staticmethod
    def _escribir_movimiento(sesion: SesionMotor, movimiento_id: uuid.UUID, version: int,
                             cambios: dict[str, Any], motivo: str) -> int:
        resultado = repo.actualizar_movimiento(sesion, movimiento_id, version, cambios)
        if resultado is None:
            raise _desfasada("El movimiento")
        auditoria.registrar(sesion, tabla=repo.TABLA_MOVIMIENTOS, registro_id=movimiento_id,
                            accion=auditoria.ACCION_ACTUALIZAR, datos_antes_json=resultado[1],
                            datos_despues_json=resultado[2], motivo=motivo)
        return resultado[0]

    @staticmethod
    def _escribir_conciliacion(sesion: SesionMotor, conciliacion_id: uuid.UUID, hecho_id: uuid.UUID,
                               importe: decimal.Decimal, motivo: str) -> int:
        par = repo.actualizar_conciliacion(sesion, conciliacion_id, hecho_id, importe)
        if par is None:  # pragma: no cover - leida bajo la raiz
            raise ErrorMotor(CodigoError.CONCILIACION_DE_OTRO_HECHO, "La conciliacion ya no es de este hecho.")
        auditoria.registrar(sesion, tabla=repo.TABLA_CONCILIACIONES, registro_id=conciliacion_id,
                            accion=auditoria.ACCION_ACTUALIZAR, datos_antes_json=par[0],
                            datos_despues_json=par[1], motivo=motivo)
        return 1

    @staticmethod
    def _escribir_atribuciones(sesion: SesionMotor, finales: dict[uuid.UUID, decimal.Decimal], motivo: str) -> int:
        total = 0
        for atribucion_id, importe in sorted(finales.items(), key=lambda p: str(p[0])):
            par = repo_corr.actualizar_atribucion(sesion, atribucion_id, {"importe_atribuido": importe})
            if par is None:  # pragma: no cover - leida bajo la raiz
                raise ErrorMotor(CodigoError.AGREGADO_NO_ENCONTRADO, "La atribucion ya no existe.")
            auditoria.registrar(sesion, tabla=TABLA_ATRIBUCIONES, registro_id=atribucion_id,
                                accion=auditoria.ACCION_ACTUALIZAR, datos_antes_json=par[0],
                                datos_despues_json=par[1], motivo=motivo)
            total += 1
        return total

    @staticmethod
    def _escribir_aportaciones(sesion: SesionMotor, hecho_id: uuid.UUID,
                               finales: dict[uuid.UUID, decimal.Decimal], motivo: str) -> int:
        total = 0
        for aportacion_id, importe in sorted(finales.items(), key=lambda p: str(p[0])):
            par = repo.actualizar_aportacion(sesion, aportacion_id, hecho_id, importe)
            if par is None:  # pragma: no cover - leida bajo la raiz
                raise ErrorMotor(CodigoError.CONCILIACION_DE_OTRO_HECHO, "La aportacion ya no es de este hecho.")
            auditoria.registrar(sesion, tabla=repo.TABLA_APORTACIONES, registro_id=aportacion_id,
                                accion=auditoria.ACCION_ACTUALIZAR, datos_antes_json=par[0],
                                datos_despues_json=par[1], motivo=motivo)
            total += 1
        return total

    @staticmethod
    def _exigir_vinculos(sesion: SesionMotor, hecho_id: uuid.UUID, vinculos: list) -> None:
        """§4.1: identidad y version de cada vinculo pedido (bajo los locks) y
        G-R1-C sobre el estado final; nunca toca vinculos no enumerados."""
        if not vinculos:
            return
        cambios: dict[uuid.UUID, tuple[Any, str]] = {}
        for pedido, previo, bloqueadas in vinculos:
            if previo is None or previo["hecho_id"] != hecho_id:
                raise ErrorMotor(CodigoError.AGREGADO_NO_ENCONTRADO,
                                 "El vinculo indicado no es de este hecho o no es accesible.")
            if previo["prevision_id"] != pedido.prevision_id_esperada:
                raise _desfasada("La previsión del vinculo")
            if bloqueadas.get(previo["prevision_id"]) != pedido.prevision_row_version_esperada:
                raise _desfasada("La previsión")
            if D(pedido.importe_asignado) <= 0:
                raise ErrorMotor(CodigoError.IMPORTE_NO_POSITIVO, "importe_asignado debe ser mayor que cero.")
            moneda = repo_prev.leer_prevision(sesion, previo["prevision_id"])["moneda"]
            cambios[pedido.vinculo_id] = (_q(pedido.importe_asignado), moneda)
        primero = next(iter(cambios.values()))
        exigir_porcion(sesion, hecho_id, cambios, solicitado=primero)

    @staticmethod
    def _escribir_vinculos(sesion: SesionMotor, vinculos: list, motivo: str) -> int:
        total = 0
        tocadas: set[uuid.UUID] = set()
        for pedido, previo, _ in sorted(vinculos, key=lambda v: str(v[0].vinculo_id)):
            prevision_id = previo["prevision_id"]
            if prevision_id not in tocadas:
                if repo_prev.tocar_prevision(sesion, prevision_id, pedido.prevision_row_version_esperada) is None:
                    raise _desfasada("La previsión")
                tocadas.add(prevision_id)
            par = repo_prev.actualizar_vinculo(sesion, pedido.vinculo_id,
                                               {"importe_asignado": _q(pedido.importe_asignado)})
            if par is None:  # pragma: no cover - releido bajo los locks
                raise ErrorMotor(CodigoError.AGREGADO_NO_ENCONTRADO, "El vinculo ya no existe.")
            auditoria.registrar(sesion, tabla=TABLA_VINCULOS, registro_id=pedido.vinculo_id,
                                accion=auditoria.ACCION_ACTUALIZAR, datos_antes_json=par[0],
                                datos_despues_json=par[1], motivo=motivo)
            total += 1
        return total

    @staticmethod
    def _validar_atribuciones(sesion: SesionMotor, hecho_id: uuid.UUID, efecto_id: uuid.UUID) -> None:
        """INV-01 sobre el estado final del efecto tocado (mismo validador que OP-21)."""
        for _, delta, estado, filas, suma in repo_corr.estado_de_efectos(sesion, hecho_id, [efecto_id]):
            EfectosService._validar_coherencia(estado=estado, filas=int(filas), suma=D(suma), delta=D(delta))

    # ==================================================================
    # Idempotencia e identidad (§6.4)
    # ==================================================================
    def _identidad(self, sesion: SesionMotor, contexto: ContextoOperacion, motivo: str,
                   estado: dict[str, Any], datos: Any) -> ResultadoCorreccionTesoreria | None:
        auditadas = [a for a in repo.auditorias_de_peticion(sesion, contexto.request_id)
                     if a["tabla"] != repo_prev.TABLA_PREVISIONES]
        if not auditadas:
            return None
        if self._misma_intencion(auditadas, motivo, estado, datos):
            versiones = {m["id"]: m["row_version"] for m in estado["movimientos"]}
            return ResultadoCorreccionTesoreria(
                hecho_id=datos.hecho_id, hecho_row_version=estado["hecho"]["row_version"],
                movimientos=versiones, idempotente=True)
        raise ErrorMotor(CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                         "Ese request_id ya se uso con otra intencion: no se repite ni se completa.")

    @staticmethod
    def _misma_intencion(auditadas: list[dict[str, Any]], motivo: str, estado: dict[str, Any], datos: Any) -> bool:
        movimientos = {m["id"]: m for m in estado["movimientos"]}
        propias = {
            repo.TABLA_HECHOS: {datos.hecho_id},
            repo.TABLA_MOVIMIENTOS: set(movimientos),
            repo.TABLA_CONCILIACIONES: {c["id"] for c in estado["conciliaciones_lista"]},
            repo.TABLA_APORTACIONES: {a["id"] for a in estado["aportaciones"]},
            repo_corr.TABLA_EFECTOS: {e["id"] for e in estado["efectos"]},
            TABLA_ATRIBUCIONES: {a["id"] for a in estado.get("atribuciones", [])},
            TABLA_VINCULOS: {v["id"] for v in estado["vinculos"]},
        }
        for fila in auditadas:
            if fila["registro_id"] not in propias.get(fila["tabla"], set()) or fila["motivo"] != motivo:
                return False
            if fila["accion"] != auditoria.ACCION_ACTUALIZAR:
                return False
        hechos = [f for f in auditadas if f["tabla"] == repo.TABLA_HECHOS]
        if len(hechos) != 1:
            return False

        def coincide(fila: dict[str, Any], campo: str, pedido: Any, conv: Callable[[Any], Any]) -> bool:
            antes, despues = fila["antes"].get(campo), fila["despues"].get(campo)
            if pedido is None:
                return antes == despues
            return despues is not None and conv(despues) == conv(pedido)

        def importe(v: Any) -> decimal.Decimal:
            return _q(v)

        def fecha(v: Any) -> str:
            return v if isinstance(v, str) else v.isoformat()

        def ident(v: Any) -> str:
            return str(v)

        if not coincide(hechos[0], "fecha_hecho", datos.fecha, fecha):
            return False
        if estado["hecho"]["importe_total"] is not None and not coincide(
                hechos[0], "importe_total", datos.importe, importe):
            return False
        filas_mov = {f["registro_id"]: f for f in auditadas if f["tabla"] == repo.TABLA_MOVIMIENTOS}
        if set(filas_mov) != set(movimientos):
            return False
        if isinstance(datos, DatosCorreccionPago):
            pedidos = {next(iter(movimientos)): (datos.importe, -1, datos.cuenta_id)} if movimientos else {}
        else:
            pedidos = {estado["salida"]["id"]: (datos.importe, -1, datos.cuenta_origen_id),
                       estado["entrada"]["id"]: (datos.importe, 1, datos.cuenta_destino_id)}
        for movimiento_id, (pedido_importe, signo, cuenta) in pedidos.items():
            fila = filas_mov[movimiento_id]
            if not coincide(fila, "importe", None if pedido_importe is None else signo * _q(pedido_importe), importe):
                return False
            if not coincide(fila, "fecha_movimiento", datos.fecha, fecha):
                return False
            if cuenta is not None and ident(fila["despues"].get("cuenta_id")) != ident(cuenta):
                return False
            if cuenta is None and fila["antes"].get("cuenta_id") != fila["despues"].get("cuenta_id"):
                return False
        explicitas = {TABLA_VINCULOS: {v.vinculo_id: v.importe_asignado for v in datos.vinculos_a_corregir}}
        if isinstance(datos, DatosCorreccionPago):
            explicitas[TABLA_ATRIBUCIONES] = dict(datos.atribuciones_nuevas)
            explicitas[repo.TABLA_APORTACIONES] = dict(datos.aportaciones_nuevas)
        campos = {TABLA_VINCULOS: "importe_asignado", TABLA_ATRIBUCIONES: "importe_atribuido",
                  repo.TABLA_APORTACIONES: "importe"}
        for tabla, valores in explicitas.items():
            filas = {f["registro_id"]: f for f in auditadas if f["tabla"] == tabla}
            for registro_id, valor in valores.items():
                fila = filas.get(registro_id)
                if fila is None or _q(fila["despues"].get(campos[tabla])) != _q(valor):
                    return False
            if tabla == TABLA_VINCULOS and set(filas) != set(valores):
                return False
        return True

    # ==================================================================
    # Resultado: R1-OBS-01 (§4.1) y propagacion de fecha (F04-D022)
    # ==================================================================
    def _resultado(self, sesion: SesionMotor, hecho_id: uuid.UUID, version: int, versiones: dict[uuid.UUID, int],
                   filas: int, *, propaga: bool) -> ResultadoCorreccionTesoreria:
        impacto = {"requiere_revision": False, "motivo": None, "afectadas": [], "propagadas": []}
        if propaga:
            impacto = self._impacto_ancla(sesion, hecho_id)
        porcion = repo_prev.porcion_de_hecho(sesion, hecho_id)
        vinculos = repo_prev.vinculos_de_hecho(sesion, hecho_id)
        excedida: list[uuid.UUID] = []
        if porcion is not None and porcion[0] is not None and vinculos and all(
                v["moneda"] == porcion[1] for v in vinculos):
            if sum((D(v["importe"]) for v in vinculos), D(0)) > D(porcion[0]):
                excedida = sorted({v["prevision_id"] for v in vinculos}, key=str)
        afectadas = tuple(sorted(set(excedida) | set(impacto["afectadas"]), key=str))
        return ResultadoCorreccionTesoreria(
            hecho_id=hecho_id, hecho_row_version=version, movimientos=versiones, filas_auditadas=filas,
            requiere_revision=bool(excedida) or bool(impacto["requiere_revision"]),
            motivo_revision="PORCION_EXCEDIDA" if excedida else impacto["motivo"],
            previsiones_afectadas=afectadas, previsiones_propagadas=tuple(impacto["propagadas"]),
        )

    def _ejecutar(self, contexto: ContextoOperacion, operacion: Any, nombre: str) -> ResultadoCorreccionTesoreria:
        resultado = self._unidad.ejecutar_con_traza(contexto, operacion, nombre=nombre)
        self.ultima_traza = resultado.traza
        return resultado.valor
