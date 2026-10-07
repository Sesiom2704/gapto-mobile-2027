# ============================================================
# GAPTO MOBILE 2027
# Fichero: posiciones_service.py
# Ruta: backend/app/services/posiciones_service.py
# Descripcion: F04-04. Derechos de cobro, obligaciones, reembolsos y
#   condonaciones.
#
#   Reutiliza la infraestructura cerrada en F04-01: una transaccion por
#   operacion, contexto tenant dentro de ella, auditoria via
#   `fn_registrar_auditoria`, retry completo y la misma taxonomia de errores.
#   No se abre una UnidadDeTrabajo dentro de otra: las operaciones compuestas
#   orquestan repositorios dentro de UNA transaccion.
#
#   INV-04 · UNA POSICION NUNCA SE INFIERE. No nace de una diferencia entre
#   atribucion y aportacion, ni de la participacion de cuenta, ni de un saldo
#   neto entre actores. Nace porque el llamante declara DECISION_EXPLICITA,
#   REGLA o CONTRATO. Este servicio no lee ninguna de esas fuentes: nada que no
#   venga en la entrada llega a la base.
#
#   INV-17 · SALDO CONOCIDO FRENTE A INDETERMINADO. El saldo no se persiste. Si
#   `saldo_apertura IS NULL` el saldo es INDETERMINADO y lo sigue siendo aunque
#   haya deltas posteriores: sobre una posicion historica desconocida se puede
#   registrar un reembolso observado de 20, pero el resultado NO es -20. El
#   tipo `Saldo` hace imposible la aritmetica en ese caso.
#
#   INV-10 · SIN COMPENSACION EXTINTIVA. Dos posiciones opuestas conviven
#   aunque su neto calculado sea cero. Aqui no se extinguen, no se reescriben
#   importes y no se crea hecho de compensacion.
#
#   ORDEN DE RAICES (mandato 34): hecho -> movimiento -> entidad, tomando solo
#   las que YA EXISTEN. Una raiz creada en la propia operacion no tiene version
#   previa que bloquear, de modo que en un reembolso con movimiento nuevo el
#   orden efectivo es simplemente "entidad".
#
#   IDEMPOTENCIA ANTES QUE VERSION (mandato 32). A diferencia de F04-02 y
#   F04-03, aqui la deteccion de reintento exacto ocurre ANTES de la guarda de
#   version. El motivo: si el COMMIT confirmo y el cliente perdio la respuesta,
#   `entidades.row_version` ya avanzo; comprobar la version primero convertiria
#   un reintento legitimo en VERSION_DESFASADA y el cliente reintentaria en
#   bucle o, peor, duplicaria la realidad con UUID nuevos. La asimetria es
#   deliberada y esta documentada.
#
#   F04-D036 anade la guarda de coherencia posicion <-> efecto en los dos
#   puntos que le pertenecen: el unico writer del vinculo (`_crear_delta`) y
#   el calculo de saldo, que falla cerrado antes que devolver un numero
#   derivado de un estado invalido.
#
#   F04-D052 · CAUSA DE REDUCCION. Toda reduccion nueva declara su causa del
#   vocabulario cerrado `CausaReduccion` y tiene una sola forma fisica:
#     PAGO (OP-12B)        REEMBOLSO + movimiento en cuenta Gapto
#     COBRO (OP-14)        REEMBOLSO + movimiento en cuenta Gapto
#     CONDONACION          CONDONACION (D-201) sin movimiento
#   La causa no se persiste como columna: la determinan arquetipo y
#   movimiento, y `causas_de_reduccion` la reconstruye en lectura. Una
#   reduccion con GENERACION_DERECHO_OBLIGACION (historica o migrada) se lee
#   como NO_DETERMINABLE, sin fecha ni procedencia como discriminante.
#   GENERACION_DERECHO_OBLIGACION queda para la creacion e incremento.
#
#   F04-D055 · CICLO DE VIDA. Con saldo determinado un cierre exige saldo
#   canonico resultante exactamente 0 (A1), por las dos vias; solo LIQUIDADA
#   y CONDONADA en runtime (A2); con saldo indeterminado, cierre por
#   declaracion sin residual (A3). Dos saldos y nunca uno por otro (A4):
#   `_calcular_saldo` es el CANONICO (exceso, A1; F04-D053 tiene su propio
#   SQL) y `_saldo_de_lectura` solo alimenta `ResultadoPosicion`.
# Version: 0.6.0
#   0.6.0 (F04-D055 B1 · Parte A): A1 en `cerrar_posicion` (bajo la raiz,
#   antes de `_cerrar`) y en `_aplicar_delta` con cierre (tras `_cerrar`,
#   sobre la posicion releida); A2 en `cerrar_posicion`; R-Q1 (motivo
#   determinado por el conjunto de causas de la ventana A1, con la misma
#   clasificacion que `causas_de_reduccion`, extraida a `_causas_leidas`);
#   A4 con `_saldo_de_lectura` y `apertura_indeterminada`.
# Version: 0.5.0
#   0.5.0 (F04-D053 B1 · B8): `_aplicar_delta` adquiere advisory D-080 y la
#   raiz de la posicion ANTES de leer el saldo y de bloquear el movimiento;
#   `cerrar_posicion` adquiere la raiz antes de leer. B1: foto previa, B4 y
#   validacion del estado final en `_aplicar_delta`; B4 en el alta (OP-12A y
#   via OP-22). A1 llega por `saldo_deltas`.
# Version: 0.4.0
#   0.4.0 (F04-D052 B2): causa obligatoria y validada antes de escribir en
#   `_aplicar_delta`; OP-12B y OP-14 exigen cuenta Gapto (supera F04-D015 §4
#   para operaciones nuevas) y OP-12B pasa a REEMBOLSO; pago por tercero en
#   OP-12B -> STOP (R-F04-038); `condonar_derecho` pasa a CONDONACION y una
#   obligacion es NATURALEZA_INCOMPATIBLE (se retira el STOP de F04-D015 §8);
#   nueva `condonar_obligacion` (CONDONACION, sin movimiento, INGRESO solo
#   declarado con el contrato de E01); en una reduccion con cierre declarado
#   el motivo corresponde a la causa (LIQUIDADA / CONDONADA); lectura
#   `causas_de_reduccion`. Las financiaciones formales quedan fuera por
#   construccion: `leer_posicion` solo lee el subtipo de posicion generica.
# Version: 0.3.0
#   0.3.0 (mandato F04 R1+R2 v0.3 §8/§9 + E01, SOLO `condonar_derecho` y
#   soporte privado inseparable): con GASTO declarado la condonacion exige
#   `presupuestable` explicito y localizacion aplicable (sin dato ->
#   DESCONOCIDA; NO_APLICA -> ENTRADA_INVALIDA); ya no hereda los valores
#   fijos de posicion. `_aplicar_delta` y `_crear_hecho` reciben parametros
#   opcionales cuyos defaults son EXACTAMENTE los anteriores
#   (PRESUPUESTABLE_POSICION / LOCALIZACION_POSICION / sin localidad / sin
#   comprobacion adicional de replay): el resto de operaciones de posiciones no
#   los pasa y su comportamiento observable no cambia. El replay de la
#   condonacion compara ademas la decision persistida del hecho.
# Version: 0.2.0
#   0.2.0 (F04-D036): coherencia monetaria del vinculo y saldo fail-closed.
# Version: 0.1.0
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import json
import re
import uuid
from typing import Any, Callable, Sequence

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos import DatosCreacionHecho, ESTADO_ACTIVO, ESTADOS_LOCALIZACION
from app.core.modelos_posicion import (
    CAUSA_NO_DETERMINABLE,
    CERO,
    CausaLeida,
    CausaReduccion,
    DatosAltaPosicion,
    DatosCierre,
    DatosCondonacion,
    DatosCondonacionObligacion,
    DatosDeltaPosicion,
    DatosReembolso,
    EFECTO_DE_POSICION,
    ESTADO_CERRADA,
    JUSTIFICACIONES,
    MOTIVO_CONDONADA,
    MOTIVO_LIQUIDADA,
    MOTIVOS_CIERRE,
    MOTIVOS_CIERRE_RUNTIME,
    RELACION_ENTIDAD_GENERADO_POR,
    RELACION_HECHO_REEMBOLSO_DE,
    ResultadoPosicion,
    Saldo,
    TIPO_DERECHO,
    TIPO_ENTIDAD_POSICION,
    TIPO_HECHO_CONDONACION,
    TIPO_HECHO_POSICION,
    TIPO_HECHO_REEMBOLSO,
    TIPO_OBLIGACION,
    TIPOS_POSICION,
)
from app.core.modelos_tesoreria import DatosConciliacion, DatosMovimiento
from app.core.unidad_trabajo import SesionMotor, Traza, UnidadDeTrabajo
from app.repositories import auditoria_repository as auditoria
from app.repositories import efectos_repository as repo_efectos
from app.repositories import hechos_repository as repo_hechos
from app.repositories import posiciones_repository as repo_pos
from app.services import coherencia_posicion, integridad_posicion
from app.repositories import tesoreria_repository as repo_tes

_MONEDA_VALIDA = re.compile(r"^[A-Z]{3}$")

# Un hecho de posicion no tiene localizacion: NO_APLICA es aqui su significado
# literal, no un sustituto de "no informado". Y no es presupuestable: la
# generacion o reduccion de una posicion no es un gasto planificable.
LOCALIZACION_POSICION = "NO_APLICA"
PRESUPUESTABLE_POSICION = False

# Los efectos de posicion nacen sin atribucion conocida: quien soporta
# economicamente la porcion es una dimension distinta (F04-02) y no se inventa
# aqui. OP-05 puede enriquecerla despues.
ATRIBUCION_INICIAL = "NO_DISPONIBLE"

# F04-D052. Motivo de cierre que corresponde a cada causa cuando la reduccion
# declara cierre: un pago o cobro liquida, una condonacion condona. Cerrar
# una condonacion como LIQUIDADA (o al reves) contradiria su forma fisica.
MOTIVO_CIERRE_DE_CAUSA = {
    CausaReduccion.PAGO: MOTIVO_LIQUIDADA,
    CausaReduccion.COBRO: MOTIVO_LIQUIDADA,
    CausaReduccion.CONDONACION: MOTIVO_CONDONADA,
}


class PosicionesService:
    """Casos de uso de F04-04."""

    __slots__ = ("_unidad", "ultima_traza")

    def __init__(self, unidad: UnidadDeTrabajo) -> None:
        self._unidad = unidad
        self.ultima_traza: Traza | None = None

    # ==================================================================
    # OP-12A — CREAR POSICION
    # ==================================================================
    def crear_posicion(
        self, contexto: ContextoOperacion, datos: DatosAltaPosicion
    ) -> ResultadoPosicion:
        """Alta atomica de entidad + subtipo + efecto causal + vinculo."""
        self._validar_alta(datos)

        def operacion(sesion: SesionMotor) -> ResultadoPosicion:
            repo_hechos.exigir_contexto(sesion)
            self._exigir_contraparte(sesion, datos.contraparte_actor_id)

            artefactos = self._artefactos_alta(datos)
            replay = self._clasificar_replay(sesion, artefactos)
            if replay == "REPLICA":
                return self._resultado_actual(sesion, datos.entidad_id, idempotente=True)
            if replay == "CONFLICTO":
                raise self._conflicto_identidad()

            hecho_id, hecho_version = self._resolver_hecho_causal(sesion, datos)

            creada = repo_pos.insertar_entidad_si_no_existe(
                sesion,
                entidad_id=datos.entidad_id,
                tipo_entidad=TIPO_ENTIDAD_POSICION,
                nombre=(datos.nombre or "").strip(),
            )
            if creada is None:
                raise self._conflicto_identidad()
            entidad_version, snapshot_entidad = creada
            auditoria.registrar(
                sesion,
                tabla=repo_pos.TABLA_ENTIDADES,
                registro_id=datos.entidad_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=snapshot_entidad,
                motivo=f"POSICION:{datos.justificacion}",
            )

            snapshot_posicion = repo_pos.insertar_posicion(
                sesion, self._valores_posicion(datos)
            )
            if snapshot_posicion is None:  # pragma: no cover - imposible tras el alta
                raise self._conflicto_identidad()
            auditoria.registrar(
                sesion,
                tabla=repo_pos.TABLA_POSICIONES,
                registro_id=datos.entidad_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=snapshot_posicion,
                motivo=f"POSICION:{datos.justificacion}",
            )

            if datos.importe_inicial is not None:
                self._crear_delta(
                    sesion,
                    hecho_id=hecho_id,
                    efecto_id=datos.efecto_id,
                    vinculo_id=datos.vinculo_id,
                    entidad_id=datos.entidad_id,
                    tipo_efecto=EFECTO_DE_POSICION[datos.tipo],
                    importe_delta=decimal.Decimal(datos.importe_inicial),
                    concepto=datos.concepto,
                )
                # F04-D053 B4 (v0.2 Q5): el efecto de alta no precede al
                # inicio de seguimiento (B7: solo con saldo determinado).
                integridad_posicion.exigir_alta_no_anterior_al_inicio(
                    sesion, datos.entidad_id, hecho_id
                )

            return self._resultado_actual(
                sesion,
                datos.entidad_id,
                hecho_id=hecho_id,
                hecho_row_version=hecho_version,
            )

        return self._ejecutar(contexto, operacion, "OP-12A crear_posicion")

    # ==================================================================
    # OP-12B — REDUCIR OBLIGACION
    # ==================================================================
    def reducir_obligacion(
        self,
        contexto: ContextoOperacion,
        *,
        entidad_id: uuid.UUID,
        entidad_row_version_esperada: int,
        delta: DatosDeltaPosicion,
        movimiento: Any | None = None,
        pagado_por_tercero: bool = False,
    ) -> ResultadoPosicion:
        """PAGO propio de una obligacion generica (F04-D052).

        Arquetipo REEMBOLSO + movimiento en una cuenta Gapto (crear uno o
        consumir uno ACTIVO existente). Materializa un efecto DEUDA negativo.
        NO crea GASTO por el principal: el gasto, si existio, se reconocio
        cuando nacio la obligacion, y volverlo a reconocer al pagar seria
        doble conteo (INV-12). Una obligacion pagada por un tercero no es pago
        propio ni condonacion: STOP sin escribir nada (R-F04-038).
        """
        if pagado_por_tercero is not False:
            raise ErrorMotor(
                CodigoError.PAGO_POR_TERCERO_FUERA_DE_ALCANCE,
                "El pago de una obligacion propia por un tercero esta fuera de "
                "alcance: no es pago propio ni condonacion.",
            )
        return self._aplicar_delta(
            contexto,
            entidad_id=entidad_id,
            entidad_row_version_esperada=entidad_row_version_esperada,
            delta=delta,
            tipo_esperado=TIPO_OBLIGACION,
            tipo_hecho_codigo=TIPO_HECHO_REEMBOLSO,
            codigo_exceso=CodigoError.EXCEDE_SALDO_POSICION,
            nombre_operacion="OP-12B reducir_obligacion",
            causa_esperada=CausaReduccion.PAGO,
            tesoreria=movimiento,
            exige_tesoreria=True,
            signo_movimiento=-1,
        )

    # ==================================================================
    # OP-14 — REEMBOLSO
    # ==================================================================
    def reembolsar(
        self,
        contexto: ContextoOperacion,
        *,
        entidad_id: uuid.UUID,
        entidad_row_version_esperada: int,
        datos: DatosReembolso,
    ) -> ResultadoPosicion:
        """COBRO propio de un DERECHO_COBRO.

        Persiste `DERECHO_COBRO` NEGATIVO. Nunca INGRESO, nunca GASTO negativo,
        nunca DEUDA: el dinero que vuelve de un derecho no es un ingreso nuevo,
        es la reduccion de algo que ya se reconocio.

        Si no existe la posicion previa, SIN_DERECHO_PREVIO. No se crea un
        derecho retroactivo porque haya llegado dinero: eso fabricaria el
        origen a partir del efecto.

        F04-D052: exige causa COBRO y movimiento en una cuenta Gapto
        (EFECTIVO incluida). La rama "sin cuenta registrada" de F04-D015 §4
        deja de admitirse para cobros nuevos; §1-3 y §5 no cambian.
        """
        return self._aplicar_delta(
            contexto,
            entidad_id=entidad_id,
            entidad_row_version_esperada=entidad_row_version_esperada,
            delta=datos.delta,
            tipo_esperado=TIPO_DERECHO,
            tipo_hecho_codigo=TIPO_HECHO_REEMBOLSO,
            codigo_exceso=CodigoError.EXCEDE_SALDO_DEL_DERECHO,
            nombre_operacion="OP-14 reembolsar",
            causa_esperada=CausaReduccion.COBRO,
            tesoreria=datos.tesoreria,
            exige_tesoreria=True,
            signo_movimiento=1,
            no_encontrada=CodigoError.SIN_DERECHO_PREVIO,
            relacion=(datos.hecho_causal_id, datos.relacion_id),
        )

    # ==================================================================
    # CONDONACION DE DERECHO (F04-D015)
    # ==================================================================
    def condonar_derecho(
        self,
        contexto: ContextoOperacion,
        *,
        entidad_id: uuid.UUID,
        entidad_row_version_esperada: int,
        datos: DatosCondonacion,
    ) -> ResultadoPosicion:
        """Renuncia definitiva a una porcion de un DERECHO_COBRO.

        No genera tesoreria y no genera INGRESO. El GASTO por la porcion
        condonada NO es automatico: exige que el llamante declare las DOS cosas
        —que pasa a soportarlo economicamente y que ese coste no estaba ya
        reconocido—. Si falta cualquiera, cero efecto GASTO.

        F04-D052: causa CONDONACION y arquetipo CONDONACION (D-201), de modo
        que un cobro y una condonacion son fisicamente distinguibles. El resto
        de F04-D015 §6, §7 y §9 no cambia. Sobre una obligacion es
        NATURALEZA_INCOMPATIBLE: su condonacion es `condonar_obligacion`.
        """

        hecho_con_gasto = bool(
            datos.declara_gasto_soportado and datos.declara_coste_no_reconocido
        )
        decision_hecho = self._decision_hecho_condonacion(datos, hecho_con_gasto)

        def extra(sesion: SesionMotor, contexto_delta: dict[str, Any]) -> None:
            if not hecho_con_gasto:
                return
            if datos.efecto_gasto_id is None:
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    "Un GASTO declarado exige su identidad reservada.",
                )
            if repo_pos.existe_gasto_vinculado(sesion, entidad_id):
                raise ErrorMotor(
                    CodigoError.GASTO_DUPLICADO,
                    "Esa posicion ya tiene un coste reconocido; anadir otro "
                    "seria doble conteo.",
                )
            creado = repo_efectos.insertar_efecto_si_no_existe(
                sesion,
                contexto_delta["hecho_id"],
                efecto_id=datos.efecto_gasto_id,
                tipo_efecto="GASTO",
                importe_delta=contexto_delta["importe"],
                estado_atribucion=ATRIBUCION_INICIAL,
                categoria_id=None,
                descripcion=None,
            )
            if creado is None:
                raise self._conflicto_identidad()
            auditoria.registrar(
                sesion,
                tabla=repo_efectos.TABLA_EFECTOS,
                registro_id=datos.efecto_gasto_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=creado[1],
                motivo="condonacion soportada economicamente por el usuario",
            )

        return self._aplicar_delta(
            contexto,
            entidad_id=entidad_id,
            entidad_row_version_esperada=entidad_row_version_esperada,
            delta=datos.delta,
            tipo_esperado=TIPO_DERECHO,
            tipo_hecho_codigo=TIPO_HECHO_CONDONACION,
            codigo_exceso=CodigoError.EXCEDE_SALDO_DEL_DERECHO,
            nombre_operacion="condonar_derecho",
            causa_esperada=CausaReduccion.CONDONACION,
            extra=extra,
            artefactos_extra=(
                []
                if datos.efecto_gasto_id is None
                else [("hecho_efectos", datos.efecto_gasto_id)]
            ),
            **decision_hecho,
        )

    # ==================================================================
    # CONDONACION DE OBLIGACION (F04-D052)
    # ==================================================================
    def condonar_obligacion(
        self,
        contexto: ContextoOperacion,
        *,
        entidad_id: uuid.UUID,
        entidad_row_version_esperada: int,
        datos: DatosCondonacionObligacion,
    ) -> ResultadoPosicion:
        """Renuncia del acreedor a una porcion de una OBLIGACION_PAGO.

        Arquetipo CONDONACION, efecto DEUDA negativo y SIN tesoreria. La
        parcial deja la posicion ACTIVA; la total con saldo conocido cierra
        solo si el llamante declara el cierre (CONDONADA); con saldo
        indeterminado se registra el importe observado, el saldo sigue
        indeterminado y el cierre total es una declaracion explicita del
        llamante, sin residual fabricado (F04-D015 §9, igual que el derecho).

        INGRESO por defecto CERO. Solo si el llamante declara
        `importe_ingreso` en esta misma operacion: mayor que cero, no
        superior a lo condonado y como maximo uno por hecho. Nunca se infiere
        de la condonacion, de la ausencia de movimiento ni del arquetipo. Con
        INGRESO rige el contrato del GASTO declarado de la condonacion de
        derecho (E01): `presupuestable` explicito y localizacion aplicable.
        Simetria semantica explicita: no se reutiliza `condonar_derecho`.
        """
        con_ingreso = datos.importe_ingreso is not None
        if con_ingreso:
            importe_ingreso = decimal.Decimal(datos.importe_ingreso)
            if importe_ingreso <= CERO:
                raise ErrorMotor(
                    CodigoError.INGRESO_NO_PERMITIDO,
                    "El INGRESO declarado de una condonacion debe ser mayor "
                    "que cero.",
                )
            if datos.delta.importe is not None and importe_ingreso > decimal.Decimal(
                datos.delta.importe
            ):
                raise ErrorMotor(
                    CodigoError.INGRESO_NO_PERMITIDO,
                    "El INGRESO declarado excede el importe condonado en esta "
                    "operacion.",
                )
            if datos.efecto_ingreso_id is None:
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    "Un INGRESO declarado exige su identidad reservada.",
                )
        elif datos.efecto_ingreso_id is not None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Sin INGRESO declarado no se reserva identidad de INGRESO.",
            )
        decision_hecho = self._decision_hecho_condonacion(datos, con_ingreso)

        def extra(sesion: SesionMotor, contexto_delta: dict[str, Any]) -> None:
            if not con_ingreso:
                return
            creado = repo_efectos.insertar_efecto_si_no_existe(
                sesion,
                contexto_delta["hecho_id"],
                efecto_id=datos.efecto_ingreso_id,
                tipo_efecto="INGRESO",
                importe_delta=decimal.Decimal(datos.importe_ingreso),
                estado_atribucion=ATRIBUCION_INICIAL,
                categoria_id=None,
                descripcion=None,
            )
            if creado is None:
                raise self._conflicto_identidad()
            auditoria.registrar(
                sesion,
                tabla=repo_efectos.TABLA_EFECTOS,
                registro_id=datos.efecto_ingreso_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=creado[1],
                motivo="INGRESO declarado por el usuario en la condonacion",
            )

        return self._aplicar_delta(
            contexto,
            entidad_id=entidad_id,
            entidad_row_version_esperada=entidad_row_version_esperada,
            delta=datos.delta,
            tipo_esperado=TIPO_OBLIGACION,
            tipo_hecho_codigo=TIPO_HECHO_CONDONACION,
            codigo_exceso=CodigoError.EXCEDE_SALDO_POSICION,
            nombre_operacion="condonar_obligacion",
            causa_esperada=CausaReduccion.CONDONACION,
            extra=extra,
            artefactos_extra=(
                []
                if datos.efecto_ingreso_id is None
                else [("hecho_efectos", datos.efecto_ingreso_id)]
            ),
            **decision_hecho,
        )

    @staticmethod
    def _decision_hecho_condonacion(
        datos: DatosCondonacion | DatosCondonacionObligacion,
        hecho_con_naturaleza: bool,
    ) -> dict[str, Any]:
        """Mandato F04 R1+R2 v0.3 §8/§9 + E01. Raiz del hecho de condonacion.

        Sin GASTO (derecho) ni INGRESO (obligacion, F04-D052) declarado el
        hecho es puramente posicional y conserva EXACTAMENTE los valores de
        siempre (defaults de `_aplicar_delta`); aportar decision o
        localizacion en ese caso no tendria significado y se rechaza. Con
        GASTO o INGRESO, `presupuestable` es decision explicita sin default y
        la localizacion es aplicable: sin dato -> DESCONOCIDA, con localidad y
        sin estado -> CONOCIDA, NO_APLICA -> ENTRADA_INVALIDA. La coherencia
        estado/localidad la juzga el CHECK fisico de 0040. Es el mismo camino
        para las dos naturalezas: el INGRESO declarado no tiene contrato
        propio.
        """
        declarados = (
            datos.presupuestable is not None
            or datos.estado_localizacion is not None
            or datos.localidad_id is not None
        )
        if not hecho_con_naturaleza:
            if declarados:
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    "Sin GASTO ni INGRESO declarado el hecho de condonacion es "
                    "puramente posicional: presupuestable y localizacion no se "
                    "aportan.",
                )
            return {}
        if datos.presupuestable is None or not isinstance(
            datos.presupuestable, bool
        ):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Una condonacion que genera GASTO o INGRESO exige decidir "
                "`presupuestable`: el motor no lo deriva.",
            )
        if datos.estado_localizacion is None:
            estado = "DESCONOCIDA" if datos.localidad_id is None else "CONOCIDA"
        else:
            if datos.estado_localizacion not in ESTADOS_LOCALIZACION:
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    "estado_localizacion debe ser CONOCIDA, DESCONOCIDA o "
                    "NO_APLICA.",
                )
            if datos.estado_localizacion == LOCALIZACION_POSICION:
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    "Con GASTO o INGRESO la localizacion es aplicable: "
                    "NO_APLICA no es valido. Si no se conoce la localidad, es "
                    "DESCONOCIDA.",
                )
            estado = datos.estado_localizacion
        return {
            "presupuestable_hecho": datos.presupuestable,
            "estado_localizacion_hecho": estado,
            "localidad_id_hecho": datos.localidad_id,
            "verificar_hecho_en_replay": True,
        }

    # ==================================================================
    # CIERRE EXPLICITO
    # ==================================================================
    def cerrar_posicion(
        self,
        contexto: ContextoOperacion,
        *,
        entidad_id: uuid.UUID,
        entidad_row_version_esperada: int,
        cierre: DatosCierre,
    ) -> ResultadoPosicion:
        """Cierre declarado. Saldo cero NO cierra nada por si solo.

        Una posicion con saldo cero puede seguir ACTIVA y recibir deltas
        legitimos despues; cerrarla automaticamente la haria irreabrible por
        una coincidencia aritmetica.

        F04-D055: solo LIQUIDADA o CONDONADA (A2); con saldo determinado, el
        saldo canonico debe ser exactamente 0 (A1); el motivo lo determina el
        conjunto de causas de la ventana A1 cuando es univoco (R-Q1). Con
        saldo indeterminado se cierra por declaracion (A3), con la misma R-Q1.
        """
        self._validar_cierre(cierre)
        if cierre.motivo_cierre not in MOTIVOS_CIERRE_RUNTIME:
            raise ErrorMotor(
                CodigoError.CIERRE_SIN_MOTIVO,
                "Un cierre de runtime solo admite LIQUIDADA o CONDONADA; "
                "CANCELADA y OTRO solo existen como datos legacy.",
            )

        def operacion(sesion: SesionMotor) -> ResultadoPosicion:
            owner = repo_hechos.exigir_contexto(sesion)
            # F04-D053 B8: raiz de la posicion antes de leerla.
            integridad_posicion.adquirir_raiz(sesion, owner, posiciones=[entidad_id])
            posicion = self._exigir_posicion(sesion, entidad_id)
            if posicion["estado"] == ESTADO_CERRADA:
                raise ErrorMotor(
                    CodigoError.POSICION_CERRADA,
                    "La posicion ya esta cerrada.",
                )
            self._tocar_entidad(sesion, entidad_id, entidad_row_version_esperada)
            self._exigir_saldo_cero(sesion, entidad_id, posicion)
            self._exigir_motivo_de_las_causas(
                sesion, entidad_id, posicion, cierre.motivo_cierre
            )
            self._cerrar(sesion, entidad_id, cierre, posicion["snapshot"])
            return self._resultado_actual(sesion, entidad_id)

        return self._ejecutar(contexto, operacion, "cerrar_posicion")

    # ==================================================================
    # Lectura de saldo
    # ==================================================================
    def saldo(
        self, contexto: ContextoOperacion, entidad_id: uuid.UUID
    ) -> ResultadoPosicion:
        def operacion(sesion: SesionMotor) -> ResultadoPosicion:
            repo_hechos.exigir_contexto(sesion)
            self._exigir_posicion(sesion, entidad_id)
            return self._resultado_actual(sesion, entidad_id)

        return self._ejecutar(contexto, operacion, "leer_saldo")

    def causas_de_reduccion(
        self, contexto: ContextoOperacion, entidad_id: uuid.UUID
    ) -> list[CausaLeida]:
        """F04-D052 (CC4). Causa de cada reduccion, reconstruida en LECTURA.

        REEMBOLSO -> PAGO (obligacion) o COBRO (derecho); CONDONACION ->
        CONDONACION; cualquier otro arquetipo -en la practica
        GENERACION_DERECHO_OBLIGACION, historico o migrado- -> NO_DETERMINABLE.
        Nada se persiste ni se reclasifica, y ni la fecha ni la procedencia de
        importacion intervienen.
        """

        def operacion(sesion: SesionMotor) -> list[CausaLeida]:
            repo_hechos.exigir_contexto(sesion)
            posicion = self._exigir_posicion(sesion, entidad_id)
            return self._causas_leidas(sesion, entidad_id, posicion)

        resultado = self._unidad.ejecutar_con_traza(
            contexto, operacion, nombre="leer_causas_de_reduccion"
        )
        self.ultima_traza = resultado.traza
        return resultado.valor

    @staticmethod
    def _causas_leidas(
        sesion: SesionMotor,
        entidad_id: uuid.UUID,
        posicion: dict[str, Any],
        *,
        en_ventana: bool = False,
    ) -> list[CausaLeida]:
        """UNICA clasificacion arquetipo -> causa (F04-D052 CC4).

        `causas_de_reduccion` la usa sin ventana; R-Q1 de F04-D055, con la
        ventana canonica de F04-D053 (`en_ventana`).
        """
        causa_reembolso = (
            CausaReduccion.PAGO
            if posicion["tipo"] == TIPO_OBLIGACION
            else CausaReduccion.COBRO
        )
        leidas = []
        for hecho_id, codigo, con_movimiento in repo_pos.reducciones_de_posicion(
            sesion,
            entidad_id,
            EFECTO_DE_POSICION[posicion["tipo"]],
            en_ventana_a1=en_ventana,
        ):
            if codigo == TIPO_HECHO_REEMBOLSO:
                causa = causa_reembolso.value
            elif codigo == TIPO_HECHO_CONDONACION:
                causa = CausaReduccion.CONDONACION.value
            else:
                causa = CAUSA_NO_DETERMINABLE
            leidas.append(CausaLeida(hecho_id, codigo, con_movimiento, causa))
        return leidas

    # ==================================================================
    # Nucleo comun de los deltas
    # ==================================================================
    def _aplicar_delta(
        self,
        contexto: ContextoOperacion,
        *,
        entidad_id: uuid.UUID,
        entidad_row_version_esperada: int,
        delta: DatosDeltaPosicion,
        tipo_esperado: str,
        tipo_hecho_codigo: str,
        codigo_exceso: CodigoError,
        nombre_operacion: str,
        causa_esperada: CausaReduccion,
        tesoreria: Any | None = None,
        exige_tesoreria: bool = False,
        signo_movimiento: int = 0,
        no_encontrada: CodigoError = CodigoError.AGREGADO_NO_ENCONTRADO,
        relacion: tuple[uuid.UUID | None, uuid.UUID | None] = (None, None),
        extra: Callable[[SesionMotor, dict[str, Any]], None] | None = None,
        artefactos_extra: Sequence[tuple[str, uuid.UUID]] = (),
        presupuestable_hecho: bool = PRESUPUESTABLE_POSICION,
        estado_localizacion_hecho: str = LOCALIZACION_POSICION,
        localidad_id_hecho: uuid.UUID | None = None,
        verificar_hecho_en_replay: bool = False,
    ) -> ResultadoPosicion:
        # Los cuatro ultimos parametros solo los pasan las condonaciones
        # (mandato F04 R1+R2 v0.3 + E01; F04-D052 para el INGRESO); sus
        # defaults reproducen el comportamiento previo del resto.
        self._validar_delta(delta)
        # F04-D052. Toda la frontera de causa se juzga ANTES de abrir la
        # transaccion: un rechazo aqui no deja ni hecho, ni efecto, ni
        # movimiento, ni posicion.
        self._validar_causa(delta, causa_esperada)
        if exige_tesoreria and tesoreria is None:
            raise ErrorMotor(
                CodigoError.CUENTA_GAPTO_REQUERIDA,
                "Un pago o cobro propio pasa por una cuenta Gapto (EFECTIVO "
                "incluida): el motor no fabrica el movimiento.",
            )
        if delta.cierre is not None:
            self._validar_cierre(delta.cierre)
            if delta.cierre.motivo_cierre != MOTIVO_CIERRE_DE_CAUSA[causa_esperada]:
                raise ErrorMotor(
                    CodigoError.CAUSA_REDUCCION_INVALIDA,
                    "El motivo de cierre no corresponde a la causa de la "
                    "reduccion.",
                )
        importe = decimal.Decimal(delta.importe)

        def operacion(sesion: SesionMotor) -> ResultadoPosicion:
            owner = repo_hechos.exigir_contexto(sesion)
            # F04-D053 B8: advisory (escribe hecho_entidades, D-080/D-158) ->
            # raiz de la posicion, ANTES de leer el saldo y antes del movimiento.
            integridad_posicion.adquirir_raiz(
                sesion, owner, posiciones=[entidad_id], advisory=True
            )

            artefactos = self._artefactos_delta(
                delta, tesoreria, relacion, artefactos_extra
            )
            # Mandato 32: el reintento exacto se reconoce ANTES de mirar la
            # version, para no convertirlo en un falso conflicto.
            replay = self._clasificar_replay(sesion, artefactos)
            if replay == "REPLICA":
                if verificar_hecho_en_replay:
                    self._exigir_hecho_replay(
                        sesion,
                        delta.hecho_id,
                        presupuestable_hecho,
                        estado_localizacion_hecho,
                        localidad_id_hecho,
                    )
                return self._resultado_actual(sesion, entidad_id, idempotente=True)
            if replay == "CONFLICTO":
                raise self._conflicto_identidad()

            posicion = repo_pos.leer_posicion(sesion, entidad_id)
            if posicion is None:
                raise ErrorMotor(
                    no_encontrada,
                    "La posicion indicada no existe o no es accesible.",
                )
            if posicion["tipo"] != tipo_esperado:
                raise ErrorMotor(
                    CodigoError.NATURALEZA_INCOMPATIBLE,
                    "La operacion no corresponde a la naturaleza de la posicion.",
                )
            if posicion["estado"] == ESTADO_CERRADA:
                raise ErrorMotor(
                    CodigoError.POSICION_CERRADA,
                    "Una posicion cerrada no admite deltas nuevos.",
                )

            # F04-D053 B1: foto previa bajo la raiz; B4 sobre la fecha nueva.
            fotos = integridad_posicion.fotografiar(
                sesion, [entidad_id], hechos=[delta.hecho_id]
            )
            integridad_posicion.exigir_fecha_no_anterior_al_inicio(
                fotos.posiciones[entidad_id], delta.fecha_hecho
            )

            saldo = self._calcular_saldo(sesion, entidad_id, posicion)
            if saldo.conocido and importe > saldo.importe:
                raise ErrorMotor(
                    codigo_exceso,
                    "La reduccion superaria el saldo conocido de la posicion.",
                )
            # Saldo indeterminado: se registra el importe observado y el saldo
            # SIGUE siendo indeterminado. No se valida cuantitativamente ni se
            # asume cero.

            # Raices preexistentes, en orden determinista: movimiento y luego
            # entidad. El hecho se crea aqui, de modo que no es raiz previa.
            movimiento_version: int | None = None
            if tesoreria is not None and not tesoreria.crea_movimiento:
                movimiento_version = self._tomar_movimiento_existente(
                    sesion, tesoreria, signo_movimiento
                )
            entidad_version = self._tocar_entidad(
                sesion, entidad_id, entidad_row_version_esperada
            )

            hecho_id = self._crear_hecho(
                sesion,
                hecho_id=delta.hecho_id,
                tipo_hecho_codigo=tipo_hecho_codigo,
                fecha_hecho=delta.fecha_hecho,
                moneda=posicion["moneda"],
                concepto=delta.concepto,
                importe_total=importe,
                presupuestable=presupuestable_hecho,
                estado_localizacion=estado_localizacion_hecho,
                localidad_id=localidad_id_hecho,
            )
            self._crear_delta(
                sesion,
                hecho_id=hecho_id,
                efecto_id=delta.efecto_id,
                vinculo_id=delta.vinculo_id,
                entidad_id=entidad_id,
                tipo_efecto=EFECTO_DE_POSICION[posicion["tipo"]],
                importe_delta=-importe,
                concepto=delta.concepto,
            )

            if tesoreria is not None:
                movimiento_version = self._resolver_tesoreria(
                    sesion,
                    tesoreria,
                    hecho_id=hecho_id,
                    importe=importe,
                    signo=signo_movimiento,
                    moneda=posicion["moneda"],
                    fecha=delta.fecha_hecho,
                    version_existente=movimiento_version,
                )

            hecho_causal, relacion_id = relacion
            if hecho_causal is not None:
                if relacion_id is None:
                    raise ErrorMotor(
                        CodigoError.ENTRADA_INVALIDA,
                        "Una relacion con el hecho causal exige su identidad "
                        "reservada.",
                    )
                self._crear_relacion(
                    sesion, relacion_id, hecho_id, hecho_causal, importe
                )

            if extra is not None:
                extra(sesion, {"hecho_id": hecho_id, "importe": importe})

            if delta.cierre is not None:
                self._cerrar(sesion, entidad_id, delta.cierre, posicion["snapshot"])
                # F04-D055 A1: saldo CANONICO posterior (con el delta recien
                # creado) sobre la posicion releida, ya CERRADA. La lectura
                # A4 de una CERRADA (0) nunca sirve aqui.
                self._exigir_saldo_cero(
                    sesion, entidad_id, self._exigir_posicion(sesion, entidad_id)
                )

            # F04-D053 B1: estado final (B2/B3 fecha a fecha con A1, B5, B6).
            integridad_posicion.validar(sesion, fotos)

            return self._resultado_actual(
                sesion,
                entidad_id,
                hecho_id=hecho_id,
                movimiento_row_version=movimiento_version,
                movimiento_id=None if tesoreria is None else tesoreria.movimiento_id,
            )

        return self._ejecutar(contexto, operacion, nombre_operacion)

    # ==================================================================
    # Piezas
    # ==================================================================
    def _crear_hecho(
        self,
        sesion: SesionMotor,
        *,
        hecho_id: uuid.UUID,
        tipo_hecho_codigo: str,
        fecha_hecho: Any,
        moneda: str,
        concepto: str | None,
        importe_total: decimal.Decimal | None,
        presupuestable: bool = PRESUPUESTABLE_POSICION,
        estado_localizacion: str = LOCALIZACION_POSICION,
        localidad_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        datos = DatosCreacionHecho(
            hecho_id=hecho_id,
            fecha_hecho=fecha_hecho,
            moneda=moneda,
            presupuestable=presupuestable,
            estado_localizacion=estado_localizacion,
            localidad_id=localidad_id,
            tipo_hecho_codigo=tipo_hecho_codigo,
            concepto=concepto,
            importe_total=importe_total,
        )
        tipo_id = repo_hechos.resolver_tipo_hecho(
            sesion, codigo=tipo_hecho_codigo, tipo_hecho_id=None
        )
        creado = repo_hechos.insertar_si_no_existe(sesion, datos, tipo_id)
        if creado is None:
            raise self._conflicto_identidad()
        auditoria.registrar(
            sesion,
            tabla=repo_hechos.TABLA,
            registro_id=hecho_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json=creado[2],
        )
        return hecho_id

    def _crear_delta(
        self,
        sesion: SesionMotor,
        *,
        hecho_id: uuid.UUID,
        efecto_id: uuid.UUID | None,
        vinculo_id: uuid.UUID | None,
        entidad_id: uuid.UUID,
        tipo_efecto: str,
        importe_delta: decimal.Decimal,
        concepto: str | None,
    ) -> None:
        if efecto_id is None or vinculo_id is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "El efecto y su vinculo exigen identidades reservadas.",
            )
        # F04-D036. Unico writer del vinculo posicion<->efecto, de modo que
        # la guarda vive aqui y no repartida por cada operacion. En los
        # deltas el hecho lo crea esta misma clase con la moneda de la
        # posicion y la comprobacion es un no-op barato; en el ALTA sobre un
        # hecho preexistente es la unica red que existe.
        posicion_destino = repo_pos.leer_posicion(sesion, entidad_id)
        coherencia_posicion.exigir_moneda_de_vinculo(
            sesion,
            hecho_id=hecho_id,
            moneda_posicion=(
                None if posicion_destino is None else posicion_destino["moneda"]
            ),
            entidad_id=entidad_id,
        )
        creado = repo_efectos.insertar_efecto_si_no_existe(
            sesion,
            hecho_id,
            efecto_id=efecto_id,
            tipo_efecto=tipo_efecto,
            importe_delta=importe_delta,
            estado_atribucion=ATRIBUCION_INICIAL,
            categoria_id=None,
            descripcion=concepto,
        )
        if creado is None:
            raise self._conflicto_identidad()
        auditoria.registrar(
            sesion,
            tabla=repo_efectos.TABLA_EFECTOS,
            registro_id=efecto_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json=creado[1],
        )
        snapshot = repo_pos.insertar_vinculo_si_no_existe(
            sesion,
            {
                "id": vinculo_id,
                "hecho_id": hecho_id,
                "efecto_id": efecto_id,
                "entidad_id": entidad_id,
                "tipo_relacion": RELACION_ENTIDAD_GENERADO_POR,
                "principal": True,
            },
        )
        if snapshot is None:
            raise self._conflicto_identidad()
        auditoria.registrar(
            sesion,
            tabla=repo_pos.TABLA_VINCULOS,
            registro_id=vinculo_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json=snapshot,
        )

    def _crear_relacion(
        self,
        sesion: SesionMotor,
        relacion_id: uuid.UUID,
        hecho_origen: uuid.UUID,
        hecho_causal: uuid.UUID,
        importe: decimal.Decimal,
    ) -> None:
        if repo_hechos.leer_estado(sesion, hecho_causal) is None:
            raise ErrorMotor(
                CodigoError.AGREGADO_NO_ENCONTRADO,
                "El hecho causal indicado no existe o no es accesible.",
            )
        snapshot = repo_pos.insertar_relacion_si_no_existe(
            sesion,
            {
                "id": relacion_id,
                "hecho_origen_id": hecho_origen,
                "hecho_destino_id": hecho_causal,
                "tipo_relacion": RELACION_HECHO_REEMBOLSO_DE,
                "importe_relacionado": importe,
            },
        )
        if snapshot is None:
            raise self._conflicto_identidad()
        auditoria.registrar(
            sesion,
            tabla=repo_pos.TABLA_RELACIONES,
            registro_id=relacion_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json=snapshot,
        )

    def _tomar_movimiento_existente(
        self, sesion: SesionMotor, tesoreria: Any, signo: int
    ) -> int:
        """Guarda de la raiz movimiento cuando se consume uno ya existente."""
        movimiento = repo_tes.leer_movimiento(sesion, tesoreria.movimiento_id)
        if movimiento is None:
            raise ErrorMotor(
                CodigoError.AGREGADO_NO_ENCONTRADO,
                "El movimiento indicado no existe o no es accesible.",
            )
        version, estado, importe_movimiento, _, _ = movimiento
        if estado != "ACTIVO":
            raise ErrorMotor(
                CodigoError.MOVIMIENTO_ANULADO,
                "Un movimiento anulado no admite conciliaciones nuevas.",
            )
        if signo > 0 and decimal.Decimal(importe_movimiento) <= CERO:
            raise ErrorMotor(
                CodigoError.SIGNO_INCOMPATIBLE,
                "El cobro de un derecho exige una ENTRADA de dinero.",
            )
        if signo < 0 and decimal.Decimal(importe_movimiento) >= CERO:
            raise ErrorMotor(
                CodigoError.SIGNO_INCOMPATIBLE,
                "El pago de una obligacion exige una SALIDA de dinero.",
            )
        if tesoreria.movimiento_row_version_esperada is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Consumir un movimiento existente exige su version conocida.",
            )
        nueva = repo_tes.tocar_movimiento(
            sesion,
            tesoreria.movimiento_id,
            tesoreria.movimiento_row_version_esperada,
        )
        if nueva is None:
            raise ErrorMotor(
                CodigoError.VERSION_DESFASADA,
                "El movimiento ha cambiado desde la version que conoce el "
                "llamante.",
            )
        return nueva

    def _resolver_tesoreria(
        self,
        sesion: SesionMotor,
        tesoreria: Any,
        *,
        hecho_id: uuid.UUID,
        importe: decimal.Decimal,
        signo: int,
        moneda: str,
        fecha: Any,
        version_existente: int | None,
    ) -> int:
        """Crea el movimiento o consume el indicado, y concilia.

        Nunca se elige el movimiento automaticamente por importe, fecha, cuenta
        o contraparte: la decision viaja en la entrada.
        """
        asignado = importe * decimal.Decimal(signo)
        if tesoreria.crea_movimiento:
            creado = repo_tes.insertar_movimiento_si_no_existe(
                sesion,
                movimiento_id=tesoreria.movimiento_id,
                cuenta_id=tesoreria.cuenta_id,
                fecha_movimiento=tesoreria.fecha_movimiento or fecha,
                importe=asignado,
                clase_movimiento="OPERACION",
                descripcion=tesoreria.descripcion,
                confirmado_at=None,
            )
            if creado is None:
                raise self._conflicto_identidad()
            version_movimiento, snapshot = creado
            auditoria.registrar(
                sesion,
                tabla=repo_tes.TABLA_MOVIMIENTOS,
                registro_id=tesoreria.movimiento_id,
                accion=auditoria.ACCION_CREAR,
                datos_despues_json=snapshot,
            )
        else:
            assert version_existente is not None
            version_movimiento = version_existente

        snapshot = repo_tes.insertar_conciliacion_si_no_existe(
            sesion,
            {
                "id": tesoreria.conciliacion_id,
                "hecho_id": hecho_id,
                "movimiento_tesoreria_id": tesoreria.movimiento_id,
                "importe_asignado": asignado,
            },
        )
        if snapshot is None:
            raise self._conflicto_identidad()
        auditoria.registrar(
            sesion,
            tabla=repo_tes.TABLA_CONCILIACIONES,
            registro_id=tesoreria.conciliacion_id,
            accion=auditoria.ACCION_CREAR,
            datos_despues_json=snapshot,
        )
        return version_movimiento

    def _cerrar(
        self,
        sesion: SesionMotor,
        entidad_id: uuid.UUID,
        cierre: DatosCierre,
        snapshot_previo: str,
    ) -> None:
        snapshot = repo_pos.cerrar_posicion(
            sesion, entidad_id, cierre.motivo_cierre, cierre.fecha_cierre
        )
        if snapshot is None:
            raise ErrorMotor(
                CodigoError.POSICION_CERRADA,
                "La posicion ya estaba cerrada.",
            )
        auditoria.registrar(
            sesion,
            tabla=repo_pos.TABLA_POSICIONES,
            registro_id=entidad_id,
            accion=auditoria.ACCION_ACTUALIZAR,
            datos_antes_json=snapshot_previo,
            datos_despues_json=snapshot,
            motivo=f"cierre explicito: {cierre.motivo_cierre}",
        )

    # ==================================================================
    # Saldo
    # ==================================================================
    def _calcular_saldo(
        self, sesion: SesionMotor, entidad_id: uuid.UUID, posicion: dict[str, Any]
    ) -> Saldo:
        """saldo_apertura + deltas ACTIVOS compatibles, o INDETERMINADO.

        `importe_original_documentado` NO participa: es lo que decia el
        documento de origen, no lo que queda vivo.
        """
        if posicion["saldo_apertura"] is None:
            return Saldo.indeterminado()
        # F04-D036. Defensa en profundidad: antes de sumar se comprueba que
        # todos los deltas que entrarian son de la moneda de la posicion.
        coherencia_posicion.exigir_saldo_calculable(
            sesion,
            entidad_id=entidad_id,
            tipo_efecto=EFECTO_DE_POSICION[posicion["tipo"]],
        )
        deltas = repo_pos.saldo_deltas(
            sesion, entidad_id, EFECTO_DE_POSICION[posicion["tipo"]]
        )
        return Saldo.de(
            decimal.Decimal(posicion["saldo_apertura"]) + decimal.Decimal(deltas)
        )

    def _resultado_actual(
        self,
        sesion: SesionMotor,
        entidad_id: uuid.UUID,
        *,
        idempotente: bool = False,
        hecho_id: uuid.UUID | None = None,
        hecho_row_version: int | None = None,
        movimiento_id: uuid.UUID | None = None,
        movimiento_row_version: int | None = None,
    ) -> ResultadoPosicion:
        posicion = self._exigir_posicion(sesion, entidad_id)
        saldo, apertura_indeterminada = self._saldo_de_lectura(
            sesion, entidad_id, posicion
        )
        return ResultadoPosicion(
            entidad_id=entidad_id,
            entidad_row_version=posicion["row_version"],
            tipo=posicion["tipo"],
            estado=posicion["estado"],
            saldo=saldo,
            hecho_id=hecho_id,
            hecho_row_version=hecho_row_version,
            movimiento_id=movimiento_id,
            movimiento_row_version=movimiento_row_version,
            idempotente=idempotente,
            apertura_indeterminada=apertura_indeterminada,
        )

    def _saldo_de_lectura(
        self, sesion: SesionMotor, entidad_id: uuid.UUID, posicion: dict[str, Any]
    ) -> tuple[Saldo, bool]:
        """F04-D055 A4. (saldo de LECTURA, apertura_indeterminada).

        ACTIVA: exactamente el canonico (INV-17 intacto). CERRADA: conocido 0
        sin tocar deltas, tambien una legacy con residual, y el indicador
        separado si la apertura era indeterminada. SOLO lo usa
        `_resultado_actual`: ningun validador lo consume.
        """
        if posicion["estado"] == ESTADO_CERRADA:
            return Saldo.de(CERO), posicion["saldo_apertura"] is None
        return self._calcular_saldo(sesion, entidad_id, posicion), False

    def _exigir_saldo_cero(
        self, sesion: SesionMotor, entidad_id: uuid.UUID, posicion: dict[str, Any]
    ) -> None:
        """F04-D055 A1 con el saldo CANONICO. Indeterminado: no se exige (A3)."""
        saldo = self._calcular_saldo(sesion, entidad_id, posicion)
        if saldo.conocido and saldo.importe != CERO:
            raise ErrorMotor(
                CodigoError.CIERRE_CON_SALDO_NO_NULO,
                "Con saldo determinado solo se cierra con saldo exactamente 0: "
                "el residual se extingue antes con un pago, cobro o "
                "condonacion explicitos.",
                contexto_extra={"saldo": str(saldo.importe)},
            )

    def _exigir_motivo_de_las_causas(
        self,
        sesion: SesionMotor,
        entidad_id: uuid.UUID,
        posicion: dict[str, Any],
        motivo_cierre: str,
    ) -> None:
        """F04-D055 R-Q1 (solo `cerrar_posicion`).

        S = causas DETERMINABLES de las reducciones de la ventana A1. Si S
        determina un unico motivo (MISMA tabla que la guarda de F04-D052), el
        cierre debe declararlo; vacio o mixto admite LIQUIDADA o CONDONADA.
        Es un conjunto: ni orden, ni ultima reduccion, ni timestamps.
        """
        causas = {
            leida.causa
            for leida in self._causas_leidas(
                sesion, entidad_id, posicion, en_ventana=True
            )
            if leida.causa != CAUSA_NO_DETERMINABLE
        }
        motivos = {MOTIVO_CIERRE_DE_CAUSA[CausaReduccion(c)] for c in causas}
        if len(motivos) == 1 and motivo_cierre not in motivos:
            raise ErrorMotor(
                CodigoError.CAUSA_REDUCCION_INVALIDA,
                "El motivo de cierre no corresponde a las causas de las "
                "reducciones de la posicion.",
            )

    # ==================================================================
    # Idempotencia
    # ==================================================================
    def _artefactos_alta(
        self, datos: DatosAltaPosicion
    ) -> list[tuple[str, uuid.UUID]]:
        artefactos = [("entidades", datos.entidad_id)]
        if datos.hecho_id is not None and datos.hecho_row_version_esperada is None:
            artefactos.append(("hechos_financieros", datos.hecho_id))
        if datos.importe_inicial is not None:
            if datos.efecto_id is not None:
                artefactos.append(("hecho_efectos", datos.efecto_id))
            if datos.vinculo_id is not None:
                artefactos.append(("hecho_entidades", datos.vinculo_id))
        return artefactos

    @staticmethod
    def _artefactos_delta(
        delta: DatosDeltaPosicion,
        tesoreria: Any | None,
        relacion: tuple[uuid.UUID | None, uuid.UUID | None],
        extra: Sequence[tuple[str, uuid.UUID]],
    ) -> list[tuple[str, uuid.UUID]]:
        artefactos: list[tuple[str, uuid.UUID]] = [
            ("hechos_financieros", delta.hecho_id),
            ("hecho_efectos", delta.efecto_id),
            ("hecho_entidades", delta.vinculo_id),
        ]
        if tesoreria is not None:
            if tesoreria.crea_movimiento:
                artefactos.append(("movimientos_tesoreria", tesoreria.movimiento_id))
            artefactos.append(
                ("hecho_movimientos_tesoreria", tesoreria.conciliacion_id)
            )
        if relacion[1] is not None:
            artefactos.append(("hecho_relaciones", relacion[1]))
        artefactos.extend(extra)
        return artefactos

    @staticmethod
    def _clasificar_replay(
        sesion: SesionMotor, artefactos: Sequence[tuple[str, uuid.UUID]]
    ) -> str:
        """Todo-o-nada sobre los artefactos reservados de la operacion.

        Una transaccion original no puede haber confirmado solo una parte, de
        modo que una coincidencia parcial no es un reintento: es reuso de
        identidad y NO se completan los artefactos ausentes.
        """
        existentes = sum(
            1
            for tabla, registro_id in artefactos
            if repo_pos.existe_registro(sesion, tabla, registro_id)
        )
        if existentes == 0:
            return "NUEVO"
        if existentes == len(artefactos):
            return "REPLICA"
        return "CONFLICTO"

    def _exigir_hecho_replay(
        self,
        sesion: SesionMotor,
        hecho_id: uuid.UUID,
        presupuestable: bool,
        estado_localizacion: str,
        localidad_id: uuid.UUID | None,
    ) -> None:
        """Replay de condonacion con GASTO: la decision persistida debe ser la
        misma. Otra decision con los mismos UUID es otra intencion."""
        estado = repo_hechos.leer_estado(sesion, hecho_id)
        if estado is None:
            raise self._conflicto_identidad()
        snap = json.loads(estado[2])
        localidad = snap.get("localidad_id")
        if (
            snap.get("presupuestable") != presupuestable
            or snap.get("estado_localizacion") != estado_localizacion
            or (str(localidad) if localidad else None)
            != (str(localidad_id) if localidad_id else None)
        ):
            raise self._conflicto_identidad()

    @staticmethod
    def _conflicto_identidad() -> ErrorMotor:
        return ErrorMotor(
            CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
            "Alguno de los identificadores reservados ya esta en uso con otra "
            "intencion.",
        )

    # ==================================================================
    # Guardas y validacion
    # ==================================================================
    def _tocar_entidad(
        self, sesion: SesionMotor, entidad_id: uuid.UUID, esperada: int
    ) -> int:
        nueva = repo_pos.tocar_entidad(sesion, entidad_id, esperada)
        if nueva is None:
            raise ErrorMotor(
                CodigoError.VERSION_DESFASADA,
                "La posicion ha cambiado desde la version que conoce el "
                "llamante.",
            )
        return nueva

    @staticmethod
    def _exigir_posicion(
        sesion: SesionMotor, entidad_id: uuid.UUID
    ) -> dict[str, Any]:
        posicion = repo_pos.leer_posicion(sesion, entidad_id)
        if posicion is None:
            raise ErrorMotor(
                CodigoError.AGREGADO_NO_ENCONTRADO,
                "La posicion indicada no existe o no es accesible.",
            )
        return posicion

    @staticmethod
    def _exigir_contraparte(
        sesion: SesionMotor, contraparte_actor_id: uuid.UUID | None
    ) -> None:
        if contraparte_actor_id is None:
            raise ErrorMotor(
                CodigoError.CONTRAPARTE_REQUERIDA,
                "Una posicion exige contraparte: sin ella no hay frente a quien.",
            )
        if not repo_efectos.actores_visibles(sesion, [contraparte_actor_id]):
            raise ErrorMotor(
                CodigoError.AGREGADO_NO_ENCONTRADO,
                "La contraparte indicada no existe o no es accesible.",
            )
        if repo_pos.actor_es_self(sesion, contraparte_actor_id):
            raise ErrorMotor(
                CodigoError.CONTRAPARTE_SELF_NO_PERMITIDA,
                "Una posicion contra uno mismo no es una posicion.",
            )

    def _resolver_hecho_causal(
        self, sesion: SesionMotor, datos: DatosAltaPosicion
    ) -> tuple[uuid.UUID, int | None]:
        """Engancha a un hecho existente o crea el hecho propio de la posicion."""
        if datos.hecho_id is not None and datos.hecho_row_version_esperada is not None:
            estado = repo_hechos.leer_estado(sesion, datos.hecho_id)
            if estado is None:
                raise ErrorMotor(
                    CodigoError.AGREGADO_NO_ENCONTRADO,
                    "El hecho indicado no existe o no es accesible.",
                )
            if estado[1] != ESTADO_ACTIVO:
                raise ErrorMotor(
                    CodigoError.OPERACION_NO_PERMITIDA_EN_ESTADO,
                    "Un hecho anulado no admite efectos nuevos.",
                )
            nueva = repo_hechos.tocar_raiz(
                sesion, datos.hecho_id, datos.hecho_row_version_esperada
            )
            if nueva is None:
                raise ErrorMotor(
                    CodigoError.VERSION_DESFASADA,
                    "El hecho ha cambiado desde la version que conoce el "
                    "llamante.",
                )
            return datos.hecho_id, nueva

        if datos.hecho_id is None:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "El alta exige la identidad reservada de su hecho causal.",
            )
        self._crear_hecho(
            sesion,
            hecho_id=datos.hecho_id,
            tipo_hecho_codigo=TIPO_HECHO_POSICION,
            fecha_hecho=datos.fecha_hecho,
            moneda=datos.moneda,
            concepto=datos.concepto,
            importe_total=datos.importe_inicial,
        )
        return datos.hecho_id, 1

    @staticmethod
    def _validar_alta(datos: DatosAltaPosicion) -> None:
        if datos.tipo not in TIPOS_POSICION:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "tipo debe ser DERECHO_COBRO u OBLIGACION_PAGO.",
            )
        if datos.justificacion not in JUSTIFICACIONES:
            # INV-04. Ninguna diferencia calculada sustituye a esta declaracion.
            raise ErrorMotor(
                CodigoError.POSICION_SIN_JUSTIFICACION,
                "Una posicion exige justificacion explicita: DECISION_EXPLICITA, "
                "REGLA o CONTRATO.",
            )
        if not (datos.nombre or "").strip():
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA, "La entidad exige nombre."
            )
        if datos.moneda is None or not _MONEDA_VALIDA.match(datos.moneda):
            raise ErrorMotor(
                CodigoError.MONEDA_INVALIDA,
                "La moneda debe ser un codigo de tres letras mayusculas.",
            )
        if (datos.saldo_apertura is None) != (datos.fecha_inicio_seguimiento is None):
            raise ErrorMotor(
                CodigoError.APERTURA_INCONSISTENTE,
                "saldo_apertura y fecha_inicio_seguimiento van juntos: o ambos "
                "o ninguno.",
            )
        if datos.saldo_apertura is not None and decimal.Decimal(
            datos.saldo_apertura
        ) < CERO:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "saldo_apertura no puede ser negativo.",
            )
        if datos.importe_inicial is not None and decimal.Decimal(
            datos.importe_inicial
        ) <= CERO:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "El importe inicial de una posicion debe ser positivo.",
            )
        if datos.fecha_hecho is None:
            raise ErrorMotor(
                CodigoError.FECHA_ECONOMICA_AUSENTE,
                "El hecho causal exige fecha economica.",
            )

    @staticmethod
    def _validar_delta(delta: DatosDeltaPosicion) -> None:
        if delta.importe is None or decimal.Decimal(delta.importe) <= CERO:
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "La API recibe magnitud positiva; el signo lo pone el motor.",
            )
        if delta.fecha_hecho is None:
            raise ErrorMotor(
                CodigoError.FECHA_ECONOMICA_AUSENTE,
                "El hecho exige fecha economica.",
            )

    @staticmethod
    def _validar_causa(
        delta: DatosDeltaPosicion, causa_esperada: CausaReduccion
    ) -> None:
        """F04-D052. Causa obligatoria, del vocabulario cerrado y la de ESTA
        operacion. Ausente, desconocida o ajena -> STOP. Nunca se infiere:
        ni por diferencia de importes ni por la presencia de movimiento."""
        if (
            not isinstance(delta.causa, CausaReduccion)
            or delta.causa is not causa_esperada
        ):
            raise ErrorMotor(
                CodigoError.CAUSA_REDUCCION_INVALIDA,
                "La reduccion exige declarar su causa y debe ser la de la "
                "operacion: PAGO, COBRO o CONDONACION.",
            )

    @staticmethod
    def _validar_cierre(cierre: DatosCierre) -> None:
        if cierre.motivo_cierre not in MOTIVOS_CIERRE:
            raise ErrorMotor(
                CodigoError.CIERRE_SIN_MOTIVO,
                "El cierre exige un motivo del conjunto cerrado.",
            )
        if cierre.fecha_cierre is None or not isinstance(cierre.fecha_cierre, dt.date):
            raise ErrorMotor(
                CodigoError.CIERRE_SIN_MOTIVO,
                "El cierre exige fecha de cierre explicita.",
            )

    @staticmethod
    def _valores_posicion(datos: DatosAltaPosicion) -> dict[str, Any]:
        return {
            "entidad_id": datos.entidad_id,
            "tipo": datos.tipo,
            "contraparte_actor_id": datos.contraparte_actor_id,
            "moneda": datos.moneda,
            "importe_original_documentado": datos.importe_original_documentado,
            "saldo_apertura": datos.saldo_apertura,
            "fecha_inicio_seguimiento": datos.fecha_inicio_seguimiento,
            "notas": datos.notas,
        }

    def _ejecutar(
        self, contexto: ContextoOperacion, operacion: Any, nombre: str
    ) -> ResultadoPosicion:
        resultado = self._unidad.ejecutar_con_traza(contexto, operacion, nombre=nombre)
        self.ultima_traza = resultado.traza
        return resultado.valor
