# ============================================================
# GAPTO MOBILE 2027
# Fichero: compra.py
# Ruta: backend/app/patrimonio/compra.py
# Descripcion: C-COMPRA-01 (registrar la compra, sin hipoteca) y C-COMPRA-03 (anadir un gasto de la compra
#   despues). R1 v0.9.5 Parte II (§II.1 con AJ-TR1-09 y AJ-TR1-10, HF-01, HF-07, HF-09, HF-10, HF-12, HF-16;
#   §II.6; §II.7) y, por remision, v0.9 §II.1-§II.5 y v0.8 Parte II (DTO RegistrarCompra, composicion H0/Hk).
#
#   Composicion: OP-22 ADSCRITO una vez por raiz NUEVA (H0 y cada Hk), en la misma transaccion y en orden de UUID:
#     H0 = intencion_id; Hk = uuid5(H0, "gapto.f06.compra.gasto:" + linea_id);
#     cada raiz: hecho ADQUISICION_PATRIMONIAL (no presupuestable, NO_APLICA), efecto VALOR_ACTIVO causa
#     ADQUISICION con su atribucion M-2, AFECTA_A principal a la propiedad DE NIVEL EFECTO y pago(s)
#     conciliado(s). El AFECTA_A de H0 lleva el SELLO de la peticion canonica completa (§1.3):
#     uuid5(H0, "gapto.f06.compra.afecta_a:" + sello). PARTE_DE de cada Hk hacia H0 con id
#     uuid5(Hk, "gapto.f06.compra.lote") (C-COMPRA-03: "gapto.f06.compra03.lote"), escrita por esta capa.
#     Valoracion COMPRA uuid5(H0, "gapto.f06.compra.valoracion") y, si viene, FISCAL_REFERENCIA.
#   Locks (§1.4): 0 advisory por raiz de OP-22 de TODAS las raices en orden de UUID -> 1 INVERSIONES -> 2 NK de
#     la propiedad -> identidad (comparador propio) -> version y guardas -> 3 cuentas NK por id + regla R1 de la
#     operacion de pago GASTO (PAGAR_GASTO; §II.5) -> relectura de la titularidad (M-2) -> 7 OP-22 por raiz ->
#     8 declaracion (conjunto calculado despues de insertar, antes del COMMIT). No toma el 0P (§I.5.4.5).
#   Identidad (§II.1, AJ-TR1-09; comparador PROPIO, sin metodos privados de OP-22 ni subclases): bajo el nivel
#     0 compara (i) identidades persistidas de cada raiz (`identidades_del_agregado`, publica) con las
#     declaradas, PARTE_DE incluida; (ii) la pertenencia al lote: exactamente las PARTE_DE compra.lote de los
#     Hk y ninguna otra hacia H0 salvo las de C-COMPRA-03; (iii) los campos de cada fila declarada por igualdad
#     exacta (F04-D050); (iv) el vinculo sellado de H0; (v) todas las raices o ninguna; (vi) sin raices
#     adicionales. Igualdad -> idempotente sin escribir ni auditar ni invocar OP-22; ninguna raiz -> compone;
#     cualquier otro caso (lote parcial incluido) -> IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION.
#   Fecha de escritura (AJ-TR1-10): con SEGUN_TITULARIDAD_ACEPTADA la propuesta es la titularidad vigente en la
#     fecha de escritura para TODAS las raices (criterio TITULARIDAD_EN_FECHA_ESCRITURA dentro del sello); la
#     fecha economica de cada efecto no cambia. C-COMPRA-03 usa la fecha economica de su efecto.
#   Declaracion (consumidor PROVISIONAL de 0352): solo con los consumidores habilitados (habilitacion.py); si no,
#     422 ENTRADA_INVALIDA. Con declaracion, el conjunto calculado tras insertar tiene que ser exactamente el
#     de las raices de la peticion (HF-07) o COMPLETITUD_VISTA_DESFASADA sin escribir.
#   Rechazos despues de escribir: un savepoint los deshace (estado identico).
# Version: 0.1.0 (F06 T1-F06 B2 N1)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any

from app.api.ejecucion_registro import tomar_inversiones
from app.comun.elegibilidad_cuentas import motivo_cuenta
from app.comun.fecha_funcional import Reloj, hoy_owner, reloj_sistema
from app.core.modelos import DatosCreacionHecho
from app.core.modelos_compuesto import DatosContextoHecho, DatosEntidadHecho, DatosHechoCompuesto, DatosPagoCompuesto
from app.core.modelos_efectos import DatosEfecto
from app.core.modelos_tesoreria import DatosConciliacion, DatosMovimiento
from app.core.unidad_adscrita import UnidadDeTrabajoAdscrita
from app.core.unidad_trabajo import SesionMotor
from app.patrimonio import atribucion as m2
from app.patrimonio import coste
from app.patrimonio import habilitacion
from app.patrimonio.completitud import Rechazo, auditar
from app.propiedades import lecturas
from app.propiedades import repositorio as repo
from app.repositories import compuesto_repository as repo_comp
from app.services.compuesto_service import HechosCompuestosService
from app.services.previsiones_service import impacto_correccion_ancla

CENT = Decimal("0.01")
EUR = "EUR"
TIPO_HECHO = "ADQUISICION_PATRIMONIAL"
OP_COMPRA = "COMPRA"
OP_COMPRA03 = "COMPRA_GASTO_POSTERIOR"
MOTIVO_COMPRA = "F06-01 B2 COMPRA"
MOTIVO_COMPRA03 = "F06-01 B2 GASTO DE LA COMPRA POSTERIOR"
MARCA_LOTE = "gapto.f06.compra.lote"
MARCA_LOTE03 = "gapto.f06.compra03.lote"
CONCEPTOS = ("ITP", "IVA_AJD", "NOTARIA_REGISTRO_GESTORIA", "AGENCIA", "OTRO")
ROLES = ("ARRAS", "FIRMA", "OTRO")

NO_ENCONTRADA = "AGREGADO_NO_ENCONTRADO"
VERSION_DESFASADA = "VERSION_DESFASADA"
IDENTIDAD_REUTILIZADA = "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
ENTRADA_INVALIDA = "ENTRADA_INVALIDA"
COMPRA_YA_REGISTRADA = "COMPRA_YA_REGISTRADA"
COMPRA_NO_REGISTRADA = "COMPRA_NO_REGISTRADA"
FECHA_PAGO_INCOHERENTE = "FECHA_PAGO_INCOHERENTE"
PROPIEDAD_NO_DISPONIBLE = "PROPIEDAD_NO_DISPONIBLE"
NO_PERMITIDA_EN_ESTADO = "OPERACION_NO_PERMITIDA_EN_ESTADO"
CUENTA_DESCONOCIDA = "CUENTA_DESCONOCIDA"
SIN_FECHA_DE_CORTE = "COMPLETITUD_SIN_FECHA_DE_CORTE"
SIN_COMPONENTES = "COMPLETITUD_SIN_COMPONENTES"
VISTA_DESFASADA = "COMPLETITUD_VISTA_DESFASADA"


class _Deshacer(Exception):
    """Rechazo DESPUES de escribir: deshace el savepoint de la composicion (estado identico)."""

    def __init__(self, codigo: str):
        super().__init__(codigo)
        self.codigo = codigo


# ------------------------------------------------------------------ forma canonica y sello (§1.3)
def _imp(v: Any) -> str:
    return str(Decimal(str(v)).quantize(CENT))


def _pct(v: Any) -> str:
    return str(Decimal(str(v)).quantize(m2.ESCALA_PCT))


def _iso(v: Any) -> str | None:
    return None if v is None else (v.isoformat() if isinstance(v, dt.date) else str(v))


def _partes_canon(partes: list[dict] | None) -> list[dict] | None:
    return None if partes is None else sorted(
        ({"actor_id": str(p["actor_id"]), "porcentaje": _pct(p["porcentaje"])} for p in partes),
        key=lambda p: p["actor_id"])


def canonica_atribucion(a: dict) -> dict:
    propuesta = a.get("propuesta_vista")
    return {"modo": str(a["modo"]).upper(), "partes": _partes_canon(a.get("partes")),
            "propuesta_vista": None if propuesta is None else {
                "criterio": str(propuesta["criterio"]).upper(), "fecha_referencia": _iso(propuesta["fecha_referencia"]),
                "partes": _partes_canon(propuesta["partes"])}}


def canonica_completitud(c: dict | None) -> dict | None:
    return None if c is None else {"completo": bool(c["completo"]), "fecha_corte": _iso(c.get("fecha_corte"))}


def canonica_gasto(g: dict) -> dict:
    return {"linea_id": str(g["linea_id"]).lower(), "concepto": str(g["concepto"]).upper(),
            "cuenta_id": str(g["cuenta_id"]).lower(), "fecha_economica": _iso(g["fecha_economica"]),
            "fecha_pago": _iso(g["fecha_pago"]), "importe": _imp(g["importe"]), "nota": g.get("nota")}


def canonica_compra(propiedad_id: uuid.UUID, p: dict) -> dict:
    return {
        "propiedad_id": str(propiedad_id), "intencion_id": str(p["intencion_id"]).lower(),
        "row_version_esperada": p["row_version_esperada"], "fecha_escritura": _iso(p["fecha_escritura"]),
        "precio": _imp(p["precio"]),
        "valor_referencia": None if p.get("valor_referencia") is None else _imp(p["valor_referencia"]),
        "pagos_propios": sorted(({"linea_id": str(x["linea_id"]).lower(), "rol": str(x["rol"]).upper(),
                                  "cuenta_id": str(x["cuenta_id"]).lower(), "fecha_pago": _iso(x["fecha_pago"]),
                                  "importe": _imp(x["importe"])} for x in p["pagos_propios"]),
                                key=lambda x: x["linea_id"]),
        "gastos": sorted((canonica_gasto(g) for g in p["gastos"]), key=lambda x: x["linea_id"]),
        "atribucion": canonica_atribucion(p["atribucion"]),
        "completitud_adquisicion": canonica_completitud(p.get("completitud_adquisicion")),
    }


def canonica_compra03(propiedad_id: uuid.UUID, p: dict) -> dict:
    return {"propiedad_id": str(propiedad_id), "intencion_id": str(p["intencion_id"]).lower(),
            "row_version_esperada": p["row_version_esperada"], "linea": canonica_gasto(p["linea"]),
            "atribucion": canonica_atribucion(p["atribucion"]),
            "completitud_adquisicion": canonica_completitud(p.get("completitud_adquisicion")),
            "huella_conjunto_vista": p.get("huella_conjunto_vista")}


def sello(canonica: dict) -> str:
    texto = json.dumps(canonica, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ composicion declarada de una raiz
def _raiz(*, hecho_id: uuid.UUID, fecha: dt.date, importe: Decimal, concepto: str, notas: str | None,
          propiedad_id: uuid.UUID, vinculo_id: uuid.UUID, efecto_id: uuid.UUID,
          pagos: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID, dt.date, Decimal]], estado_atr: str,
          atribuciones: tuple) -> DatosHechoCompuesto:
    importe = importe.quantize(CENT)
    return DatosHechoCompuesto(
        hecho=DatosCreacionHecho(hecho_id=hecho_id, fecha_hecho=fecha, moneda=EUR, presupuestable=False,
                                 estado_localizacion="NO_APLICA", tipo_hecho_codigo=TIPO_HECHO,
                                 concepto=concepto, importe_total=importe, notas=notas),
        efectos=[DatosEfecto(efecto_id=efecto_id, tipo_efecto="VALOR_ACTIVO", importe_delta=importe,
                             estado_atribucion=estado_atr, acontecimiento="ADQUISICION", atribuciones=atribuciones)],
        pagos=[DatosPagoCompuesto(
            movimiento=DatosMovimiento(movimiento_id=mid, cuenta_id=cuenta, fecha_movimiento=fp,
                                       importe=-imp.quantize(CENT), clase_movimiento="OPERACION", descripcion=concepto),
            conciliacion=DatosConciliacion(conciliacion_id=cid, hecho_id=hecho_id, movimiento_tesoreria_id=mid,
                                           importe_asignado=-imp.quantize(CENT)))
            for mid, cid, cuenta, fp, imp in pagos],
        contexto=DatosContextoHecho(entidades=[DatosEntidadHecho(
            registro_id=vinculo_id, entidad_id=propiedad_id, tipo_relacion="AFECTA_A", principal=True,
            efecto_id=efecto_id)]),
    )


def _iguales(persistido: Any, esperado: Any) -> bool:
    if esperado is None or persistido is None:
        return persistido is None and esperado is None
    if isinstance(esperado, bool):
        return persistido is esperado
    if isinstance(esperado, Decimal):
        try:
            return Decimal(str(persistido)) == esperado
        except (decimal.InvalidOperation, ValueError):
            return False
    if isinstance(esperado, (uuid.UUID, dt.date)):
        return str(persistido) == (str(esperado) if isinstance(esperado, uuid.UUID) else esperado.isoformat())
    return persistido == esperado


def _fila(sesion: SesionMotor, tabla: str, ident: uuid.UUID, esperado: dict[str, Any]) -> bool:
    fila = repo_comp.leer(sesion, tabla, ident)
    return fila is not None and all(_iguales(fila.get(k), v) for k, v in esperado.items())


def identidades_declaradas(d: DatosHechoCompuesto, parte_de: uuid.UUID | None) -> dict[str, set[uuid.UUID]]:
    """Conjunto exacto de identidades por tabla del agregado (mismo conjunto cerrado que FILTROS_AGREGADO), con la
    PARTE_DE que escribe esta capa. Propio de B2: no usa ningun metodo privado de OP-22 (AJ-TR1-09)."""
    vacio: dict[str, set[uuid.UUID]] = {t: set() for t in repo_comp.FILTROS_AGREGADO}
    vacio["hecho_efectos"] = {e.efecto_id for e in d.efectos}
    vacio["efecto_atribuciones"] = {a.atribucion_id for e in d.efectos for a in e.atribuciones}
    vacio["hecho_movimientos_tesoreria"] = {p.conciliacion.conciliacion_id for p in d.pagos}
    vacio["hecho_entidades"] = {x.registro_id for x in d.contexto.entidades}
    vacio["hecho_relaciones"] = set() if parte_de is None else {parte_de}
    return vacio


def agregado_coincide(sesion: SesionMotor, d: DatosHechoCompuesto, parte_de: tuple[uuid.UUID, uuid.UUID] | None
                      ) -> bool:
    """(i) identidades y (iii) campos de cada fila declarada, por igualdad exacta (F04-D050)."""
    raiz = d.hecho_id
    h = d.hecho
    if repo_comp.identidades_del_agregado(sesion, raiz) != identidades_declaradas(d, None if parte_de is None
                                                                                   else parte_de[0]):
        return False
    hecho = repo_comp.leer(sesion, "hechos_financieros", raiz)
    if hecho is None or repo_comp.codigo_tipo_hecho(sesion, hecho["tipo_hecho_id"]) != h.tipo_hecho_codigo:
        return False
    if not all(_iguales(hecho.get(k), v) for k, v in {
            "fecha_hecho": h.fecha_hecho, "moneda": h.moneda, "concepto": h.concepto, "importe_total": h.importe_total,
            "estado_localizacion": h.estado_localizacion, "notas": h.notas, "presupuestable": h.presupuestable,
            "localidad_id": None}.items()):
        return False
    for e in d.efectos:
        if not _fila(sesion, "hecho_efectos", e.efecto_id, {
                "hecho_id": raiz, "tipo_efecto": e.tipo_efecto, "importe_delta": e.importe_delta,
                "estado_atribucion": e.estado_atribucion, "categoria_id": e.categoria_id,
                "causa_valor_activo": e.causa_valor_activo}):
            return False
        for a in e.atribuciones:
            if not _fila(sesion, "efecto_atribuciones", a.atribucion_id, {
                    "efecto_id": e.efecto_id, "actor_id": a.actor_id, "importe_atribuido": a.importe_atribuido,
                    "criterio_atribucion": a.criterio_atribucion, "porcentaje_aplicado": a.porcentaje_aplicado}):
                return False
    for p in d.pagos:
        m, c = p.movimiento, p.conciliacion
        if not _fila(sesion, "movimientos_tesoreria", m.movimiento_id, {
                "cuenta_id": m.cuenta_id, "fecha_movimiento": m.fecha_movimiento, "importe": m.importe,
                "clase_movimiento": m.clase_movimiento}):
            return False
        if not _fila(sesion, "hecho_movimientos_tesoreria", c.conciliacion_id, {
                "hecho_id": raiz, "movimiento_tesoreria_id": c.movimiento_tesoreria_id,
                "importe_asignado": c.importe_asignado}):
            return False
    for x in d.contexto.entidades:
        if not _fila(sesion, "hecho_entidades", x.registro_id, {
                "hecho_id": raiz, "entidad_id": x.entidad_id, "tipo_relacion": x.tipo_relacion,
                "principal": x.principal, "efecto_id": x.efecto_id}):
            return False
    if parte_de is not None and not _fila(sesion, "hecho_relaciones", parte_de[0], {
            "hecho_origen_id": raiz, "hecho_destino_id": parte_de[1], "tipo_relacion": "PARTE_DE"}):
        return False
    return True


def _relaciones_hacia(sesion: SesionMotor, destino: uuid.UUID) -> set[tuple[uuid.UUID, uuid.UUID]]:
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT id, hecho_origen_id FROM gapto.hecho_relaciones WHERE hecho_destino_id = %s "
                    "AND tipo_relacion = 'PARTE_DE'", (destino,))
        return {(i, o) for i, o in cur.fetchall()}


def _insertar_parte_de(sesion: SesionMotor, origen: uuid.UUID, destino: uuid.UUID, marca: str) -> None:
    sesion.ejecutar("INSERT INTO gapto.hecho_relaciones (id, hecho_origen_id, hecho_destino_id, tipo_relacion) "
                    "VALUES (%s, %s, %s, 'PARTE_DE')", (uuid.uuid5(origen, marca), origen, destino))


def _existe(sesion: SesionMotor, hecho_id: uuid.UUID) -> bool:
    return repo_comp.leer(sesion, "hechos_financieros", hecho_id) is not None


def compra_registrada(sesion: SesionMotor, propiedad_id: uuid.UUID) -> bool:
    """Unicidad estructural (v0.8): efecto VALOR_ACTIVO ADQUISICION de un hecho ACTIVO ADQUISICION_PATRIMONIAL con
    AFECTA_A principal a la propiedad. Se relee bajo el lock de la entidad."""
    return sesion.uno(
        "SELECT 1 FROM gapto.hecho_entidades x JOIN gapto.hechos_financieros h ON h.id = x.hecho_id "
        "AND h.estado = 'ACTIVO' JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id AND th.codigo = %s "
        "JOIN gapto.hecho_efectos e ON e.hecho_id = h.id AND e.tipo_efecto = 'VALOR_ACTIVO' "
        "AND e.causa_valor_activo = 'ADQUISICION' AND (x.efecto_id IS NULL OR x.efecto_id = e.id) "
        "WHERE x.entidad_id = %s AND x.tipo_relacion = 'AFECTA_A' AND x.principal LIMIT 1",
        (TIPO_HECHO, propiedad_id)) is not None


def h0_candidatos(sesion: SesionMotor, propiedad_id: uuid.UUID) -> list[uuid.UUID]:
    """HF-09: H0 = destino comun de las PARTE_DE compra.lote hacia un hecho ADQUISICION_PATRIMONIAL ACTIVO con
    AFECTA_A principal DE NIVEL EFECTO a la propiedad; sin Hk, el unico hecho con esas condiciones y sin PARTE_DE
    saliente. El llamante exige exactamente uno."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT h.id FROM gapto.hecho_entidades x JOIN gapto.hechos_financieros h ON h.id = x.hecho_id "
            "AND h.estado = 'ACTIVO' JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id AND th.codigo = %s "
            "WHERE x.entidad_id = %s AND x.tipo_relacion = 'AFECTA_A' AND x.principal AND x.efecto_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM gapto.hecho_relaciones r WHERE r.hecho_origen_id = h.id "
            "AND r.tipo_relacion = 'PARTE_DE') ORDER BY h.id", (TIPO_HECHO, propiedad_id))
        return [f[0] for f in cur.fetchall()]


def _bloquear_y_validar_cuentas(sesion: SesionMotor, usos: list[tuple[uuid.UUID, dt.date]]) -> str | None:
    """Nivel 3: cuentas FOR NO KEY UPDATE por id; regla R1 con la operacion de pago EXPLICITA (GASTO ->
    PAGAR_GASTO; §II.5): no se apoya en «todo lo que no es INGRESO es GASTO»."""
    for cuenta in sorted({c for c, _ in usos}, key=str):
        sesion.uno("SELECT id FROM gapto.cuentas WHERE id = %s FOR NO KEY UPDATE", (cuenta,))
    for cuenta, fecha in usos:
        if motivo_cuenta(sesion, cuenta, "GASTO", fecha, bloquear=True) is not None:
            return CUENTA_DESCONOCIDA
    return None


def _de_otros(sesion: SesionMotor, propiedad_id: uuid.UUID, hoy: dt.date) -> bool:
    vigente = m2.titularidad_en_fecha(sesion, propiedad_id, hoy)
    return bool(vigente) and not any(p["yo"] for p in vigente)


def _liquidez_atribuible(sesion: SesionMotor, movimientos: list[tuple[uuid.UUID, dt.date, Decimal]]) -> str:
    """AJ-10: parte de las salidas que corresponde al usuario segun la PARTICIPACION DE CADA CUENTA (no la
    titularidad de la propiedad ni la atribucion)."""
    total = Decimal(0)
    for cuenta, fecha, importe in movimientos:
        fila = sesion.uno(
            "SELECT coalesce(sum(cp.porcentaje), 0) FROM gapto.cuenta_participaciones cp "
            "JOIN gapto.actores_financieros a ON a.id = cp.actor_id AND a.tercero_id IS NULL "
            "WHERE cp.cuenta_id = %s AND cp.vigente_desde <= %s AND (cp.vigente_hasta IS NULL OR cp.vigente_hasta >= %s)",
            (cuenta, fecha, fecha))
        total += importe.quantize(CENT) * Decimal(fila[0]) / m2.CIEN
    return str(total.quantize(CENT))


def _respuesta(sesion: SesionMotor, propiedad_id: uuid.UUID, hechos: list[dict], movimientos: list,
               atribucion: dict, hoy: dt.date, idempotente: bool) -> dict:
    vista = lecturas.detalle(sesion, propiedad_id, hoy)
    salida = sum((imp.quantize(CENT) for _, _, imp in movimientos), Decimal(0))
    leido = coste.leer(sesion, propiedad_id, hoy)
    return {"propiedad": vista, "idempotente": idempotente,
            "compra": {"hechos": hechos, "coste_adquisicion": None if leido is None else leido["ADQUISICION"],
                       "sale_de_tus_cuentas": str(salida), "liquidez_atribuible": _liquidez_atribuible(sesion, movimientos),
                       "gasto_del_mes": "0.00", "atribucion": atribucion}}


def _partes_del_sello(canon: dict) -> list[tuple[uuid.UUID, Decimal]] | None:
    """Replay: la composicion se reconstruye con las partes SELLADAS (las que se escribieron), nunca con la
    titularidad actual, que pudo cambiar (M-2: un cambio posterior no reatribuye)."""
    a = canon["atribucion"]
    if a["modo"] == m2.NO_LO_SE:
        return None
    fuente = a["partes"] if a["modo"] == m2.MANUAL else a["propuesta_vista"]["partes"]
    return [(uuid.UUID(p["actor_id"]), Decimal(p["porcentaje"])) for p in fuente]


def _validar_declaracion(sesion: SesionMotor, propiedad_id: uuid.UUID, raiz: dict, completitud: dict | None,
                         fechas_nuevas: list[dt.date], hoy: dt.date) -> str | None:
    """Reglas de la declaracion antes de escribir (las de C-PROP-05: corte no futuro y no anterior a la
    adquisicion; algun componente <= corte contando los que crea la propia peticion)."""
    if completitud is None or not completitud["completo"]:
        return None
    corte = completitud["fecha_corte"]
    if corte > hoy:
        return SIN_FECHA_DE_CORTE
    if raiz["fecha_adquisicion"] is not None and corte < raiz["fecha_adquisicion"]:
        return SIN_FECHA_DE_CORTE
    previo, _ = repo.conjunto_completitud(sesion, propiedad_id, "ADQUISICION", corte)
    if not previo and not any(f <= corte for f in fechas_nuevas):
        return SIN_COMPONENTES
    return None


def _declarar(sesion: SesionMotor, propiedad_id: uuid.UUID, completitud: dict | None,
              efectos_esperados: set[str] | None) -> None:
    """Persiste la declaracion (consumidor provisional de 0352). El conjunto se calcula DESPUES de insertar.
    HF-07: en C-COMPRA-01 el conjunto tiene que ser exactamente el de las raices de la peticion."""
    if completitud is None:
        return
    if not completitud["completo"]:
        repo.escribir_declaracion_completitud(sesion, propiedad_id, "ADQUISICION", (None, None, None))
        return
    vigente, _ = repo.conjunto_completitud(sesion, propiedad_id, "ADQUISICION", completitud["fecha_corte"])
    if efectos_esperados is not None and {c["efecto_id"] for c in vigente} != efectos_esperados:
        raise _Deshacer(VISTA_DESFASADA)
    repo.escribir_declaracion_completitud(sesion, propiedad_id, "ADQUISICION",
                                          (True, completitud["fecha_corte"], vigente))


def _op22(sesion: SesionMotor) -> HechosCompuestosService:
    return HechosCompuestosService(UnidadDeTrabajoAdscrita(sesion), impacto_ancla=impacto_correccion_ancla)


# ------------------------------------------------------------------ C-COMPRA-01
def registrar_compra(sesion: SesionMotor, *, propiedad_id: uuid.UUID, peticion: dict,
                     reloj: Reloj = reloj_sistema) -> dict | Rechazo:
    completitud = peticion.get("completitud_adquisicion")
    if completitud is not None and not habilitacion.consumidores_0352_habilitados():
        return Rechazo(ENTRADA_INVALIDA)               # consumidor provisional de 0352 no habilitado
    if completitud is not None and (completitud["completo"] != (completitud.get("fecha_corte") is not None)):
        return Rechazo(ENTRADA_INVALIDA)               # HF-10
    lineas_ids = [str(x["linea_id"]).lower() for x in [*peticion["pagos_propios"], *peticion["gastos"]]]
    if len(set(lineas_ids)) != len(lineas_ids) or not peticion["pagos_propios"]:
        return Rechazo(ENTRADA_INVALIDA)
    forma = m2.validar_forma(peticion["atribucion"], criterio=m2.CRITERIO_ESCRITURA,
                             fecha_referencia=peticion["fecha_escritura"])
    if forma is not None:
        return Rechazo(forma)
    canon = canonica_compra(propiedad_id, peticion)
    s = sello(canon)
    h0 = uuid.UUID(canon["intencion_id"])
    lineas = {uuid.UUID(g["linea_id"]): g for g in canon["gastos"]}
    hks = {lid: uuid.uuid5(h0, f"gapto.f06.compra.gasto:{lid}") for lid in lineas}
    raices = sorted({h0, *hks.values()}, key=str)
    escritura = dt.date.fromisoformat(canon["fecha_escritura"])
    # 0 -> 1 -> 2
    for r in raices:
        repo_comp.tomar_advisory_raiz(sesion, r)
    tomar_inversiones(sesion)
    raiz = repo.bloquear(sesion, propiedad_id)
    if raiz is None:
        return Rechazo(NO_ENCONTRADA)
    hoy = hoy_owner(sesion, reloj)
    vinculo_h0 = uuid.uuid5(h0, "gapto.f06.compra.afecta_a:" + s)
    parte_de = {hk: (uuid.uuid5(hk, MARCA_LOTE), h0) for hk in hks.values()}

    def composiciones(partes: list[tuple[uuid.UUID, Decimal]] | None) -> dict[uuid.UUID, DatosHechoCompuesto]:
        modo = canon["atribucion"]["modo"]
        e0 = uuid.uuid5(h0, "gapto.f06.compra.efecto")
        estado, filas = m2.filas(e0, Decimal(canon["precio"]), partes, modo, "gapto.f06.compra.atribucion:")
        datos = {h0: _raiz(hecho_id=h0, fecha=escritura, importe=Decimal(canon["precio"]), concepto="COMPRA",
                           notas=None, propiedad_id=propiedad_id, vinculo_id=vinculo_h0, efecto_id=e0,
                           pagos=[(uuid.uuid5(h0, f"gapto.f06.compra.pago:{p['linea_id']}"),
                                   uuid.uuid5(h0, f"gapto.f06.compra.conciliacion:{p['linea_id']}"),
                                   uuid.UUID(p["cuenta_id"]), dt.date.fromisoformat(p["fecha_pago"]), Decimal(p["importe"]))
                                  for p in canon["pagos_propios"]],
                           estado_atr=estado, atribuciones=filas)}
        for lid, g in lineas.items():
            hk = hks[lid]
            ek = uuid.uuid5(hk, "gapto.f06.compra.efecto")
            estado, filas = m2.filas(ek, Decimal(g["importe"]), partes, modo, "gapto.f06.compra.atribucion:")
            datos[hk] = _raiz(hecho_id=hk, fecha=dt.date.fromisoformat(g["fecha_economica"]),
                              importe=Decimal(g["importe"]), concepto=g["concepto"], notas=g["nota"],
                              propiedad_id=propiedad_id, vinculo_id=uuid.uuid5(hk, "gapto.f06.compra.afecta_a"),
                              efecto_id=ek,
                              pagos=[(uuid.uuid5(hk, "gapto.f06.compra.pago"), uuid.uuid5(hk, "gapto.f06.compra.conciliacion"),
                                      uuid.UUID(g["cuenta_id"]), dt.date.fromisoformat(g["fecha_pago"]),
                                      Decimal(g["importe"]))],
                              estado_atr=estado, atribuciones=filas)
        return datos

    hechos = [{"linea_id": None, "hecho_id": str(h0)}] + [
        {"linea_id": str(lid), "hecho_id": str(hks[lid])} for lid in sorted(lineas, key=str)]
    movimientos = [(uuid.UUID(p["cuenta_id"]), dt.date.fromisoformat(p["fecha_pago"]), -Decimal(p["importe"]))
                   for p in canon["pagos_propios"]] + [
        (uuid.UUID(g["cuenta_id"]), dt.date.fromisoformat(g["fecha_pago"]), -Decimal(g["importe"]))
        for g in canon["gastos"]]

    # IDENTIDAD (§II.1, AJ-TR1-09), bajo los locks de nivel 0 y antes que la version
    existentes = [r for r in raices if _existe(sesion, r)]
    if existentes:
        if len(existentes) != len(raices):                                              # (v) lote parcial
            return Rechazo(IDENTIDAD_REUTILIZADA)
        compra03 = {(i, o) for i, o in _relaciones_hacia(sesion, h0) if i == uuid.uuid5(o, MARCA_LOTE03)}
        if _relaciones_hacia(sesion, h0) - compra03 != {(i, hk) for hk, (i, _) in parte_de.items()}:
            return Rechazo(IDENTIDAD_REUTILIZADA)                                       # (ii) y (vi)
        if repo_comp.leer(sesion, "hecho_entidades", vinculo_h0) is None:               # (iv) sello
            return Rechazo(IDENTIDAD_REUTILIZADA)
        declaradas = composiciones(_partes_del_sello(canon))
        for r, d in declaradas.items():                                                 # (i) y (iii)
            if not agregado_coincide(sesion, d, parte_de.get(r)):
                return Rechazo(IDENTIDAD_REUTILIZADA)
        return _respuesta(sesion, propiedad_id, hechos, movimientos, canon["atribucion"], hoy, True)

    # INTENCION NUEVA
    if raiz["row_version"] != canon["row_version_esperada"]:
        return Rechazo(VERSION_DESFASADA)
    if not raiz["enabled"]:
        return Rechazo(PROPIEDAD_NO_DISPONIBLE)
    if _de_otros(sesion, propiedad_id, hoy):
        return Rechazo(NO_PERMITIDA_EN_ESTADO)
    if compra_registrada(sesion, propiedad_id):
        return Rechazo(COMPRA_YA_REGISTRADA)
    if sum((Decimal(p["importe"]) for p in canon["pagos_propios"]), Decimal(0)) != Decimal(canon["precio"]):
        return Rechazo(m2.SUMA_NO_CUADRA)
    for p in canon["pagos_propios"]:
        fp = dt.date.fromisoformat(p["fecha_pago"])
        if (p["rol"] == "FIRMA" and fp != escritura) or (p["rol"] == "ARRAS" and fp > escritura):
            return Rechazo(FECHA_PAGO_INCOHERENTE)
    rechazo = _bloquear_y_validar_cuentas(sesion, [(c, f) for c, f, _ in movimientos])
    if rechazo:
        return Rechazo(rechazo)
    partes = m2.resolver(sesion, propiedad_id, peticion["atribucion"])
    if isinstance(partes, str):
        return Rechazo(partes)
    datos = composiciones(partes)
    fechas = [escritura] + [dt.date.fromisoformat(g["fecha_economica"]) for g in canon["gastos"]]
    rechazo = _validar_declaracion(sesion, propiedad_id, raiz, completitud, fechas, hoy)
    if rechazo:
        return Rechazo(rechazo)
    antes = repo.snapshot(sesion, propiedad_id)
    try:
        with sesion.conexion.transaction():
            op22 = _op22(sesion)
            for r in raices:                                                            # 7: solo raices nuevas
                op22.registrar_hecho_compuesto(sesion.contexto, datos[r])
            for hk in hks.values():
                _insertar_parte_de(sesion, hk, h0, MARCA_LOTE)
            repo.insertar_valoracion(sesion, valoracion_id=uuid.uuid5(h0, "gapto.f06.compra.valoracion"),
                                     propiedad_id=propiedad_id, valor_total=Decimal(canon["precio"]), fecha=escritura,
                                     metodo="COMPRA", fuente=None, notas=None)
            if canon["valor_referencia"] is not None:
                repo.insertar_valoracion(sesion, valoracion_id=uuid.uuid5(h0, "gapto.f06.compra.valoracion_fiscal"),
                                         propiedad_id=propiedad_id, valor_total=Decimal(canon["valor_referencia"]),
                                         fecha=escritura, metodo="FISCAL_REFERENCIA", fuente=None, notas=None)
            corte = completitud["fecha_corte"] if completitud is not None and completitud["completo"] else None
            esperados = None if corte is None else {str(d.efectos[0].efecto_id) for d in datos.values()
                                                    if d.hecho.fecha_hecho <= corte}
            _declarar(sesion, propiedad_id, completitud, esperados)                       # 8
    except _Deshacer as exc:
        return Rechazo(exc.codigo)
    repo.subir_version(sesion, propiedad_id)
    auditar(sesion, propiedad_id, antes, {"operacion": OP_COMPRA, "contenido": {"sello": s}}, MOTIVO_COMPRA)
    return _respuesta(sesion, propiedad_id, hechos, movimientos, canon["atribucion"], hoy, False)


# ------------------------------------------------------------------ C-COMPRA-03
def gasto_posterior(sesion: SesionMotor, *, propiedad_id: uuid.UUID, peticion: dict,
                    reloj: Reloj = reloj_sistema) -> dict | Rechazo:
    completitud = peticion.get("completitud_adquisicion")
    huella_vista = peticion.get("huella_conjunto_vista")
    if (completitud is not None or huella_vista is not None) and not habilitacion.consumidores_0352_habilitados():
        return Rechazo(ENTRADA_INVALIDA)               # consumidor provisional de 0352 no habilitado
    if completitud is not None and (completitud["completo"] != (completitud.get("fecha_corte") is not None)):
        return Rechazo(ENTRADA_INVALIDA)
    if completitud is not None and completitud["completo"] and not huella_vista:
        return Rechazo(ENTRADA_INVALIDA)
    if huella_vista is not None and (completitud is None or not completitud["completo"]):
        return Rechazo(ENTRADA_INVALIDA)
    g0 = peticion["linea"]
    forma = m2.validar_forma(peticion["atribucion"], criterio=m2.CRITERIO_EFECTO,
                             fecha_referencia=g0["fecha_economica"])
    if forma is not None:
        return Rechazo(forma)
    canon = canonica_compra03(propiedad_id, peticion)
    s = sello(canon)
    hk = uuid.UUID(canon["intencion_id"])
    g = canon["linea"]
    fe = dt.date.fromisoformat(g["fecha_economica"])
    repo_comp.tomar_advisory_raiz(sesion, hk)
    tomar_inversiones(sesion)
    raiz = repo.bloquear(sesion, propiedad_id)
    if raiz is None:
        return Rechazo(NO_ENCONTRADA)
    hoy = hoy_owner(sesion, reloj)
    vinculo = uuid.uuid5(hk, "gapto.f06.compra03.afecta_a:" + s)
    ek = uuid.uuid5(hk, "gapto.f06.compra03.efecto")
    movimientos = [(uuid.UUID(g["cuenta_id"]), dt.date.fromisoformat(g["fecha_pago"]), -Decimal(g["importe"]))]

    def composicion_hk(partes):
        estado, filas = m2.filas(ek, Decimal(g["importe"]), partes, canon["atribucion"]["modo"],
                                 "gapto.f06.compra03.atribucion:")
        return _raiz(hecho_id=hk, fecha=fe, importe=Decimal(g["importe"]), concepto=g["concepto"], notas=g["nota"],
                     propiedad_id=propiedad_id, vinculo_id=vinculo, efecto_id=ek,
                     pagos=[(uuid.uuid5(hk, "gapto.f06.compra03.pago"), uuid.uuid5(hk, "gapto.f06.compra03.conciliacion"),
                             uuid.UUID(g["cuenta_id"]), dt.date.fromisoformat(g["fecha_pago"]), Decimal(g["importe"]))],
                     estado_atr=estado, atribuciones=filas)

    hechos = [{"linea_id": g["linea_id"], "hecho_id": str(hk)}]
    if _existe(sesion, hk):                                                             # identidad, una raiz
        destino = [d for i, d in _relaciones_desde(sesion, hk) if i == uuid.uuid5(hk, MARCA_LOTE03)]
        if len(destino) != 1 or not agregado_coincide(sesion, composicion_hk(_partes_del_sello(canon)),
                                                     (uuid.uuid5(hk, MARCA_LOTE03), destino[0])):
            return Rechazo(IDENTIDAD_REUTILIZADA)
        return _respuesta(sesion, propiedad_id, hechos, movimientos, canon["atribucion"], hoy, True)
    if raiz["row_version"] != canon["row_version_esperada"]:
        return Rechazo(VERSION_DESFASADA)
    if not raiz["enabled"]:
        return Rechazo(PROPIEDAD_NO_DISPONIBLE)
    candidatos = h0_candidatos(sesion, propiedad_id)
    if len(candidatos) != 1:
        return Rechazo(COMPRA_NO_REGISTRADA)
    h0 = candidatos[0]
    rechazo = _bloquear_y_validar_cuentas(sesion, [(c, f) for c, f, _ in movimientos])
    if rechazo:
        return Rechazo(rechazo)
    partes = m2.resolver(sesion, propiedad_id, peticion["atribucion"])
    if isinstance(partes, str):
        return Rechazo(partes)
    if completitud is not None and completitud["completo"]:
        rechazo = _validar_declaracion(sesion, propiedad_id, raiz, completitud, [fe], hoy)
        if rechazo:
            return Rechazo(rechazo)
        # la huella vista es la del conjunto ANTERIOR al alta, leida con a_fecha = corte nuevo (HF-09)
        _, huella = repo.conjunto_completitud(sesion, propiedad_id, "ADQUISICION", completitud["fecha_corte"])
        if huella != huella_vista:
            return Rechazo(VISTA_DESFASADA)
    antes = repo.snapshot(sesion, propiedad_id)
    _op22(sesion).registrar_hecho_compuesto(sesion.contexto, composicion_hk(partes))
    _insertar_parte_de(sesion, hk, h0, MARCA_LOTE03)
    _declarar(sesion, propiedad_id, completitud, None)
    repo.subir_version(sesion, propiedad_id)
    auditar(sesion, propiedad_id, antes, {"operacion": OP_COMPRA03, "contenido": {"sello": s}}, MOTIVO_COMPRA03)
    return _respuesta(sesion, propiedad_id, hechos, movimientos, canon["atribucion"], hoy, False)


def _relaciones_desde(sesion: SesionMotor, origen: uuid.UUID) -> list[tuple[uuid.UUID, uuid.UUID]]:
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT id, hecho_destino_id FROM gapto.hecho_relaciones WHERE hecho_origen_id = %s "
                    "AND tipo_relacion = 'PARTE_DE'", (origen,))
        return cur.fetchall()
