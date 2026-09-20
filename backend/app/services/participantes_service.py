# ============================================================
# GAPTO MOBILE 2027
# Fichero: participantes_service.py
# Ruta: backend/app/services/participantes_service.py
# Descripcion: Writer de `hecho_participantes` (F04-D038 §9, §10, §11, §24).
#
#   QUE REPRESENTA. Actores identificados que participaron en el
#   acontecimiento. Nada mas. Un participante NO implica atribucion economica,
#   aportacion, pago, posicion, propiedad, derecho ni obligacion: cada una de
#   esas dimensiones vive en su propia superficie y exige su propia decision.
#   Estar en una cena no significa deber nada por ella.
#
#   VOCABULARIO. DB Schema declara `rol` como vocabulario deliberadamente
#   extensible: no hay CHECK ni catalogo fisico y F04-07 no crea ninguno. El
#   conjunto operativo admitido por ESTA version es un unico token,
#   `PARTICIPANTE`, que significa exclusivamente "actor identificado que
#   participo". No se admiten `PAGADOR` ni `INVITADO` ni equivalentes: serian
#   nombres nuevos para dimensiones que ya representan
#   `hecho_aportaciones_pago` y `efecto_atribuciones`, y tener dos sitios donde
#   leer quien pago es la puerta de entrada al doble conteo. El registro puede
#   ampliarse sin DDL en fases posteriores cuando exista semantica real.
#
#   ENRIQUECIMIENTO POSTERIOR. Conocer mas tarde la identidad de alguien que
#   siempre estuvo alli no es realidad suplementaria (OP-18) ni crea hecho
#   economico nuevo: es enriquecimiento descriptivo del hecho existente, y por
#   eso se hace con este mismo writer bajo lock de raiz, `row_version` y
#   auditoria. Si en cambio una fila existente era FALSA, retirarla es
#   correccion y no le corresponde a este writer.
#
#   CONCURRENCIA. El root es `hechos_financieros`. La version se consume con
#   `tocar_raiz`, cuya guarda vive en el WHERE del UPDATE, y eso deja la raiz
#   bloqueada para el resto de la transaccion. La coherencia del recuento se
#   evalua DESPUES de insertar, ya con el lock tomado: es lo que impide que dos
#   transacciones concurrentes confirmen dos personas distintas contra un total
#   de uno.
#   RETIRADA LOCAL. Si una fila nunca debio existir, se retira aqui y no por
#   OP-21: OP-21 gobierna la correccion AGREGADA y las superficies que su
#   contrato expone, y convertirlo en agregador universal de cualquier tabla
#   que el motor incorpore despues ampliaria su superficie sin aportar ninguna
#   garantia que una correccion local bien auditada no de ya. La frontera es
#   nitida: si la unica realidad falsa es la asociacion de participante, se
#   corrige aqui; si hace falta confirmar de forma indivisible ademas otra
#   superficie financiera del agregado, esta operacion NO debe usarse para
#   simular una correccion agregada.
#
#   Retirar no es "quitar de la lista". Significa que esa asociacion NUNCA fue
#   verdadera, y por eso exige motivo explicito y conserva el snapshot completo
#   de la fila eliminada: el dato sale del estado actual, la evidencia de que
#   se capturo mal no desaparece.
#
#   Y retirar a alguien NO decrementa `numero_participantes_total`. Si la cena
#   declaraba ocho y Pedro nunca estuvo, puede que Pedro ocupase erroneamente
#   el hueco de uno de los desconocidos: siguen siendo ocho. Si el total
#   tambien era falso, se corrige aparte y a proposito.
#
# Version: 0.2.0
#   0.2.0 (F04-D038 enmienda §11): retirada local de participante falso.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.unidad_trabajo import SesionMotor, UnidadDeTrabajo
from app.repositories import auditoria_repository as auditoria
from app.repositories import efectos_repository as repo_efectos
from app.repositories import hechos_repository as repo_hechos
from app.repositories import participantes_repository as repo_part
from app.services import coherencia_participantes

ROL_PARTICIPANTE = "PARTICIPANTE"

#: Vocabulario operativo de ESTA version del motor. Ampliable sin DDL.
ROLES_OPERATIVOS: frozenset[str] = frozenset({ROL_PARTICIPANTE})

ESTADO_ACTIVO = "ACTIVO"
_LONGITUD_MAXIMA_ROL = 40


@dataclass(frozen=True, slots=True)
class DatosParticipante:
    """Un actor identificado del acontecimiento.

    `participante_id` lo reserva el llamante, como el resto del motor: es lo
    que hace seguro el reintento tras un COMMIT de resultado desconocido.
    """

    participante_id: uuid.UUID
    actor_id: uuid.UUID
    rol: str = ROL_PARTICIPANTE


@dataclass(frozen=True, slots=True)
class ResultadoParticipantes:
    hecho_id: uuid.UUID
    row_version: int
    participantes_creados: int
    identificados: int
    total_declarado: int | None
    idempotente: bool = False
    snapshots: tuple[dict[str, Any], ...] = field(default_factory=tuple)


class ParticipantesService:
    """Writer de participantes identificados."""

    def __init__(self, unidad: UnidadDeTrabajo) -> None:
        self._unidad = unidad
        self.ultima_traza: Any = None

    # ==================================================================
    # Operacion publica
    # ==================================================================
    def registrar_participantes(
        self,
        contexto: ContextoOperacion,
        *,
        hecho_id: uuid.UUID,
        row_version_esperada: int,
        participantes: Sequence[DatosParticipante],
    ) -> ResultadoParticipantes:
        """Anade 1..N participantes identificados a un hecho existente."""
        if not participantes:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Registrar participantes exige al menos uno.",
            )
        normalizados = tuple(self._normalizar(p) for p in participantes)
        self._validar_identidades_unicas(normalizados)
        self._validar_sin_duplicados_logicos(normalizados)

        def operacion(sesion: SesionMotor) -> ResultadoParticipantes:
            repo_hechos.exigir_contexto(sesion)
            estado = self._exigir_hecho_activo(sesion, hecho_id)
            self._exigir_actores_conocidos(
                sesion, [p.actor_id for p in normalizados]
            )

            clasificacion = self._clasificar_replay(sesion, normalizados, hecho_id)
            if clasificacion == "REPLICA":
                # Un reintento demostrado no vuelve a consumir version: la que
                # el llamante conoce seguiria siendo valida y romperla aqui le
                # haria creer que alguien mas escribio.
                visible, total = repo_part.total_declarado(sesion, hecho_id)
                return ResultadoParticipantes(
                    hecho_id=hecho_id,
                    row_version=estado[0],
                    participantes_creados=0,
                    identificados=repo_part.recuento_identificados(sesion, hecho_id),
                    total_declarado=total,
                    idempotente=True,
                )
            if clasificacion == "CONFLICTO":
                raise ErrorMotor(
                    CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                    "Alguno de los identificadores reservados ya esta en uso "
                    "con otra intencion.",
                )

            self._exigir_sin_participacion_previa(sesion, hecho_id, normalizados)
            nueva_version = self._tocar_raiz(sesion, hecho_id, row_version_esperada)

            snapshots: list[dict[str, Any]] = []
            for participante in normalizados:
                snapshot = repo_part.insertar_participante_si_no_existe(
                    sesion,
                    participante_id=participante.participante_id,
                    hecho_id=hecho_id,
                    actor_id=participante.actor_id,
                    rol=participante.rol,
                )
                if snapshot is None:
                    raise ErrorMotor(
                        CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                        "El identificador reservado del participante ya esta "
                        "en uso.",
                    )
                auditoria.registrar(
                    sesion,
                    tabla=repo_part.TABLA_PARTICIPANTES,
                    registro_id=participante.participante_id,
                    accion=auditoria.ACCION_CREAR,
                    datos_despues_json=snapshot,
                    motivo="Participante identificado del acontecimiento.",
                )
                snapshots.append({"id": str(participante.participante_id)})

            # Estado FINAL, con la raiz ya bloqueada por `tocar_raiz`.
            coherencia_participantes.exigir_recuento_coherente(
                sesion, hecho_id=hecho_id
            )
            _, total = repo_part.total_declarado(sesion, hecho_id)
            return ResultadoParticipantes(
                hecho_id=hecho_id,
                row_version=nueva_version,
                participantes_creados=len(normalizados),
                identificados=repo_part.recuento_identificados(sesion, hecho_id),
                total_declarado=total,
                snapshots=tuple(snapshots),
            )

        resultado = self._unidad.ejecutar_con_traza(
            contexto, operacion, nombre="F04-07 registrar_participantes"
        )
        self.ultima_traza = resultado.traza
        return resultado.valor

    def retirar_participante(
        self,
        contexto: ContextoOperacion,
        *,
        hecho_id: uuid.UUID,
        participante_id: uuid.UUID,
        row_version_esperada: int,
        motivo: str,
    ) -> ResultadoParticipantes:
        """Retira una asociacion que nunca fue verdadera."""
        if motivo is None or not motivo.strip():
            raise ErrorMotor(
                CodigoError.MOTIVO_AUSENTE,
                "Retirar un participante exige motivo explicito: se esta "
                "afirmando que esa asociacion nunca fue verdadera.",
            )

        def operacion(sesion: SesionMotor) -> ResultadoParticipantes:
            repo_hechos.exigir_contexto(sesion)
            self._exigir_hecho_activo(sesion, hecho_id)

            # Se comprueba ANTES de consumir version: si la fila no existe o
            # es de otro hecho, el agregado no debe quedar tocado.
            fila = repo_part.leer_participante(sesion, participante_id)
            if fila is None or fila[0] != hecho_id:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "El participante indicado no existe en ese hecho o no es "
                    "accesible.",
                )

            nueva_version = self._tocar_raiz(sesion, hecho_id, row_version_esperada)

            snapshot = repo_part.eliminar_participante(
                sesion, participante_id=participante_id, hecho_id=hecho_id
            )
            if snapshot is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "El participante indicado no existe en ese hecho o no es "
                    "accesible.",
                )
            # El snapshot es la UNICA prueba que queda de esa fila.
            auditoria.registrar(
                sesion,
                tabla=repo_part.TABLA_PARTICIPANTES,
                registro_id=participante_id,
                accion=auditoria.ACCION_ANULAR,
                datos_antes_json=snapshot,
                motivo=motivo,
            )

            # Mismo protocolo que el alta aunque un DELETE normalmente reduzca
            # el recuento: un unico camino de revalidacion es mas facil de
            # sostener que dos con excepciones.
            coherencia_participantes.exigir_recuento_coherente(
                sesion, hecho_id=hecho_id
            )
            _, total = repo_part.total_declarado(sesion, hecho_id)
            return ResultadoParticipantes(
                hecho_id=hecho_id,
                row_version=nueva_version,
                participantes_creados=0,
                identificados=repo_part.recuento_identificados(sesion, hecho_id),
                total_declarado=total,
            )

        resultado = self._unidad.ejecutar_con_traza(
            contexto, operacion, nombre="F04-07 retirar_participante"
        )
        self.ultima_traza = resultado.traza
        return resultado.valor

    # ==================================================================
    # Interno — validacion sin base de datos
    # ==================================================================
    @staticmethod
    def _normalizar(participante: DatosParticipante) -> DatosParticipante:
        """Normaliza y valida el rol antes de tocar la base.

        El token se persiste ya normalizado. Aceptar texto libre del cliente
        convertiria la UNIQUE (hecho, actor, rol) en papel mojado: `PARTICIPANTE`
        y `participante` serian dos filas distintas para la misma persona.
        """
        if participante.participante_id is None or participante.actor_id is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Un participante exige identidad reservada y actor.",
            )
        crudo = (participante.rol or "").strip().upper().replace(" ", "_")
        if not crudo or len(crudo) > _LONGITUD_MAXIMA_ROL:
            raise ErrorMotor(
                CodigoError.ROL_PARTICIPANTE_INVALIDO,
                "El rol de participante es obligatorio y no puede exceder "
                f"{_LONGITUD_MAXIMA_ROL} caracteres.",
            )
        if crudo not in ROLES_OPERATIVOS:
            raise ErrorMotor(
                CodigoError.ROL_PARTICIPANTE_INVALIDO,
                f"El rol '{crudo}' no pertenece al vocabulario operativo de "
                "esta version. Participar no describe quien pago ni quien "
                "soporto el gasto: eso vive en aportaciones y atribuciones.",
            )
        if crudo == participante.rol:
            return participante
        return DatosParticipante(
            participante_id=participante.participante_id,
            actor_id=participante.actor_id,
            rol=crudo,
        )

    @staticmethod
    def _validar_identidades_unicas(
        participantes: Sequence[DatosParticipante],
    ) -> None:
        vistos = {p.participante_id for p in participantes}
        if len(vistos) != len(participantes):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Un lote no puede repetir la misma identidad reservada.",
            )

    @staticmethod
    def _validar_sin_duplicados_logicos(
        participantes: Sequence[DatosParticipante],
    ) -> None:
        ternas = {(p.actor_id, p.rol) for p in participantes}
        if len(ternas) != len(participantes):
            raise ErrorMotor(
                CodigoError.PARTICIPANTE_DUPLICADO,
                "El lote repite el mismo actor con el mismo rol.",
            )

    # ==================================================================
    # Interno — base de datos
    # ==================================================================
    def _exigir_hecho_activo(
        self, sesion: SesionMotor, hecho_id: uuid.UUID
    ) -> tuple[Any, ...]:
        estado = repo_hechos.leer_estado(sesion, hecho_id)
        if estado is None:
            raise ErrorMotor(
                CodigoError.AGREGADO_NO_ENCONTRADO,
                "El hecho indicado no existe o no es accesible.",
            )
        if estado[1] != ESTADO_ACTIVO:
            raise ErrorMotor(
                CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
                "Un hecho anulado no admite participantes nuevos.",
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

    def _exigir_sin_participacion_previa(
        self,
        sesion: SesionMotor,
        hecho_id: uuid.UUID,
        participantes: Sequence[DatosParticipante],
    ) -> None:
        """Duplicado logico devuelto como error de dominio.

        La UNIQUE fisica ya lo impediria, pero afloraria como violacion de
        constraint traducida a VIOLACION_INVARIANTE_FISICA y expondria el
        nombre del indice como si fuese contrato de API.
        """
        for participante in participantes:
            ocupada = repo_part.participacion_existente(
                sesion,
                hecho_id=hecho_id,
                actor_id=participante.actor_id,
                rol=participante.rol,
            )
            if ocupada is not None:
                raise ErrorMotor(
                    CodigoError.PARTICIPANTE_DUPLICADO,
                    "Ese actor ya consta como participante del hecho con ese "
                    "rol.",
                )

    def _clasificar_replay(
        self,
        sesion: SesionMotor,
        participantes: Sequence[DatosParticipante],
        hecho_id: uuid.UUID,
    ) -> str:
        """NUEVO, REPLICA o CONFLICTO para el lote.

        Un lote es atomico y no puede haberse aplicado a medias. Si unos
        identificadores existen y otros no, no es un reintento: es reuso de
        identidad.
        """
        existentes = 0
        coincidentes = 0
        for participante in participantes:
            fila = repo_part.leer_participante(sesion, participante.participante_id)
            if fila is None:
                continue
            existentes += 1
            if (
                fila[0] == hecho_id
                and fila[1] == participante.actor_id
                and fila[2] == participante.rol
            ):
                coincidentes += 1
        if existentes == 0:
            return "NUEVO"
        if existentes == len(participantes) and coincidentes == existentes:
            return "REPLICA"
        return "CONFLICTO"

    def _tocar_raiz(
        self, sesion: SesionMotor, hecho_id: uuid.UUID, row_version_esperada: int
    ) -> int:
        nueva = repo_hechos.tocar_raiz(sesion, hecho_id, row_version_esperada)
        if nueva is None:
            raise ErrorMotor(
                CodigoError.VERSION_DESFASADA,
                "El hecho ha cambiado desde la version que conoce el llamante.",
            )
        return nueva
