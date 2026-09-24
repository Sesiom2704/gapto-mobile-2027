# ============================================================
# GAPTO MOBILE 2027
# Fichero: efectos_service.py
# Ruta: backend/app/services/efectos_service.py
# Descripcion: OP-04 registrar efectos economicos y OP-05 atribuir efectos.
#
#   Reutiliza integramente la infraestructura cerrada en F04-01: una sola
#   transaccion por operacion, contexto tenant dentro de ella, auditoria por
#   `fn_registrar_auditoria`, retry de transaccion completa y taxonomia de
#   errores. No se duplica nada de eso.
#
#   Tres reglas que PostgreSQL no puede imponer y sostiene este servicio:
#
#   INV-01/INV-02 · `NO_DISPONIBLE` exige CERO filas de atribucion. El
#   validador fisico solo cubre COMPLETA y PARCIAL, asi que sin esta guarda un
#   efecto podria declararse "sin informacion" teniendo un actor conocido, y un
#   informe leeria como desconocido algo que si se sabia.
#
#   INV-03/INV-04 · La atribucion no se deriva de la participacion de cuenta ni
#   de quien pago, y una diferencia entre atribucion y aportacion NO crea
#   posicion. Aqui eso se materializa por omision deliberada: este servicio no
#   lee `cuenta_participaciones` ni escribe en aportaciones, tesoreria o
#   posiciones. Nada que no este en la entrada llega a la base.
#
#   INV-09 · `VALOR_ACTIVO` exige acontecimiento real declarado. Ver la nota de
#   `modelos_efectos` sobre el alcance real de esa guarda.
#
#   INV-20 · El token de concurrencia del agregado es
#   `hechos_financieros.row_version`; ni `hecho_efectos` ni
#   `efecto_atribuciones` tienen el suyo. Toda operacion con exito incrementa
#   esa version UNA sola vez, con la guarda en SQL.
# Version: 0.4.0
#   0.4.0 (F04-D046 R2 · mandato R1+R2 v0.3 §5/§9 + E01): frontera
#   presupuestaria y territorial de OP-04. `presupuestable` esta INACTIVO
#   mientras el hecho no contiene GASTO ni INGRESO; cuando OP-04 produce la
#   transicion sin -> con GASTO/INGRESO la decision es OBLIGATORIA y explicita
#   (el booleano fisico almacenado durante la etapa inactiva no cuenta como
#   decision). Sin transicion, un `presupuestable` explicito carece de
#   significado en OP-04 y se rechaza (la correccion del escalar es OP-02).
#   Si OP-04 escribe algun efecto GASTO/INGRESO, `NO_APLICA` en el hecho es
#   invalido. Ambas son guardas de frontera de escritura hacia adelante: no
#   invalidan historico. Errores: ENTRADA_INVALIDA, rollback total. La version
#   del hecho sigue incrementandose UNA sola vez: en la transicion, el propio
#   UPDATE de la decision es el toque de raiz.
# Version: 0.3.0
#   0.3.0 (F04-02): F04-D007 valida el signo de CADA importe atribuido contra
#   el delta del efecto. La comprobacion agregada no basta: un reparto de +120
#   y -20 sobre +100 suma bien y aun asi introduce neteo entre actores.
# Version: 0.2.0
#   0.2.0 (F04-02): F04-D005 conserva el acontecimiento declarado de
#   VALOR_ACTIVO en `auditoria.motivo` con convencion `VALOR_ACTIVO:<CODIGO>`.
#   F04-D006 fija la idempotencia de lote como estrictamente todo-o-nada.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import decimal
import json
import uuid
from typing import Any, Iterable, Sequence

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import ESTADO_ACTIVO
from app.core.modelos_efectos import (
    ACONTECIMIENTOS_VALOR_ACTIVO,
    ATRIBUCION_COMPLETA,
    ATRIBUCION_NO_DISPONIBLE,
    ATRIBUCION_PARCIAL,
    CRITERIOS_ATRIBUCION,
    DatosAtribucion,
    DatosEfecto,
    ESTADOS_ATRIBUCION,
    RANGO_ESTADO,
    ResultadoEfecto,
    ResultadoOperacionEfectos,
    TIPOS_EFECTO,
    TIPO_VALOR_ACTIVO,
)
from app.core.unidad_trabajo import SesionMotor, Traza, UnidadDeTrabajo
from app.repositories import auditoria_repository as auditoria
from app.repositories import efectos_repository as repo_efectos
from app.repositories import hechos_repository as repo_hechos
from app.repositories import relaciones_repository as repo_rel

CERO = decimal.Decimal("0")

# F04-D046 R2 · A08-bis (INV-11). Naturalezas con efecto presupuestario.
NATURALEZAS_PRESUPUESTABLES = frozenset({"GASTO", "INGRESO"})
LOCALIZACION_NO_APLICA = "NO_APLICA"
MOTIVO_ACTIVACION_PRESUPUESTABLE = (
    "F04-D046 A08-bis: primer GASTO/INGRESO del hecho; decision presupuestable"
)


def _a_dict(snapshot_json: str) -> dict[str, Any]:
    return json.loads(snapshot_json, parse_float=decimal.Decimal)


def _signo(valor: decimal.Decimal) -> int:
    return (valor > CERO) - (valor < CERO)


def _motivo_acontecimiento(efecto: DatosEfecto) -> str | None:
    """F04-D005: conserva en auditoria el acontecimiento DECLARADO.

    Convencion estable `VALOR_ACTIVO:<CODIGO>`. Deja rastro de que declaro el
    caller y cuando; NO demuestra que el acontecimiento fuese objetivamente
    real, y ningun read-model puede parsear este campo como fuente de verdad de
    dominio. Si una fase posterior necesita consultar o filtrar por esa causa,
    corresponde STOP y decidir persistencia de dominio.
    """
    if efecto.tipo_efecto != TIPO_VALOR_ACTIVO:
        return None
    return f"VALOR_ACTIVO:{efecto.acontecimiento}"


class EfectosService:
    """Casos de uso de F04-02 sobre efectos y atribuciones."""

    __slots__ = ("_unidad", "ultima_traza")

    def __init__(self, unidad: UnidadDeTrabajo) -> None:
        self._unidad = unidad
        self.ultima_traza: Traza | None = None

    # ==================================================================
    # OP-04 — REGISTRAR EFECTOS
    # ==================================================================
    def registrar_efectos(
        self,
        contexto: ContextoOperacion,
        *,
        hecho_id: uuid.UUID,
        row_version_esperada: int,
        efectos: Sequence[DatosEfecto],
        presupuestable: bool | None = None,
    ) -> ResultadoOperacionEfectos:
        """Declara 1..N efectos, con su reparto inicial, en UNA transaccion.

        `presupuestable` (F04-D046 A08-bis) solo se admite, y entonces es
        obligatorio, cuando esta llamada introduce el primer GASTO/INGRESO del
        hecho.
        """
        if not efectos:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "OP-04 exige al menos un efecto.",
            )
        for efecto in efectos:
            self._validar_efecto(efecto)
        self._validar_identidades_unicas(efectos)
        if presupuestable is not None and not isinstance(presupuestable, bool):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "`presupuestable` debe ser booleano.",
            )
        escribe_elegible = any(
            e.tipo_efecto in NATURALEZAS_PRESUPUESTABLES for e in efectos
        )

        def operacion(sesion: SesionMotor) -> ResultadoOperacionEfectos:
            repo_hechos.exigir_contexto(sesion)
            estado_hecho = self._exigir_hecho_activo(sesion, hecho_id)

            self._exigir_actores_conocidos(
                sesion,
                [a.actor_id for e in efectos for a in e.atribuciones],
            )

            clasificacion = self._clasificar_replay(sesion, efectos, hecho_id)
            if clasificacion == "REPLICA":
                # Un reintento demostrado NO vuelve a incrementar row_version:
                # hacerlo invalidaria la version que el llamante ya conoce.
                # F04-D046: si el reintento trae una decision presupuestaria,
                # debe ser la que quedo persistida; otra es otra intencion.
                if presupuestable is not None and (
                    _a_dict(estado_hecho[2]).get("presupuestable") != presupuestable
                ):
                    raise ErrorMotor(
                        CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                        "El reintento declara otra decision presupuestaria.",
                    )
                return ResultadoOperacionEfectos(
                    hecho_id=hecho_id,
                    row_version=estado_hecho[0],
                    efectos=self._resultados_existentes(sesion, efectos),
                    idempotente=True,
                )
            if clasificacion == "CONFLICTO":
                raise ErrorMotor(
                    CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                    "Alguno de los identificadores reservados ya esta en uso "
                    "con otra intencion.",
                )

            nueva_version = self._frontera_y_toque_raiz(
                sesion,
                hecho_id=hecho_id,
                row_version_esperada=row_version_esperada,
                estado_hecho=estado_hecho,
                escribe_elegible=escribe_elegible,
                presupuestable=presupuestable,
            )

            resultados: list[ResultadoEfecto] = []
            atribuciones_creadas = 0
            for efecto in efectos:
                creado = repo_efectos.insertar_efecto_si_no_existe(
                    sesion,
                    hecho_id,
                    efecto_id=efecto.efecto_id,
                    tipo_efecto=efecto.tipo_efecto,
                    importe_delta=efecto.importe_delta,
                    estado_atribucion=efecto.estado_atribucion,
                    categoria_id=efecto.categoria_id,
                    descripcion=efecto.descripcion,
                )
                if creado is None:
                    # El UUID existe pero no era visible: otro tenant o carrera.
                    raise ErrorMotor(
                        CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                        "El identificador reservado del efecto ya esta en uso.",
                    )
                _, snapshot = creado
                auditoria.registrar(
                    sesion,
                    tabla=repo_efectos.TABLA_EFECTOS,
                    registro_id=efecto.efecto_id,
                    accion=auditoria.ACCION_CREAR,
                    datos_despues_json=snapshot,
                    motivo=_motivo_acontecimiento(efecto),
                )
                for atribucion in efecto.atribuciones:
                    self._crear_atribucion(sesion, efecto.efecto_id, atribucion)
                    atribuciones_creadas += 1

                resultados.append(
                    ResultadoEfecto(
                        efecto_id=efecto.efecto_id,
                        tipo_efecto=efecto.tipo_efecto,
                        estado_atribucion=efecto.estado_atribucion,
                        idempotente=False,
                        snapshot=_a_dict(snapshot),
                    )
                )

            return ResultadoOperacionEfectos(
                hecho_id=hecho_id,
                row_version=nueva_version,
                efectos=tuple(resultados),
                atribuciones_creadas=atribuciones_creadas,
                idempotente=False,
            )

        return self._ejecutar(contexto, operacion, "OP-04 registrar_efectos")

    # ==================================================================
    # OP-05 — ATRIBUIR EFECTOS
    # ==================================================================
    def atribuir_efecto(
        self,
        contexto: ContextoOperacion,
        *,
        hecho_id: uuid.UUID,
        row_version_esperada: int,
        efecto_id: uuid.UUID,
        atribuciones: Sequence[DatosAtribucion],
        estado_resultante: str,
    ) -> ResultadoOperacionEfectos:
        """Enriquece la atribucion de un efecto. Nunca reescribe lo ya conocido."""
        if estado_resultante not in ESTADOS_ATRIBUCION:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "estado_atribucion resultante invalido.",
            )
        for atribucion in atribuciones:
            self._validar_atribucion(atribucion)
        self._validar_actores_unicos(atribuciones)

        def operacion(sesion: SesionMotor) -> ResultadoOperacionEfectos:
            repo_hechos.exigir_contexto(sesion)
            estado_hecho = self._exigir_hecho_activo(sesion, hecho_id)

            efecto = repo_efectos.leer_efecto(sesion, efecto_id)
            if efecto is None or efecto[0] != hecho_id:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "El efecto indicado no existe, no es accesible o no "
                    "pertenece a ese hecho.",
                )
            _, _, importe_delta, estado_actual, snapshot_previo = efecto

            if RANGO_ESTADO[estado_resultante] < RANGO_ESTADO[estado_actual]:
                raise ErrorMotor(
                    CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
                    "La atribucion solo se enriquece; retroceder de estado es "
                    "correccion de realidad registrada, no alta.",
                )
            if estado_actual == ATRIBUCION_COMPLETA:
                raise ErrorMotor(
                    CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
                    "El efecto ya tiene el reparto completo conocido.",
                )

            self._validar_signo_por_fila(
                atribuciones, decimal.Decimal(importe_delta)
            )

            self._exigir_actores_conocidos(
                sesion, [a.actor_id for a in atribuciones]
            )

            clasificacion = self._clasificar_replay_atribuciones(
                sesion, atribuciones, efecto_id
            )
            if clasificacion == "REPLICA" and estado_actual == estado_resultante:
                return ResultadoOperacionEfectos(
                    hecho_id=hecho_id,
                    row_version=estado_hecho[0],
                    atribuciones_creadas=0,
                    idempotente=True,
                )
            if clasificacion == "CONFLICTO":
                raise ErrorMotor(
                    CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                    "Alguno de los identificadores de atribucion ya esta en "
                    "uso con otra intencion.",
                )

            ya_atribuidos = repo_efectos.actores_ya_atribuidos(sesion, efecto_id)
            repetidos = [a for a in atribuciones if a.actor_id in ya_atribuidos]
            if repetidos:
                raise ErrorMotor(
                    CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
                    "Ese actor ya tiene una atribucion materializada en el "
                    "efecto; cambiarla es correccion, no enriquecimiento.",
                )

            filas_previas, suma_previa = repo_efectos.resumen_atribuciones(
                sesion, efecto_id
            )
            suma_nueva = sum(
                (a.importe_atribuido for a in atribuciones), start=CERO
            )
            self._validar_coherencia(
                estado=estado_resultante,
                filas=filas_previas + len(atribuciones),
                suma=decimal.Decimal(suma_previa) + suma_nueva,
                delta=decimal.Decimal(importe_delta),
            )

            nueva_version = self._tocar_raiz(sesion, hecho_id, row_version_esperada)

            for atribucion in atribuciones:
                self._crear_atribucion(sesion, efecto_id, atribucion)

            if estado_resultante != estado_actual:
                snapshot_nuevo = repo_efectos.actualizar_estado_efecto(
                    sesion, efecto_id, estado_resultante
                )
                auditoria.registrar(
                    sesion,
                    tabla=repo_efectos.TABLA_EFECTOS,
                    registro_id=efecto_id,
                    accion=auditoria.ACCION_ACTUALIZAR,
                    datos_antes_json=snapshot_previo,
                    datos_despues_json=snapshot_nuevo,
                    motivo=f"transicion de atribucion {estado_actual} -> {estado_resultante}",
                )

            return ResultadoOperacionEfectos(
                hecho_id=hecho_id,
                row_version=nueva_version,
                atribuciones_creadas=len(atribuciones),
                idempotente=False,
            )

        return self._ejecutar(contexto, operacion, "OP-05 atribuir_efecto")

    # ==================================================================
    # Interno — persistencia
    # ==================================================================
    def _crear_atribucion(
        self, sesion: SesionMotor, efecto_id: uuid.UUID, atribucion: DatosAtribucion
    ) -> None:
        snapshot = repo_efectos.insertar_atribucion_si_no_existe(
            sesion,
            atribucion_id=atribucion.atribucion_id,
            efecto_id=efecto_id,
            actor_id=atribucion.actor_id,
            importe_atribuido=atribucion.importe_atribuido,
            criterio_atribucion=atribucion.criterio_atribucion,
            porcentaje_aplicado=atribucion.porcentaje_aplicado,
        )
        if snapshot is None:
            raise ErrorMotor(
                CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                "El identificador reservado de la atribucion ya esta en uso.",
            )
        auditoria.registrar(
            sesion,
            tabla=repo_efectos.TABLA_ATRIBUCIONES,
            registro_id=atribucion.atribucion_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json=snapshot,
        )

    def _frontera_y_toque_raiz(
        self,
        sesion: SesionMotor,
        *,
        hecho_id: uuid.UUID,
        row_version_esperada: int,
        estado_hecho: tuple[int, str, str],
        escribe_elegible: bool,
        presupuestable: bool | None,
    ) -> int:
        """F04-D046 R2 (mandato v0.3 §5/§9). Guardas de frontera de OP-04.

        Se evalua ANTES de insertar: el estado previo se lee dentro de la
        transaccion y el UPDATE final de la raiz lleva la guarda de version en
        SQL, de modo que una escritura concurrente que cambie el hecho entre la
        lectura y el UPDATE hace fallar con VERSION_DESFASADA.
        """
        snapshot = _a_dict(estado_hecho[2])
        if (
            escribe_elegible
            and snapshot.get("estado_localizacion") == LOCALIZACION_NO_APLICA
        ):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Un hecho con GASTO o INGRESO no admite estado_localizacion "
                "NO_APLICA: si la localidad es aplicable pero no se conoce, es "
                "DESCONOCIDA.",
            )
        elegible_antes = any(
            repo_rel.capacidad_por_naturaleza(sesion, hecho_id, naturaleza)
            is not None
            for naturaleza in NATURALEZAS_PRESUPUESTABLES
        )
        transicion = escribe_elegible and not elegible_antes
        if not transicion:
            if presupuestable is not None:
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    "Esta llamada no introduce el primer GASTO/INGRESO del "
                    "hecho: `presupuestable` no tiene significado en OP-04 "
                    "(el escalar se corrige con OP-02).",
                )
            return self._tocar_raiz(sesion, hecho_id, row_version_esperada)

        if presupuestable is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "OP-04 introduce el primer GASTO/INGRESO del hecho: exige "
                "decidir `presupuestable`. El valor almacenado mientras el "
                "hecho no tenia GASTO/INGRESO esta INACTIVO y no es decision.",
            )
        actualizado = repo_hechos.actualizar_campos(
            sesion, hecho_id, row_version_esperada, {"presupuestable": presupuestable}
        )
        if actualizado is None:
            raise ErrorMotor(
                CodigoError.VERSION_DESFASADA,
                "El hecho ha cambiado desde la version que conoce el llamante.",
            )
        auditoria.registrar(
            sesion,
            tabla=repo_hechos.TABLA,
            registro_id=hecho_id,
            accion=auditoria.ACCION_ACTUALIZAR,
            datos_antes_json=estado_hecho[2],
            datos_despues_json=actualizado[2],
            motivo=MOTIVO_ACTIVACION_PRESUPUESTABLE,
        )
        return actualizado[0]

    def _tocar_raiz(
        self, sesion: SesionMotor, hecho_id: uuid.UUID, row_version_esperada: int
    ) -> int:
        """Incrementa UNA vez la version del hecho raiz, con guarda en SQL.

        La guarda vive en el WHERE, no en Python: entre leer y escribir cabe
        otra transaccion, y solo la clausula SQL impide la perdida de
        actualizacion. Ademas deja la fila raiz bloqueada para el resto de la
        transaccion, que es el mismo lock root que usan los validadores de 0310.
        """
        nueva = repo_hechos.tocar_raiz(sesion, hecho_id, row_version_esperada)
        if nueva is None:
            raise ErrorMotor(
                CodigoError.VERSION_DESFASADA,
                "El hecho ha cambiado desde la version que conoce el llamante.",
            )
        return nueva

    # ==================================================================
    # Interno — lectura y clasificacion
    # ==================================================================
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
                "Un hecho anulado no admite efectos ni atribuciones nuevas.",
            )
        return estado

    def _exigir_actores_conocidos(
        self, sesion: SesionMotor, actor_ids: Iterable[uuid.UUID]
    ) -> None:
        pedidos = list(dict.fromkeys(actor_ids))
        if not pedidos:
            return
        visibles = repo_efectos.actores_visibles(sesion, pedidos)
        if len(visibles) != len(pedidos):
            # No se distingue "no existe" de "es de otro tenant": RLS lo oculta
            # y preguntarlo por otra via seria una fuga.
            raise ErrorMotor(
                CodigoError.ACTOR_DESCONOCIDO,
                "Algun actor indicado no existe o no es accesible.",
            )

    def _clasificar_replay(
        self, sesion: SesionMotor, efectos: Sequence[DatosEfecto], hecho_id: uuid.UUID
    ) -> str:
        """NUEVO, REPLICA o CONFLICTO para un lote de efectos.

        Un lote es atomico, de modo que no puede haberse aplicado a medias. Si
        unos identificadores existen y otros no, no es un reintento: es reuso
        de identidad y se rechaza.
        """
        existentes = 0
        coincidentes = 0
        for efecto in efectos:
            if repo_efectos.leer_efecto(sesion, efecto.efecto_id) is None:
                continue
            existentes += 1
            if repo_efectos.creacion_efecto_previa_coincide(
                sesion, self._valores_efecto(efecto, hecho_id)
            ):
                coincidentes += 1
        if existentes == 0:
            return "NUEVO"
        if existentes == len(efectos) and coincidentes == existentes:
            return "REPLICA"
        return "CONFLICTO"

    def _clasificar_replay_atribuciones(
        self,
        sesion: SesionMotor,
        atribuciones: Sequence[DatosAtribucion],
        efecto_id: uuid.UUID,
    ) -> str:
        if not atribuciones:
            return "NUEVO"
        existentes = 0
        coincidentes = 0
        for atribucion in atribuciones:
            valores = self._valores_atribucion(efecto_id, atribucion)
            fila = sesion.uno(
                "SELECT 1 FROM gapto.efecto_atribuciones WHERE id = %s::uuid",
                (atribucion.atribucion_id,),
            )
            if fila is None:
                continue
            existentes += 1
            if repo_efectos.creacion_atribucion_previa_coincide(sesion, valores):
                coincidentes += 1
        if existentes == 0:
            return "NUEVO"
        if existentes == len(atribuciones) and coincidentes == existentes:
            return "REPLICA"
        return "CONFLICTO"

    def _resultados_existentes(
        self, sesion: SesionMotor, efectos: Sequence[DatosEfecto]
    ) -> tuple[ResultadoEfecto, ...]:
        salida: list[ResultadoEfecto] = []
        for efecto in efectos:
            actual = repo_efectos.leer_efecto(sesion, efecto.efecto_id)
            if actual is None:  # pragma: no cover - imposible tras REPLICA
                continue
            salida.append(
                ResultadoEfecto(
                    efecto_id=efecto.efecto_id,
                    tipo_efecto=actual[1],
                    estado_atribucion=actual[3],
                    idempotente=True,
                    snapshot=_a_dict(actual[4]),
                )
            )
        return tuple(salida)

    # ==================================================================
    # Interno — validacion pura
    # ==================================================================
    @staticmethod
    def _valores_efecto(efecto: DatosEfecto, hecho_id: uuid.UUID) -> dict[str, Any]:
        """Intencion de creacion, con EXACTAMENTE las claves del snapshot.

        Omitir una sola clave —`hecho_id` lo estuvo— hace que la comparacion
        jsonb nunca iguale y convierte todo reintento legitimo en un falso
        conflicto de identidad.
        """
        return {
            "id": efecto.efecto_id,
            "hecho_id": hecho_id,
            "tipo_efecto": efecto.tipo_efecto,
            "importe_delta": efecto.importe_delta,
            "categoria_id": efecto.categoria_id,
            "estado_atribucion": efecto.estado_atribucion,
            "descripcion": efecto.descripcion,
        }

    @staticmethod
    def _valores_atribucion(
        efecto_id: uuid.UUID, atribucion: DatosAtribucion
    ) -> dict[str, Any]:
        return {
            "id": atribucion.atribucion_id,
            "efecto_id": efecto_id,
            "actor_id": atribucion.actor_id,
            "importe_atribuido": atribucion.importe_atribuido,
            "porcentaje_aplicado": atribucion.porcentaje_aplicado,
            "criterio_atribucion": atribucion.criterio_atribucion,
        }

    def _validar_efecto(self, efecto: DatosEfecto) -> None:
        if efecto.tipo_efecto not in TIPOS_EFECTO:
            raise ErrorMotor(
                CodigoError.NATURALEZA_INVALIDA,
                "La naturaleza del efecto no pertenece al conjunto cerrado.",
            )
        if efecto.importe_delta is None or decimal.Decimal(efecto.importe_delta) == CERO:
            # El signo NO se deduce del tipo ni el tipo del signo: son datos
            # independientes y ninguno se infiere del otro.
            raise ErrorMotor(
                CodigoError.DELTA_CERO,
                "Un efecto de importe cero no existe: el delta debe ser "
                "distinto de cero.",
            )
        if efecto.estado_atribucion not in ESTADOS_ATRIBUCION:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "estado_atribucion invalido.",
            )

        if efecto.tipo_efecto == TIPO_VALOR_ACTIVO:
            if efecto.acontecimiento not in ACONTECIMIENTOS_VALOR_ACTIVO:
                raise ErrorMotor(
                    CodigoError.VALOR_ACTIVO_SIN_ACONTECIMIENTO,
                    "VALOR_ACTIVO exige declarar el acontecimiento real que "
                    "produce el delta patrimonial; una valoracion no lo es.",
                )
        elif efecto.acontecimiento is not None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Solo VALOR_ACTIVO admite acontecimiento declarado.",
            )

        for atribucion in efecto.atribuciones:
            self._validar_atribucion(atribucion)
        self._validar_actores_unicos(efecto.atribuciones)
        self._validar_signo_por_fila(
            efecto.atribuciones, decimal.Decimal(efecto.importe_delta)
        )

        self._validar_coherencia(
            estado=efecto.estado_atribucion,
            filas=len(efecto.atribuciones),
            suma=sum(
                (a.importe_atribuido for a in efecto.atribuciones), start=CERO
            ),
            delta=decimal.Decimal(efecto.importe_delta),
        )

    @staticmethod
    def _validar_atribucion(atribucion: DatosAtribucion) -> None:
        if atribucion.criterio_atribucion not in CRITERIOS_ATRIBUCION:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "criterio_atribucion invalido.",
            )
        if atribucion.importe_atribuido is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "importe_atribuido es obligatorio; 0,00 es dato conocido y la "
                "ausencia de dato se expresa no creando la fila.",
            )

    @staticmethod
    def _validar_signo_por_fila(
        atribuciones: Sequence[DatosAtribucion], delta: decimal.Decimal
    ) -> None:
        """F04-D007: cada importe hereda la semantica de signo del delta.

        No basta con que la suma cuadre. Un reparto de +120 y -20 sobre un
        efecto de +100 suma bien y aun asi es invalido: la fila negativa mete
        compensacion entre actores dentro del reparto de un solo efecto, que es
        neteo, y el neteo es lectura derivada, nunca realidad persistida
        (INV-10). El agregado fisico no puede verlo porque solo mira la suma.

        0,00 sigue siendo valido en ambos sentidos: es atribucion nula
        CONOCIDA, distinta de la ausencia de fila.
        """
        signo_delta = _signo(delta)
        for atribucion in atribuciones:
            importe = decimal.Decimal(atribucion.importe_atribuido)
            if importe == CERO:
                continue
            if _signo(importe) != signo_delta:
                raise ErrorMotor(
                    CodigoError.SIGNO_INCOMPATIBLE,
                    "Cada importe atribuido debe mantener el signo del delta "
                    "del efecto; una fila de signo contrario seria "
                    "compensacion entre actores, no atribucion.",
                )

    @staticmethod
    def _validar_actores_unicos(atribuciones: Sequence[DatosAtribucion]) -> None:
        actores = [a.actor_id for a in atribuciones]
        if len(set(actores)) != len(actores):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Un actor no puede aparecer dos veces en el mismo reparto.",
            )

    @staticmethod
    def _validar_identidades_unicas(efectos: Sequence[DatosEfecto]) -> None:
        ids = [e.efecto_id for e in efectos] + [
            a.atribucion_id for e in efectos for a in e.atribuciones
        ]
        if len(set(ids)) != len(ids):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Los identificadores reservados del lote deben ser distintos.",
            )

    @staticmethod
    def _validar_coherencia(
        *, estado: str, filas: int, suma: decimal.Decimal, delta: decimal.Decimal
    ) -> None:
        """INV-01 completa, incluida la parte que 0310 no cubre."""
        if estado == ATRIBUCION_NO_DISPONIBLE:
            if filas > 0:
                raise ErrorMotor(
                    CodigoError.NO_DISPONIBLE_CON_FILAS,
                    "NO_DISPONIBLE significa que no se conoce ninguna "
                    "atribucion; con una sola fila conocida ya no aplica.",
                )
            return

        if estado == ATRIBUCION_COMPLETA:
            if suma != delta:
                raise ErrorMotor(
                    CodigoError.SUMA_NO_CUADRA,
                    "COMPLETA exige que la suma atribuida iguale exactamente "
                    "el delta del efecto.",
                )
            return

        # PARCIAL
        if filas == 0:
            raise ErrorMotor(
                CodigoError.SUMA_NO_CUADRA,
                "PARCIAL exige atribucion conocida; sin ninguna fila el estado "
                "correcto es NO_DISPONIBLE.",
            )
        if suma != CERO and _signo(suma) != _signo(delta):
            raise ErrorMotor(
                CodigoError.SIGNO_INCOMPATIBLE,
                "La suma atribuida debe mantener el signo del delta.",
            )
        if abs(suma) > abs(delta):
            raise ErrorMotor(
                CodigoError.SUMA_NO_CUADRA,
                "La suma atribuida no puede superar en valor absoluto el delta.",
            )
        if suma == delta:
            raise ErrorMotor(
                CodigoError.SUMA_NO_CUADRA,
                "Si el reparto conocido cubre exactamente el delta, el estado "
                "correcto es COMPLETA, no PARCIAL.",
            )

    def _ejecutar(
        self, contexto: ContextoOperacion, operacion: Any, nombre: str
    ) -> ResultadoOperacionEfectos:
        resultado = self._unidad.ejecutar_con_traza(
            contexto, operacion, nombre=nombre
        )
        self.ultima_traza = resultado.traza
        return resultado.valor
