# ============================================================
# GAPTO MOBILE 2027
# Fichero: lecturas.py
# Ruta: backend/app/contratos/lecturas.py
# Descripcion: Lecturas de F06-02/03 (contrato v1.1 Parte VI y V-bis). Solo SELECT, bajo RLS y filtradas por
#   owner. Sin renta (no existe en el bloque; un contrato V3 con `regla_renta_id` solo lleva la marca).
#     L-CON-01  contratos de una propiedad por situacion DERIVADA y ocupacion de hoy por habitacion
#     L-CON-02  contrato completo con `terminable` y su `motivo`
#     L-CON-03  propuesta de arrendadores, habitaciones y nombre (no escribe ni bloquea)
#     L-SRV-01  servicios de una propiedad y su tratamiento en cada contrato vigente
#     L-TER-01  `GET /v1/terceros/{id}`: roles, clasificaciones y «Uso en Gapto» (sin direcciones)
#     V-bis     selector de terceros del ASISTENTE (naturaleza + uso derivado, UNA consulta, sin N+1);
#               lectura NUEVA: no cambia TerceroLista ni el writer de F05.
#   La situacion y la ocupacion se DERIVAN al leer: ninguna columna (INV-ALQ-12).
# Version: 0.1.0 (F06 T3-F06 Bloque 3, paso 4)
# ============================================================

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from app.categorias.normalizacion import normalizar
from app.contratos import errores as e
from app.contratos import modelos as m
from app.contratos import repositorio as repo
from app.core.unidad_trabajo import SesionMotor
from app.propiedades import repositorio as repo_prop

TIPO_PRODUCTO = {v: k for k, v in m.TIPOS_CONTRATO.items()}
TEXTO_POR_FACTURA = "Se reparte en cada factura"
MARCA_RENTA_V3 = "Renta registrada · se gestiona en la parte de cobros"


# ------------------------------------------------------------------ derivaciones puras
def situacion(c: dict[str, Any], hoy: dt.date) -> str:
    """BORRADOR, CANCELADO o, para un FORMALIZADO: FINALIZADO (fin real < hoy), PROXIMO (inicio > hoy) o VIGENTE."""
    if c["estado_documental"] != "FORMALIZADO":
        return c["estado_documental"]
    if c["fecha_fin_real"] is not None and c["fecha_fin_real"] < hoy:
        return "FINALIZADO"
    if c["fecha_inicio"] is not None and c["fecha_inicio"] > hoy:
        return "PROXIMO"
    return "VIGENTE"


def fin_previsto_vencido(c: dict[str, Any], hoy: dt.date) -> bool:
    """Marca derivada (sin columna): vigente, sin fin real y con fin previsto anterior a hoy."""
    return (situacion(c, hoy) == "VIGENTE" and c["fecha_fin_real"] is None
            and c["fecha_fin_prevista"] is not None and c["fecha_fin_prevista"] < hoy)


def _resumen(c: dict[str, Any], hoy: dt.date) -> dict[str, Any]:
    return {"id": c["id"], "contrato_id": c["id"], "nombre": c["nombre"], "tipo": TIPO_PRODUCTO.get(c["tipo_contrato"], c["tipo_contrato"]),
            "habitacion": c["habitacion"], "estado_documental": c["estado_documental"],
            "situacion": situacion(c, hoy), "fecha_inicio": c["fecha_inicio"],
            "fecha_fin_prevista": c["fecha_fin_prevista"], "fecha_fin_real": c["fecha_fin_real"],
            "fin_previsto_vencido": fin_previsto_vencido(c, hoy), "row_version": c["row_version"],
            "renta_registrada": c["regla_renta_id"] is not None,
            "marca_renta": MARCA_RENTA_V3 if c["regla_renta_id"] is not None else None}


def ocupacion(contratos: list[dict[str, Any]], habitaciones: int | None, hoy: dt.date) -> list[dict[str, Any]]:
    """Por habitacion 1..N: OCUPADA (FORMALIZADO vigente hoy, de esa habitacion o de vivienda completa),
    PROXIMA (FORMALIZADO que empieza despues de hoy) o LIBRE. Un borrador y un cancelado no ocupan."""
    filas = []
    for n in range(1, (habitaciones or 0) + 1):
        propios = [c for c in contratos if c["estado_documental"] == "FORMALIZADO"
                   and (c["tipo_contrato"] == m.TIPO_VIVIENDA or (c["tipo_contrato"] == m.TIPO_HABITACION
                                                                   and c["habitacion"] == n))]
        vigentes = [c for c in propios if situacion(c, hoy) == "VIGENTE"]
        proximos = sorted((c for c in propios if situacion(c, hoy) == "PROXIMO"),
                          key=lambda c: (c["fecha_inicio"], str(c["id"])))
        if vigentes:
            estado, contrato = "OCUPADA", vigentes[0]
        elif proximos:
            estado, contrato = "PROXIMA", proximos[0]
        else:
            estado, contrato = "LIBRE", None
        filas.append({"habitacion": n, "estado": estado, "contrato_id": None if contrato is None else contrato["id"],
                      "desde": None if contrato is None else contrato["fecha_inicio"],
                      "hasta": None if contrato is None else (contrato["fecha_fin_real"] or contrato["fecha_fin_prevista"])})
    return filas


# ------------------------------------------------------------------ L-CON-01
def contratos_de_propiedad(sesion: SesionMotor, propiedad_id: uuid.UUID, hoy: dt.date) -> dict[str, Any] | None:
    ficha = repo_prop.leer(sesion, propiedad_id)
    if ficha is None:
        return None
    todos = repo.contratos_de_propiedad(sesion, propiedad_id)
    grupos: dict[str, list] = {"vigentes": [], "proximos": [], "borradores": [], "finalizados": [], "cancelados": []}
    destino = {"VIGENTE": "vigentes", "PROXIMO": "proximos", "BORRADOR": "borradores", "FINALIZADO": "finalizados",
               "CANCELADO": "cancelados"}
    principales = _inquilinos_principales(sesion, propiedad_id)
    planas = []
    for c in todos:
        fila = {**_resumen(c, hoy), "inquilino_principal": principales.get(c["id"])}
        grupos[destino[situacion(c, hoy)]].append(fila)
        planas.append(fila)
    # `contratos` (lista plana) y `habitaciones_ficha` son la forma del cliente; los grupos son un superconjunto
    return {"propiedad_id": propiedad_id, "habitaciones": ficha["habitaciones"],
            "habitaciones_ficha": ficha["habitaciones"], "hoy": hoy, "contratos": planas, **grupos,
            "ocupacion": ocupacion(todos, ficha["habitaciones"], hoy)}


def _inquilinos_principales(sesion: SesionMotor, propiedad_id: uuid.UUID) -> dict[uuid.UUID, str | None]:
    """Nombre del INQUILINO principal de cada contrato de la propiedad (una consulta; YO nunca es inquilino)."""
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT ON (cp.contrato_entidad_id) cp.contrato_entidad_id, t.nombre "
            "FROM gapto.contrato_participantes cp JOIN gapto.contratos c ON c.entidad_id = cp.contrato_entidad_id "
            "JOIN gapto.actores_financieros a ON a.id = cp.actor_id LEFT JOIN gapto.terceros t ON t.id = a.tercero_id "
            "WHERE c.propiedad_entidad_id = %s AND cp.rol = 'INQUILINO' AND cp.principal "
            "ORDER BY cp.contrato_entidad_id, cp.vigente_hasta NULLS FIRST, cp.vigente_desde DESC, cp.id",
            (propiedad_id,))
        return {f[0]: f[1] for f in cur.fetchall()}


# ------------------------------------------------------------------ L-CON-02
def _modo_tratamiento(t: dict[str, Any]) -> str:
    if t["incluido_en_renta"]:
        return "INCLUIDO"
    if t["repercutible"]:
        return "POR_FACTURA" if t["modo_reparto"] == "POR_FACTURA" else "REPERCUTIDO_FIJO"
    return "NO_REPERCUTIDO"


def tratamiento_vista(t: dict[str, Any]) -> dict[str, Any]:
    modo = _modo_tratamiento(t)
    return {"id": t["id"], "servicio_id": t["servicio_id"], "modo": modo, "modo_reparto": t["modo_reparto"],
            "actor_repercusion_id": t["actor_repercusion_id"], "porcentaje": t["porcentaje_repercutible"],
            "texto": TEXTO_POR_FACTURA if modo == "POR_FACTURA" else None,
            "vigente_desde": t["vigente_desde"], "vigente_hasta": t["vigente_hasta"]}


def detalle_contrato(sesion: SesionMotor, contrato_id: uuid.UUID, hoy: dt.date) -> dict[str, Any] | None:
    c = repo.contrato(sesion, contrato_id)
    if c is None:
        return None
    c = {"id": contrato_id, **c}
    renta = c["regla_renta_id"] is not None
    vigente = c["estado_documental"] == "FORMALIZADO" and c["fecha_fin_real"] is None
    if renta:
        terminable, motivo = False, e.RENTA_PENDIENTE
    else:
        terminable, motivo = vigente, None if vigente else e.CONTRATO_NO_VIGENTE
    personas = [{**p, "vigente": p["vigente_hasta"] is None or p["vigente_hasta"] >= hoy}
                for p in repo.participantes(sesion, contrato_id)]
    clausulas = repo.clausulas(sesion, contrato_id)
    abierta = next((v for v in reversed(clausulas) if v["vigente_hasta"] is None), None)
    propiedad = repo_prop.leer(sesion, c["propiedad_id"])
    trats = repo.tratamientos(sesion, contrato_id)
    nombres = _nombres_servicios(sesion, [t["servicio_id"] for t in trats])
    actores = {p["actor_id"]: p["nombre"] for p in personas}
    for p in personas:   # forma del cliente: persona_id y actor {yo, tercero_id, nombre}
        p["persona_id"] = p["id"]
        p["actor"] = {"yo": p["tercero_id"] is None, "tercero_id": p["tercero_id"], "nombre": p["nombre"]}
    clausula = None if abierta is None else {**abierta, "version_id": abierta["id"], "tipo": abierta["tipo_revision"]}
    servicios = [{**tratamiento_vista(t), **nombres.get(t["servicio_id"], {}),
                  "actor_nombre": actores.get(t["actor_repercusion_id"])} for t in trats]
    return {**_resumen(c, hoy), "propiedad_id": c["propiedad_id"],
            "propiedad_nombre": None if propiedad is None else propiedad["nombre"], "notas": c["notas"],
            "terminable": {"terminable": terminable, "motivo": motivo},
            "personas": personas, "clausula": clausula, "clausulas": clausulas, "servicios": servicios}


def _nombres_servicios(sesion: SesionMotor, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    salida: dict[uuid.UUID, dict[str, Any]] = {}
    for sid in set(ids):
        s = repo.servicio(sesion, sid)
        if s is not None:
            salida[sid] = {"servicio_nombre": s["nombre"], "tipo_servicio": s["tipo_servicio"]}
    return salida


# ------------------------------------------------------------------ L-CON-03
def _iniciales(nombre: str | None) -> str:
    palabras = [p for p in (nombre or "").split() if p]
    if not palabras:
        return ""
    return (palabras[0][0] + (palabras[-1][0] if len(palabras) > 1 else "")).upper()


def propuesta(sesion: SesionMotor, propiedad_id: uuid.UUID, *, tipo: str, habitacion: int | None,
              inicio: dt.date | None, inquilino_id: uuid.UUID | None, hoy: dt.date) -> dict[str, Any] | None:
    """Propuesta (nunca escribe ni bloquea). Arrendadores = titulares vigentes en `inicio` (vacia con titularidad
    DESCONOCIDA). Nombre `AA-HABn-II` / `AA-VIV-II` / `AA-OTRO-II`; con «-2», «-3»… si ya existe."""
    ficha = repo_prop.leer(sesion, propiedad_id)
    if ficha is None or tipo not in m.TIPOS_CONTRATO:
        return None
    fecha = inicio or hoy
    arrendadores = [{"actor_id": f["actor_id"], "tercero_id": f["tercero_id"], "yo": f["tercero_id"] is None,
                     "nombre": f["nombre"]}
                    for f in repo_prop.participaciones(sesion, propiedad_id)
                    if f["vigente_desde"] <= fecha and (f["vigente_hasta"] is None or f["vigente_hasta"] >= fecha)]
    todos = repo.contratos_de_propiedad(sesion, propiedad_id)
    inquilino = repo.tercero_con_hijas(sesion, inquilino_id) if inquilino_id is not None else None
    etiqueta = {"VIVIENDA_COMPLETA": "VIV", "OTRO": "OTRO"}.get(tipo, f"HAB{habitacion}" if habitacion else "HAB")
    base = "-".join(p for p in (f"{fecha.year % 100:02d}", etiqueta, _iniciales(None if inquilino is None
                                                                               else inquilino["nombre"])) if p)
    existentes = {c["nombre"] for c in todos}
    nombre, n = base, 1
    while nombre in existentes:
        n += 1
        nombre = f"{base}-{n}"
    return {"arrendadores": arrendadores, "habitaciones": ocupacion(todos, ficha["habitaciones"], hoy),
            "nombre_propuesto": nombre}


# ------------------------------------------------------------------ L-SRV-01
def servicios_de_propiedad(sesion: SesionMotor, propiedad_id: uuid.UUID, hoy: dt.date) -> dict[str, Any] | None:
    if repo_prop.leer(sesion, propiedad_id) is None:
        return None
    contratos = [c for c in repo.contratos_de_propiedad(sesion, propiedad_id) if c["estado_documental"] != "CANCELADO"]
    with sesion.conexion.cursor() as cur:  # una sola consulta para todos los tratamientos (sin N+1)
        cur.execute(
            "SELECT s.contrato_entidad_id, s.servicio_entidad_id, s.incluido_en_renta, s.repercutible, "
            "s.modo_reparto, s.actor_repercusion_id, s.porcentaje_repercutible, s.vigente_desde, s.vigente_hasta, "
            "s.id FROM gapto.contrato_servicios s JOIN gapto.contratos c ON c.entidad_id = s.contrato_entidad_id "
            "WHERE c.propiedad_entidad_id = %s AND s.vigente_desde <= %s "
            "AND (s.vigente_hasta IS NULL OR s.vigente_hasta >= %s)", (propiedad_id, hoy, hoy))
        filas = cur.fetchall()
    trat = [dict(zip(("contrato_id", "servicio_id", "incluido_en_renta", "repercutible", "modo_reparto",
                      "actor_repercusion_id", "porcentaje_repercutible", "vigente_desde", "vigente_hasta", "id"), f))
            for f in filas]
    vigentes = {c["id"]: c for c in contratos if situacion(c, hoy) == "VIGENTE"}
    servicios: dict[uuid.UUID, dict[str, Any]] = {}
    for s in repo.servicios_de_propiedad(sesion, propiedad_id):
        ficha = servicios.setdefault(s["id"], {
            "id": s["id"], "nombre": s["nombre"], "tipo_servicio": s["tipo_servicio"],
            "categoria_default_id": s["categoria_default_id"], "row_version": s["row_version"],
            "fecha_inicio": s["fecha_inicio"], "fecha_fin_real": s["fecha_fin_real"], "vinculos": [],
            "tratamientos": []})
        ficha["vinculos"].append({"id": s["vinculo_id"], "desde": s["vinculo_desde"], "hasta": s["vinculo_hasta"],
                                  "vigente": s["vinculo_desde"] <= hoy and (s["vinculo_hasta"] is None
                                                                            or s["vinculo_hasta"] >= hoy)})
    for t in trat:
        if t["servicio_id"] in servicios and t["contrato_id"] in vigentes:
            servicios[t["servicio_id"]]["tratamientos"].append(
                {"contrato_id": t["contrato_id"], "contrato_nombre": vigentes[t["contrato_id"]]["nombre"],
                 **tratamiento_vista({**t, "servicio_id": t["servicio_id"]})})
    for ficha in servicios.values():
        ficha["vigente"] = any(v["vigente"] for v in ficha["vinculos"]) and ficha["fecha_fin_real"] is None
    ordenados = sorted(servicios.values(), key=lambda f: (not f["vigente"], f["nombre"], str(f["id"])))
    for f in ordenados:   # forma del cliente (ServicioPropiedad)
        f["servicio_id"] = f["id"]
        f["desde"] = min((v["desde"] for v in f["vinculos"]), default=f["fecha_inicio"])
        f["hasta"] = f["fecha_fin_real"]
        f["categoria_default_nombre"] = None
        f["compania_ultimos_pagos"] = None   # D5: informativo; no se deriva en este bloque (sin datos inventados)
    return {"propiedad_id": propiedad_id, "servicios": ordenados,
            "vigentes": [f for f in ordenados if f["vigente"]], "anteriores": [f for f in ordenados if not f["vigente"]]}


# ------------------------------------------------------------------ L-TER-01
def tercero_detalle(sesion: SesionMotor, tercero_id: uuid.UUID) -> dict[str, Any] | None:
    t = repo.tercero_con_hijas(sesion, tercero_id)
    if t is None:
        return None
    with sesion.conexion.cursor() as cur:
        cur.execute(
            "SELECT c.entidad_id, ce.nombre, cp.rol, cp.vigente_desde, cp.vigente_hasta, c.estado_documental, "
            "c.fecha_inicio, c.propiedad_entidad_id FROM gapto.actores_financieros a "
            "JOIN gapto.contrato_participantes cp ON cp.actor_id = a.id "
            "JOIN gapto.contratos c ON c.entidad_id = cp.contrato_entidad_id "
            "JOIN gapto.entidades ce ON ce.id = c.entidad_id "
            f"WHERE a.tercero_id = %s AND a.owner_user_id = {repo.OWNER} AND ce.owner_user_id = {repo.OWNER} "
            "ORDER BY c.fecha_inicio DESC NULLS LAST, c.entidad_id DESC, cp.vigente_desde DESC, cp.id DESC",
            (tercero_id,))
        usos = [dict(zip(("contrato_id", "contrato_nombre", "rol", "vigente_desde", "vigente_hasta",
                          "estado_documental", "fecha_inicio", "propiedad_id"), f)) for f in cur.fetchall()]
    return {"tercero": t, "roles": repo.roles_de_tercero(sesion, tercero_id),
            "clasificaciones": repo.clasificaciones_de_tercero(sesion, tercero_id),
            "uso": [{"contrato_id": u["contrato_id"], "contrato_nombre": u["contrato_nombre"], "rol": u["rol"],
                     "desde": u["vigente_desde"], "hasta": u["vigente_hasta"]} for u in usos],
            "uso_en_gapto": usos}


# ------------------------------------------------------------------ V-bis
_SELECTOR = (
    "SELECT t.id, t.nombre, t.naturaleza, t.row_version, "
    "(SELECT max(h.fecha_hecho) FROM gapto.hecho_terceros ht JOIN gapto.hechos_financieros h ON h.id = ht.hecho_id "
    " WHERE ht.tercero_id = t.id AND h.estado = 'ACTIVO') AS ultimo_hecho, "
    "u.contrato_id, u.contrato_nombre, u.rol, u.fecha_inicio, u.vigente_hasta "
    "FROM gapto.terceros t LEFT JOIN LATERAL ("
    " SELECT c.entidad_id AS contrato_id, ce.nombre AS contrato_nombre, cp.rol, cp.vigente_desde AS fecha_inicio, "
    " cp.vigente_hasta "
    " FROM gapto.actores_financieros a JOIN gapto.contrato_participantes cp ON cp.actor_id = a.id "
    " JOIN gapto.contratos c ON c.entidad_id = cp.contrato_entidad_id JOIN gapto.entidades ce ON ce.id = c.entidad_id "
    f" WHERE a.tercero_id = t.id AND a.owner_user_id = {repo.OWNER} AND ce.owner_user_id = {repo.OWNER} "
    " AND c.estado_documental <> 'CANCELADO' "
    " ORDER BY c.fecha_inicio DESC NULLS LAST, c.entidad_id DESC, cp.vigente_desde DESC, cp.id DESC LIMIT 1"
    ") u ON true "
    f"WHERE t.owner_user_id = {repo.OWNER} AND t.enabled"
)
LIMITE_SELECTOR = 50


def selector_asistente(sesion: SesionMotor, texto: str | None) -> list[dict[str, Any]]:
    """V-bis: terceros ACTIVOS del owner con naturaleza y `uso` derivado, en UNA consulta. Uso = contrato mas
    reciente en el que participa (desempates por contrato y vigencia) o, sin contratos, la fecha de su ultimo
    hecho ACTIVO; si no hay nada, None («sin uso»). `homonimo` = hay otro activo con el mismo nombre
    normalizado (C06). El selector solo lista activos: los inactivos van por el circuito de candidatos (V-ter)."""
    with sesion.conexion.cursor() as cur:
        cur.execute(_SELECTOR)
        filas = [dict(zip(("id", "nombre", "naturaleza", "row_version", "ultimo_hecho", "contrato_id",
                           "contrato_nombre", "rol", "fecha_inicio", "vigente_hasta"), f)) for f in cur.fetchall()]
    claves = [normalizar(f["nombre"]) for f in filas]
    repetidos = {k for k in claves if claves.count(k) > 1}
    salida = []
    for f, clave in zip(filas, claves):
        if f["contrato_id"] is not None:
            uso: dict[str, Any] = {"tipo": "CONTRATO", "contrato_id": f["contrato_id"],
                                   "contrato_nombre": f["contrato_nombre"], "rol": f["rol"],
                                   "desde": f["fecha_inicio"], "hasta": f["vigente_hasta"]}
        elif f["ultimo_hecho"] is not None:
            uso = {"tipo": "MOVIMIENTO", "fecha": f["ultimo_hecho"]}
        else:
            uso = {"tipo": "SIN_USO"}
        salida.append({"id": f["id"], "nombre": f["nombre"], "naturaleza": f["naturaleza"],
                       "row_version": f["row_version"], "homonimo": clave in repetidos, "uso": uso,
                       "_clave": clave})
    if texto and texto.strip():
        q = normalizar(texto)
        salida = [s for s in salida if q in s["_clave"]]
    salida.sort(key=lambda s: (s["_clave"], str(s["id"])))
    for s in salida:
        del s["_clave"]
    return salida[:LIMITE_SELECTOR]
