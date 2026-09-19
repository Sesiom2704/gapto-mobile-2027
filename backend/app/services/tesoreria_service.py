# ============================================================
# GAPTO MOBILE 2027
# Fichero: tesoreria_service.py
# Ruta: backend/app/services/tesoreria_service.py
# Descripcion: OP-06 aportaciones reales, OP-07 vinculo aportacion-conciliacion,
#   OP-08 movimiento real de tesoreria, OP-09 conciliacion hecho-movimiento
#   y OP-11 reversion de tesoreria (F04-06).
#
#   Reutiliza integramente la infraestructura de F04-01: una transaccion por
#   operacion, contexto tenant dentro de ella, auditoria via
#   `fn_registrar_auditoria`, retry de transaccion completa y la misma
#   taxonomia de errores.
#
#   INDEPENDENCIA ENTRE DIMENSIONES. Este servicio NO lee ni escribe
#   `efecto_atribuciones`, NO reparte movimientos por participacion de cuenta y
#   NO crea derechos ni obligaciones. Que el usuario financiara 70 de un pago
#   de 100 no dice nada sobre como se atribuye el gasto, y que aportacion y
#   atribucion difieran no crea posicion entre actores: eso pertenece a
#   F04-04/F04-07. La independencia se materializa por omision deliberada:
#   nada que no venga en la entrada llega a la base.
#
#   F04-D010 · DOBLE RAIZ. OP-09 modifica dos agregados, `hechos_financieros` y
#   `movimientos_tesoreria`, cada uno con su propia `row_version`. Las dos
#   guardas viven en SQL y se aplican ANTES de insertar la conciliacion, de modo
#   que si cualquiera esta desfasada la transaccion muere sin haber tocado
#   nada. Se toman siempre en el mismo orden —hecho y despues movimiento— para
#   no introducir un ciclo de espera nuevo entre operaciones concurrentes.
#
#   D-169. La comparacion aportaciones-vs-porcion la garantiza el constraint
#   trigger diferido de 0310, y SOLO cuando la moneda del hecho coincide con la
#   de la cuenta. Aqui se prevalida para dar un error legible, nunca para
#   sustituirlo: dos transacciones concurrentes pueden ver individualmente un
#   estado valido y solo el trigger impide que el estado final lo incumpla.
#   En multidivisa no se compara nada: no hay FX y no se inventa ninguno.
# Version: 0.2.0
#   0.2.0 (F04-06 B2): OP-11 reversion de tesoreria. No crea hecho, efecto ni
#   relacion; consume same-account (D-099) y profundidad 1 (D-133).
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import json
import uuid
from typing import Any, Iterable, Sequence

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import ESTADO_ACTIVO
from app.core.modelos_tesoreria import (
    DatosReversion,
    ResultadoReversion,
    CERO,
    CLASES_MOVIMIENTO,
    CRITERIOS_APORTACION,
    DatosAportacion,
    DatosConciliacion,
    DatosMovimiento,
    MOVIMIENTO_ANULADO,
    ResultadoAportaciones,
    ResultadoConciliacion,
    ResultadoMovimiento,
    ResultadoVinculo,
)
from app.core.unidad_trabajo import SesionMotor, Traza, UnidadDeTrabajo
from app.repositories import auditoria_repository as auditoria
from app.repositories import efectos_repository as repo_efectos
from app.repositories import hechos_repository as repo_hechos
from app.repositories import tesoreria_repository as repo_tes

CIEN = decimal.Decimal("100")


def _signo(valor: decimal.Decimal) -> int:
    return (valor > CERO) - (valor < CERO)


def _a_dict(snapshot_json: str) -> dict[str, Any]:
    return json.loads(snapshot_json, parse_float=decimal.Decimal)


class TesoreriaService:
    """Casos de uso de F04-03."""

    __slots__ = ("_unidad", "ultima_traza")

    def __init__(self, unidad: UnidadDeTrabajo) -> None:
        self._unidad = unidad
        self.ultima_traza: Traza | None = None

    # ==================================================================
    # OP-06 — REGISTRAR APORTACIONES REALES
    # ==================================================================
    def registrar_aportaciones(
        self,
        contexto: ContextoOperacion,
        *,
        hecho_id: uuid.UUID,
        hecho_row_version_esperada: int,
        aportaciones: Sequence[DatosAportacion],
    ) -> ResultadoAportaciones:
        """Declara quien financio realmente el pago de un hecho.

        Un mismo actor puede aparecer en varias filas: no hay UNIQUE artificial
        por actor, porque un actor puede financiar un pago en varios tramos y
        agregarlos perderia informacion.
        """
        if not aportaciones:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA, "OP-06 exige al menos una aportacion."
            )
        for aportacion in aportaciones:
            self._validar_aportacion(aportacion)
        self._exigir_identidades_unicas([a.aportacion_id for a in aportaciones])

        def operacion(sesion: SesionMotor) -> ResultadoAportaciones:
            repo_hechos.exigir_contexto(sesion)
            estado_hecho = self._exigir_hecho_activo(sesion, hecho_id)
            self._exigir_actores_conocidos(
                sesion, [a.actor_id for a in aportaciones if a.actor_id is not None]
            )

            # Un alta puede nacer ya vinculada. La prevalidacion de D-169 se
            # hace ACUMULANDO por destino: dos aportaciones del mismo lote
            # pueden caber por separado y no caber juntas, y comprobarlas de
            # una en una dejaria pasar exactamente ese caso hasta el trigger.
            por_destino: dict[uuid.UUID, decimal.Decimal] = {}
            for aportacion in aportaciones:
                destino = aportacion.hecho_movimiento_tesoreria_id
                if destino is None:
                    continue
                self._exigir_destino_de_salida(sesion, hecho_id, destino)
                por_destino[destino] = por_destino.get(destino, CERO) + decimal.Decimal(
                    aportacion.importe
                )
            for destino, acumulado in por_destino.items():
                self._prevalidar_d169(sesion, destino, acumulado)

            valores = [self._valores_aportacion(hecho_id, a) for a in aportaciones]
            clasificacion = self._clasificar_replay(
                sesion,
                valores,
                repo_tes.leer_aportacion,
                repo_tes.creacion_aportacion_previa_coincide,
            )
            if clasificacion == "REPLICA":
                return ResultadoAportaciones(
                    hecho_id=hecho_id,
                    hecho_row_version=estado_hecho[0],
                    aportaciones_creadas=0,
                    idempotente=True,
                )
            if clasificacion == "CONFLICTO":
                raise ErrorMotor(
                    CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                    "Alguno de los identificadores reservados ya esta en uso "
                    "con otra intencion.",
                )

            nueva_version = self._tocar_hecho(
                sesion, hecho_id, hecho_row_version_esperada
            )
            for fila in valores:
                snapshot = repo_tes.insertar_aportacion_si_no_existe(sesion, fila)
                if snapshot is None:
                    raise ErrorMotor(
                        CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                        "El identificador reservado de la aportacion ya esta en uso.",
                    )
                auditoria.registrar(
                    sesion,
                    tabla=repo_tes.TABLA_APORTACIONES,
                    registro_id=fila["id"],
                    accion=auditoria.ACCION_CREAR,
                    datos_despues_json=snapshot,
                )

            return ResultadoAportaciones(
                hecho_id=hecho_id,
                hecho_row_version=nueva_version,
                aportaciones_creadas=len(valores),
                idempotente=False,
            )

        return self._ejecutar(contexto, operacion, "OP-06 registrar_aportaciones")

    # ==================================================================
    # OP-07 — VINCULAR APORTACION A CONCILIACION
    # ==================================================================
    def vincular_aportacion(
        self,
        contexto: ContextoOperacion,
        *,
        hecho_id: uuid.UUID,
        hecho_row_version_esperada: int,
        aportacion_id: uuid.UUID,
        destino: uuid.UUID | None,
    ) -> ResultadoVinculo:
        """Declara que esa aportacion financio esa salida concreta.

        `destino=None` desvincula. Vincular NUNCA se deduce de que los importes
        cuadren, de que sea la unica conciliacion o de que coincida el actor o
        la cuenta: eso son sugerencias y viven en capas superiores. Persistir
        el vinculo exige una decision explicita del llamante (INV-13), porque
        0310 puede comprobar el mismo hecho y la magnitud agregada, pero no
        puede saber si esa aportacion financio realmente esa salida.
        """

        def operacion(sesion: SesionMotor) -> ResultadoVinculo:
            repo_hechos.exigir_contexto(sesion)
            estado_hecho = self._exigir_hecho_activo(sesion, hecho_id)

            actual = repo_tes.leer_aportacion(sesion, aportacion_id)
            if actual is None or actual[0] != hecho_id:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "La aportacion indicada no existe, no es accesible o no "
                    "pertenece a ese hecho.",
                )
            _, importe, vinculo_actual, snapshot_previo = actual

            if vinculo_actual == destino:
                # No-op real. No se incrementa version ni se audita: auditar un
                # no-op afirmaria un cambio de realidad que no ocurrio.
                return ResultadoVinculo(
                    aportacion_id=aportacion_id,
                    hecho_row_version=estado_hecho[0],
                    vinculada_a=destino,
                    sin_cambios=True,
                )

            if destino is not None:
                self._exigir_destino_de_salida(sesion, hecho_id, destino)
                self._prevalidar_d169(sesion, destino, decimal.Decimal(importe))

            nueva_version = self._tocar_hecho(
                sesion, hecho_id, hecho_row_version_esperada
            )
            snapshot_nuevo = repo_tes.actualizar_vinculo(sesion, aportacion_id, destino)
            auditoria.registrar(
                sesion,
                tabla=repo_tes.TABLA_APORTACIONES,
                registro_id=aportacion_id,
                accion=auditoria.ACCION_ACTUALIZAR,
                datos_antes_json=snapshot_previo,
                datos_despues_json=snapshot_nuevo,
                motivo=(
                    "vinculo de aportacion a conciliacion"
                    if destino is not None
                    else "desvinculacion de aportacion"
                ),
            )
            return ResultadoVinculo(
                aportacion_id=aportacion_id,
                hecho_row_version=nueva_version,
                vinculada_a=destino,
                sin_cambios=False,
            )

        return self._ejecutar(contexto, operacion, "OP-07 vincular_aportacion")

    # ==================================================================
    # OP-08 — REGISTRAR MOVIMIENTO REAL
    # ==================================================================
    def registrar_movimiento(
        self, contexto: ContextoOperacion, datos: DatosMovimiento
    ) -> ResultadoMovimiento:
        """Registra dinero que realmente entro o salio de una cuenta.

        No crea hecho, ni efecto, ni atribucion, ni aportacion, ni posicion. Un
        movimiento sin hecho es un estado valido y frecuente —importacion,
        clasificacion posterior, conciliacion pendiente— y no se fabrica un
        hecho ficticio para darle compania.

        El movimiento conserva el 100 % bancario: no se divide por
        participacion de cuenta y no se persiste liquidez atribuible.
        """
        self._validar_movimiento(datos)

        def operacion(sesion: SesionMotor) -> ResultadoMovimiento:
            repo_hechos.exigir_contexto(sesion)
            if repo_tes.leer_cuenta(sesion, datos.cuenta_id) is None:
                raise ErrorMotor(
                    CodigoError.CUENTA_DESCONOCIDA,
                    "La cuenta indicada no existe o no es accesible.",
                )

            valores = self._valores_movimiento(datos)
            existente = repo_tes.leer_movimiento(sesion, datos.movimiento_id)
            if existente is not None:
                if repo_tes.creacion_movimiento_previa_coincide(sesion, valores):
                    return ResultadoMovimiento(
                        movimiento_id=datos.movimiento_id,
                        row_version=existente[0],
                        idempotente=True,
                        snapshot=_a_dict(existente[4]),
                    )
                raise ErrorMotor(
                    CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                    "El identificador reservado del movimiento ya esta en uso "
                    "con otra intencion.",
                )

            creado = repo_tes.insertar_movimiento_si_no_existe(
                sesion,
                movimiento_id=datos.movimiento_id,
                cuenta_id=datos.cuenta_id,
                fecha_movimiento=datos.fecha_movimiento,
                importe=datos.importe,
                clase_movimiento=datos.clase_movimiento,
                descripcion=datos.descripcion,
                confirmado_at=datos.confirmado_at,
            )
            if creado is None:
                raise ErrorMotor(
                    CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                    "El identificador reservado del movimiento ya esta en uso.",
                )
            row_version, snapshot = creado
            auditoria.registrar(
                sesion,
                tabla=repo_tes.TABLA_MOVIMIENTOS,
                registro_id=datos.movimiento_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=snapshot,
            )
            return ResultadoMovimiento(
                movimiento_id=datos.movimiento_id,
                row_version=row_version,
                idempotente=False,
                snapshot=_a_dict(snapshot),
            )

        return self._ejecutar(contexto, operacion, "OP-08 registrar_movimiento")

    # ==================================================================
    # OP-09 — CONCILIAR HECHO <-> MOVIMIENTO
    # ==================================================================
    def conciliar(
        self,
        contexto: ContextoOperacion,
        datos: DatosConciliacion,
        *,
        hecho_row_version_esperada: int,
        movimiento_row_version_esperada: int,
    ) -> ResultadoConciliacion:
        """Declara que porcion de un movimiento corresponde a un hecho.

        La conciliacion parcial es valida y puede quedar porcion sin conciliar
        de forma permanente. No existe obligacion de que la suma conciliada
        iguale `importe_total`, ni los efectos, ni las aportaciones.
        """
        if datos.importe_asignado is None or decimal.Decimal(
            datos.importe_asignado
        ) == CERO:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "El importe asignado de una conciliacion no puede ser cero.",
            )

        def operacion(sesion: SesionMotor) -> ResultadoConciliacion:
            repo_hechos.exigir_contexto(sesion)
            self._exigir_hecho_activo(sesion, datos.hecho_id)

            movimiento = repo_tes.leer_movimiento(
                sesion, datos.movimiento_tesoreria_id
            )
            if movimiento is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "El movimiento indicado no existe o no es accesible.",
                )
            mov_version, mov_estado, mov_importe, _, _ = movimiento
            if mov_estado == MOVIMIENTO_ANULADO:
                raise ErrorMotor(
                    CodigoError.MOVIMIENTO_ANULADO,
                    "Un movimiento anulado no admite conciliaciones nuevas.",
                )

            asignado = decimal.Decimal(datos.importe_asignado)
            if _signo(asignado) != _signo(decimal.Decimal(mov_importe)):
                raise ErrorMotor(
                    CodigoError.SIGNO_INCOMPATIBLE,
                    "La porcion conciliada debe tener el mismo signo que el "
                    "movimiento: una salida no se concilia con una entrada.",
                )

            valores = self._valores_conciliacion(datos)
            existente = repo_tes.leer_conciliacion(sesion, datos.conciliacion_id)
            if existente is not None:
                if repo_tes.creacion_conciliacion_previa_coincide(sesion, valores):
                    estado_hecho = repo_hechos.leer_estado(sesion, datos.hecho_id)
                    return ResultadoConciliacion(
                        conciliacion_id=datos.conciliacion_id,
                        hecho_row_version=estado_hecho[0],  # type: ignore[index]
                        movimiento_row_version=mov_version,
                        idempotente=True,
                    )
                raise ErrorMotor(
                    CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                    "El identificador reservado de la conciliacion ya esta en "
                    "uso con otra intencion.",
                )

            pareja = repo_tes.conciliacion_de_pareja(
                sesion, datos.hecho_id, datos.movimiento_tesoreria_id
            )
            if pareja is not None:
                # UNIQUE (hecho_id, movimiento_tesoreria_id). Se detecta antes
                # de insertar para devolver un error de dominio con sentido en
                # vez de traducir una violacion de constraint, y para no partir
                # artificialmente la misma pareja en varias filas.
                raise ErrorMotor(
                    CodigoError.YA_CONCILIADO,
                    "Ese hecho y ese movimiento ya estan conciliados entre si.",
                )

            previa = decimal.Decimal(
                repo_tes.suma_conciliada_del_movimiento(
                    sesion, datos.movimiento_tesoreria_id
                )
            )
            if abs(previa + asignado) > abs(decimal.Decimal(mov_importe)):
                raise ErrorMotor(
                    CodigoError.EXCEDE_IMPORTE_MOVIMIENTO,
                    "La suma conciliada superaria el importe del movimiento.",
                )

            # Las DOS guardas, antes de cualquier mutacion y siempre en el mismo
            # orden. Si la segunda falla, la primera muere con el rollback y
            # ninguna de las dos versiones cambia.
            nueva_hecho = self._tocar_hecho(
                sesion, datos.hecho_id, hecho_row_version_esperada
            )
            nueva_movimiento = repo_tes.tocar_movimiento(
                sesion, datos.movimiento_tesoreria_id, movimiento_row_version_esperada
            )
            if nueva_movimiento is None:
                raise ErrorMotor(
                    CodigoError.VERSION_DESFASADA,
                    "El movimiento ha cambiado desde la version que conoce el "
                    "llamante.",
                )

            snapshot = repo_tes.insertar_conciliacion_si_no_existe(sesion, valores)
            if snapshot is None:
                raise ErrorMotor(
                    CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                    "El identificador reservado de la conciliacion ya esta en uso.",
                )
            auditoria.registrar(
                sesion,
                tabla=repo_tes.TABLA_CONCILIACIONES,
                registro_id=datos.conciliacion_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=snapshot,
            )
            return ResultadoConciliacion(
                conciliacion_id=datos.conciliacion_id,
                hecho_row_version=nueva_hecho,
                movimiento_row_version=nueva_movimiento,
                idempotente=False,
            )

        return self._ejecutar(contexto, operacion, "OP-09 conciliar")

    # ==================================================================
    # Interno
    # ==================================================================
    def _tocar_hecho(
        self, sesion: SesionMotor, hecho_id: uuid.UUID, esperada: int
    ) -> int:
        nueva = repo_hechos.tocar_raiz(sesion, hecho_id, esperada)
        if nueva is None:
            raise ErrorMotor(
                CodigoError.VERSION_DESFASADA,
                "El hecho ha cambiado desde la version que conoce el llamante.",
            )
        return nueva

    def _exigir_hecho_activo(
        self, sesion: SesionMotor, hecho_id: uuid.UUID
    ) -> tuple[int, str, str]:
        estado = repo_hechos.leer_estado(sesion, hecho_id)
        if estado is None:
            raise ErrorMotor(
                CodigoError.AGREGADO_NO_ENCONTRADO,
                "El hecho indicado no existe o no es accesible.",
            )
        if estado[1] != ESTADO_ACTIVO:
            raise ErrorMotor(
                CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
                "Un hecho anulado no admite aportaciones ni conciliaciones "
                "nuevas.",
            )
        return estado

    def _exigir_actores_conocidos(
        self, sesion: SesionMotor, actor_ids: Iterable[uuid.UUID]
    ) -> None:
        pedidos = list(dict.fromkeys(actor_ids))
        if not pedidos:
            return
        if len(repo_efectos.actores_visibles(sesion, pedidos)) != len(pedidos):
            raise ErrorMotor(
                CodigoError.ACTOR_DESCONOCIDO,
                "Algun actor indicado no existe o no es accesible.",
            )

    def _exigir_destino_de_salida(
        self, sesion: SesionMotor, hecho_id: uuid.UUID, destino: uuid.UUID
    ) -> None:
        """La conciliacion destino debe existir, ser del mismo hecho y ser salida."""
        conciliacion = repo_tes.leer_conciliacion(sesion, destino)
        if conciliacion is None:
            raise ErrorMotor(
                CodigoError.AGREGADO_NO_ENCONTRADO,
                "La conciliacion indicada no existe o no es accesible.",
            )
        if conciliacion[0] != hecho_id:
            raise ErrorMotor(
                CodigoError.CONCILIACION_DE_OTRO_HECHO,
                "Esa conciliacion pertenece a otro hecho.",
            )
        movimiento = repo_tes.movimiento_de_conciliacion(sesion, destino)
        if movimiento is None:  # pragma: no cover - incoherencia imposible
            raise ErrorMotor(
                CodigoError.INTERNO, "La conciliacion no resuelve su movimiento."
            )
        importe_movimiento, estado_movimiento = movimiento
        if estado_movimiento == MOVIMIENTO_ANULADO:
            raise ErrorMotor(
                CodigoError.MOVIMIENTO_ANULADO,
                "El movimiento de esa conciliacion esta anulado.",
            )
        if decimal.Decimal(importe_movimiento) > CERO:
            raise ErrorMotor(
                CodigoError.USO_EN_COBRO_NO_PERMITIDO,
                "Una aportacion financia una SALIDA; una entrada no puede ser "
                "su destino.",
            )
        if decimal.Decimal(conciliacion[2]) > CERO:
            raise ErrorMotor(
                CodigoError.VINCULO_NO_CORRESPONDE_A_ESA_SALIDA,
                "La porcion conciliada no corresponde a una salida.",
            )

    def _prevalidar_d169(
        self, sesion: SesionMotor, destino: uuid.UUID, importe: decimal.Decimal
    ) -> None:
        """Mejora el mensaje; NO sustituye al constraint trigger de 0310."""
        datos = repo_tes.monedas_comparables(sesion, destino)
        if datos is None:  # pragma: no cover
            return
        comparables, porcion, vinculada = datos
        if not comparables:
            # Multidivisa: 0310 excluye la comparacion por diseno. No se compara
            # nominalmente, no se convierte y no se inventa tipo de cambio.
            return
        if decimal.Decimal(vinculada) + importe > decimal.Decimal(porcion):
            raise ErrorMotor(
                CodigoError.SUMA_EXCEDE_PORCION,
                "Las aportaciones vinculadas superarian la porcion conciliada.",
            )

    def _clasificar_replay(
        self, sesion: SesionMotor, valores: list[dict[str, Any]], lector, comparador
    ) -> str:
        """Todo-o-nada, igual que F04-D006.

        Un lote atomico no puede haberse aplicado a medias: si unos
        identificadores existen y otros no, no es un reintento sino reuso de
        identidad, y no se completan las filas ausentes.
        """
        existentes = 0
        coincidentes = 0
        for fila in valores:
            if lector(sesion, fila["id"]) is None:
                continue
            existentes += 1
            if comparador(sesion, fila):
                coincidentes += 1
        if existentes == 0:
            return "NUEVO"
        if existentes == len(valores) and coincidentes == existentes:
            return "REPLICA"
        return "CONFLICTO"

    @staticmethod
    def _exigir_identidades_unicas(ids: Sequence[uuid.UUID]) -> None:
        if len(set(ids)) != len(ids):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Los identificadores reservados del lote deben ser distintos.",
            )

    @staticmethod
    def _valores_aportacion(
        hecho_id: uuid.UUID, aportacion: DatosAportacion
    ) -> dict[str, Any]:
        return {
            "id": aportacion.aportacion_id,
            "hecho_id": hecho_id,
            "actor_id": aportacion.actor_id,
            "importe": aportacion.importe,
            "porcentaje_aplicado": aportacion.porcentaje_aplicado,
            "criterio_aportacion": aportacion.criterio_aportacion,
            "medio_pago_codigo": aportacion.medio_pago_codigo,
            "hecho_movimiento_tesoreria_id": aportacion.hecho_movimiento_tesoreria_id,
        }

    @staticmethod
    def _valores_movimiento(datos: DatosMovimiento) -> dict[str, Any]:
        """Claves comparables de la intencion de alta.

        `confirmado_at` solo entra cuando lo aporto el llamante: si lo fijo el
        reloj de la transaccion, un reintento produciria otro instante y
        convertiria un retry legitimo en conflicto de identidad.
        """
        valores: dict[str, Any] = {
            "id": datos.movimiento_id,
            "cuenta_id": datos.cuenta_id,
            "fecha_movimiento": datos.fecha_movimiento,
            "importe": datos.importe,
            "descripcion": datos.descripcion,
            "clase_movimiento": datos.clase_movimiento,
        }
        if datos.confirmado_at is not None:
            valores["confirmado_at"] = datos.confirmado_at
        return valores

    @staticmethod
    def _valores_conciliacion(datos: DatosConciliacion) -> dict[str, Any]:
        return {
            "id": datos.conciliacion_id,
            "hecho_id": datos.hecho_id,
            "movimiento_tesoreria_id": datos.movimiento_tesoreria_id,
            "importe_asignado": datos.importe_asignado,
        }

    @staticmethod
    def _validar_aportacion(aportacion: DatosAportacion) -> None:
        if aportacion.importe is None or decimal.Decimal(aportacion.importe) <= CERO:
            raise ErrorMotor(
                CodigoError.IMPORTE_NO_POSITIVO,
                "El importe de una aportacion debe ser mayor que cero: una "
                "aportacion representa dinero efectivamente aportado.",
            )
        if aportacion.criterio_aportacion not in CRITERIOS_APORTACION:
            raise ErrorMotor(
                CodigoError.CRITERIO_INVALIDO,
                "criterio_aportacion no pertenece al conjunto cerrado.",
            )
        if aportacion.porcentaje_aplicado is not None:
            porcentaje = decimal.Decimal(aportacion.porcentaje_aplicado)
            if porcentaje < CERO or porcentaje > CIEN:
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    "porcentaje_aplicado debe estar entre 0 y 100.",
                )

    @staticmethod
    def _validar_movimiento(datos: DatosMovimiento) -> None:
        if datos.importe is None or decimal.Decimal(datos.importe) == CERO:
            raise ErrorMotor(
                CodigoError.IMPORTE_CERO,
                "Un movimiento de importe cero no representa dinero movido.",
            )
        if datos.fecha_movimiento is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "fecha_movimiento es obligatoria.",
            )
        if datos.clase_movimiento not in CLASES_MOVIMIENTO:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "clase_movimiento debe ser OPERACION o AJUSTE_SALDO.",
            )
        if datos.confirmado_at is not None and not isinstance(
            datos.confirmado_at, dt.datetime
        ):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "confirmado_at debe ser un instante, no una fecha.",
            )


    # ==================================================================
    # OP-11 — REVERSION DE TESORERIA (F04-06 / B2)
    # ==================================================================
    def revertir_movimiento(
        self, contexto: ContextoOperacion, datos: DatosReversion
    ) -> ResultadoReversion:
        """Dinero que el banco devuelve al sitio del que salio.

        NO es una devolucion economica y NO es una correccion. Una reversion de
        tesoreria no crea hecho, ni efecto, ni `hecho_relaciones`, ni
        transferencia inversa. El acontecimiento economico original sigue
        siendo cierto: lo que cambia es que el apunte bancario se deshizo.

        Por eso tampoco se concilia con el hecho del original: hacerlo
        reduciria la porcion asignada y reescribiria hacia atras una realidad
        economica que nadie ha negado.

        GARANTIAS FISICAS CONSUMIDAS, NO REIMPLEMENTADAS:
        - misma cuenta, por la FK compuesta de 0220 (D-099);
        - profundidad maxima 1 en ambos sentidos, por 0280 (D-133);
        - signo contrario y suma de reversiones ACTIVAS <= original;
        - una reversion ACTIVA no apunta a un original ANULADO (D-119/T6).
        El servicio prevalida para producir un error de dominio legible. Si
        prevalidacion y trigger divergieran, manda el trigger.
        """
        self._validar_reversion(datos)

        def operacion(sesion: SesionMotor) -> ResultadoReversion:
            repo_hechos.exigir_contexto(sesion)

            existente = repo_tes.leer_movimiento(sesion, datos.reversion_id)
            if existente is not None:
                return self._replay_reversion(sesion, datos, existente)

            # El lock del original va ANTES de leer cuanto se ha revertido ya:
            # es lo unico que impide que dos reversiones concurrentes calculen
            # el mismo pendiente y lo agoten dos veces.
            original = repo_tes.contexto_de_reversion(
                sesion, datos.movimiento_original_id
            )
            if original is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "El movimiento original no existe o no es accesible.",
                )
            if original["es_reversion"]:
                raise ErrorMotor(
                    CodigoError.REVERSION_DE_REVERSION,
                    "Una reversion solo puede apuntar a un movimiento raiz: "
                    "deshacer una reversion se registra como un movimiento "
                    "ordinario nuevo, sin enlazarlo.",
                )
            if original["estado"] != "ACTIVO":
                raise ErrorMotor(
                    CodigoError.ORIGINAL_ANULADO,
                    "No se revierte un movimiento anulado: si nunca existio, "
                    "no hay nada que deshacer.",
                )
            if original["cuenta_id"] != datos.cuenta_id:
                raise ErrorMotor(
                    CodigoError.CUENTA_DISTINTA,
                    "La reversion vive en la misma cuenta que el original: "
                    "devolver el dinero a otra cuenta es una transferencia, "
                    "no una reversion.",
                )

            magnitud = decimal.Decimal(datos.importe)
            revertido = decimal.Decimal(original["revertido"])
            disponible = abs(decimal.Decimal(original["importe"])) - revertido
            if magnitud > disponible:
                raise ErrorMotor(
                    CodigoError.EXCEDE_IMPORTE_ORIGINAL,
                    "La suma de reversiones activas no puede superar el "
                    "importe del movimiento original.",
                )

            # El signo lo pone el motor a partir del original.
            signo = -1 if decimal.Decimal(original["importe"]) > 0 else 1
            importe = magnitud * signo

            creada = repo_tes.insertar_reversion_si_no_existe(
                sesion,
                reversion_id=datos.reversion_id,
                cuenta_id=datos.cuenta_id,
                fecha_movimiento=datos.fecha_movimiento,
                importe=importe,
                # Conserva la clase del original: revertir un AJUSTE_SALDO no lo
                # convierte en una operacion ordinaria.
                clase_movimiento=original["clase_movimiento"],
                descripcion=datos.descripcion,
                confirmado_at=datos.confirmado_at,
                reversion_de_movimiento_id=datos.movimiento_original_id,
            )
            if creada is None:
                raise ErrorMotor(
                    CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                    "El identificador reservado de la reversion ya esta en uso "
                    "con otra intencion.",
                )
            row_version, snapshot = creada
            auditoria.registrar(
                sesion,
                tabla=repo_tes.TABLA_MOVIMIENTOS,
                registro_id=datos.reversion_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=snapshot,
            )
            return ResultadoReversion(
                reversion_id=datos.reversion_id,
                movimiento_original_id=datos.movimiento_original_id,
                row_version=row_version,
                importe=importe,
                revertido_acumulado=revertido + magnitud,
                pendiente=disponible - magnitud,
            )

        return self._ejecutar(contexto, operacion, "OP-11 revertir_movimiento")

    def _replay_reversion(
        self,
        sesion: SesionMotor,
        datos: DatosReversion,
        existente: tuple[Any, ...],
    ) -> ResultadoReversion:
        """Reintento de una OP-11 cuyo COMMIT quedo en resultado desconocido.

        La identidad de una reversion es a que original apunta y por cuanto. Si
        el UUID reservado esta ocupado por otra cosa, es conflicto y no se
        completa nada.
        """
        importe_actual = decimal.Decimal(existente[2])
        if not repo_tes.creacion_reversion_previa_coincide(
            sesion,
            reversion_id=datos.reversion_id,
            original_id=datos.movimiento_original_id,
            importe=importe_actual,
        ) or abs(importe_actual) != decimal.Decimal(datos.importe):
            raise ErrorMotor(
                CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                "El identificador reservado de la reversion ya esta en uso con "
                "otra intencion.",
            )
        original = repo_tes.contexto_de_reversion(
            sesion, datos.movimiento_original_id
        )
        assert original is not None
        revertido = decimal.Decimal(original["revertido"])
        return ResultadoReversion(
            reversion_id=datos.reversion_id,
            movimiento_original_id=datos.movimiento_original_id,
            row_version=existente[0],
            importe=importe_actual,
            revertido_acumulado=revertido,
            pendiente=abs(decimal.Decimal(original["importe"])) - revertido,
            idempotente=True,
        )

    @staticmethod
    def _validar_reversion(datos: DatosReversion) -> None:
        if datos.reversion_id == datos.movimiento_original_id:
            raise ErrorMotor(
                CodigoError.AUTORREVERSION,
                "Un movimiento no se revierte a si mismo.",
            )
        if datos.importe is None or decimal.Decimal(datos.importe) <= 0:
            raise ErrorMotor(
                CodigoError.SIGNOS_INCORRECTOS,
                "El importe de una reversion se declara como magnitud "
                "positiva: el signo contrario lo pone el motor.",
            )
        if datos.fecha_movimiento is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Una reversion exige fecha de movimiento.",
            )

    def _ejecutar(
        self, contexto: ContextoOperacion, operacion: Any, nombre: str
    ) -> Any:
        resultado = self._unidad.ejecutar_con_traza(contexto, operacion, nombre=nombre)
        self.ultima_traza = resultado.traza
        return resultado.valor
