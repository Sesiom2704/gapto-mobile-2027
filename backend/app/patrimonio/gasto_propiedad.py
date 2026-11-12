# ============================================================
# GAPTO MOBILE 2027
# Fichero: gasto_propiedad.py
# Ruta: backend/app/patrimonio/gasto_propiedad.py
# Descripcion: B3 · C-MEJ-01 (gasto de una propiedad: MEJORA, REPARACION o GASTO_CORRIENTE), C-MEJ-02 (mejora
#   historica, sin pago) y lecturas de B3: propuesta de reparto en la fecha del hecho (P-H2-03; reutiliza la
#   lectura de titularidad en una fecha de B2, atribucion.titularidad_en_fecha, sin duplicarla),
#   L-GASTO-PROPIEDAD (HF-21), lista de gastos de la propiedad e impacto de una correccion de clase (§III.3.5).
#   R1 v0.9.5 Parte III (§III.1bis 1-10 con 8bis, 8ter y 8quater; §III.1ter), v0.9 §III.1 y v0.8 C-MEJ-01/02.
#
#   Composicion (OP-22 ADSCRITO, una raiz, hecho_id = intencion_id):
#     MEJORA          -> hecho MEJORA_PATRIMONIAL, presupuestable false inactivo (F04-D047), efecto VALOR_ACTIVO
#                        con causa TRANSFORMACION_CAPITALIZABLE, sin categoria;
#     REPARACION /
#     GASTO_CORRIENTE -> hecho GASTO, efecto GASTO con categoria y `presupuestable` (como VS-01). La clase NO se
#                        persiste: ninguna lectura distingue reparacion de gasto corriente (v0.8, AJ-11);
#     las tres        -> estado_localizacion DESCONOCIDA (§III.1ter, HF-03), AFECTA_A principal a la propiedad DE
#                        NIVEL EFECTO con id uuid5(intencion, "gapto.f06.gasto_propiedad.afecta_a") (marca de
#                        procedencia, v0.9 §III.3.2 opcion b), movimiento y conciliacion (C-MEJ-01) y atribucion
#                        M-2 (§1.2) con ids uuid5(efecto, prefijo + actor).
#     Deuda (8, 8bis, 8ter): una posicion DERECHO_COBRO por cada parte de cotitular con `me_debe = SI` que figure
#     en `derechos_confirmados` con el mismo importe, por la superficie CERTIFICADA de OP-22
#     (DatosHechoCompuesto.posiciones; efecto causal y vinculo en el mismo hecho). Nunca se infiere: sin el valor
#     por parte, 422. No es un movimiento: la liquidez no cambia. Exclusiones: cuenta compartida (solo con
#     `aportacion_indicada = MANUAL` e importe <= la parte), EMPRESA (rechazo), C-MEJ-02 (rechazo), NO_LO_SE o
#     sin importe (rechazo). No se registran aportaciones de pago (como B2): la aportacion acreditada es la de la
#     cuenta solo del usuario y la manual solo dimensiona el derecho (duda del §16 del mandato, resuelta asi).
#   Locks (v0.8 C-MEJ-01): 0 advisory de la raiz -> 1 INVERSIONES -> 2 propiedad FOR SHARE -> 3 cuenta FOR NO KEY
#     UPDATE -> 4 categoria (guarda C-a, FOR SHARE) -> 5 terceros de los derechos FOR SHARE -> relectura de la
#     titularidad (M-2) -> 7 OP-22. La propiedad se valida en esta capa (sin ampliar validar_contexto de VS-01).
#   Identidad: la de OP-22 (igualdad exacta del agregado, F04-D050). Un reintento compone SOLO desde la peticion
#     sellada (partes enviadas) y no revalida; tras un C-MEJ-03 responde IDENTIDAD_REUTILIZADA (O5.22).
#   M-8: propiedad DE_OTROS -> OPERACION_NO_PERMITIDA_EN_ESTADO (§III.2).
# Version: 0.1.0 (F06 T1-F06 B3 N1)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from app.api.ejecucion_registro import tomar_inversiones
from app.api.elegibilidad_categoria import validar_seleccion_categoria
from app.api.traductor_gasto_pagado import participacion_self_100
from app.comun.elegibilidad_cuentas import motivo_cuenta
from app.comun.fecha_funcional import Reloj, es_futura, hoy_owner, reloj_sistema
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_compuesto import DatosContextoHecho, DatosEntidadHecho, DatosHechoCompuesto, DatosPagoCompuesto
from app.core.modelos_efectos import DatosEfecto
from app.core.modelos_posicion import JUSTIFICACION_DECISION, TIPO_DERECHO, DatosAltaPosicion
from app.core.modelos_tesoreria import DatosConciliacion, DatosMovimiento
from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
from app.core.unidad_trabajo import SesionMotor
from app.patrimonio import atribucion as m2
from app.patrimonio.completitud import Rechazo
from app.propiedades import repositorio as repo
from app.repositories import compuesto_repository as repo_comp
from app.services.compuesto_service import HechosCompuestosService
from app.services.previsiones_service import impacto_correccion_ancla

CENT = Decimal("0.01")
CERO = Decimal("0")
EUR = "EUR"
PREFIJO_GP = "gapto.f06.gasto_propiedad."
PREFIJO_MH = "gapto.f06.mejora_historica."
PROCEDENCIAS = {PREFIJO_GP: "GASTO_PROPIEDAD", PREFIJO_MH: "MEJORA_HISTORICA"}
CRITERIO_HECHO = "TITULARIDAD_EN_FECHA_HECHO"
TIPO_MEJORA = "MEJORA_PATRIMONIAL"
TIPO_GASTO = "GASTO"
CAUSA_MEJORA = "TRANSFORMACION_CAPITALIZABLE"
CLASES = ("MEJORA", "REPARACION", "GASTO_CORRIENTE")
NOMBRE_POSICION = "Gasto de propiedad"

NO_ENCONTRADA = "AGREGADO_NO_ENCONTRADO"
ENTRADA_INVALIDA = "ENTRADA_INVALIDA"
CLASE_AUSENTE = "CLASE_GASTO_PROPIEDAD_AUSENTE"
PROPIEDAD_NO_DISPONIBLE = "PROPIEDAD_NO_DISPONIBLE"
NO_PERMITIDA_EN_ESTADO = "OPERACION_NO_PERMITIDA_EN_ESTADO"
CUENTA_DESCONOCIDA = "CUENTA_DESCONOCIDA"
FECHA_FUTURA = "FECHA_FUTURA"
VERSION_DESFASADA = "VERSION_DESFASADA"

#: §III.1bis 8quater: texto contractual LITERAL del dictamen (Q-R1-07, condicion obligatoria 2).
LIMITACION_R_DM02_01 = (
    "Los hechos de gasto de propiedad con una posición de deuda asociada no admiten actualmente la operación "
    "Corregir clase. No existe en este alcance una vía soportada para corregir su clase conservando la posición. "
    "Esta capacidad queda pendiente de una corrección de clase para hechos con varios efectos."
)


def ident(intencion_id: uuid.UUID, prefijo: str, rol: str) -> uuid.UUID:
    return uuid.uuid5(intencion_id, prefijo + rol)


def intencion_vigente(efecto_id: uuid.UUID) -> uuid.UUID:
    """§III.3.6: intencion_vigente(h) = uuid5(e.id, "gapto.f06.cmej03.intencion")."""
    return uuid.uuid5(efecto_id, "gapto.f06.cmej03.intencion")


# ------------------------------------------------------------------ validacion pura (antes de los locks)
def _partes_peticion(atribucion: dict) -> list[tuple[uuid.UUID, Decimal]]:
    if atribucion["modo"] == m2.NO_LO_SE:
        return []
    fuente = atribucion["partes"] if atribucion["modo"] == m2.MANUAL else atribucion["propuesta_vista"]["partes"]
    return sorted(((uuid.UUID(str(p["actor_id"])), Decimal(str(p["porcentaje"]))) for p in fuente),
                  key=lambda x: str(x[0]))


def validar_deuda(*, importe: Decimal, atribucion: dict, deuda: list[dict], aportacion: str | None,
                  derechos: list[dict], actor_self: uuid.UUID, con_pago: bool) -> str | None:
    """8, 8bis y 8ter, lo que se puede juzgar sin estado: valor explicito por parte de cotitular (O9.19),
    derechos confirmados = exactamente los SI con su importe (O9.22), sin derecho sin pago (O9.20) ni con NO_LO_SE
    o sin importe (O9.21). La cuenta compartida y la naturaleza se juzgan despues, bajo sus locks."""
    partes = _partes_peticion(atribucion)
    otros = [a for a, _ in partes if a != actor_self]
    vistos = [uuid.UUID(str(d["actor_id"])) for d in deuda]
    if len(set(vistos)) != len(vistos) or not set(vistos) <= set(otros):
        return ENTRADA_INVALIDA
    si = {uuid.UUID(str(d["actor_id"])) for d in deuda if d["me_debe"] == "SI"}
    confirmados = {uuid.UUID(str(d["actor_id"])): Decimal(str(d["importe"])) for d in derechos}
    if len(confirmados) != len(derechos):
        return ENTRADA_INVALIDA
    if not con_pago:                                                       # C-MEJ-02 (8ter, exclusion 3)
        return ENTRADA_INVALIDA if (si or derechos or aportacion is not None) else None
    if set(vistos) != set(otros):                                          # O9.19: nada se infiere
        return ENTRADA_INVALIDA
    if not partes:                                                         # NO_LO_SE (exclusion 4)
        return ENTRADA_INVALIDA if (si or derechos or aportacion is not None) else None
    if set(confirmados) != si:                                             # O9.22 (8bis)
        return ENTRADA_INVALIDA
    if aportacion is not None and not si:
        return ENTRADA_INVALIDA
    reparto = m2.repartir(importe, partes)
    for actor, valor in confirmados.items():
        parte = reparto[actor]
        if parte <= 0:                                                     # sin importe (exclusion 4)
            return ENTRADA_INVALIDA
        if aportacion is None and valor != parte:
            return ENTRADA_INVALIDA
        if aportacion is not None and not (CERO < valor <= parte):
            return ENTRADA_INVALIDA
    return None


def validar_clase(clase: str | None, categoria_id, presupuestable) -> str | None:
    if clase is None:
        return CLASE_AUSENTE
    if clase == "MEJORA":
        return ENTRADA_INVALIDA if (categoria_id is not None or presupuestable is not None) else None
    return ENTRADA_INVALIDA if (categoria_id is None or presupuestable is None) else None


# ------------------------------------------------------------------ lecturas auxiliares bajo lock
def bloquear_propiedad_compartida(sesion: SesionMotor, propiedad_id: uuid.UUID) -> dict[str, Any] | None:
    """Nivel 2 de C-MEJ-01/02/03: FOR SHARE de la entidad PROPIEDAD del owner (solo se vincula; v0.8 §1.4)."""
    fila = sesion.uno(
        "SELECT e.row_version, e.enabled, p.fecha_salida_patrimonio, e.nombre FROM gapto.entidades e "
        "JOIN gapto.propiedades p ON p.entidad_id = e.id WHERE e.id = %s AND e.tipo_entidad = 'PROPIEDAD' "
        "AND e.owner_user_id = current_setting('gapto.owner_user_id')::uuid FOR SHARE OF e", (propiedad_id,))
    return None if fila is None else {"row_version": fila[0], "enabled": fila[1], "salida": fila[2],
                                      "nombre": fila[3]}


def disponible(raiz: dict[str, Any]) -> bool:
    return bool(raiz["enabled"]) and raiz["salida"] is None


def de_otros(sesion: SesionMotor, propiedad_id: uuid.UUID, fecha: dt.date) -> bool:
    """M-8: titularidad vigente sin participacion propia (DE_OTROS)."""
    vigente = m2.titularidad_en_fecha(sesion, propiedad_id, fecha)
    return bool(vigente) and not any(p["yo"] for p in vigente)


def actor_self(sesion: SesionMotor) -> uuid.UUID:
    a = repo.actor_self(sesion)
    if a is None:
        raise LookupError("el tenant no tiene actor self")
    return a


def naturalezas(sesion: SesionMotor, actores: list[uuid.UUID], *, bloquear: bool) -> dict[uuid.UUID, str | None]:
    """Naturaleza del tercero de cada actor (None = actor self o sin tercero). Nivel 5: FOR SHARE por UUID."""
    salida: dict[uuid.UUID, str | None] = {}
    for actor in sorted(set(actores), key=str):
        fila = sesion.uno(
            "SELECT t.naturaleza FROM gapto.actores_financieros a LEFT JOIN gapto.terceros t ON t.id = a.tercero_id "
            "WHERE a.id = %s AND a.owner_user_id = current_setting('gapto.owner_user_id')::uuid"
            + (" FOR SHARE OF a" if bloquear else ""), (actor,))
        salida[actor] = None if fila is None else fila[0]
    return salida


# ------------------------------------------------------------------ composicion
def _posiciones(iid: uuid.UUID, fecha: dt.date, nota: str | None, confirmados: dict[uuid.UUID, Decimal]
                ) -> list[DatosAltaPosicion]:
    return [DatosAltaPosicion(
        entidad_id=ident(iid, PREFIJO_GP, f"posicion:{actor}"), nombre=nota or NOMBRE_POSICION, tipo=TIPO_DERECHO,
        contraparte_actor_id=actor, moneda=EUR, justificacion=JUSTIFICACION_DECISION, fecha_inicio_seguimiento=fecha,
        saldo_apertura=CERO, hecho_id=iid, fecha_hecho=fecha, concepto=nota,
        efecto_id=ident(iid, PREFIJO_GP, f"posicion_efecto:{actor}"),
        vinculo_id=ident(iid, PREFIJO_GP, f"posicion_vinculo:{actor}"), importe_inicial=importe.quantize(CENT))
        for actor, importe in sorted(confirmados.items(), key=lambda x: str(x[0]))]


def componer_gasto(*, iid: uuid.UUID, prefijo: str, clase: str, propiedad_id: uuid.UUID, fecha: dt.date,
             importe: Decimal, nota: str | None, categoria_id, presupuestable, cuenta_id: uuid.UUID | None,
             atribucion: dict, partes: list[tuple[uuid.UUID, Decimal]] | None,
             confirmados: dict[uuid.UUID, Decimal]) -> DatosHechoCompuesto:
    x = importe.quantize(CENT)
    mejora = clase == "MEJORA"
    efecto_id = ident(iid, prefijo, "efecto")
    estado, filas = m2.filas(efecto_id, x, partes, atribucion["modo"], prefijo + "atribucion:")
    hecho = DatosCreacionHecho(
        hecho_id=iid, fecha_hecho=fecha, moneda=EUR, presupuestable=False if mejora else bool(presupuestable),
        estado_localizacion="DESCONOCIDA", tipo_hecho_codigo=TIPO_MEJORA if mejora else TIPO_GASTO, concepto=nota,
        importe_total=x)
    efecto = DatosEfecto(
        efecto_id=efecto_id, tipo_efecto="VALOR_ACTIVO" if mejora else "GASTO", importe_delta=x,
        estado_atribucion=estado, categoria_id=None if mejora else categoria_id,
        acontecimiento=CAUSA_MEJORA if mejora else None, atribuciones=filas)
    pagos = []
    if cuenta_id is not None:
        mov = DatosMovimiento(movimiento_id=ident(iid, prefijo, "movimiento"), cuenta_id=cuenta_id,
                              fecha_movimiento=fecha, importe=-x, clase_movimiento="OPERACION", descripcion=nota)
        pagos.append(DatosPagoCompuesto(movimiento=mov, conciliacion=DatosConciliacion(
            conciliacion_id=ident(iid, prefijo, "conciliacion"), hecho_id=iid,
            movimiento_tesoreria_id=mov.movimiento_id, importe_asignado=-x)))
    return DatosHechoCompuesto(
        hecho=hecho, efectos=[efecto], pagos=pagos, posiciones=_posiciones(iid, fecha, nota, confirmados),
        contexto=DatosContextoHecho(entidades=[DatosEntidadHecho(
            registro_id=ident(iid, prefijo, "afecta_a"), entidad_id=propiedad_id, tipo_relacion="AFECTA_A",
            principal=True, efecto_id=efecto_id)]))


def _op22(sesion: SesionMotor) -> HechosCompuestosService:
    return HechosCompuestosService(UnidadDeTrabajoAdscrita(sesion), impacto_ancla=impacto_correccion_ancla)


def _confirmados(derechos: list[dict], deuda: list[dict]) -> dict[uuid.UUID, Decimal]:
    si = {uuid.UUID(str(d["actor_id"])) for d in deuda if d["me_debe"] == "SI"}
    return {uuid.UUID(str(d["actor_id"])): Decimal(str(d["importe"])) for d in derechos
            if uuid.UUID(str(d["actor_id"])) in si}


def _respuesta(sesion: SesionMotor, propiedad_id: uuid.UUID, d: DatosHechoCompuesto, clase: str,
               idempotente: bool) -> dict[str, Any]:
    e = d.efectos[0]
    lectura = leer_gasto(sesion, propiedad_id, d.hecho.hecho_id) or {}
    return {
        "hecho_id": d.hecho.hecho_id, "idempotente": idempotente, "tipo_hecho": d.hecho.tipo_hecho_codigo,
        "clase": clase, "importe": str(e.importe_delta), "estado_atribucion": e.estado_atribucion,
        "atribuciones": [{"actor_id": a.actor_id, "importe": str(a.importe_atribuido),
                          "porcentaje": str(a.porcentaje_aplicado)} for a in e.atribuciones],
        "posiciones": lectura.get("posiciones", []),
        "intencion_correccion_id": lectura.get("intencion_correccion_id"),
        "gasto_del_mes": str(-e.importe_delta) if e.tipo_efecto == "GASTO" else "0.00",
    }


# ------------------------------------------------------------------ C-MEJ-01
def registrar_gasto(sesion: SesionMotor, *, peticion: dict, reloj: Reloj = reloj_sistema) -> dict | Rechazo:
    p = peticion
    iid, propiedad_id, clase = p["intencion_id"], p["propiedad_id"], p.get("clase")
    rechazo = validar_clase(clase, p.get("categoria_id"), p.get("presupuestable"))
    if rechazo:
        return Rechazo(rechazo)
    atr = p["atribucion"]
    forma = m2.validar_forma(atr, criterio=CRITERIO_HECHO, fecha_referencia=p["fecha_hecho"])
    if forma:
        return Rechazo(forma)
    importe = Decimal(str(p["importe"])).quantize(CENT)
    yo = actor_self(sesion)
    rechazo = validar_deuda(importe=importe, atribucion=atr, deuda=p["deuda"], aportacion=p.get("aportacion_indicada"),
                            derechos=p["derechos_confirmados"], actor_self=yo, con_pago=True)
    if rechazo:
        return Rechazo(rechazo)
    confirmados = _confirmados(p["derechos_confirmados"], p["deuda"])
    # 0 -> 1 -> 2
    repo_comp.tomar_advisory_raiz(sesion, iid)
    tomar_inversiones(sesion)
    raiz = bloquear_propiedad_compartida(sesion, propiedad_id)
    if raiz is None:
        return Rechazo(NO_ENCONTRADA)
    # 3: cuenta (lock contractual antes de la identidad, como VS-01)
    sesion.uno("SELECT id FROM gapto.cuentas WHERE id = %s FOR NO KEY UPDATE", (p["cuenta_id"],))

    def datos(partes):
        return componer_gasto(iid=iid, prefijo=PREFIJO_GP, clase=clase, propiedad_id=propiedad_id, fecha=p["fecha_hecho"],
                        importe=importe, nota=p.get("nota"), categoria_id=p.get("categoria_id"),
                        presupuestable=p.get("presupuestable"), cuenta_id=p["cuenta_id"], atribucion=atr,
                        partes=partes, confirmados=confirmados)

    if repo_comp.leer(sesion, "hechos_financieros", iid) is not None:            # identidad: OP-22 decide
        d = datos(None if atr["modo"] == m2.NO_LO_SE else _partes_peticion(atr))
        r = _op22(sesion).registrar_hecho_compuesto(sesion.contexto, d)
        return _respuesta(sesion, propiedad_id, d, clase, r.idempotente)
    fecha = p["fecha_hecho"]
    if es_futura(sesion, fecha, reloj):
        return Rechazo(FECHA_FUTURA)
    if not disponible(raiz):
        return Rechazo(PROPIEDAD_NO_DISPONIBLE)
    if de_otros(sesion, propiedad_id, hoy_owner(sesion, reloj)):
        return Rechazo(NO_PERMITIDA_EN_ESTADO)
    if motivo_cuenta(sesion, p["cuenta_id"], "GASTO", fecha, bloquear=True) is not None:
        return Rechazo(CUENTA_DESCONOCIDA)
    if clase != "MEJORA":                                                         # 4: guarda C-a
        rechazo = validar_seleccion_categoria(sesion, p["categoria_id"], "GASTO")
        if rechazo:
            return Rechazo(rechazo)
    if confirmados:                                                               # 5: 8ter bajo locks
        nat = naturalezas(sesion, list(confirmados), bloquear=True)
        if any(nat.get(a) != "PERSONA" for a in confirmados):                     # EMPRESA (O9.18)
            return Rechazo(ENTRADA_INVALIDA)
        solo_mia = participacion_self_100(sesion, p["cuenta_id"], yo, fecha)
        if solo_mia == (p.get("aportacion_indicada") is not None):                # O9.16
            return Rechazo(ENTRADA_INVALIDA)
    partes = m2.resolver(sesion, propiedad_id, atr)                              # relectura M-2 bajo lock
    if isinstance(partes, str):
        return Rechazo(partes)
    if partes is not None and not {a for a, _ in partes} >= set(confirmados):
        return Rechazo(ENTRADA_INVALIDA)
    d = datos(partes)
    r = _op22(sesion).registrar_hecho_compuesto(sesion.contexto, d)
    return _respuesta(sesion, propiedad_id, d, clase, r.idempotente)


# ------------------------------------------------------------------ C-MEJ-02
def registrar_mejora_historica(sesion: SesionMotor, *, propiedad_id: uuid.UUID, peticion: dict,
                               reloj: Reloj = reloj_sistema) -> dict | Rechazo:
    p = peticion
    iid = p["intencion_id"]
    atr = p["atribucion"]
    forma = m2.validar_forma(atr, criterio=CRITERIO_HECHO, fecha_referencia=p["fecha"])
    if forma:
        return Rechazo(forma)
    importe = Decimal(str(p["importe"])).quantize(CENT)
    yo = actor_self(sesion)
    rechazo = validar_deuda(importe=importe, atribucion=atr, deuda=p["deuda"], aportacion=None, derechos=[],
                            actor_self=yo, con_pago=False)
    if rechazo:
        return Rechazo(rechazo)
    repo_comp.tomar_advisory_raiz(sesion, iid)
    tomar_inversiones(sesion)
    raiz = bloquear_propiedad_compartida(sesion, propiedad_id)
    if raiz is None:
        return Rechazo(NO_ENCONTRADA)

    def datos(partes):
        return componer_gasto(iid=iid, prefijo=PREFIJO_MH, clase="MEJORA", propiedad_id=propiedad_id, fecha=p["fecha"],
                        importe=importe, nota=p["descripcion"], categoria_id=None, presupuestable=None,
                        cuenta_id=None, atribucion=atr, partes=partes, confirmados={})

    if repo_comp.leer(sesion, "hechos_financieros", iid) is not None:
        d = datos(None if atr["modo"] == m2.NO_LO_SE else _partes_peticion(atr))
        r = _op22(sesion).registrar_hecho_compuesto(sesion.contexto, d)
        return _respuesta(sesion, propiedad_id, d, "MEJORA", r.idempotente)
    if raiz["row_version"] != p["row_version_esperada"]:
        return Rechazo(VERSION_DESFASADA)
    if es_futura(sesion, p["fecha"], reloj):
        return Rechazo(FECHA_FUTURA)
    if not disponible(raiz):
        return Rechazo(PROPIEDAD_NO_DISPONIBLE)
    if de_otros(sesion, propiedad_id, hoy_owner(sesion, reloj)):
        return Rechazo(NO_PERMITIDA_EN_ESTADO)
    partes = m2.resolver(sesion, propiedad_id, atr)
    if isinstance(partes, str):
        return Rechazo(partes)
    d = datos(partes)
    r = _op22(sesion).registrar_hecho_compuesto(sesion.contexto, d)
    return _respuesta(sesion, propiedad_id, d, "MEJORA", r.idempotente)


# ------------------------------------------------------------------ lecturas
def propuesta(sesion: SesionMotor, propiedad_id: uuid.UUID, fecha: dt.date, cuenta_id: uuid.UUID | None
              ) -> dict | None:
    """P-H2-03: la titularidad de la PROPIEDAD en la fecha del hecho (la misma lectura que relee la escritura bajo
    lock), con la naturaleza de cada cotitular y si la cuenta es solo del usuario. La cuenta nunca entra en la
    propuesta: solo decide la preseleccion de la deuda (8bis/8ter)."""
    leida = repo.leer(sesion, propiedad_id)
    if leida is None:
        return None
    partes = m2.titularidad_en_fecha(sesion, propiedad_id, fecha)
    nat = naturalezas(sesion, [x["actor_id"] for x in partes], bloquear=False)
    cuenta = None
    if cuenta_id is not None:
        yo = actor_self(sesion)
        with sesion.conexion.cursor() as cur:
            cur.execute("SELECT actor_id FROM gapto.cuenta_participaciones WHERE cuenta_id = %s AND vigente_desde <= %s "
                        "AND (vigente_hasta IS NULL OR vigente_hasta >= %s) ORDER BY actor_id::text",
                        (cuenta_id, fecha, fecha))
            actores = [f[0] for f in cur.fetchall()]
        cuenta = {"cuenta_id": cuenta_id, "solo_mia": participacion_self_100(sesion, cuenta_id, yo, fecha),
                  "compartida_con": [a for a in actores if a != yo]}
    return {"fecha": fecha, "propiedad_id": propiedad_id, "nombre": leida["nombre"],
            "titularidad_disponible": bool(partes),
            "partes": [{**x, "naturaleza": nat.get(x["actor_id"])} for x in partes], "cuenta": cuenta}


_LECTURA = (
    "SELECT h.id, h.estado, h.row_version, th.codigo, "
    "coalesce((SELECT e.importe_delta FROM gapto.hecho_efectos e WHERE e.id = x.efecto_id), h.importe_total), "
    "h.fecha_hecho, h.concepto, h.presupuestable, "
    "h.estado_localizacion, x.id, "
    "(SELECT coalesce(array_agg(e.id ORDER BY e.id), '{}') FROM gapto.hecho_efectos e WHERE e.hecho_id = h.id), "
    "(SELECT e.categoria_id FROM gapto.hecho_efectos e WHERE e.id = x.efecto_id), "
    "(SELECT e.tipo_efecto FROM gapto.hecho_efectos e WHERE e.id = x.efecto_id), "
    "(SELECT coalesce(json_agg(json_build_object('entidad_id', v.entidad_id, 'actor_id', d.contraparte_actor_id, "
    "  'tercero_id', a.tercero_id, 'tipo', d.tipo, 'importe', ef.importe_delta::text) ORDER BY v.entidad_id), '[]') "
    "  FROM gapto.hecho_entidades v JOIN gapto.derechos_obligaciones_financieras d ON d.entidad_id = v.entidad_id "
    "  JOIN gapto.hecho_efectos ef ON ef.id = v.efecto_id "
    "  LEFT JOIN gapto.actores_financieros a ON a.id = d.contraparte_actor_id "
    "  WHERE v.hecho_id = h.id AND v.efecto_id IS NOT NULL), "
    "(SELECT coalesce(json_agg(json_build_object('actor_id', t.actor_id, 'importe', t.importe_atribuido::text, "
    "  'porcentaje', t.porcentaje_aplicado::text) ORDER BY t.actor_id), '[]') FROM gapto.efecto_atribuciones t "
    "  WHERE t.efecto_id = x.efecto_id) "
    "FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id "
    "JOIN gapto.hecho_entidades x ON x.hecho_id = h.id AND x.entidad_id = %(p)s AND x.tipo_relacion = 'AFECTA_A' "
    "AND x.principal AND x.id IN (%(gp)s, %(mh)s) "
    "WHERE h.id = %(h)s"
)


def leer_gasto(sesion: SesionMotor, propiedad_id: uuid.UUID, hecho_id: uuid.UUID) -> dict | None:
    """L-GASTO-PROPIEDAD (HF-21). UNA sentencia (una instantanea): `intencion_correccion_id` solo si el hecho esta
    ACTIVO y tiene EXACTAMENTE un efecto vigente (la misma condicion que la guarda 2bis, O5.33); si no, null. Con
    posicion de deuda, la limitacion literal de 8quater. None si el hecho no es de esta propiedad por la marca de
    procedencia de C-MEJ-01/02 (incluidos los ajenos: 404)."""
    import json as _json
    fila = sesion.uno(_LECTURA, {"p": propiedad_id, "h": hecho_id, "gp": ident(hecho_id, PREFIJO_GP, "afecta_a"),
                                 "mh": ident(hecho_id, PREFIJO_MH, "afecta_a")})
    if fila is None:
        return None
    (hid, estado, version, tipo, importe, fecha, nota, presup, loc, vinculo, efectos, cat, tipo_ef, posiciones,
     atribuciones) = fila
    efectos = list(efectos or [])
    posiciones = posiciones if isinstance(posiciones, list) else _json.loads(posiciones)
    atribuciones = atribuciones if isinstance(atribuciones, list) else _json.loads(atribuciones)
    unico = estado == "ACTIVO" and len(efectos) == 1
    con_deuda = bool(posiciones)
    procedencia = "GASTO_PROPIEDAD" if vinculo == ident(hecho_id, PREFIJO_GP, "afecta_a") else "MEJORA_HISTORICA"
    return {
        "hecho_id": hid, "propiedad_id": propiedad_id, "estado": estado, "row_version": version, "tipo_hecho": tipo,
        "clase": "MEJORA" if tipo_ef == "VALOR_ACTIVO" else ("GASTO" if tipo_ef == "GASTO" else None),
        "importe": str(Decimal(importe).quantize(CENT)), "fecha": fecha, "nota": nota, "categoria_id": cat,
        "presupuestable": presup, "estado_localizacion": loc, "procedencia": procedencia,
        "efectos_vigentes": len(efectos), "con_deuda": con_deuda, "posiciones": posiciones,
        "atribuciones": atribuciones,
        "intencion_correccion_id": intencion_vigente(efectos[0]) if unico else None,
        "limitacion": LIMITACION_R_DM02_01 if con_deuda else None,
    }


def listar_gastos(sesion: SesionMotor, propiedad_id: uuid.UUID) -> list[dict] | None:
    if repo.leer(sesion, propiedad_id) is None:
        return None
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT h.id FROM gapto.hecho_entidades x JOIN gapto.hechos_financieros h ON h.id = x.hecho_id "
            "WHERE x.entidad_id = %s AND x.tipo_relacion = 'AFECTA_A' AND x.principal "
            "ORDER BY h.fecha_hecho DESC, h.id", (propiedad_id,))
        candidatos = [f[0] for f in cur.fetchall()]
    salida = []
    for h in candidatos:
        g = leer_gasto(sesion, propiedad_id, h)
        if g is not None:
            salida.append({k: g[k] for k in ("hecho_id", "tipo_hecho", "clase", "importe", "fecha", "nota",
                                              "procedencia", "estado", "con_deuda")})
    return salida


def _txt(v: Decimal) -> str:
    return str(v.quantize(CENT))


def comparacion(*, fecha: dt.date, importe: Decimal, tipo_efecto: str, clase_nueva: str,
                presupuestable_nuevo: bool | None) -> dict[str, str]:
    """§III.3.5: contribuciones DE ESTE HECHO (no totales): Resultado del mes (-importe si GASTO, 0 si
    VALOR_ACTIVO), coste de mejoras (importe si VALOR_ACTIVO TRANSFORMACION, 0 si no) y presupuesto (-importe si
    queda GASTO con presupuestable = true)."""
    x = importe.quantize(CENT)
    destino_gasto = clase_nueva != "MEJORA"
    antes_gasto = tipo_efecto == "GASTO"
    return {
        "mes": fecha.strftime("%Y-%m"),
        "resultado_mes_delta_antes": _txt(-x if antes_gasto else CERO),
        "resultado_mes_delta_despues": _txt(-x if destino_gasto else CERO),
        "mejoras_antes": _txt(CERO if antes_gasto else x),
        "mejoras_despues": _txt(CERO if destino_gasto else x),
        "presupuesto_delta_despues": _txt(-x if (destino_gasto and presupuestable_nuevo is True) else CERO),
    }


def impacto(sesion: SesionMotor, propiedad_id: uuid.UUID, hecho_id: uuid.UUID, clase_nueva: str,
            presupuestable: bool | None) -> dict | None:
    g = leer_gasto(sesion, propiedad_id, hecho_id)
    if g is None or g["clase"] is None:
        return None
    return comparacion(fecha=g["fecha"], importe=Decimal(g["importe"]),
                       tipo_efecto="VALOR_ACTIVO" if g["clase"] == "MEJORA" else "GASTO", clase_nueva=clase_nueva,
                       presupuestable_nuevo=presupuestable)
