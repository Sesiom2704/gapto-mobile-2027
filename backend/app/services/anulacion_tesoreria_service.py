# ============================================================
# GAPTO MOBILE 2027
# Fichero: anulacion_tesoreria_service.py
# Ruta: backend/app/services/anulacion_tesoreria_service.py
# Descripcion: F04-R2 R2-C (contrato F04-R2 v0.9 §2.3, §2.3.2 bis, §2.3.5,
#   §2.3.6, §2.4, §2.5, §5, §6, §8.1, §9). OP-03P «anular un registro pagado
#   por duplicado»: el registro (gasto, ingreso, transferencia o devolucion)
#   NUNCA existio y su tesoreria tampoco. El hecho y sus movimientos pasan a
#   ANULADO; se retiran sus aportaciones, conciliaciones y la fila de
#   `transferencias`. Efectos, atribuciones, magnitudes, terceros, etiquetas y
#   relaciones (incluida DEVOLUCION_DE saliente) NO se tocan (I-03P-5).
#
#   QUE NO ES. No anula nada que haya ocurrido: exige la declaracion explicita
#   `movimiento_en_banco = false` (§2.3.3); si es true o falta ->
#   OPERACION_NO_PERMITIDA_EN_ESTADO / MOVIMIENTO_REAL_NO_ANULABLE. No existe
#   «anular el hecho y dejar el movimiento ACTIVO sin conciliar». Un hecho sin
#   tesoreria es OP-03 ordinaria (§2.3.4): aqui se rechaza (SIN_TESORERIA).
#   Toda evidencia persistida de realidad externa (§2.5) prevalece sobre la
#   declaracion. No reutiliza `anular_hecho` (adquiere despues de escribir).
#
#   ELEGIBILIDAD, toda bajo los locks (L-R):
#     A-1 hecho ACTIVO de tipo GASTO, INGRESO o TRANSFERENCIA (una devolucion
#         es elegible; las inversiones se excluyen, §3.3);
#     A-2 sin dependencias entrantes activas (G-R1-A);
#     A-3 cada movimiento ACTIVO, conciliado SOLO con el hecho, sin reversiones
#         de ningun estado, y su unica transferencia es la del propio hecho
#         (una TRANSFERENCIA exige su fila y sus dos patas);
#     A-4 ni el hecho ni sus movimientos importados; nada de AJUSTE_SALDO;
#     A-5 §5: periodo cerrado y fecha anterior al inicio del ledger.
#   Versiones (§6.3): la del hecho y la de CADA movimiento, leidas.
#
#   FASES (§2.3.2 bis; prohibido volver atras en §6.1):
#     L1 conjunto C sin lock (no autoriza nada) -> L3/L4 hecho FNKU y sus
#     posiciones (adquirir_raiz, sin advisory) -> L5 reglas FU y previsiones
#     por UUID (adquirir_impacto_ancla) -> L6 movimientos FNKU por UUID (las
#     dos patas) -> L-R relectura de C; si cambio -> ConjuntoCambiado (40001,
#     reintento COMPLETO). Despues, W1 aportaciones -> W2 conciliaciones -> W3
#     transferencia -> W4 movimientos ANULADO -> W5 hecho ANULADO -> W6
#     propagacion sobre lo ya bloqueado (aplicar_impacto_ancla) -> W7
#     integridad de posiciones (F04-D053) sobre el estado final.
#
#   AUDITORIA (§8.1): una fila por fila mutada, en la misma transaccion; DELETE
#   -> ELIMINAR con foto previa; ANULADO -> ANULAR con fotos antes/despues
#   (row_version incluida); motivo y request_id comunes (REQUEST_ID_AUSENTE si
#   falta). Idempotencia (§6.4): el mismo request_id sobre el hecho que ya anulo
#   -> idempotente; con otra intencion -> IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION.
# Version: 0.1.0 (F04-R2 R2-C)
# ============================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.unidad_trabajo import SesionMotor, Traza, UnidadDeTrabajo
from app.repositories import anulacion_tesoreria_repository as repo
from app.repositories import auditoria_repository as auditoria
from app.repositories import correccion_tesoreria_repository as repo_lect
from app.repositories import hechos_repository as repo_hechos
from app.repositories import posiciones_repository as repo_pos
from app.repositories import previsiones_repository as repo_prev
from app.services import integridad_posicion
from app.services.previsiones_service import ConjuntoCambiado

TIPOS_ANULABLES = ("GASTO", "INGRESO", "TRANSFERENCIA")
TIPO_TRANSFERENCIA = "TRANSFERENCIA"
ESTADO_ACTIVO = "ACTIVO"
ESTADO_ANULADO = "ANULADO"
CLASE_AJUSTE = "AJUSTE_SALDO"


@dataclass(frozen=True, slots=True)
class DatosAnulacionRegistro:
    """Entrada de OP-03P (§2.3). `movimientos_row_version_esperadas`: version
    LEIDA de cada movimiento conciliado con el hecho (las dos patas en una
    transferencia). `movimiento_en_banco`: declaracion explicita del usuario,
    sin valor por defecto (§2.3.3)."""

    hecho_id: uuid.UUID
    row_version_esperada: int
    movimientos_row_version_esperadas: Mapping[uuid.UUID, int]
    motivo: str | None
    movimiento_en_banco: bool | None = None


@dataclass(frozen=True, slots=True)
class ResultadoAnulacionRegistro:
    hecho_id: uuid.UUID
    hecho_row_version: int
    movimientos: dict[uuid.UUID, int]
    idempotente: bool = False
    filas_auditadas: int = 0
    requiere_revision: bool = False
    motivo_revision: str | None = None
    previsiones_afectadas: tuple[uuid.UUID, ...] = ()
    previsiones_propagadas: tuple[uuid.UUID, ...] = ()


# ------------------------------------------------------------------ rechazos
def _fuera(detalle: str) -> ErrorMotor:
    return ErrorMotor(
        CodigoError.CORRECCION_AGREGADA_REQUERIDA,
        "Esta anulacion queda fuera del alcance de v1.",
        contexto_extra={"motivo": "FUERA_DE_ALCANCE_V1", "detalle": detalle},
    )


def _estado(motivo: str, mensaje: str, **extra: Any) -> ErrorMotor:
    return ErrorMotor(CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO, mensaje,
                      contexto_extra={"motivo": motivo, **extra})


def _desfasada(que: str) -> ErrorMotor:
    return ErrorMotor(CodigoError.VERSION_DESFASADA, f"{que} ha cambiado desde la version que conoce el llamante.")


def _validar_entrada(contexto: ContextoOperacion, datos: DatosAnulacionRegistro) -> str:
    """Sin base de datos: request_id, motivo y declaracion (§2.3.3, §8.1, §9)."""
    if getattr(contexto, "request_id", None) is None:
        raise ErrorMotor(CodigoError.ENTRADA_INVALIDA, "La anulacion exige request_id de correlacion.",
                         contexto_extra={"motivo": "REQUEST_ID_AUSENTE"})
    if not (datos.motivo or "").strip():
        raise ErrorMotor(CodigoError.MOTIVO_AUSENTE, "La anulacion de un registro pagado exige motivo explicito.")
    if datos.movimiento_en_banco is not False:
        raise _estado("MOVIMIENTO_REAL_NO_ANULABLE",
                      "Solo se anula si declaras que ningun movimiento existio en el banco; si fue real, "
                      "corrigelo o registra lo que ocurrio.")
    return datos.motivo.strip()


def _exigir_request_id_en_transaccion(sesion: SesionMotor) -> None:
    fila = sesion.uno("SELECT COALESCE(current_setting('gapto.request_id', true), '')")
    if not fila or not fila[0]:
        raise ErrorMotor(CodigoError.ENTRADA_INVALIDA, "La transaccion no tiene request_id de correlacion.",
                         contexto_extra={"motivo": "REQUEST_ID_AUSENTE"})


# ------------------------------------------------------------------ conjunto C (L1 y L-R)
def conjunto(sesion: SesionMotor, hecho_id: uuid.UUID) -> dict[str, Any]:
    """Todo lo que la anulacion puede afectar, SIN lock. En L1 solo fija el
    conjunto que se va a adquirir; en L-R se compara con el releido."""
    conciliaciones = repo_lect.conciliaciones(sesion, hecho_id)
    movimientos = {c["movimiento_id"] for c in conciliaciones}
    transferencias = repo.transferencias_de(sesion, movimientos)
    for t in transferencias:  # las dos patas, aunque solo una este conciliada
        movimientos.update((t["salida"], t["entrada"]))
    return {
        "conciliaciones": tuple((c["id"], c["movimiento_id"]) for c in conciliaciones),
        "aportaciones": tuple(a["id"] for a in repo_lect.aportaciones(sesion, hecho_id)),
        "movimientos": tuple(sorted(movimientos, key=str)),
        "transferencias": tuple((t["id"], t["salida"], t["entrada"]) for t in transferencias),
        "posiciones": tuple(sorted(repo_pos.posiciones_de_hecho(sesion, hecho_id), key=str)),
        "dependencias": tuple(sorted(repo_hechos.dependencias_activas(sesion, hecho_id), key=str)),
    }


class AnulacionTesoreriaService:
    """OP-03P. Colaboradores de previsiones INYECTADOS y obligatorios (como
    OP-03, F04-D022): `adquirir_impacto` (nivel 5, antes de los movimientos) y
    `aplicar_impacto` (W6, sobre lo ya bloqueado)."""

    __slots__ = ("_unidad", "_adquirir_impacto", "_aplicar_impacto", "ultima_traza")

    def __init__(
        self,
        unidad: UnidadDeTrabajo,
        *,
        adquirir_impacto: Callable[[SesionMotor, uuid.UUID], Any],
        aplicar_impacto: Callable[[SesionMotor, Any], dict[str, Any]],
    ) -> None:
        self._unidad = unidad
        self._adquirir_impacto = adquirir_impacto
        self._aplicar_impacto = aplicar_impacto
        self.ultima_traza: Traza | None = None

    def anular_registro(self, contexto: ContextoOperacion, datos: DatosAnulacionRegistro) -> ResultadoAnulacionRegistro:
        motivo = _validar_entrada(contexto, datos)

        def operacion(sesion: SesionMotor) -> ResultadoAnulacionRegistro:
            owner = repo_hechos.exigir_contexto(sesion)
            _exigir_request_id_en_transaccion(sesion)
            hecho_id = datos.hecho_id
            # ---------------------------------------------------------- fase L
            previo = conjunto(sesion, hecho_id)                                   # L1
            posiciones = integridad_posicion.adquirir_raiz(sesion, owner, hechos=[hecho_id])  # L3 + L4
            fotos = integridad_posicion.fotografiar(sesion, posiciones, hechos=[hecho_id])
            plan = self._adquirir_impacto(sesion, hecho_id)                      # L5
            repo_lect.bloquear_movimientos(sesion, previo["movimientos"])        # L6
            if conjunto(sesion, hecho_id) != previo:                             # L-R
                raise ConjuntoCambiado()
            hecho = repo_lect.leer_hecho(sesion, hecho_id)
            if hecho is None:  # pragma: no cover - adquirir_raiz ya falla cerrado
                raise ErrorMotor(CodigoError.AGREGADO_NO_ENCONTRADO, "El hecho indicado no existe o no es accesible.")
            movimientos = [repo_lect.leer_movimiento(sesion, m) for m in previo["movimientos"]]

            idempotente = self._identidad(sesion, contexto, motivo, datos, hecho)
            if idempotente is not None:
                return idempotente
            self._elegibilidad(sesion, datos, hecho, previo, movimientos)

            # ---------------------------------------------------------- fase W
            filas = 0
            for aportacion_id in sorted(previo["aportaciones"], key=str):        # W1
                foto = repo.eliminar_aportacion(sesion, aportacion_id, hecho_id)
                if foto is None:  # pragma: no cover - releida bajo la raiz
                    raise ErrorMotor(CodigoError.CONCILIACION_DE_OTRO_HECHO, "La aportacion ya no es de este hecho.")
                auditoria.registrar(sesion, tabla=repo.TABLA_APORTACIONES, registro_id=aportacion_id,
                                    accion=repo.ACCION_ELIMINAR, datos_antes_json=foto, motivo=motivo)
                filas += 1
            for conciliacion_id, _ in sorted(previo["conciliaciones"], key=lambda c: str(c[0])):  # W2
                foto = repo.eliminar_conciliacion(sesion, conciliacion_id, hecho_id)
                if foto is None:  # pragma: no cover - releida bajo la raiz
                    raise ErrorMotor(CodigoError.CONCILIACION_DE_OTRO_HECHO, "La conciliacion ya no es de este hecho.")
                auditoria.registrar(sesion, tabla=repo.TABLA_CONCILIACIONES, registro_id=conciliacion_id,
                                    accion=repo.ACCION_ELIMINAR, datos_antes_json=foto, motivo=motivo)
                filas += 1
            for transferencia_id, salida, entrada in previo["transferencias"]:   # W3
                foto = repo.eliminar_transferencia(sesion, transferencia_id, salida, entrada)
                if foto is None:  # pragma: no cover - releida bajo los movimientos
                    raise ErrorMotor(CodigoError.AGREGADO_NO_ENCONTRADO, "La transferencia ya no es de este hecho.")
                auditoria.registrar(sesion, tabla=repo.TABLA_TRANSFERENCIAS, registro_id=transferencia_id,
                                    accion=repo.ACCION_ELIMINAR, datos_antes_json=foto, motivo=motivo)
                filas += 1
            versiones: dict[uuid.UUID, int] = {}
            for movimiento in movimientos:                                       # W4 (por UUID)
                resultado = repo.anular_movimiento(sesion, movimiento["id"], movimiento["row_version"], motivo)
                if resultado is None:  # pragma: no cover - version leida bajo el lock
                    raise _desfasada("El movimiento")
                auditoria.registrar(sesion, tabla=repo.TABLA_MOVIMIENTOS, registro_id=movimiento["id"],
                                    accion=auditoria.ACCION_ANULAR, datos_antes_json=resultado[1],
                                    datos_despues_json=resultado[2], motivo=motivo)
                versiones[movimiento["id"]] = resultado[0]
                filas += 1
            # W5: el hecho, con las guardas de OP-03 sobre lo que queda.
            if repo_hechos.tiene_realidad_asociada(sesion, hecho_id):  # I-03P-1
                raise ErrorMotor(CodigoError.HECHO_CON_REALIDAD_ASOCIADA,
                                 "El hecho conserva realidad vinculada: no se anula.")
            resultado = repo.anular_hecho(sesion, hecho_id, hecho["row_version"], motivo)
            if resultado is None:  # pragma: no cover - version leida bajo el lock
                raise _desfasada("El hecho")
            auditoria.registrar(sesion, tabla=repo.TABLA_HECHOS, registro_id=hecho_id,
                                accion=auditoria.ACCION_ANULAR, datos_antes_json=resultado[1],
                                datos_despues_json=resultado[2], motivo=motivo)
            filas += 1
            impacto = self._aplicar_impacto(sesion, plan)                        # W6
            integridad_posicion.validar(sesion, fotos)                           # W7
            return ResultadoAnulacionRegistro(
                hecho_id=hecho_id, hecho_row_version=resultado[0], movimientos=versiones, filas_auditadas=filas,
                requiere_revision=bool(impacto["requiere_revision"]), motivo_revision=impacto["motivo"],
                previsiones_afectadas=tuple(impacto["afectadas"]),
                previsiones_propagadas=tuple(impacto["propagadas"]),
            )

        return self._ejecutar(contexto, operacion, "OP-03P anular_registro")

    # ==================================================================
    # Elegibilidad (bajo los locks)
    # ==================================================================
    def _elegibilidad(self, sesion: SesionMotor, datos: DatosAnulacionRegistro, hecho: dict[str, Any],
                      previo: dict[str, Any], movimientos: list[dict[str, Any] | None]) -> None:
        hecho_id = datos.hecho_id
        # A-1
        if hecho["estado"] != ESTADO_ACTIVO:
            raise _estado("HECHO_ANULADO", "El hecho ya esta anulado.")
        if hecho["tipo"] not in TIPOS_ANULABLES:
            raise _fuera("TIPO_NO_SOPORTADO")
        if repo_lect.tiene_entidad_de_inversion(sesion, hecho_id):
            raise _fuera("INVERSION")
        # A-2 (G-R1-A)
        if previo["dependencias"]:
            raise ErrorMotor(
                CodigoError.HECHO_CON_REALIDAD_ASOCIADA,
                "Otros hechos activos dependen de este hecho: no se puede anular mientras sigan activos.",
                contexto_extra={"motivo": "DEPENDENCIAS_ACTIVAS", "dependientes": [
                    {"hecho_id": str(origen), "tipo_relacion": tipo} for origen, tipo in previo["dependencias"]]},
            )
        if not previo["conciliaciones"]:
            raise _fuera("SIN_TESORERIA")  # §2.3.4: OP-03 ordinaria
        if any(m is None for m in movimientos):  # pragma: no cover - conciliados y bloqueados
            raise ErrorMotor(CodigoError.AGREGADO_NO_ENCONTRADO, "Un movimiento del hecho no es accesible.")
        # A-4 (§2.5): la evidencia persistida prevalece sobre la declaracion.
        destinos = [(repo.TABLA_HECHOS, hecho_id)] + [(repo.TABLA_MOVIMIENTOS, m["id"]) for m in movimientos]
        if repo_lect.importado(sesion, destinos):
            raise _estado("ORIGEN_IMPORTADO", "Un registro importado no se anula por esta via.")
        if any(m["clase"] == CLASE_AJUSTE for m in movimientos):
            raise _fuera("TIPO_NO_SOPORTADO")
        # A-3
        for movimiento in movimientos:
            if movimiento["estado"] != ESTADO_ACTIVO:
                raise ErrorMotor(CodigoError.MOVIMIENTO_ANULADO, "Un movimiento del registro no esta activo.")
            if repo_lect.hechos_conciliados(sesion, movimiento["id"]) != [hecho_id]:
                raise _fuera("MOVIMIENTO_COMPARTIDO")
            if movimiento["reversiones"] > 0 or movimiento["reversion_de"] is not None:
                raise _estado("REVERSION_EXISTENTE", "El movimiento tiene reversiones: lo ocurrido despues se "
                              "registra con su operacion, no anulando el original.")
        transferencias = previo["transferencias"]
        if hecho["tipo"] == TIPO_TRANSFERENCIA:
            # I-03P-3: su fila y sus dos patas, ambas conciliadas con el hecho.
            conciliados = {m for _, m in previo["conciliaciones"]}
            if (len(transferencias) != 1 or len(movimientos) != 2
                    or {transferencias[0][1], transferencias[0][2]} != conciliados):
                raise _fuera("TIPO_NO_SOPORTADO")
        elif transferencias:
            raise _fuera("TIPO_NO_SOPORTADO")  # un gasto o ingreso conciliado con una pata ajena
        # A-5 (§5.1, §5.2)
        fechas = {hecho["fecha"]} | {m["fecha"] for m in movimientos}
        if repo_lect.periodo_cerrado(sesion, fechas):
            raise ErrorMotor(CodigoError.PERIODO_CERRADO_SIN_POLITICA,
                             "La anulacion afecta a un periodo cerrado y no hay politica que lo permita.")
        if any(inicio is not None and fecha < inicio
               for fecha, inicio in repo.fechas_e_inicio_ledger(sesion, [m["id"] for m in movimientos])):
            raise _estado("FECHA_ANTERIOR_INICIO",
                          "Un movimiento es anterior al inicio del ledger de su cuenta: su saldo inicial ya lo incluye.")
        # §6.3: versiones leidas del hecho y de CADA movimiento.
        if hecho["row_version"] != datos.row_version_esperada:
            raise _desfasada("El hecho")
        if dict(datos.movimientos_row_version_esperadas) != {m["id"]: m["row_version"] for m in movimientos}:
            raise _desfasada("Un movimiento del registro")

    # ==================================================================
    # Idempotencia e identidad (§6.4)
    # ==================================================================
    def _identidad(self, sesion: SesionMotor, contexto: ContextoOperacion, motivo: str,
                   datos: DatosAnulacionRegistro, hecho: dict[str, Any]) -> ResultadoAnulacionRegistro | None:
        auditadas = [a for a in repo_lect.auditorias_de_peticion(sesion, contexto.request_id)
                     if a["tabla"] != repo_prev.TABLA_PREVISIONES]
        if not auditadas:
            return None
        if hecho["estado"] == ESTADO_ANULADO and self._misma_intencion(auditadas, motivo, datos):
            movimientos = {a["registro_id"]: int(a["despues"]["row_version"]) for a in auditadas
                           if a["tabla"] == repo.TABLA_MOVIMIENTOS}
            return ResultadoAnulacionRegistro(hecho_id=datos.hecho_id, hecho_row_version=hecho["row_version"],
                                              movimientos=movimientos, idempotente=True)
        raise ErrorMotor(CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                         "Ese request_id ya se uso con otra intencion: no se repite ni se completa.")

    @staticmethod
    def _misma_intencion(auditadas: list[dict[str, Any]], motivo: str, datos: DatosAnulacionRegistro) -> bool:
        """Lo AUDITADO con ese request_id decide, no lo que dice el llamante:
        la anulacion de ESTE hecho, con este motivo y las mismas versiones."""
        acciones = {repo.TABLA_HECHOS: auditoria.ACCION_ANULAR, repo.TABLA_MOVIMIENTOS: auditoria.ACCION_ANULAR,
                    repo.TABLA_CONCILIACIONES: repo.ACCION_ELIMINAR, repo.TABLA_APORTACIONES: repo.ACCION_ELIMINAR,
                    repo.TABLA_TRANSFERENCIAS: repo.ACCION_ELIMINAR}
        hechos = [a for a in auditadas if a["tabla"] == repo.TABLA_HECHOS]
        if len(hechos) != 1 or hechos[0]["registro_id"] != datos.hecho_id:
            return False
        if int(hechos[0]["antes"].get("row_version", -1)) != datos.row_version_esperada:
            return False
        for fila in auditadas:
            if acciones.get(fila["tabla"]) != fila["accion"] or fila["motivo"] != motivo:
                return False
            if fila["tabla"] in (repo.TABLA_CONCILIACIONES, repo.TABLA_APORTACIONES) and \
                    str(fila["antes"].get("hecho_id")) != str(datos.hecho_id):
                return False
        movimientos = {a["registro_id"]: int(a["antes"].get("row_version", -1)) for a in auditadas
                       if a["tabla"] == repo.TABLA_MOVIMIENTOS}
        return movimientos == dict(datos.movimientos_row_version_esperadas)

    def _ejecutar(self, contexto: ContextoOperacion, operacion: Any, nombre: str) -> ResultadoAnulacionRegistro:
        resultado = self._unidad.ejecutar_con_traza(contexto, operacion, nombre=nombre)
        self.ultima_traza = resultado.traza
        return resultado.valor
