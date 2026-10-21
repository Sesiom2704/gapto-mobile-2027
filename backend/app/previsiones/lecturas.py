# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas.py
# Ruta: backend/app/previsiones/lecturas.py
# Descripcion: Read models de la confirmacion de previsiones (F05-06 M5; F05
#   §59 F05-D044 decisiones 6 y 7; D-M5-07, D-M5-08; AJ-M5-DEC-04, 08; lamina
#   PREV v0.2 y HOME-01 v0.4). SOLO SELECT, sin locks propios, gapto_runtime
#   con RLS: el owner sale de la GUC, nunca de un parametro.
#
#   Definiciones (sobre previsiones ABIERTAS; `hoy` = hoy_owner, nunca UTC):
#   - cubierto = suma de importe_asignado de vinculos con hecho ACTIVO (como
#     resumen_realidad del motor); con_realidad = al menos uno.
#   - vencida = fecha_esperada_hasta (o desde si faltase) < hoy.
#   - Requiere atencion = vencida o con_realidad (una parcial no vencida
#     sigue aqui, D-PREV-09). Orden: vencidas por fecha e id y despues las
#     parciales por fecha e id.
#   - Proximos = sin realidad y fecha >= hoy; las tres primeras por fecha e id.
#   - «queda» = esperado - cubierto solo si el esperado es conocido y el
#     resultado es > 0; desviacion = cubierto - esperado si es > 0 (D-PREV-13).
#     Esperado desconocido -> None («Desconocido»), NUNCA 0.
#   - Importes por naturaleza (AJ-M5-DEC-04): GASTO -> «Por pagar», INGRESO
#     -> «Por cobrar», TRANSFERENCIA no suma. Cada naturaleza cuenta aparte
#     las que tienen el esperado desconocido. Nunca un total unico; Inicio no
#     suma importes (solo el recuento comun y las filas).
#   - Estados excluidos: las listas solo leen ABIERTAS, asi que REALIZADA,
#     OMITIDA, CANCELADA y sus derivados REQUIERE_REVISION y REALIZADA_SIN_
#     REALIDAD_ACTIVA (DEU-M5-PREV-REVISION) no aparecen. El detalle por id
#     devuelve cualquier estado, sin acciones fuera de ABIERTA.
#   - Las previsiones nunca entran en resultado_mes ni en la liquidez
#     (MONTH-RULE-06): este modulo no lo toca.
#   - «Sin fecha»: la seccion existe en el contrato, pero fecha_esperada_desde y
#     _hasta son NOT NULL en el head fisico, de modo que hoy siempre va vacia.
#
#   Candidatos de «Ya lo registre» (AJ-M5-DEC-08): hecho ACTIVO del owner, del
#   mismo tipo; mismo tercero o misma categoria (sin ninguno en la prevision:
#   lista vacia con mensaje); fecha en la ventana; importe_total conocido, misma
#   moneda y porcion disponible > 0 (importe_total - todos los vinculos del
#   hecho, sea cual sea el estado de su prevision, como G-R1-C); excluidos los
#   ya vinculados a esta prevision; orden por cercania de fecha y sin
#   preseleccion. VENTANA_CANDIDATOS_DIAS y VENTANA_CANDIDATOS_AMPLIADA_DIAS
#   son una HEURISTICA UX REVISABLE (P-PREV-07), no un invariante: vincular no
#   aplica la ventana y la autoridad final es OP-17 bajo locks.
# Version: 0.1.0 (F05-06 M5 §A2)
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any

from app.comun.rutas_categoria import catalogo, ruta_texto
from app.core.unidad_trabajo import SesionMotor

#: Heuristica UX revisable (no invariante): ±15 dias alrededor del intervalo
#: esperado; «Buscar en mas fechas» amplia a ±60 con los mismos filtros.
VENTANA_CANDIDATOS_DIAS = 15
VENTANA_CANDIDATOS_AMPLIADA_DIAS = 60
MAX_REQUIERE_ATENCION_INICIO = 2
MAX_PROXIMOS = 3
MONEDA_V1 = "EUR"

NATURALEZA = {"GASTO": "POR_PAGAR", "INGRESO": "POR_COBRAR", "TRANSFERENCIA": "ENTRE_CUENTAS"}
TIPOS_CONFIRMABLES = ("GASTO", "INGRESO", "TRANSFERENCIA")
MENSAJE_SIN_CRITERIO = ("Esta previsión no tiene tercero ni categoría: no hay registros que proponer. "
                        "Puedes registrarlo desde la previsión.")

_CENT = decimal.Decimal("0.01")
_CERO = decimal.Decimal(0)

_COLUMNAS = (
    "SELECT p.id, p.row_version, p.estado, th.codigo, p.concepto, p.tercero_id, t.nombre, p.categoria_id, "
    "p.fecha_esperada_desde, p.fecha_esperada_hasta, p.moneda, p.importe_esperado, "
    "p.cuenta_salida_esperada_id, cs.nombre, p.cuenta_entrada_esperada_id, ce.nombre, p.regla_version_id, "
    "p.presupuestable, "
    "EXISTS (SELECT 1 FROM gapto.mapeos_importacion m WHERE m.tabla_destino = 'previsiones' "
    "        AND m.registro_destino_id = p.id), "
    "(SELECT count(*) FROM gapto.prevision_hechos pv JOIN gapto.hechos_financieros h ON h.id = pv.hecho_id "
    " WHERE pv.prevision_id = p.id AND h.estado = 'ACTIVO'), "
    "(SELECT COALESCE(sum(pv.importe_asignado), 0) FROM gapto.prevision_hechos pv "
    " JOIN gapto.hechos_financieros h ON h.id = pv.hecho_id WHERE pv.prevision_id = p.id AND h.estado = 'ACTIVO') "
    "FROM gapto.previsiones p JOIN gapto.tipos_hecho th ON th.id = p.tipo_hecho_id "
    "LEFT JOIN gapto.terceros t ON t.id = p.tercero_id "
    "LEFT JOIN gapto.cuentas cs ON cs.id = p.cuenta_salida_esperada_id "
    "LEFT JOIN gapto.cuentas ce ON ce.id = p.cuenta_entrada_esperada_id "
)


def _texto(valor: decimal.Decimal | None) -> str | None:
    return None if valor is None else str(decimal.Decimal(valor).quantize(_CENT))


def _fecha_ref(desde: dt.date | None, hasta: dt.date | None) -> dt.date | None:
    return hasta if hasta is not None else desde


def _origen(regla_version_id, v3: bool) -> str:
    if v3:
        return "V3"
    return "REGLA" if regla_version_id is not None else "MANUAL"


def _fila(f: tuple, nodos: dict, hoy: dt.date) -> dict[str, Any]:
    (pid, row_version, estado, tipo, concepto, tercero_id, tercero, categoria_id, desde, hasta, moneda, esperado,
     cs_id, cs_nombre, ce_id, ce_nombre, regla_version_id, presupuestable, v3, n_activos, cubierto) = f
    cubierto = decimal.Decimal(cubierto)
    esperado = None if esperado is None else decimal.Decimal(esperado)
    queda = desviacion = None
    if esperado is not None:
        if esperado - cubierto > 0:
            queda = esperado - cubierto
        elif cubierto - esperado > 0:
            desviacion = cubierto - esperado
    ref = _fecha_ref(desde, hasta)
    nodo = nodos.get(categoria_id) if categoria_id is not None else None
    return {
        "id": pid, "row_version": row_version, "estado": estado, "tipo": tipo,
        "naturaleza": NATURALEZA.get(tipo), "concepto": concepto,
        "tercero": None if tercero_id is None else {"id": tercero_id, "nombre": tercero},
        "categoria": None if nodo is None else {"id": nodo["id"], "nombre": nodo["nombre"], "ruta": ruta_texto(nodo)},
        "fecha_desde": desde, "fecha_hasta": hasta, "moneda": moneda,
        "importe_esperado": _texto(esperado), "cubierto": _texto(cubierto),
        "queda": _texto(queda), "desviacion": _texto(desviacion),
        "con_realidad": n_activos > 0, "pagos": n_activos,
        "vencida": estado == "ABIERTA" and ref is not None and ref < hoy,
        "cuenta_salida": None if cs_id is None else {"id": cs_id, "nombre": cs_nombre},
        "cuenta_entrada": None if ce_id is None else {"id": ce_id, "nombre": ce_nombre},
        "origen": _origen(regla_version_id, v3), "presupuestable": presupuestable,
        "_ref": ref, "_esperado": esperado, "_queda": queda, "_cubierto": cubierto,
    }


def _publica(fila: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in fila.items() if not k.startswith("_")}


def _abiertas(sesion: SesionMotor, hoy: dt.date) -> list[dict[str, Any]]:
    nodos = catalogo(sesion)
    with sesion.conexion.cursor() as cur:
        cur.execute(_COLUMNAS + "WHERE p.estado = 'ABIERTA' AND th.codigo = ANY(%s)", (list(TIPOS_CONFIRMABLES),))
        return [_fila(f, nodos, hoy) for f in cur.fetchall()]


def _clave(fila: dict[str, Any]) -> tuple:
    return (fila["_ref"] is None, fila["_ref"] or dt.date.max, str(fila["id"]))


def _requiere_atencion(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    vencidas = sorted((f for f in filas if f["vencida"]), key=_clave)
    parciales = sorted((f for f in filas if not f["vencida"] and f["con_realidad"]), key=_clave)
    return vencidas + parciales


def inicio(sesion: SesionMotor, hoy: dt.date) -> dict[str, Any]:
    """Inicio (HOME-01 v0.4): recuento comun, las dos primeras y los proximos.
    Sin importes sumados."""
    filas = _abiertas(sesion, hoy)
    atencion = _requiere_atencion(filas)
    proximos = sorted((f for f in filas if not f["con_realidad"] and f["_ref"] is not None and f["_ref"] >= hoy),
                      key=_clave)
    return {
        "hoy": hoy,
        "requiere_atencion": {"n": len(atencion),
                              "primeras": [_publica(f) for f in atencion[:MAX_REQUIERE_ATENCION_INICIO]]},
        "proximos": [_publica(f) for f in proximos[:MAX_PROXIMOS]],
    }


def _por_naturaleza(filas: list[dict[str, Any]], tipo: str) -> dict[str, Any]:
    """Lo que falta por naturaleza: «queda» si el esperado es conocido; las de
    esperado desconocido se cuentan aparte (nunca como 0)."""
    propias = [f for f in filas if f["tipo"] == tipo]
    conocidas = [f for f in propias if f["_esperado"] is not None]
    importe = None if not conocidas and propias else sum((f["_queda"] or _CERO for f in conocidas), _CERO)
    return {"importe": _texto(importe), "n": len(propias), "desconocidos": len(propias) - len(conocidas)}


def pendientes(sesion: SesionMotor, hoy: dt.date) -> dict[str, Any]:
    """Lista «Pendientes» (HOME-01 I04, PREV B): vencidas, con pago parcial y
    sin fecha, con «Por pagar» y «Por cobrar» separados."""
    filas = _abiertas(sesion, hoy)
    atencion = _requiere_atencion(filas)
    return {
        "hoy": hoy,
        "n": len(atencion),
        "por_pagar": _por_naturaleza(atencion, "GASTO"),
        "por_cobrar": _por_naturaleza(atencion, "INGRESO"),
        "secciones": {
            "vencidas": [_publica(f) for f in atencion if f["vencida"]],
            "con_pago_parcial": [_publica(f) for f in atencion if not f["vencida"]],
            "sin_fecha": [_publica(f) for f in filas if f["_ref"] is None],
        },
    }


# ------------------------------------------------------------------ detalle
def _accion(disponible: bool, motivo: str | None = None) -> dict[str, Any]:
    return {"disponible": disponible, "motivo": None if disponible else motivo}


def acciones(fila: dict[str, Any], estado_derivado: str | None) -> dict[str, dict[str, Any]]:
    """Acciones de la prevision con su motivo en lenguaje llano."""
    if fila["estado"] != "ABIERTA" or estado_derivado is not None:
        motivo = "Esta previsión ya no está pendiente: aquí solo se consulta."
        return {k: _accion(False, motivo) for k in ("registrar", "ya_lo_registre", "omitir", "swipe")}
    if fila["moneda"] != MONEDA_V1:
        motivo = "Solo se pueden confirmar previsiones en euros en esta versión."
        return {k: _accion(False, motivo) for k in ("registrar", "ya_lo_registre", "omitir", "swipe")}
    if fila["tipo"] not in TIPOS_CONFIRMABLES:
        motivo = "Este tipo de previsión no se confirma desde aquí."
        return {k: _accion(False, motivo) for k in ("registrar", "ya_lo_registre", "omitir", "swipe")}
    omitir = _accion(not fila["con_realidad"], "«No hubo este mes» no está disponible: ya tiene un pago enlazado.")
    cuenta = fila["cuenta_salida"] if fila["tipo"] == "GASTO" else fila["cuenta_entrada"]
    if fila["tipo"] == "TRANSFERENCIA":
        swipe = _accion(False, "Las transferencias se registran con su formulario.")
    elif fila["_esperado"] is None:
        swipe = _accion(False, "Sin importe esperado no hay confirmación rápida: indica el importe real en el formulario.")
    elif fila["con_realidad"]:
        swipe = _accion(False, "Ya tiene un pago enlazado: registra o enlaza el resto desde el formulario.")
    elif cuenta is None:
        swipe = _accion(False, "No tiene una cuenta prevista: elige la cuenta en el formulario.")
    else:
        swipe = _accion(True)
    return {"registrar": _accion(True), "ya_lo_registre": _accion(True), "omitir": omitir, "swipe": swipe}


def detalle(sesion: SesionMotor, prevision_id: uuid.UUID, hoy: dt.date) -> dict[str, Any] | None:
    """Detalle por id en CUALQUIER estado (AJ de Q6); None si no es visible."""
    nodos = catalogo(sesion)
    f = sesion.uno(_COLUMNAS + "WHERE p.id = %s", (prevision_id,))
    if f is None:
        return None
    fila = _fila(f, nodos, hoy)
    derivado = None
    if fila["estado"] == "REALIZADA" and not fila["con_realidad"]:
        derivado = "REALIZADA_SIN_REALIDAD_ACTIVA"
    elif fila["estado"] in ("OMITIDA", "CANCELADA") and fila["con_realidad"]:
        derivado = "REQUIERE_REVISION"
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT pv.id, pv.hecho_id, pv.importe_asignado, h.fecha_hecho, h.concepto, h.importe_total "
            "FROM gapto.prevision_hechos pv JOIN gapto.hechos_financieros h ON h.id = pv.hecho_id "
            "WHERE pv.prevision_id = %s AND h.estado = 'ACTIVO' ORDER BY h.fecha_hecho, pv.id", (prevision_id,))
        vinculos = [{"vinculo_id": v[0], "hecho_id": v[1], "importe_asignado": _texto(v[2]), "fecha_hecho": v[3],
                     "concepto": v[4], "importe_total": _texto(v[5])} for v in cur.fetchall()]
    return {**_publica(fila), "estado_derivado": derivado, "vinculos": vinculos,
            "acciones": acciones(fila, derivado)}


# ------------------------------------------------------------------ candidatos
_CANDIDATOS = (
    "SELECT h.id, h.fecha_hecho, h.concepto, h.importe_total, h.moneda, "
    "(SELECT COALESCE(sum(pv.importe_asignado), 0) FROM gapto.prevision_hechos pv WHERE pv.hecho_id = h.id), "
    "(SELECT count(*) FROM gapto.prevision_hechos pv JOIN gapto.previsiones q ON q.id = pv.prevision_id "
    " WHERE pv.hecho_id = h.id AND q.moneda <> h.moneda), "
    "(SELECT t.nombre FROM gapto.hecho_terceros ht JOIN gapto.terceros t ON t.id = ht.tercero_id "
    " WHERE ht.hecho_id = h.id ORDER BY ht.principal DESC, ht.id LIMIT 1), "
    "(SELECT c.nombre FROM gapto.hecho_movimientos_tesoreria hm JOIN gapto.movimientos_tesoreria m "
    " ON m.id = hm.movimiento_tesoreria_id JOIN gapto.cuentas c ON c.id = m.cuenta_id "
    " WHERE hm.hecho_id = h.id ORDER BY m.id LIMIT 1), "
    "(SELECT e.categoria_id FROM gapto.hecho_efectos e WHERE e.hecho_id = h.id AND e.categoria_id IS NOT NULL "
    " ORDER BY e.id LIMIT 1) "
    "FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho th ON th.id = h.tipo_hecho_id "
    "WHERE h.estado = 'ACTIVO' AND th.codigo = %(tipo)s AND h.moneda = %(moneda)s "
    "AND h.importe_total IS NOT NULL "
    "AND h.fecha_hecho BETWEEN %(desde)s AND %(hasta)s "
    "AND NOT EXISTS (SELECT 1 FROM gapto.prevision_hechos pv WHERE pv.hecho_id = h.id "
    "                AND pv.prevision_id = %(prevision)s) "
    "AND ({coincide})"
)
_POR_TERCERO = "EXISTS (SELECT 1 FROM gapto.hecho_terceros ht WHERE ht.hecho_id = h.id AND ht.tercero_id = %(tercero)s)"
_POR_CATEGORIA = ("EXISTS (SELECT 1 FROM gapto.hecho_efectos e WHERE e.hecho_id = h.id "
                  "AND e.categoria_id = %(categoria)s)")


def _distancia(fecha: dt.date, desde: dt.date, hasta: dt.date) -> int:
    if fecha < desde:
        return (desde - fecha).days
    if fecha > hasta:
        return (fecha - hasta).days
    return 0


def candidatos(sesion: SesionMotor, prevision_id: uuid.UUID, *, ampliado: bool = False) -> dict[str, Any] | None:
    """Candidatos de «Ya lo registre». None si la prevision no es visible."""
    p = sesion.uno(
        "SELECT th.codigo, p.moneda, p.tercero_id, p.categoria_id, p.fecha_esperada_desde, p.fecha_esperada_hasta "
        "FROM gapto.previsiones p JOIN gapto.tipos_hecho th ON th.id = p.tipo_hecho_id WHERE p.id = %s",
        (prevision_id,))
    if p is None:
        return None
    tipo, moneda, tercero, categoria, desde, hasta = p
    dias = VENTANA_CANDIDATOS_AMPLIADA_DIAS if ampliado else VENTANA_CANDIDATOS_DIAS
    salida = {"prevision_id": prevision_id, "ampliado": ampliado, "ventana_dias": dias, "mensaje": None,
              "candidatos": []}
    if tercero is None and categoria is None:
        return {**salida, "mensaje": MENSAJE_SIN_CRITERIO}
    desde = desde or hasta
    hasta = hasta or desde
    coincide = " OR ".join(c for c, v in ((_POR_TERCERO, tercero), (_POR_CATEGORIA, categoria)) if v is not None)
    nodos = catalogo(sesion)
    with sesion.conexion.cursor() as cur:
        cur.execute(_CANDIDATOS.format(coincide=coincide),
                    {"tipo": tipo, "moneda": moneda, "prevision": prevision_id, "tercero": tercero,
                     "categoria": categoria, "desde": desde - dt.timedelta(days=dias),
                     "hasta": hasta + dt.timedelta(days=dias)})
        filas = cur.fetchall()
    lista = []
    for hid, fecha, concepto, total, _moneda, asignado, otras_monedas, tercero_n, cuenta, cat_id in filas:
        if otras_monedas:  # NO_DETERMINABLE (G-R1-C): sin comparacion numerica, no se propone
            continue
        disponible = decimal.Decimal(total) - decimal.Decimal(asignado)
        if disponible <= 0:
            continue
        nodo = nodos.get(cat_id) if cat_id is not None else None
        lista.append({"hecho_id": hid, "fecha_hecho": fecha, "concepto": concepto, "tercero": tercero_n,
                      "categoria": None if nodo is None else ruta_texto(nodo), "cuenta": cuenta,
                      "importe_total": _texto(total), "porcion_disponible": _texto(disponible),
                      "_d": _distancia(fecha, desde, hasta)})
    lista.sort(key=lambda c: (c["_d"], -c["fecha_hecho"].toordinal(), str(c["hecho_id"])))
    return {**salida, "candidatos": [{k: v for k, v in c.items() if k != "_d"} for c in lista]}


# ------------------------------------------------------------------ apoyo del adaptador (SELECT)
def porcion_restante(sesion: SesionMotor, hecho_id: uuid.UUID) -> decimal.Decimal | None:
    """importe_total - todos los vinculos del hecho (G-R1-C). None si no es
    determinable (importe NULL o algun vinculo en otra moneda)."""
    f = sesion.uno(
        "SELECT h.importe_total, "
        "(SELECT COALESCE(sum(pv.importe_asignado), 0) FROM gapto.prevision_hechos pv WHERE pv.hecho_id = h.id), "
        "(SELECT count(*) FROM gapto.prevision_hechos pv JOIN gapto.previsiones q ON q.id = pv.prevision_id "
        " WHERE pv.hecho_id = h.id AND q.moneda <> h.moneda) "
        "FROM gapto.hechos_financieros h WHERE h.id = %s", (hecho_id,))
    if f is None or f[0] is None or f[2]:
        return None
    return decimal.Decimal(f[0]) - decimal.Decimal(f[1])


def tipo_de_prevision(sesion: SesionMotor, prevision_id: uuid.UUID) -> str | None:
    f = sesion.uno("SELECT th.codigo FROM gapto.previsiones p JOIN gapto.tipos_hecho th ON th.id = p.tipo_hecho_id "
                   "WHERE p.id = %s", (prevision_id,))
    return None if f is None else f[0]


def tipo_de_hecho(sesion: SesionMotor, hecho_id: uuid.UUID) -> str | None:
    f = sesion.uno("SELECT th.codigo FROM gapto.hechos_financieros h JOIN gapto.tipos_hecho th "
                   "ON th.id = h.tipo_hecho_id WHERE h.id = %s", (hecho_id,))
    return None if f is None else f[0]


def vinculos_del_hecho(sesion: SesionMotor, hecho_id: uuid.UUID) -> dict[uuid.UUID, tuple[uuid.UUID, decimal.Decimal]]:
    """vinculo_id -> (prevision_id, importe_asignado) de todos los vinculos del hecho."""
    with sesion.conexion.cursor() as cur:
        cur.execute("SELECT id, prevision_id, importe_asignado FROM gapto.prevision_hechos WHERE hecho_id = %s",
                    (hecho_id,))
        return {f[0]: (f[1], decimal.Decimal(f[2])) for f in cur.fetchall()}


def estado_persistido(sesion: SesionMotor, prevision_id: uuid.UUID) -> str | None:
    f = sesion.uno("SELECT estado FROM gapto.previsiones WHERE id = %s", (prevision_id,))
    return None if f is None else f[0]
