# ============================================================
# GAPTO MOBILE 2027
# Fichero: compuesto_service.py
# Ruta: backend/app/services/compuesto_service.py
# Descripcion: F04-D048 R3 (A17). OP-22 «Registrar hecho compuesto».
#
#   ORQUESTADOR, NO MOTOR. OP-22 no reimplementa ninguna dimension financiera:
#   construye los servicios certificados adscritos a su UNICA transaccion
#   (`UnidadDeTrabajoAdscrita`) y llama a sus metodos publicos tal cual:
#     OP-01 hecho | OP-18 suplemento (Q02) | OP-04/05 efectos y reparto |
#     participantes | OP-12 posicion EXPLICITA enganchada a la raiz |
#     OP-08 movimiento + OP-09 conciliacion | OP-06 aportaciones |
#     writers contextuales A18 | OP-17 vinculo con prevision.
#   Todo lo solicitado se confirma entero o nada: sin savepoints y con un solo
#   COMMIT, el de la unidad de trabajo que abre la transaccion. El retry ante
#   40P01/40001 es el de esa unidad: repite la invocacion ENTERA con los mismos
#   UUID reservados.
#
#   OP-19 NO SE TOCA (R3-01): sigue siendo el comando especializado de gasto
#   compartido sin posiciones.
#
#   IDENTIDAD ANTES DE VALIDACION (§14). Lo primero es mirar si la raiz ya
#   existe. Si existe, se compara la intencion completa contra lo persistido
#   (identidad y contenido, nunca estado mutable como `enabled`):
#     todo presente e igual -> resultado idempotente (equivale a YA_APLICADA);
#     falta algo o algo difiere -> IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
#     sin completar nada. Solo una intencion realmente nueva ejecuta las
#     validaciones dependientes del estado actual.
#
#   NADA SE INFIERE. Una posicion solo nace si viene declarada (con
#   contraparte, importe y justificacion propios de OP-12). Nunca por
#   diferencia atribucion/aportacion, pagador, cuenta, movimiento ni reparto de
#   propiedad o cuenta (INV-04). La aportacion solo existe si se declara
#   (Q01), y la realizacion de una prevision solo si `marcar_realizada=True`.
#
#   LOCKS (pronunciamiento R3-02, contrastado con los servicios reales):
#     1. advisory INVERSIONES si la invocacion va a escribir hecho_entidades
#        (contexto o vinculo GENERADO_POR de OP-12);
#     2. raiz hechos_financieros (creada aqui o bloqueada por los servicios);
#     3. movimientos (nuevos);
#     4. entidades de posicion (nuevas, orden de la entrada);
#     5. regla y prevision (OP-17), siempre al final.
#   Es el mismo sentido que OP-09 (hecho->movimiento), los deltas de posicion
#   (movimiento->entidad) y OP-21 (advisory->hecho).
#
#   F07 (§21): OP-22 no crea financiaciones, cuotas, calendarios, asignaciones
#   de inversion ni valoraciones. Solo puede VINCULAR contexto a entidades ya
#   existentes segun la matriz R3-01 (el resto -> OWNERSHIP_F07).
#
#   v0.2.0 (F04-D050): el reconocimiento de identidad exige IGUALDAD EXACTA del
#   agregado (contrato A-E). A la comprobacion existente -lo declarado existe e
#   es igual (B, D, E)- se anade que el agregado persistido no contenga
#   elementos no declarados (C): por cada tabla del agregado, el conjunto de
#   identidades persistidas debe coincidir con el conjunto declarado. Antes se
#   reconocia por inclusion y un reintento con intencion reducida (p. ej. sin
#   la aportacion ya materializada) se devolvia como exito idempotente.
#   Tambien (contrato A): el vinculo de una posicion solo se exige cuando la
#   posicion declara importe inicial; antes el reintento identico de una
#   posicion sin importe se rechazaba como conflicto.
# Version: 0.2.0
# ============================================================

from __future__ import annotations

import dataclasses
import uuid
from typing import Any

from app.core.contexto import ContextoOperacion
from app.core.errores import CodigoError, ErrorMotor
from app.core.modelos_compuesto import DatosHechoCompuesto, ResultadoHechoCompuesto
from app.core.modelos_prevision import DatosVinculo
from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
from app.core.unidad_trabajo import SesionMotor, Traza, UnidadDeTrabajo
from app.repositories import compuesto_repository as repo_comp
from app.repositories import hechos_repository as repo_hechos
from app.services import contexto_service as ctx
from app.services.contexto_service import ContextoService, _mismo
from app.services.efectos_service import EfectosService
from app.services.hechos_service import HechosService
from app.services.participantes_service import ParticipantesService
from app.services.posiciones_service import PosicionesService
from app.services.previsiones_service import PrevisionesService
from app.services.suplementos_service import SuplementosService
from app.services.tesoreria_service import TesoreriaService

NATURALEZAS_PRESUPUESTABLES = ("GASTO", "INGRESO")


class HechosCompuestosService:
    """OP-22. Registro atomico de una intencion financiera compuesta."""

    def __init__(self, unidad: UnidadDeTrabajo, *, impacto_ancla: Any) -> None:
        """`impacto_ancla` se transporta a `HechosService`, que lo exige."""
        self._unidad = unidad
        self._impacto_ancla = impacto_ancla
        self.ultima_traza: Traza | None = None

    # ==================================================================
    # OP-22
    # ==================================================================
    def registrar_hecho_compuesto(
        self, contexto: ContextoOperacion, datos: DatosHechoCompuesto
    ) -> ResultadoHechoCompuesto:
        self._validar_estructura(datos)
        raiz = datos.hecho_id

        def operacion(sesion: SesionMotor) -> ResultadoHechoCompuesto:
            owner = repo_hechos.exigir_contexto(sesion)

            # 1. Advisory D-080 antes de cualquier row lock (R3-02). No es una
            #    validacion de estado: tomarlo antes de leer la identidad hace
            #    ademas que, con dos invocaciones identicas solapadas, la
            #    segunda VEA la raiz ya confirmada y responda idempotente.
            ctx.tomar_advisory_si_entidades(
                sesion,
                owner,
                bool(datos.contexto.entidades) or bool(datos.posiciones),
            )

            # 2. IDENTIDAD antes que cualquier validacion de estado (§14).
            if repo_hechos.leer_estado(sesion, raiz) is not None:
                if self._agregado_coincide(sesion, datos):
                    return self._resultado_existente(sesion, datos)
                raise ErrorMotor(
                    CodigoError.IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION,
                    "La raiz de OP-22 ya existe con otra intencion o solo existe "
                    "una parte del agregado: no se completa en silencio.",
                )

            adscrita = UnidadDeTrabajoAdscrita(sesion)
            resultado = self._componer(contexto, adscrita, datos)
            return resultado

        ejecutado = self._unidad.ejecutar_con_traza(
            contexto, operacion, nombre="OP-22 registrar_hecho_compuesto"
        )
        self.ultima_traza = ejecutado.traza
        return ejecutado.valor

    # ==================================================================
    # Composicion (intencion nueva)
    # ==================================================================
    def _componer(
        self,
        contexto: ContextoOperacion,
        adscrita: UnidadDeTrabajoAdscrita,
        datos: DatosHechoCompuesto,
    ) -> ResultadoHechoCompuesto:
        raiz = datos.hecho_id
        cuenta: dict[str, int] = {}

        # Raiz: OP-01 o, para realidad suplementaria, OP-18 adscrito (Q02).
        if datos.hecho is not None:
            version = HechosService(adscrita, impacto_ancla=self._impacto_ancla).crear_hecho(
                contexto, datos.hecho
            ).row_version
        else:
            version = SuplementosService(adscrita).registrar(
                contexto, datos.suplemento
            ).hecho_row_version

        if datos.efectos:
            elegible = any(e.tipo_efecto in NATURALEZAS_PRESUPUESTABLES for e in datos.efectos)
            r = EfectosService(adscrita).registrar_efectos(
                contexto,
                hecho_id=raiz,
                row_version_esperada=version,
                efectos=datos.efectos,
                # A08-bis: propagacion de la decision ya explicita del hecho.
                presupuestable=datos.hecho.presupuestable if elegible else None,
            )
            version = r.row_version
            cuenta["efectos"] = len(r.efectos)
            cuenta["atribuciones"] = r.atribuciones_creadas

        if datos.participantes:
            r = ParticipantesService(adscrita).registrar_participantes(
                contexto,
                hecho_id=raiz,
                row_version_esperada=version,
                participantes=datos.participantes,
            )
            version = r.row_version
            cuenta["participantes"] = r.participantes_creados

        posiciones: dict[uuid.UUID, int] = {}
        if datos.posiciones:
            servicio_pos = PosicionesService(adscrita)
            for alta in datos.posiciones:
                r = servicio_pos.crear_posicion(
                    contexto, dataclasses.replace(alta, hecho_row_version_esperada=version)
                )
                posiciones[alta.entidad_id] = r.entidad_row_version
                version = r.hecho_row_version

        movimientos: dict[uuid.UUID, int] = {}
        if datos.pagos:
            tesoreria = TesoreriaService(adscrita)
            for pago in datos.pagos:
                mov = tesoreria.registrar_movimiento(contexto, pago.movimiento)
                conc = tesoreria.conciliar(
                    contexto,
                    pago.conciliacion,
                    hecho_row_version_esperada=version,
                    movimiento_row_version_esperada=mov.row_version,
                )
                version = conc.hecho_row_version
                movimientos[pago.movimiento.movimiento_id] = conc.movimiento_row_version
            cuenta["conciliaciones"] = len(datos.pagos)

        if datos.aportaciones:
            r = TesoreriaService(adscrita).registrar_aportaciones(
                contexto,
                hecho_id=raiz,
                hecho_row_version_esperada=version,
                aportaciones=datos.aportaciones,
            )
            version = r.hecho_row_version
            cuenta["aportaciones"] = r.aportaciones_creadas

        if not datos.contexto.vacio:
            r = ContextoService(adscrita).enriquecer(
                contexto, hecho_id=raiz, row_version_esperada=version, datos=datos.contexto
            )
            version = r.hecho_row_version
            cuenta["contexto"] = (
                r.terceros_creados + r.entidades_creadas + r.magnitudes_creadas + r.etiquetas_creadas
            )

        prevision_version: int | None = None
        if datos.prevision is not None:
            p = datos.prevision
            prevision_version = PrevisionesService(adscrita).vincular_realidad(
                contexto,
                prevision_id=p.prevision_id,
                row_version_esperada=p.prevision_row_version_esperada,
                datos=DatosVinculo(
                    vinculo_id=p.vinculo_id,
                    hecho_id=raiz,
                    importe_asignado=p.importe_asignado,
                    marcar_realizada=p.marcar_realizada,
                    equivalencia_declarada=p.equivalencia_declarada,
                ),
                uuid_sucesor=p.uuid_sucesor,
            ).row_version

        return ResultadoHechoCompuesto(
            hecho_id=raiz,
            hecho_row_version=version,
            movimientos=movimientos,
            posiciones=posiciones,
            prevision_row_version=prevision_version,
            efectos_creados=cuenta.get("efectos", 0),
            atribuciones_creadas=cuenta.get("atribuciones", 0),
            participantes_creados=cuenta.get("participantes", 0),
            aportaciones_creadas=cuenta.get("aportaciones", 0),
            conciliaciones_creadas=cuenta.get("conciliaciones", 0),
            contexto_creado=cuenta.get("contexto", 0),
        )

    # ==================================================================
    # Replay: comparacion del agregado completo (identidad + contenido)
    # ==================================================================
    @staticmethod
    def _campos(fila: dict[str, Any] | None, esperado: dict[str, Any]) -> bool:
        if fila is None:
            return False
        return all(_mismo(fila.get(k), v) for k, v in esperado.items())

    def _agregado_coincide(self, sesion: SesionMotor, d: DatosHechoCompuesto) -> bool:
        raiz = d.hecho_id
        leer = lambda tabla, i: repo_comp.leer(sesion, tabla, i)  # noqa: E731
        comprobaciones: list[bool] = []

        hecho = leer("hechos_financieros", raiz)
        if d.hecho is not None:
            h = d.hecho
            esperado = {
                "fecha_hecho": h.fecha_hecho,
                "moneda": h.moneda,
                "concepto": h.concepto,
                "importe_total": h.importe_total,
                "numero_participantes_total": h.numero_participantes_total,
                "estado_localizacion": h.estado_localizacion,
                "localidad_id": h.localidad_id,
                "notas": h.notas,
            }
            if any(e.tipo_efecto in NATURALEZAS_PRESUPUESTABLES for e in d.efectos):
                esperado["presupuestable"] = h.presupuestable
            comprobaciones.append(self._campos(hecho, esperado))
            if h.tipo_hecho_id is not None:
                comprobaciones.append(_mismo(hecho["tipo_hecho_id"], h.tipo_hecho_id))
            elif h.tipo_hecho_codigo is not None:
                comprobaciones.append(
                    repo_comp.codigo_tipo_hecho(sesion, hecho["tipo_hecho_id"])
                    == h.tipo_hecho_codigo
                )
        else:
            s = d.suplemento
            comprobaciones.append(
                self._campos(
                    hecho,
                    {"fecha_hecho": s.fecha_hecho, "moneda": s.moneda, "concepto": s.concepto},
                )
            )
            comprobaciones.append(
                self._campos(
                    leer("hecho_efectos", s.efecto_id),
                    {"hecho_id": raiz, "tipo_efecto": s.tipo_efecto, "importe_delta": s.importe_delta},
                )
            )

        for e in d.efectos:
            comprobaciones.append(
                self._campos(
                    leer("hecho_efectos", e.efecto_id),
                    {
                        "hecho_id": raiz,
                        "tipo_efecto": e.tipo_efecto,
                        "importe_delta": e.importe_delta,
                        "estado_atribucion": e.estado_atribucion,
                        "categoria_id": e.categoria_id,
                    },
                )
            )
            for a in e.atribuciones:
                comprobaciones.append(
                    self._campos(
                        leer("efecto_atribuciones", a.atribucion_id),
                        {
                            "efecto_id": e.efecto_id,
                            "actor_id": a.actor_id,
                            "importe_atribuido": a.importe_atribuido,
                            "criterio_atribucion": a.criterio_atribucion,
                        },
                    )
                )
        for p in d.participantes:
            comprobaciones.append(
                self._campos(
                    leer("hecho_participantes", p.participante_id),
                    {"hecho_id": raiz, "actor_id": p.actor_id, "rol": p.rol},
                )
            )
        for alta in d.posiciones:
            comprobaciones.append(
                self._campos(
                    leer("derechos_obligaciones_financieras", alta.entidad_id),
                    {
                        "tipo": alta.tipo,
                        "contraparte_actor_id": alta.contraparte_actor_id,
                        "moneda": alta.moneda,
                    },
                )
            )
            # El vinculo (y su efecto causal) solo existe si la posicion trae
            # importe inicial (OP-12A `_crear_delta`). Exigirlo siempre hacia
            # que el reintento IDENTICO de una posicion sin importe fuese
            # conflicto (F04-D050, contrato A).
            if alta.importe_inicial is not None:
                comprobaciones.append(
                    self._campos(
                        leer("hecho_entidades", alta.vinculo_id),
                        {"hecho_id": raiz, "entidad_id": alta.entidad_id, "efecto_id": alta.efecto_id},
                    )
                )
        for pago in d.pagos:
            m = pago.movimiento
            comprobaciones.append(
                self._campos(
                    leer("movimientos_tesoreria", m.movimiento_id),
                    {
                        "cuenta_id": m.cuenta_id,
                        "fecha_movimiento": m.fecha_movimiento,
                        "importe": m.importe,
                        "clase_movimiento": m.clase_movimiento,
                    },
                )
            )
            c = pago.conciliacion
            comprobaciones.append(
                self._campos(
                    leer("hecho_movimientos_tesoreria", c.conciliacion_id),
                    {
                        "hecho_id": raiz,
                        "movimiento_tesoreria_id": c.movimiento_tesoreria_id,
                        "importe_asignado": c.importe_asignado,
                    },
                )
            )
        for a in d.aportaciones:
            comprobaciones.append(
                self._campos(
                    leer("hecho_aportaciones_pago", a.aportacion_id),
                    {
                        "hecho_id": raiz,
                        "actor_id": a.actor_id,
                        "importe": a.importe,
                        "criterio_aportacion": a.criterio_aportacion,
                        "hecho_movimiento_tesoreria_id": a.hecho_movimiento_tesoreria_id,
                    },
                )
            )
        if not d.contexto.vacio:
            comprobaciones.append(ctx.clasificar_replay(sesion, raiz, d.contexto) == "REPLICA")
        if d.prevision is not None:
            p = d.prevision
            comprobaciones.append(
                self._campos(
                    leer("prevision_hechos", p.vinculo_id),
                    {
                        "prevision_id": p.prevision_id,
                        "hecho_id": raiz,
                        "importe_asignado": p.importe_asignado,
                    },
                )
            )
            if p.marcar_realizada:
                prevision = leer("previsiones", p.prevision_id)
                comprobaciones.append(prevision is not None and prevision["estado"] == "REALIZADA")
        # F04-D050 (C): sin elementos persistidos no declarados.
        comprobaciones.append(
            repo_comp.identidades_del_agregado(sesion, raiz) == self._identidades_declaradas(d)
        )
        return all(comprobaciones)

    @staticmethod
    def _identidades_declaradas(d: DatosHechoCompuesto) -> dict[str, set[uuid.UUID]]:
        """Conjunto exacto de identidades que la intencion materializa, por tabla
        del agregado (mismo conjunto cerrado que `FILTROS_AGREGADO`).

        Una posicion declarada crea efecto causal y vinculo solo cuando trae
        `importe_inicial` (OP-12A, `_crear_delta`); sin importe, solo existen la
        entidad y la posicion, que no cuelgan de la raiz."""
        con_delta = [a for a in d.posiciones if a.importe_inicial is not None]
        efectos = {e.efecto_id for e in d.efectos} | {a.efecto_id for a in con_delta}
        if d.suplemento is not None:
            efectos.add(d.suplemento.efecto_id)
        relaciones: set[uuid.UUID] = set()
        if d.suplemento is not None and d.suplemento.con_relacion:
            relaciones.add(d.suplemento.relacion_id)
        return {
            "hecho_efectos": efectos,
            "efecto_atribuciones": {a.atribucion_id for e in d.efectos for a in e.atribuciones},
            "hecho_participantes": {p.participante_id for p in d.participantes},
            "hecho_movimientos_tesoreria": {p.conciliacion.conciliacion_id for p in d.pagos},
            "hecho_aportaciones_pago": {a.aportacion_id for a in d.aportaciones},
            "hecho_entidades": {a.vinculo_id for a in con_delta}
            | {x.registro_id for x in d.contexto.entidades},
            "hecho_terceros": {x.registro_id for x in d.contexto.terceros},
            "hecho_magnitudes": {x.registro_id for x in d.contexto.magnitudes},
            "hecho_etiquetas": {x.registro_id for x in d.contexto.etiquetas},
            "prevision_hechos": set() if d.prevision is None else {d.prevision.vinculo_id},
            "hecho_relaciones": relaciones,
            "efecto_cuentas": set(),
            "inversion_asignaciones_efecto": set(),
        }

    @staticmethod
    def _resultado_existente(
        sesion: SesionMotor, d: DatosHechoCompuesto
    ) -> ResultadoHechoCompuesto:
        raiz = d.hecho_id
        leer = lambda tabla, i: repo_comp.leer(sesion, tabla, i)  # noqa: E731
        prevision = (
            None if d.prevision is None else leer("previsiones", d.prevision.prevision_id)
        )
        return ResultadoHechoCompuesto(
            hecho_id=raiz,
            hecho_row_version=leer("hechos_financieros", raiz)["row_version"],
            idempotente=True,
            movimientos={
                p.movimiento.movimiento_id: leer("movimientos_tesoreria", p.movimiento.movimiento_id)["row_version"]
                for p in d.pagos
            },
            posiciones={
                a.entidad_id: leer("entidades", a.entidad_id)["row_version"] for a in d.posiciones
            },
            prevision_row_version=None if prevision is None else prevision["row_version"],
        )

    # ==================================================================
    # Validacion estructural (sin estado)
    # ==================================================================
    @staticmethod
    def _validar_estructura(d: DatosHechoCompuesto) -> None:
        if (d.hecho is None) == (d.suplemento is None):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "OP-22 exige exactamente una raiz: un hecho nuevo (OP-01) o una "
                "realidad suplementaria (OP-18).",
            )
        raiz = d.hecho_id
        if d.suplemento is not None and (d.efectos or d.participantes or d.posiciones):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "Con raiz suplementaria OP-22 compone solo pago, aportaciones, "
                "contexto y prevision: el efecto lo crea OP-18 (Q02).",
            )
        for pago in d.pagos:
            if pago.conciliacion.hecho_id != raiz:
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    "La conciliacion debe referirse a la raiz de OP-22.",
                )
            if pago.conciliacion.movimiento_tesoreria_id != pago.movimiento.movimiento_id:
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    "La conciliacion debe referirse al movimiento con el que viaja.",
                )
        for alta in d.posiciones:
            if alta.hecho_id != raiz or alta.hecho_row_version_esperada is not None:
                raise ErrorMotor(
                    CodigoError.ENTRADA_INVALIDA,
                    "Una posicion de OP-22 se engancha a la raiz y su version la "
                    "encadena el orquestador.",
                )
        if d.prevision is not None and not isinstance(d.prevision.marcar_realizada, bool):
            raise ErrorMotor(
                CodigoError.ENTRADA_INVALIDA,
                "`marcar_realizada` es una decision explicita obligatoria.",
            )
        ctx.validar_estructura(d.contexto)
