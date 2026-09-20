# ============================================================
# GAPTO MOBILE 2027
# Fichero: hechos_service.py
# Ruta: backend/app/services/hechos_service.py
# Descripcion: Primer write-path productivo del motor financiero.
#
#     OP-01  crear hecho
#     OP-02  corregir un error de captura
#     OP-03  anular un hecho que nunca debio existir
#
#   Cada operacion es UNA transaccion completa: mutacion + control de
#   row_version + auditoria + contexto tenant viven o mueren juntos.
#
#   Frontera con F04-02 respetada expresamente: este servicio NO crea, lee
#   para decidir, ni modifica efectos economicos, atribuciones, aportaciones ni
#   tesoreria. Solo comprueba su EXISTENCIA en dos puntos, y en ambos para
#   negarse a seguir, nunca para decidir su semantica:
#     - OP-02, al corregir tipo_hecho_id con efectos dependientes: F04-D004
#       prohibe el cambio escalar y reserva la correccion agregada a F04-06,
#       asi que se falla cerrado en vez de recalcular nada;
#     - OP-03, ante realidad ya vinculada: entonces el hecho ocurrio y lo que
#       corresponde es devolucion o reversion, que pertenecen a F04-06.
# Version: 0.6.0
#   0.6.0 (F04-D036): OP-02 no puede corregir `moneda` si el estado final
#   dejaria un efecto del hecho dentro del saldo de una posicion de otra
#   moneda. La guarda es hermana de la de `tipo_hecho_id`: el campo NO pasa
#   a ser inmutable, solo deja de ser corregible escalarmente cuando existe
#   una dependencia con ancla monetaria propia.
# Version: 0.5.0
#   0.5.0 (F04-05, auditoria): OP-02 y OP-03 dejan de hacer rollback por una
#   cadena RODANTE no propagable. Conforme a F04-D022 confirman la correccion,
#   propagan lo seguro y devuelven `requiere_revision` con motivo estable e
#   identificadores afectados. El colaborador pasa a ser OBLIGATORIO.
# Version: 0.4.0
#   0.4.0 (F04-05): la guarda de ancla se INYECTA como colaborador en vez de
#   importar el repositorio de previsiones, y se evalua despues del control
#   optimista para que VERSION_DESFASADA conserve su precedencia.
# Version: 0.3.0
#   0.3.0 (F04-05): OP-02 falla cerrado al corregir la fecha economica de un
#   hecho que ancla una cadena RODANTE con sucesor. Cambio minimo y trazado;
#   ninguna otra semantica de OP-01/02/03 se altera.
# Version: 0.2.0
#   0.2.0 (F04-02): F04-D004 materializada. El error transitorio
#   DECISION_DIFERIDA_F04_02 se sustituye por CORRECCION_AGREGADA_REQUERIDA.
#   Ninguna otra semantica de OP-01/02/03 cambia.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import decimal
import json
import re
import uuid
from typing import Any, Callable

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import (
    CamposCorreccion,
    DatosCreacionHecho,
    ESTADO_ACTIVO,
    ESTADO_ANULADO,
    ESTADOS_LOCALIZACION,
    ResultadoHecho,
)
from app.core.unidad_trabajo import SesionMotor, Traza, UnidadDeTrabajo
from app.repositories import auditoria_repository as auditoria
from app.repositories import hechos_repository as repo
from app.services import coherencia_posicion

_MONEDA_VALIDA = re.compile(r"^[A-Z]{3}$")


def _a_dict(snapshot_json: str) -> dict[str, Any]:
    """Deserializa conservando exactitud decimal.

    `parse_float=Decimal` evita que importe_total pase por float: un importe
    financiero no puede cruzar una representacion binaria aproximada ni
    siquiera para mostrarse.
    """
    return json.loads(snapshot_json, parse_float=decimal.Decimal)


def _motivo_obligatorio(motivo: str | None, operacion: str) -> str:
    if motivo is None or not motivo.strip():
        raise ErrorMotor(
            CodigoError.MOTIVO_AUSENTE,
            f"{operacion} exige un motivo explicito.",
        )
    return motivo.strip()


class HechosService:
    """Casos de uso de F04-01 sobre gapto.hechos_financieros."""

    __slots__ = ("_unidad", "ultima_traza", "_impacto_ancla")

    def __init__(
        self,
        unidad: UnidadDeTrabajo,
        *,
        impacto_ancla: Callable[[SesionMotor, uuid.UUID], dict[str, Any]],
    ) -> None:
        """`impacto_ancla` es un colaborador INYECTADO y OBLIGATORIO.

        F04-D022 exige que OP-02 y OP-03 CONFIRMEN la correccion de la realidad
        y devuelvan el impacto derivado sobre la cadena RODANTE. Esa logica
        pertenece al dominio de previsiones, de modo que se inyecta: este
        servicio —cerrado en F04-01— no importa nada de F04-05 y no se traslada
        SQL de previsiones al repositorio de hechos.

        Es obligatorio a proposito. Si fuese opcional, una construccion que lo
        omitiese dejaria a OP-02/OP-03 incumpliendo D-022 en silencio, y ese
        incumplimiento no se veria en ninguna prueba del propio servicio.
        """
        self._unidad = unidad
        self.ultima_traza: Traza | None = None
        self._impacto_ancla = impacto_ancla

    # ------------------------------------------------------------------
    # OP-01 — CREAR HECHO
    # ------------------------------------------------------------------
    def crear_hecho(
        self, contexto: ContextoOperacion, datos: DatosCreacionHecho
    ) -> ResultadoHecho:
        """Registra un acontecimiento economico real.

        Idempotente por la identidad reservada: reintentar con el MISMO UUID
        tras un COMMIT de resultado desconocido no crea un segundo hecho.
        """
        self._validar_creacion(datos)

        def operacion(sesion: SesionMotor) -> ResultadoHecho:
            repo.exigir_contexto(sesion)
            tipo_hecho_id = repo.resolver_tipo_hecho(
                sesion,
                codigo=datos.tipo_hecho_codigo,
                tipo_hecho_id=datos.tipo_hecho_id,
            )

            creado = repo.insertar_si_no_existe(sesion, datos, tipo_hecho_id)
            if creado is not None:
                row_version, estado, snapshot = creado
                auditoria.registrar(
                    sesion,
                    tabla=repo.TABLA,
                    registro_id=datos.hecho_id,
                    accion=auditoria.ACCION_CREAR,
                    datos_despues_json=snapshot,
                )
                return ResultadoHecho(
                    hecho_id=datos.hecho_id,
                    row_version=row_version,
                    estado=estado,
                    idempotente=False,
                    snapshot=_a_dict(snapshot),
                )

            # El UUID ya estaba ocupado. Solo se acepta como exito si puede
            # demostrarse que corresponde a la MISMA intencion de creacion.
            if repo.creacion_previa_coincide(sesion, datos, tipo_hecho_id):
                actual = repo.leer_estado(sesion, datos.hecho_id)
                if actual is None:  # pragma: no cover - incoherencia imposible
                    raise ErrorMotor(
                        CodigoError.INTERNO,
                        "La auditoria de creacion existe pero el hecho no es visible.",
                    )
                row_version, estado, snapshot = actual
                return ResultadoHecho(
                    hecho_id=datos.hecho_id,
                    row_version=row_version,
                    estado=estado,
                    idempotente=True,
                    snapshot=_a_dict(snapshot),
                )

            raise ErrorMotor(
                CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                "El identificador reservado ya esta en uso con otra intencion "
                "de creacion.",
            )

        return self._ejecutar(contexto, operacion, "OP-01 crear_hecho")

    # ------------------------------------------------------------------
    # OP-02 — CORREGIR ERROR DE CAPTURA
    # ------------------------------------------------------------------
    def corregir_hecho(
        self,
        contexto: ContextoOperacion,
        *,
        hecho_id: uuid.UUID,
        row_version_esperada: int,
        campos: CamposCorreccion,
        motivo: str | None,
    ) -> ResultadoHecho:
        """Corrige un dato que NUNCA fue cierto.

        No sirve para representar algo que cambio despues: los campos que
        expresarian eso (`estado`, `anulado_at`, `motivo_anulacion`) los
        rechaza `CamposCorreccion.desde_dict`, y el propio DTO no los expone.
        """
        motivo_limpio = _motivo_obligatorio(motivo, "La correccion de captura")
        cambios = campos.solicitados()
        if not cambios:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Una correccion debe indicar al menos un campo a corregir.",
            )

        def operacion(sesion: SesionMotor) -> ResultadoHecho:
            repo.exigir_contexto(sesion)

            actual = repo.leer_estado(sesion, hecho_id)
            if actual is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "El hecho indicado no existe o no es accesible.",
                )
            row_version_actual, estado_actual, snapshot_previo = actual

            if "tipo_hecho_id" in cambios and cambios["tipo_hecho_id"] is not None:
                repo.resolver_tipo_hecho(
                    sesion, codigo=None, tipo_hecho_id=cambios["tipo_hecho_id"]
                )

            if estado_actual != ESTADO_ACTIVO:
                raise ErrorMotor(
                    CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
                    "Un hecho anulado no admite correccion de captura.",
                )

            if (
                "moneda" in cambios
                and cambios["moneda"] is not None
                and cambios["moneda"] != _a_dict(snapshot_previo).get("moneda")
            ):
                coherencia_posicion.exigir_moneda_corregible(
                    sesion, hecho_id=hecho_id, moneda_candidata=cambios["moneda"]
                )

            if "tipo_hecho_id" in cambios and repo.tiene_efectos(sesion, hecho_id):
                raise ErrorMotor(
                    CodigoError.CORRECCION_AGREGADA_REQUERIDA,
                    "Corregir el tipo de un hecho con efectos dependientes "
                    "exige una correccion agregada explicita; el cambio "
                    "escalar no puede reinterpretar los efectos ya "
                    "materializados.",
                )

            if row_version_actual != row_version_esperada:
                if repo.correccion_ya_aplicada(
                    sesion,
                    hecho_id,
                    contexto.request_id,
                    cambios,
                    snapshot_previo,
                ):
                    return ResultadoHecho(
                        hecho_id=hecho_id,
                        row_version=row_version_actual,
                        estado=estado_actual,
                        idempotente=True,
                        snapshot=_a_dict(snapshot_previo),
                    )
                raise ErrorMotor(
                    CodigoError.VERSION_DESFASADA,
                    "El hecho ha cambiado desde la version que conoce el llamante.",
                )

            actualizado = repo.actualizar_campos(
                sesion, hecho_id, row_version_esperada, cambios
            )
            if actualizado is None:
                # Alguien gano la carrera entre la lectura y el UPDATE. No se
                # reintenta en silencio: el llamante debe releer y decidir.
                raise ErrorMotor(
                    CodigoError.VERSION_DESFASADA,
                    "El hecho ha cambiado desde la version que conoce el llamante.",
                )
            row_version_nueva, estado_nuevo, snapshot_nuevo = actualizado

            auditoria.registrar(
                sesion,
                tabla=repo.TABLA,
                registro_id=hecho_id,
                accion=auditoria.ACCION_ACTUALIZAR,
                datos_antes_json=snapshot_previo,
                datos_despues_json=snapshot_nuevo,
                motivo=motivo_limpio,
            )

            # F04-D022. La anulacion SIEMPRE confirma. Si el hecho anclaba una
            # cadena RODANTE, la perdida de realidad se expone como impacto
            # DERIVADO —AMB-009— y nunca como rollback de OP-03.
            impacto = self._impacto_ancla(sesion, hecho_id)

            return ResultadoHecho(
                hecho_id=hecho_id,
                row_version=row_version_nueva,
                estado=estado_nuevo,
                idempotente=False,
                snapshot=_a_dict(snapshot_nuevo),
                requiere_revision=impacto["requiere_revision"],
                motivo_revision=impacto["motivo"],
                previsiones_afectadas=impacto["afectadas"],
                previsiones_propagadas=impacto["propagadas"],
            )

        return self._ejecutar(contexto, operacion, "OP-02 corregir_hecho")

    # ------------------------------------------------------------------
    # OP-03 — ANULAR HECHO
    # ------------------------------------------------------------------
    def anular_hecho(
        self,
        contexto: ContextoOperacion,
        *,
        hecho_id: uuid.UUID,
        row_version_esperada: int,
        motivo_anulacion: str | None,
    ) -> ResultadoHecho:
        """Marca ANULADO un hecho que nunca debio existir. No borra nada."""
        motivo_limpio = _motivo_obligatorio(motivo_anulacion, "La anulacion")

        def operacion(sesion: SesionMotor) -> ResultadoHecho:
            repo.exigir_contexto(sesion)

            actual = repo.leer_estado(sesion, hecho_id)
            if actual is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "El hecho indicado no existe o no es accesible.",
                )
            row_version_actual, estado_actual, snapshot_previo = actual

            if estado_actual == ESTADO_ANULADO:
                if repo.anulacion_ya_registrada(
                    sesion, hecho_id, contexto.request_id
                ):
                    return ResultadoHecho(
                        hecho_id=hecho_id,
                        row_version=row_version_actual,
                        estado=estado_actual,
                        idempotente=True,
                        snapshot=_a_dict(snapshot_previo),
                    )
                raise ErrorMotor(
                    CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
                    "El hecho ya esta anulado.",
                )

            if repo.tiene_realidad_asociada(sesion, hecho_id):
                raise ErrorMotor(
                    CodigoError.HECHO_CON_REALIDAD_ASOCIADA,
                    "El hecho tiene realidad vinculada: no es un hecho que "
                    "nunca debio existir.",
                )

            if row_version_actual != row_version_esperada:
                raise ErrorMotor(
                    CodigoError.VERSION_DESFASADA,
                    "El hecho ha cambiado desde la version que conoce el llamante.",
                )

            anulado = repo.anular(
                sesion, hecho_id, row_version_esperada, motivo_limpio
            )
            if anulado is None:
                raise ErrorMotor(
                    CodigoError.VERSION_DESFASADA,
                    "El hecho ha cambiado desde la version que conoce el llamante.",
                )
            row_version_nueva, estado_nuevo, snapshot_nuevo = anulado

            auditoria.registrar(
                sesion,
                tabla=repo.TABLA,
                registro_id=hecho_id,
                accion=auditoria.ACCION_ANULAR,
                datos_antes_json=snapshot_previo,
                datos_despues_json=snapshot_nuevo,
                motivo=motivo_limpio,
            )

            # F04-D022. La anulacion SIEMPRE confirma. Si el hecho anclaba una
            # cadena RODANTE, la perdida de realidad se expone como impacto
            # DERIVADO —AMB-009— y nunca como rollback de OP-03.
            impacto = self._impacto_ancla(sesion, hecho_id)

            return ResultadoHecho(
                hecho_id=hecho_id,
                row_version=row_version_nueva,
                estado=estado_nuevo,
                idempotente=False,
                snapshot=_a_dict(snapshot_nuevo),
                requiere_revision=impacto["requiere_revision"],
                motivo_revision=impacto["motivo"],
                previsiones_afectadas=impacto["afectadas"],
                previsiones_propagadas=impacto["propagadas"],
            )

        return self._ejecutar(contexto, operacion, "OP-03 anular_hecho")

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------
    def _ejecutar(
        self,
        contexto: ContextoOperacion,
        operacion: Any,
        nombre: str,
    ) -> ResultadoHecho:
        resultado = self._unidad.ejecutar_con_traza(
            contexto, operacion, nombre=nombre
        )
        self.ultima_traza = resultado.traza
        return resultado.valor

    @staticmethod
    def _validar_creacion(datos: DatosCreacionHecho) -> None:
        """Validaciones que no necesitan base de datos.

        La coherencia localizacion/localidad NO se valida aqui: ya vive como
        CHECK declarativo en la migration 0040 y duplicarla en Python crearia
        dos fuentes de verdad que pueden divergir. Se deja que falle en la BD y
        se traduce a VIOLACION_INVARIANTE_FISICA.
        """
        if datos.fecha_hecho is None:
            raise ErrorMotor(
                CodigoError.FECHA_ECONOMICA_AUSENTE,
                "Un hecho exige fecha economica; no se sustituye por la fecha "
                "de captura.",
            )
        if datos.moneda is None or not _MONEDA_VALIDA.match(datos.moneda):
            raise ErrorMotor(
                CodigoError.MONEDA_INVALIDA,
                "La moneda debe ser un codigo de tres letras mayusculas.",
            )
        if datos.presupuestable is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "`presupuestable` no tiene default: debe indicarse.",
            )
        if datos.estado_localizacion not in ESTADOS_LOCALIZACION:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "estado_localizacion debe ser CONOCIDA, DESCONOCIDA o "
                "NO_APLICA. NO_APLICA no es el default de 'no informado'.",
            )
