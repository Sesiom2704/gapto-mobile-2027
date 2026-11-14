# ============================================================
# GAPTO MOBILE 2027
# Fichero: pagos.py
# Ruta: backend/app/patrimonio/pagos.py
# Descripcion: T2-F06 PAG · componedor comun «quien pago y quien debe» de C-MEJ-01 v2 (contrato operativo unico
#   del mandato PAG §1.1; anexo B §10.2, que prevalece; L-02, L-08, L-09; Q-PAG-01..10).
#   Cinco conceptos separados: atribucion (reparto), pagador real, aportacion real, cuenta utilizada y posicion.
#   La titularidad de la propiedad nunca determina el pagador.
#
#   Peticion:
#     pagos[]  : {pagador: "YO", cuenta_id, importe} (sale de mi cuenta: movimiento + conciliacion por ese importe)
#                o {pagador: <actor cotitular>, importe} (por fuera de mis cuentas: aportacion SIN movimiento).
#                Como mucho un pago mio. Suma de pagos = importe del gasto (PAGOS_NO_CUADRAN, tesoreria).
#     saldos[] : uno por cotitular del reparto: ME_DEBE, LE_DEBO o NADA, con importe salvo NADA
#                (SALDO_NO_DECLARADO si falta; SALDO_INCOHERENTE si no cuadra con el signo; posiciones).
#     posiciones_confirmadas[] : {actor_id, tipo, importe}, una por saldo distinto de NADA, identica en actor, tipo e
#                importe (ENTRADA_INVALIDA si sobra o falta una). El servidor nunca infiere una posicion (INV-04).
#   Signo (§1.1.2): saldo_c = pagado_c - parte_c. saldo_c < 0 (c pago menos que su parte): ME_DEBE -> DERECHO_COBRO;
#     saldo_c > 0 (c pago mas que su parte): LE_DEBO -> OBLIGACION_PAGO.
#   Deuda parcial e invitacion (L-08): 0 < importe <= |saldo_c| en el sentido del signo; NADA siempre.
#   Limites (§1.1.5): la SUMA de mis ME_DEBE no supera lo que pague de mas y la de mis LE_DEBO lo que pague de menos
#     (nunca posiciones entre terceros). Con tres o mas titulares solo P1, P2 y P3: el mixto es solo bilateral.
#   NO_LO_SE: pagadores validados contra la titularidad en la fecha bajo lock (en el writer), ninguna deuda.
#   Composicion (OP-22, superficie certificada; sin DDL ni F04): un movimiento y una conciliacion SOLO por mi pago,
#     una aportacion MANUAL por pagador (la mia enlazada a mi conciliacion; la del cotitular sin movimiento) y una
#     posicion OP-12A (JUSTIFICACION_DECISION) por saldo distinto de NADA. Identificadores uuid5 por rol.
#   Lectura `lectura_pagos` (L-GASTO-PROPIEDAD, bloque `pago`): aportaciones por actor con y sin movimiento y su
#     cuenta, lo que salio de mis cuentas (y desde que cuentas, para «Ver el movimiento en la cuenta») y las
#     posiciones en su sentido; `declarado` False = «pago sin declarar»
#     (hechos de B3 del tren 1: nunca se reinterpretan, Q-PAG-07).
#   Codigo de partida: laboratorio lab-t2 05dec08 (pagos.py 0.1.0-lab), copia revisada contra el §1.1.
# Version: 0.1.0 (F06 T2-F06 PAG N1)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Callable

from app.core.modelos_compuesto import DatosPagoCompuesto
from app.core.modelos_posicion import JUSTIFICACION_DECISION, TIPO_DERECHO, TIPO_OBLIGACION, DatosAltaPosicion
from app.core.modelos_tesoreria import DatosAportacion, DatosConciliacion, DatosMovimiento
from app.patrimonio import atribucion as m2

CENT = Decimal("0.01")
CERO = Decimal("0")
YO = "YO"
EUR = "EUR"
ME_DEBE, LE_DEBO, NADA = "ME_DEBE", "LE_DEBO", "NADA"
SENTIDOS = (ME_DEBE, LE_DEBO, NADA)
TIPO_DE_SENTIDO = {ME_DEBE: TIPO_DERECHO, LE_DEBO: TIPO_OBLIGACION}
SENTIDO_DE_TIPO = {TIPO_DERECHO: ME_DEBE, TIPO_OBLIGACION: LE_DEBO}
ENTRADA_INVALIDA = "ENTRADA_INVALIDA"
PAGOS_NO_CUADRAN = "PAGOS_NO_CUADRAN"
SALDO_INCOHERENTE = "SALDO_INCOHERENTE"
SALDO_NO_DECLARADO = "SALDO_NO_DECLARADO"
PAGO_DESDE_CUENTA_COMPARTIDA = "PAGO_DESDE_CUENTA_COMPARTIDA"
NOMBRE_POSICION = "Gasto de propiedad"


def _d(v) -> Decimal:
    return Decimal(str(v)).quantize(CENT)


def _uuid(v) -> uuid.UUID:
    return uuid.UUID(str(v))


def es_mio(pago: dict) -> bool:
    return str(pago["pagador"]) == YO


def mi_pago(pagos: list[dict]) -> dict | None:
    return next((p for p in pagos if es_mio(p)), None)


def pagadores_otros(pagos: list[dict]) -> list[uuid.UUID]:
    return [_uuid(p["pagador"]) for p in pagos if not es_mio(p)]


def actores_saldo(saldos: list[dict]) -> list[uuid.UUID]:
    """Actores con posicion (saldo distinto de NADA): sus terceros se bloquean y deben ser PERSONA."""
    return [_uuid(s["actor_id"]) for s in saldos if s["sentido"] != NADA]


def pagado_por_actor(pagos: list[dict], yo: uuid.UUID) -> dict[uuid.UUID, Decimal]:
    pagado: dict[uuid.UUID, Decimal] = {}
    for p in pagos:
        actor = yo if es_mio(p) else _uuid(p["pagador"])
        pagado[actor] = pagado.get(actor, CERO) + _d(p["importe"])
    return pagado


def modo(*, importe: Decimal, reparto: dict[uuid.UUID, Decimal], pagos: list[dict], yo: uuid.UUID) -> str:
    """Presentacion del caso (anexo B §10.2): P1 pago yo todo, P3 un cotitular paga todo, P2 cada uno su parte;
    cualquier otra combinacion es MIXTO. No cambia el modelo financiero (Q-PAG-01): solo limita el mixto."""
    pagado = pagado_por_actor(pagos, yo)
    if len(pagos) == 1 and es_mio(pagos[0]):
        return "P1"
    if len(pagos) == 1:
        return "P3"
    if all(pagado.get(a, CERO) == parte for a, parte in reparto.items()) and set(pagado) <= set(reparto):
        return "P2"
    return "MIXTO"


def validar(*, importe: Decimal, partes: list[tuple[uuid.UUID, Decimal]] | None, yo: uuid.UUID,
            pagos: list[dict], saldos: list[dict], confirmadas: list[dict]) -> str | None:
    """Pura (antes de los locks). `partes` None = NO_LO_SE. Devuelve el codigo de rechazo o None."""
    # tesoreria: quien puso el dinero y desde donde
    if not pagos or any(_d(p["importe"]) <= 0 for p in pagos):
        return ENTRADA_INVALIDA
    mios = [p for p in pagos if es_mio(p)]
    if len(mios) > 1 or any(not p.get("cuenta_id") for p in mios):
        return ENTRADA_INVALIDA
    if any(p.get("cuenta_id") for p in pagos if not es_mio(p)):
        return ENTRADA_INVALIDA                                            # el cotitular no paga desde mis cuentas
    otros = pagadores_otros(pagos)
    if len(set(otros)) != len(otros) or yo in otros:
        return ENTRADA_INVALIDA
    if sum((_d(p["importe"]) for p in pagos), CERO) != importe:
        return PAGOS_NO_CUADRAN
    if any(s["sentido"] not in SENTIDOS for s in saldos):
        return ENTRADA_INVALIDA
    for s in saldos:                                                       # forma del importe del saldo
        if (s["sentido"] == NADA) != (s.get("importe") is None):
            return ENTRADA_INVALIDA
    # confirmacion visible: una entrada por saldo distinto de NADA, identica en actor, tipo e importe
    esperadas = sorted((str(_uuid(s["actor_id"])), TIPO_DE_SENTIDO[s["sentido"]], _d(s["importe"]))
                       for s in saldos if s["sentido"] != NADA)
    recibidas = sorted((str(_uuid(c["actor_id"])), str(c["tipo"]), _d(c["importe"])) for c in confirmadas)
    if esperadas != recibidas:
        return ENTRADA_INVALIDA
    if partes is None:                                                     # NO_LO_SE: sin reparto, sin deuda
        return ENTRADA_INVALIDA if any(s["sentido"] != NADA for s in saldos) else None
    # atribucion: pagadores dentro del reparto y un saldo declarado por cotitular
    cotitulares = {a for a, _ in partes if a != yo}
    if not set(otros) <= cotitulares:
        return ENTRADA_INVALIDA
    declarados = {_uuid(s["actor_id"]): s for s in saldos}
    if len(declarados) != len(saldos) or set(declarados) != cotitulares:
        return SALDO_NO_DECLARADO
    reparto = m2.repartir(importe, partes)
    if len(partes) >= 3 and modo(importe=importe, reparto=reparto, pagos=pagos, yo=yo) == "MIXTO":
        return ENTRADA_INVALIDA                                            # §1.1.5: el mixto solo es bilateral
    # posiciones: el signo de cada cotitular y mis limites (nunca posiciones entre terceros)
    pagado = pagado_por_actor(pagos, yo)
    mi_saldo = pagado.get(yo, CERO) - reparto.get(yo, CERO)               # >0: pague de mas; <0: pague de menos
    suma_me_debe = suma_le_debo = CERO
    for actor, s in declarados.items():
        if s["sentido"] == NADA:
            continue
        saldo = pagado.get(actor, CERO) - reparto[actor]                   # <0: pago de menos; >0: pago de mas
        valor = _d(s["importe"])
        if s["sentido"] == ME_DEBE:
            if not (saldo < 0 and valor <= -saldo):
                return SALDO_INCOHERENTE
            suma_me_debe += valor
        else:
            if not (saldo > 0 and valor <= saldo):
                return SALDO_INCOHERENTE
            suma_le_debo += valor
    if suma_me_debe > max(mi_saldo, CERO) or suma_le_debo > max(-mi_saldo, CERO):
        return SALDO_INCOHERENTE
    return None


def componer(*, iid: uuid.UUID, ident: Callable[[str], uuid.UUID], fecha: dt.date, nota: str | None,
             pagos: list[dict], saldos: list[dict], yo: uuid.UUID
             ) -> tuple[list[DatosPagoCompuesto], list[DatosAportacion], list[DatosAltaPosicion]]:
    """Solo desde la peticion sellada (un replay compone lo mismo). `ident(rol)` deriva los UUID del writer."""
    salida_pagos, aportaciones = [], []
    for pago in sorted(pagos, key=lambda x: str(x["pagador"])):
        x = _d(pago["importe"])
        if es_mio(pago):
            mov = DatosMovimiento(movimiento_id=ident("movimiento"), cuenta_id=_uuid(pago["cuenta_id"]),
                                  fecha_movimiento=fecha, importe=-x, clase_movimiento="OPERACION", descripcion=nota)
            conc = DatosConciliacion(conciliacion_id=ident("conciliacion"), hecho_id=iid,
                                     movimiento_tesoreria_id=mov.movimiento_id, importe_asignado=-x)
            salida_pagos.append(DatosPagoCompuesto(movimiento=mov, conciliacion=conc))
            aportaciones.append(DatosAportacion(aportacion_id=ident("aportacion:yo"), importe=x,
                                                criterio_aportacion="MANUAL", actor_id=yo,
                                                hecho_movimiento_tesoreria_id=conc.conciliacion_id))
        else:
            actor = _uuid(pago["pagador"])
            aportaciones.append(DatosAportacion(aportacion_id=ident(f"aportacion:{actor}"), importe=x,
                                                criterio_aportacion="MANUAL", actor_id=actor))
    posiciones = []
    for s in sorted(saldos, key=lambda x: str(x["actor_id"])):
        if s["sentido"] == NADA:
            continue
        actor = _uuid(s["actor_id"])
        posiciones.append(DatosAltaPosicion(
            entidad_id=ident(f"posicion:{actor}"), nombre=nota or NOMBRE_POSICION,
            tipo=TIPO_DE_SENTIDO[s["sentido"]], contraparte_actor_id=actor,
            moneda=EUR, justificacion=JUSTIFICACION_DECISION, fecha_inicio_seguimiento=fecha, saldo_apertura=CERO,
            hecho_id=iid, fecha_hecho=fecha, concepto=nota, efecto_id=ident(f"posicion_efecto:{actor}"),
            vinculo_id=ident(f"posicion_vinculo:{actor}"), importe_inicial=_d(s["importe"])))
    return salida_pagos, aportaciones, posiciones


def lectura_pagos(sesion, hecho_id: uuid.UUID, posiciones: list[dict]) -> dict:
    """HT2-06 / Q-PAG-10 (§1.3.1): quien pago, con y sin movimiento y su cuenta, cuanto salio de mis cuentas y las
    posiciones en su sentido. `declarado` False = hecho sin aportaciones (B3 del tren 1): «pago sin declarar»,
    nunca se reinterpreta (Q-PAG-07)."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT a.actor_id, a.importe::text, a.hecho_movimiento_tesoreria_id IS NOT NULL, "
            "(SELECT m.cuenta_id FROM gapto.hecho_movimientos_tesoreria x JOIN gapto.movimientos_tesoreria m "
            "  ON m.id = x.movimiento_tesoreria_id WHERE x.id = a.hecho_movimiento_tesoreria_id) "
            "FROM gapto.hecho_aportaciones_pago a WHERE a.hecho_id = %s ORDER BY a.actor_id::text", (hecho_id,))
        filas = cur.fetchall()
        cur.execute(
            "SELECT coalesce(sum(m.importe), 0)::text, coalesce(array_agg(DISTINCT m.cuenta_id) "
            "FILTER (WHERE m.cuenta_id IS NOT NULL), '{}') FROM gapto.hecho_movimientos_tesoreria x "
            "JOIN gapto.movimientos_tesoreria m ON m.id = x.movimiento_tesoreria_id WHERE x.hecho_id = %s",
            (hecho_id,))
        salido, cuentas = cur.fetchone()
    return {
        "declarado": bool(filas),
        "sale_de_mis_cuentas": str(_d(-Decimal(salido))),
        "cuentas_movimiento": sorted(str(c) for c in (cuentas or [])),
        "pagos": [{"actor_id": a, "importe": str(_d(i)), "con_movimiento": m, "cuenta_id": c} for a, i, m, c in filas],
        "posiciones": [{"actor_id": p["actor_id"], "sentido": SENTIDO_DE_TIPO.get(p["tipo"]), "tipo": p["tipo"],
                        "importe": str(_d(p["importe"])), "estado": p.get("estado")} for p in posiciones],
    }
