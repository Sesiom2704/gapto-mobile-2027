# ============================================================
# GAPTO MOBILE 2027
# Fichero: alta.py
# Ruta: backend/app/hipotecas/alta.py
# Descripcion: W-HIP-01 · alta de la hipoteca DENTRO de C-COMPRA-01 (F06-01H; contrato v0.4 §3.2; D6, D7;
#   mandato T3-F06 bloque 2 v1.1 §2.1). Lo invoca `patrimonio/compra.py` en la misma transaccion y en el
#   mismo savepoint que la compra; este modulo no abre transacciones.
#   - forma(): bloque `hipoteca` de la peticion (§3.2.1) ANTES de cualquier lock. Falta o fuera de rango ->
#     CONDICIONES_INCOMPLETAS con motivo (DATO_OBLIGATORIO_AUSENTE, VALORES_FUERA_DE_RANGO,
#     SISTEMA_NO_SOPORTADO, PERIODICIDAD_NO_SOPORTADA, PRIMERA_CUOTA_NO_POSTERIOR_A_LA_ESCRITURA). Modalidad
#     no representable (§3.2.7-8): fecha_desembolso, pago_directo_vendedor, tramos o importe_ingresado = P ->
#     MODALIDAD_DESEMBOLSO_NO_SOPORTADA; importe_ingresado != P o comision_retenida > 0 ->
#     DESEMBOLSO_DISTINTO_DE_CAPITAL (§3.2.7-7). Nunca se registra una fecha o forma ficticia.
#   - Identidades (§1.2): todas uuid5 de H0 (= intencion_id de la compra): F, sus participaciones, la relacion
#     GARANTIZADA_POR, la version ALTA, las cuotas 1..N y sus previsiones, y el hecho de desembolso Hd con su
#     efecto DEUDA, atribuciones, movimiento +P, conciliacion, aportaciones, vinculo de nivel efecto y PARTE_DE.
#   - Hd (§3.2.3-5; firma 8aa948f9 tipo de Hd; C-01): hecho GENERACION_DERECHO_OBLIGACION, no presupuestable,
#     fecha = escritura, importe = P; UN efecto DEUDA +P atribuido por la titularidad DEL PRESTAMO (D13);
#     movimiento +P en la cuenta de desembolso conciliado ENTERO; SIN aportaciones (OP-06/OP-07 solo las admiten
#     sobre salidas; firma STOP n.º 2 / Q3, 5f3f5f8e…, opcion A definitiva); por OP-22 adscrito. Vinculo AFECTA_A de NIVEL EFECTO a la
#     financiacion por el writer propio (vinculo.py). Enlace con la compra: PARTE_DE Hd -> H0 con la marca
#     `gapto.f06.compra.desembolso` (H-HIP-02, paso 1).
#   - Financiacion (§1.1): entidad FINANCIACION «Hipoteca · <propiedad>»; HIPOTECA, EUR, P, apertura 0 con
#     inicio de seguimiento = escritura, ACTIVA; participaciones del prestamo desde la escritura; relacion
#     GARANTIZADA_POR -> propiedad; version ALTA con hecho_causa_id = Hd; N cuotas del cuadro (calculadora.py)
#     cada una con su prevision MANUAL creada por PrevisionesService.crear_manual (I3) adscrita; auditoria CREAR
#     de la financiacion.
#   - aviso_reparto_distinto (§3.2.7-5): la distribucion de la cuenta de desembolso y la del prestamo en la
#     escritura difieren. No altera atribuciones ni posiciones.
#   Locks: los toma la compra (R1, §6): advisory de raices (H0, Hk, Hd) -> INVERSIONES -> propiedad -> cuentas
#   por UUID una vez cada una (pagos, desembolso y cargo) -> resto del agregado.
# Version: 0.1.0 (F06 T3-F06 bloque 2 F06-01H, paso 5)
# Version: 0.1.1 (F06 T3-F06 bloque 2 F06-01H, paso 6): APORTACIONES_EN_ENTRADA = False definitiva por la firma
#   del STOP n.º 2 (5f3f5f8e…); solo comentarios.
# ============================================================

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.modelos import DatosCreacionHecho
from app.core.modelos_compuesto import DatosHechoCompuesto, DatosPagoCompuesto
from app.core.modelos_efectos import DatosEfecto
from app.core.modelos_prevision import DatosPrevisionManual
from app.core.modelos_tesoreria import DatosAportacion, DatosConciliacion, DatosMovimiento
from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
from app.core.unidad_trabajo import SesionMotor
from app.hipotecas import calculadora as calc
from app.hipotecas import vinculo
from app.patrimonio import atribucion as m2
from app.repositories import auditoria_repository as auditoria
from app.services.previsiones_service import PrevisionesService

CENT = Decimal("0.01")
EUR = "EUR"
TIPO_HD = "GENERACION_DERECHO_OBLIGACION"
MARCA_DESEMBOLSO = "gapto.f06.compra.desembolso"
OPERACION_DESEMBOLSO = "DESEMBOLSO_FINANCIACION"
MOTIVO_ALTA = "F06-01H W-HIP-01: alta de la hipoteca en la compra"
MOTIVO_ACTOR = "F06-01H W-HIP-01: alta del actor financiero del financiador de la hipoteca"

CONDICIONES_INCOMPLETAS = calc.CONDICIONES_INCOMPLETAS
HIPOTECA_YA_REGISTRADA = "HIPOTECA_YA_REGISTRADA"
CUENTA_SIN_CAPACIDAD = "CUENTA_SIN_CAPACIDAD"
TERCERO_NO_DISPONIBLE = "TERCERO_NO_DISPONIBLE"
DATO_OBLIGATORIO_AUSENTE = "DATO_OBLIGATORIO_AUSENTE"
PRIMERA_CUOTA_NO_POSTERIOR = "PRIMERA_CUOTA_NO_POSTERIOR_A_LA_ESCRITURA"
MODALIDAD_NO_SOPORTADA = "MODALIDAD_DESEMBOLSO_NO_SOPORTADA"
DESEMBOLSO_DISTINTO = "DESEMBOLSO_DISTINTO_DE_CAPITAL"
TIPOS_INTERES = ("FIJO", "VARIABLE")
MAX_TASA_DECIMALES = Decimal("0.0001")
OBLIGATORIOS = ("financiador", "importe_prestamo", "cuenta_desembolso_id", "titularidad", "tipo_interes",
                "tasa_anual_pct", "numero_cuotas", "fecha_primera_cuota", "cuenta_cargo_id")
#: Campos de modalidad no representable en v1 (§3.2.7-8): se aceptan en el DTO solo para rechazarlos con motivo.
MODALIDAD = ("fecha_desembolso", "pago_directo_vendedor", "tramos")
#: DEFINITIVA (firma de Moises STOP n.º 2 / Q3, 5f3f5f8e…; enmienda e28be7c6… del contrato v0.4 §3.2.3-5 y O-H30
#: y del literal B2 v1.1 MB2-13): para una entrada la regla vigente de OP-06/OP-07 es «ninguna aportacion»
#: (USO_EN_COBRO_NO_PERMITIDO); Hd va sin aportaciones (Q-T3D-04). No se toca OP-06/OP-07. Constante de codigo.
APORTACIONES_EN_ENTRADA = False


def _dec(v: Any) -> Decimal | None:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


# ------------------------------------------------------------------ forma (antes de cualquier lock)
def forma(h: dict[str, Any], escritura: dt.date) -> str | None:
    """Motivo de CONDICIONES_INCOMPLETAS o None. Modalidad no representable primero (§3.2.7-7/8)."""
    p = _dec(h.get("importe_prestamo"))
    if any(h.get(k) not in (None, False, []) for k in MODALIDAD):
        return MODALIDAD_NO_SOPORTADA
    ingresado, comision = h.get("importe_ingresado"), h.get("comision_retenida")
    if comision is not None and (_dec(comision) is None or _dec(comision) != 0):
        return DESEMBOLSO_DISTINTO
    if ingresado is not None:
        return DESEMBOLSO_DISTINTO if (p is None or _dec(ingresado) != p) else MODALIDAD_NO_SOPORTADA
    if any(h.get(k) is None for k in OBLIGATORIOS):
        return DATO_OBLIGATORIO_AUSENTE
    sistema, periodicidad = h.get("sistema") or calc.SISTEMA, h.get("periodicidad") or calc.PERIODICIDAD
    try:
        calc.validar_condiciones(sistema=sistema, periodicidad=periodicidad)
    except calc.CondicionesIncompletas as exc:
        return exc.motivo
    tasa, n = _dec(h["tasa_anual_pct"]), h["numero_cuotas"]
    if p is None or tasa is None or h["tipo_interes"] not in TIPOS_INTERES:
        return calc.VALORES_FUERA_DE_RANGO
    if tasa != tasa.quantize(MAX_TASA_DECIMALES):
        return calc.VALORES_FUERA_DE_RANGO
    try:
        calc.validar_valores(capital=p, tasa_anual=tasa, numero_cuotas=n)
    except calc.CondicionesIncompletas as exc:
        return exc.motivo
    if h["fecha_primera_cuota"] <= escritura:
        return PRIMERA_CUOTA_NO_POSTERIOR
    if h.get("diferencial_pct") is not None and _dec(h["diferencial_pct"]) is None:
        return calc.VALORES_FUERA_DE_RANGO
    return None


def canonica(h: dict[str, Any]) -> dict[str, Any]:
    """Forma canonica del bloque para el sello de la compra (§1.3 de B2): un cambio de cualquier campo cambia el
    sello y el replay se rechaza con IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION (O-H15)."""
    from app.patrimonio.compra import canonica_atribucion   # import diferido: compra importa este modulo
    tasa = Decimal(str(h["tasa_anual_pct"]))
    dif = h.get("diferencial_pct")
    return {
        "financiador": {"tercero_id": str(h["financiador"]["tercero_id"]).lower()},
        "importe_prestamo": str(Decimal(str(h["importe_prestamo"])).quantize(CENT)),
        "cuenta_desembolso_id": str(h["cuenta_desembolso_id"]).lower(),
        "titularidad": canonica_atribucion(h["titularidad"]),
        "tipo_interes": h["tipo_interes"], "tasa_anual_pct": str(tasa.quantize(MAX_TASA_DECIMALES)),
        "indice_referencia": h.get("indice_referencia"),
        "diferencial_pct": None if dif is None else str(Decimal(str(dif)).quantize(MAX_TASA_DECIMALES)),
        "numero_cuotas": int(h["numero_cuotas"]), "fecha_primera_cuota": h["fecha_primera_cuota"].isoformat()
        if isinstance(h["fecha_primera_cuota"], dt.date) else str(h["fecha_primera_cuota"]),
        "cuenta_cargo_id": str(h["cuenta_cargo_id"]).lower(),
        "sistema": calc.SISTEMA, "periodicidad": calc.PERIODICIDAD,
    }


# ------------------------------------------------------------------ plan (identidades y valores esperados)
@dataclass(frozen=True)
class Plan:
    h0: uuid.UUID
    propiedad_id: uuid.UUID
    escritura: dt.date
    canon: dict[str, Any]
    financiacion_id: uuid.UUID
    hd: uuid.UUID
    efecto_deuda: uuid.UUID
    movimiento: uuid.UUID
    conciliacion: uuid.UUID
    vinculo_id: uuid.UUID
    parte_de: uuid.UUID
    relacion: uuid.UUID
    version: uuid.UUID
    cuadro: tuple[calc.Cuota, ...]

    @property
    def p(self) -> Decimal:
        return Decimal(self.canon["importe_prestamo"])

    @property
    def cuenta_desembolso(self) -> uuid.UUID:
        return uuid.UUID(self.canon["cuenta_desembolso_id"])

    @property
    def cuenta_cargo(self) -> uuid.UUID:
        return uuid.UUID(self.canon["cuenta_cargo_id"])

    @property
    def primera_cuota(self) -> dt.date:
        return dt.date.fromisoformat(self.canon["fecha_primera_cuota"])

    def cuota_id(self, k: int) -> uuid.UUID:
        return uuid.uuid5(self.financiacion_id, f"gapto.f06.hipoteca.cuota:{k}")

    def prevision_id(self, k: int) -> uuid.UUID:
        return uuid.uuid5(self.financiacion_id, f"gapto.f06.hipoteca.prevision:{k}")

    def participacion_id(self, actor: uuid.UUID) -> uuid.UUID:
        return uuid.uuid5(self.financiacion_id, f"gapto.f06.hipoteca.participacion:{actor}")

    def aportacion_id(self, actor: uuid.UUID) -> uuid.UUID:
        return uuid.uuid5(self.hd, f"gapto.f06.hipoteca.aportacion:{actor}")


def plan(h0: uuid.UUID, propiedad_id: uuid.UUID, escritura: dt.date, canon: dict[str, Any]) -> Plan:
    f = uuid.uuid5(h0, "gapto.f06.hipoteca.financiacion")
    hd = uuid.uuid5(h0, MARCA_DESEMBOLSO)
    cuadro = calc.cuadro_frances(Decimal(canon["importe_prestamo"]), Decimal(canon["tasa_anual_pct"]),
                                 canon["numero_cuotas"], dt.date.fromisoformat(canon["fecha_primera_cuota"]))
    return Plan(h0=h0, propiedad_id=propiedad_id, escritura=escritura, canon=canon, financiacion_id=f, hd=hd,
                efecto_deuda=uuid.uuid5(hd, "gapto.f06.hipoteca.efecto_deuda"),
                movimiento=uuid.uuid5(hd, "gapto.f06.hipoteca.movimiento"),
                conciliacion=uuid.uuid5(hd, "gapto.f06.hipoteca.conciliacion"),
                vinculo_id=uuid.uuid5(hd, "gapto.f06.hipoteca.vinculo_financiacion"),
                parte_de=uuid.uuid5(hd, MARCA_DESEMBOLSO), relacion=uuid.uuid5(f, "gapto.f06.hipoteca.garantizada_por"),
                version=uuid.uuid5(f, "gapto.f06.hipoteca.version_alta"), cuadro=tuple(cuadro))


# ------------------------------------------------------------------ lecturas bajo lock
def participacion_cuenta(sesion: SesionMotor, cuenta: uuid.UUID, fecha: dt.date) -> list[tuple[uuid.UUID, Decimal]]:
    """Distribucion economica de la cuenta en la fecha, ordenada por actor (texto)."""
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT actor_id, porcentaje FROM gapto.cuenta_participaciones WHERE cuenta_id = %s "
                    "AND vigente_desde <= %s AND (vigente_hasta IS NULL OR vigente_hasta >= %s) "
                    "ORDER BY actor_id::text", (cuenta, fecha, fecha))
        return [(a, Decimal(p).quantize(m2.ESCALA_PCT)) for a, p in cur.fetchall()]


def aviso_reparto_distinto(cuenta: list[tuple[uuid.UUID, Decimal]],
                           prestamo: list[tuple[uuid.UUID, Decimal]] | None) -> bool:
    """§3.2.7-5: True si las dos distribuciones en la escritura difieren (sin prestamo repartido: False)."""
    if not prestamo:
        return False
    return sorted(cuenta, key=lambda x: str(x[0])) != sorted(
        ((a, Decimal(p).quantize(m2.ESCALA_PCT)) for a, p in prestamo), key=lambda x: str(x[0]))


def hipoteca_activa(sesion: SesionMotor, propiedad_id: uuid.UUID) -> bool:
    """INV-HIP-16 bajo el lock de la propiedad: ya hay una HIPOTECA ACTIVA garantizada por la propiedad."""
    return sesion.uno(
        "SELECT 1 FROM gapto.entidad_relaciones r JOIN gapto.financiaciones f ON f.entidad_id = r.entidad_origen_id "
        "WHERE r.entidad_destino_id = %s AND r.tipo_relacion = 'GARANTIZADA_POR' AND f.tipo_financiacion = 'HIPOTECA' "
        "AND f.estado = 'ACTIVA' LIMIT 1", (propiedad_id,)) is not None


def financiador(sesion: SesionMotor, tercero_id: uuid.UUID) -> uuid.UUID | str:
    """Writer de actor (v0.2 §2.1): tercero del owner, habilitado, FOR SHARE; su actor (lo crea si falta)."""
    from app.actores import repositorio as repo_actores
    from app.actores import servicio as serv_actores
    tercero = repo_actores.leer_tercero_compartido(sesion, tercero_id)
    if tercero is None or not tercero["enabled"]:
        return TERCERO_NO_DISPONIBLE
    try:
        return serv_actores.actor_de_tercero(sesion, tercero_id, MOTIVO_ACTOR)
    except serv_actores.RechazoActor:
        return TERCERO_NO_DISPONIBLE


# ------------------------------------------------------------------ composicion
def composicion_hd(pl: Plan, prestamo: list[tuple[uuid.UUID, Decimal]] | None, modo: str,
                   cuenta: list[tuple[uuid.UUID, Decimal]]) -> DatosHechoCompuesto:
    """Hd por OP-22 (sin el vinculo de nivel efecto, que escribe el writer propio)."""
    estado, filas = m2.filas(pl.efecto_deuda, pl.p, prestamo, modo, "gapto.f06.hipoteca.atribucion:")
    importes = m2.repartir(pl.p, cuenta) if cuenta else {}
    return DatosHechoCompuesto(
        hecho=DatosCreacionHecho(hecho_id=pl.hd, fecha_hecho=pl.escritura, moneda=EUR, presupuestable=False,
                                 estado_localizacion="NO_APLICA", tipo_hecho_codigo=TIPO_HD,
                                 concepto="PRESTAMO RECIBIDO", importe_total=pl.p, notas=None),
        efectos=[DatosEfecto(efecto_id=pl.efecto_deuda, tipo_efecto="DEUDA", importe_delta=pl.p,
                             estado_atribucion=estado, atribuciones=filas)],
        pagos=[DatosPagoCompuesto(
            movimiento=DatosMovimiento(movimiento_id=pl.movimiento, cuenta_id=pl.cuenta_desembolso,
                                       fecha_movimiento=pl.escritura, importe=pl.p, clase_movimiento="OPERACION",
                                       descripcion="PRESTAMO RECIBIDO"),
            conciliacion=DatosConciliacion(conciliacion_id=pl.conciliacion, hecho_id=pl.hd,
                                           movimiento_tesoreria_id=pl.movimiento, importe_asignado=pl.p))],
        # Firma STOP n.º 2 (opcion A, definitiva): OP-06/OP-07 solo admiten aportaciones sobre SALIDAS; la entrada
        # +P no lleva aportacion.
        aportaciones=[] if not APORTACIONES_EN_ENTRADA else [
            DatosAportacion(aportacion_id=pl.aportacion_id(a), importe=importes[a],
                            criterio_aportacion="PARTICIPACION_CUENTA", actor_id=a, porcentaje_aplicado=pc,
                            hecho_movimiento_tesoreria_id=pl.conciliacion)
            for a, pc in cuenta if importes[a] > 0],
    )


def escribir(sesion: SesionMotor, pl: Plan, *, nombre_propiedad: str, financiador_actor: uuid.UUID,
             prestamo: list[tuple[uuid.UUID, Decimal]] | None) -> None:
    """Agregado de la financiacion (§3.2.3 1-4, 7, 9) DESPUES de Hd (OP-22) y dentro del savepoint de la compra."""
    ultima = pl.cuadro[-1].vencimiento
    sesion.ejecutar("INSERT INTO gapto.entidades (id, owner_user_id, tipo_entidad, nombre) VALUES "
                    "(%s, current_setting('gapto.owner_user_id')::uuid, 'FINANCIACION', %s)",
                    (pl.financiacion_id, f"Hipoteca · {nombre_propiedad}"[:200]))
    sesion.ejecutar(
        "INSERT INTO gapto.financiaciones (entidad_id, tipo_financiacion, financiador_actor_id, moneda, "
        "capital_original_contratado, saldo_principal_apertura, fecha_inicio_seguimiento, fecha_inicio, "
        "fecha_vencimiento_final_prevista, estado) VALUES (%s, 'HIPOTECA', %s, 'EUR', %s, 0, %s, %s, %s, 'ACTIVA')",
        (pl.financiacion_id, financiador_actor, pl.p, pl.escritura, pl.escritura, ultima))
    for actor, pct in prestamo or []:
        sesion.ejecutar("INSERT INTO gapto.entidad_participaciones (id, entidad_id, actor_id, porcentaje, vigente_desde) "
                        "VALUES (%s, %s, %s, %s, %s)", (pl.participacion_id(actor), pl.financiacion_id, actor,
                                                        pct.quantize(m2.ESCALA_PCT), pl.escritura))
    sesion.ejecutar("INSERT INTO gapto.entidad_relaciones (id, entidad_origen_id, entidad_destino_id, tipo_relacion, "
                    "vigente_desde) VALUES (%s, %s, %s, 'GARANTIZADA_POR', %s)",
                    (pl.relacion, pl.financiacion_id, pl.propiedad_id, pl.escritura))
    c = pl.canon
    sesion.ejecutar(
        "INSERT INTO gapto.financiacion_condiciones_versiones (id, financiacion_entidad_id, vigente_desde, "
        "motivo_version, hecho_causa_id, tipo_interes, tasa_anual_pct, indice_referencia, diferencial_pct, "
        "sistema_amortizacion, periodicidad, intervalo, importe_cuota_referencia, numero_cuotas_referencia) "
        "VALUES (%s, %s, %s, 'ALTA', %s, %s, %s, %s, %s, 'FRANCES', 'MENSUAL', 1, %s, %s)",
        (pl.version, pl.financiacion_id, pl.escritura, pl.hd, c["tipo_interes"], Decimal(c["tasa_anual_pct"]),
         c["indice_referencia"], None if c["diferencial_pct"] is None else Decimal(c["diferencial_pct"]),
         pl.cuadro[0].cuota, len(pl.cuadro)))
    previsiones = PrevisionesService(UnidadDeTrabajoAdscrita(sesion))
    n = len(pl.cuadro)
    for q in pl.cuadro:
        previsiones.crear_manual(sesion.contexto, DatosPrevisionManual(
            prevision_id=pl.prevision_id(q.numero), concepto=f"Cuota {q.numero}/{n} · Hipoteca",
            tipo_hecho_codigo="GASTO", fecha_esperada_desde=q.vencimiento, fecha_esperada_hasta=q.vencimiento,
            flujo_tesoreria_esperado="SALIDA", moneda=EUR, presupuestable=True, entidad_id=pl.financiacion_id,
            cuenta_salida_esperada_id=pl.cuenta_cargo, importe_esperado=q.cuota))
        sesion.ejecutar(
            "INSERT INTO gapto.financiacion_cuotas (id, financiacion_entidad_id, condicion_version_id, numero_cuota, "
            "fecha_vencimiento, capital_previsto, interes_previsto, comisiones_previstas, importe_total_previsto, "
            "prevision_id) VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s)",
            (pl.cuota_id(q.numero), pl.financiacion_id, pl.version, q.numero, q.vencimiento, q.capital, q.interes,
             q.cuota, pl.prevision_id(q.numero)))
    vinculo.escribir(sesion, vinculo.capacidad_alta(pl.vinculo_id), hecho_id=pl.hd, efecto_id=pl.efecto_deuda,
                     financiacion_id=pl.financiacion_id)
    sesion.ejecutar("INSERT INTO gapto.hecho_relaciones (id, hecho_origen_id, hecho_destino_id, tipo_relacion) "
                    "VALUES (%s, %s, %s, 'PARTE_DE')", (pl.parte_de, pl.hd, pl.h0))
    auditoria.registrar(sesion, tabla="financiaciones", registro_id=pl.financiacion_id, accion=auditoria.ACCION_CREAR,
                        datos_despues_json=json.dumps({"financiacion_id": str(pl.financiacion_id),
                                                       "hecho_desembolso_id": str(pl.hd),
                                                       "contenido": pl.canon}, ensure_ascii=False),
                        motivo=MOTIVO_ALTA)
