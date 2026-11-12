# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_212_f05_gate_g9_rol_real.py
# Ruta: tests/api/test_212_f05_gate_g9_rol_real.py
# Descripcion: F05-GATE G9 (F05 §49.16.2; F05-D050 §64.7): seguridad con el
#   ROL REAL de aplicacion (el adaptador ejecuta como gapto_runtime con la GUC
#   de owner; aqui nunca como superusuario salvo para leer la huella).
#     - Inventario: todas las rutas /v1/* de la app se recorren desde la propia
#       app (FastAPI), no desde una lista escrita a mano.
#     - Aislamiento: el owner B tiene un recurso REAL de cada tipo que aparece
#       como parametro de ruta (categoria, asociacion, magnitud, preferencia,
#       cuenta, tercero, contexto, plantilla, acceso, hecho, devolucion,
#       posicion, transferencia, prevision, afinidad). El owner A llama a CADA
#       ruta con parametros usando los IDs de B y un cuerpo valido generado del
#       DTO de la ruta (cuentas del cuerpo = las de A). Oraculo: ningun 2xx que
#       devuelva datos de B (un 2xx de escritura solo si es identico al de un
#       ID inexistente: idempotente sin oraculo de existencia), y la huella fisica de TODO el schema gapto
#       (md5 por tabla, filas completas) identica antes y despues: ni efectos
#       en B ni efectos colaterales en A.
#     - Permitido: las mismas rutas de lectura con los IDs propios de B, desde
#       el cliente de B, responden 200 (el rol real puede leer lo suyo).
#     - Ninguna funcion SECURITY DEFINER salvo el sumidero de auditoria
#       (fn_registrar_auditoria, gapto_internal, F03) y ningun SET ROLE en el
#       backend distinto del rol runtime de la UdT.
#   El detalle por ruta se escribe en $G9_SALIDA (si esta definida).
# Version: 0.1.0 (F05-07/GATE tirada nocturna, paso 8)
# Version: 0.2.0 (F06-01 B1, lote 12): el owner B tiene tambien una propiedad
#   real (parametro `propiedad_id` de las rutas nuevas de B1) y el
#   aislamiento por cuerpo gana el cotitular de otro owner en el alta de una
#   propiedad.
# Version: 0.3.0 (F06 T1-F06 B3 N1; adaptacion declarada y minima por la regla v2 de T1-F06, decision de Moises del
#   2026-11-12 `5b54258a…`, mandato B3 N1 §5.1): para admitir las rutas de B3 con parametros (lista cerrada), el
#   owner B tiene tambien un gasto REAL de su propiedad (C-MEJ-01) que sustituye a `hecho_id` en las rutas
#   /v1/propiedades/{propiedad_id}/gastos/..., y CONSULTA gana los parametros obligatorios de dos lecturas
#   (propuesta-gasto: fecha; impacto-correccion: clase_nueva). El oraculo, las rutas recorridas (todas, desde la
#   propia app) y las demas sustituciones no cambian.
# ============================================================

from __future__ import annotations

import datetime as dt
import decimal
import enum
import json
import os
import pathlib
import re
import types
import typing
import uuid

import psycopg
import pytest
from pydantic import BaseModel

import f05_05_helpers as x5
import f05_06_m2_helpers as m2
import f05_06_m3_helpers as m3
import f05_06_m5_helpers as m5
import vs01_api_helpers as h

RAIZ = pathlib.Path(__file__).resolve().parents[2]


def huella() -> dict[str, str]:
    """md5 de las filas completas de cada tabla del schema gapto (superusuario: SOLO lectura)."""
    with psycopg.connect(h.dsn()) as c:
        tablas = [t for (t,) in c.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'gapto' ORDER BY 1")]
        sql = " UNION ALL ".join(
            f"SELECT '{t}', coalesce(md5(string_agg(x::text, '|' ORDER BY x::text)), '') FROM gapto.{t} x" for t in tablas)
        return dict(c.execute(sql).fetchall())


def _valor(anotacion, nombre: str, cuenta_a: uuid.UUID):
    origen, args = typing.get_origin(anotacion), typing.get_args(anotacion)
    if origen is typing.Annotated:
        return _valor(args[0], nombre, cuenta_a)
    if origen in (typing.Union, types.UnionType):
        no_none = [a for a in args if a is not type(None)]
        return _valor(no_none[0], nombre, cuenta_a) if no_none else None
    if origen is typing.Literal:
        return args[0]
    if origen in (list, tuple, set):
        return [_valor(args[0], nombre, cuenta_a)] if args else []
    if origen is dict:
        return {}
    if isinstance(anotacion, type) and issubclass(anotacion, BaseModel):
        return fabricar(anotacion, cuenta_a)
    if isinstance(anotacion, type) and issubclass(anotacion, enum.Enum):
        return list(anotacion)[0].value
    if anotacion is uuid.UUID:
        return str(cuenta_a) if "cuenta" in nombre else str(uuid.uuid4())
    if anotacion is bool:
        return True
    if anotacion is int:
        return 1
    if anotacion in (decimal.Decimal, float):
        return "1.00"
    if anotacion is dt.date:
        return "2026-10-10"
    if anotacion is str:
        return "1.00" if "importe" in nombre else "Motivo G9"
    return None


def fabricar(modelo: type[BaseModel], cuenta_a: uuid.UUID) -> dict:
    """Cuerpo con TODOS los campos del DTO (obligatorios y opcionales) con valores plausibles."""
    return {n: _valor(f.annotation, n, cuenta_a) for n, f in modelo.model_fields.items()}


def _modelo_cuerpo(ruta) -> type[BaseModel] | None:
    for p in ruta.dependant.body_params:
        anot = getattr(p, "type_", None) or getattr(getattr(p, "field_info", None), "annotation", None)
        if isinstance(anot, type) and issubclass(anot, BaseModel):
            return anot
    return None


@pytest.fixture()
def b():
    """Owner B con un recurso real de cada tipo de parametro de ruta."""
    owner, actor, cli, cta, ahorro = m3.entorno()
    tercero = x5.tercero(cli, "ALDI de B")
    tania, carlos = m3.persona(cli, "Tania de B"), m3.persona(cli, "Carlos de B")
    categoria = x5.categoria(owner, "Categoría de B")
    mid, aid = uuid.uuid4(), uuid.uuid4()
    h.como_owner(owner, "INSERT INTO gapto.magnitudes (id, owner_user_id, nombre, unidad_default, precision_decimales) "
                        "VALUES (%s, %s, 'Litros de B', 'l', 2)", (mid, owner))
    h.como_owner(owner, "INSERT INTO gapto.categoria_magnitudes (id, categoria_id, magnitud_id, obligatoria, orden) "
                        "VALUES (%s, %s, %s, false, 0)", (aid, categoria, mid))
    tipos = cli.get("/v1/preferencias", headers=h.AUTH).json()["tipos"]
    pref, plt, acc, afi = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for ruta, cuerpo in (("/v1/preferencias", {"id": str(pref), "tipo_hecho_id": tipos["GASTO"], "cuenta_default_id": str(cta)}),
                         ("/v1/plantillas", {"id": str(plt), "nombre": "Plantilla de B", "tipo_hecho_id": tipos["GASTO"],
                                             "cuenta_default_id": str(cta)}),
                         ("/v1/acciones-rapidas", {"id": str(acc), "plantilla_registro_id": str(plt), "nombre": "Acceso B"}),
                         ("/v1/afinidades", {"id": str(afi), "tercero_id": str(tercero), "categoria_id": str(categoria)})):
        r = cli.post(ruta, json=cuerpo, headers=h.AUTH)
        assert r.status_code == 200, (ruta, r.text)
    contexto = x5.contexto(cli, "Contexto de B")
    gasto = m2.compra(cli, cta, categoria_id=categoria)
    _, r = m2.devolver(cli, gasto)
    assert r.status_code == 200, r.text
    devolucion = uuid.UUID(r.json()["hecho_id"])
    c, r = m3.cena(cli, cta, tania, carlos)
    assert r.status_code == 200, r.text
    cena = uuid.UUID(c["intencion_id"])
    posicion = m3.entidad_de_posicion(owner, cena)
    transf = x5.transferencia(cli, cta, ahorro)
    prevision = m5.prevision(owner, "Luz de B")
    propiedad = uuid.uuid4()
    r = cli.post("/v1/propiedades", json={"intencion_id": str(propiedad), "nombre": "Piso de B", "tipo_propiedad": "VIVIENDA",
                                          "titularidad": {"modo": "SOLO_MIA", "desde": "2026-01-01"}}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    gasto_propiedad = uuid.uuid4()
    yo = r.json()["propiedad"]["titularidad"]["partes"][0]["actor_id"]
    r = cli.post("/v1/intenciones/gasto-propiedad", json={
        "intencion_id": str(gasto_propiedad), "propiedad_id": str(propiedad), "clase": "MEJORA", "importe": "100.00",
        "fecha_hecho": "2026-05-15", "cuenta_id": str(cta), "deuda": [], "derechos_confirmados": [],
        "atribucion": {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": {
            "criterio": "TITULARIDAD_EN_FECHA_HECHO", "fecha_referencia": "2026-05-15",
            "partes": [{"actor_id": yo, "porcentaje": "100.0000"}]}}}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    ids = {"categoria_id": categoria, "asociacion_id": aid, "magnitud_id": mid, "preferencia_id": pref, "cuenta_id": cta,
           "capacidad": "PAGAR_GASTO", "tercero_id": tercero, "contexto_id": contexto, "plantilla_id": plt,
           "accion_id": acc, "origen_id": gasto, "devolucion_id": devolucion, "entidad_id": posicion, "hecho_id": gasto,
           "prevision_id": prevision, "afinidad_id": afi, "propiedad_id": propiedad,
           "gasto_propiedad": gasto_propiedad}
    return {"owner": owner, "cli": cli, "ids": ids, "cena": cena, "transferencia": transf, "tania": tania}


#: Parametros de consulta obligatorios de algunas lecturas (sin ellos la respuesta seria un 422 de validacion).
CONSULTA = {"/v1/terceros/{tercero_id}/afinidades": "?fecha=2026-10-10",
            "/v1/propiedades/{propiedad_id}/propuesta-gasto": "?fecha=2026-10-10",
            "/v1/propiedades/{propiedad_id}/gastos/{hecho_id}/impacto-correccion": "?clase_nueva=REPARACION"}
#: Cuerpos validos explicitos donde el DTO es una union discriminada (el generado no pasaria la validacion).
CUERPOS = {("POST", "/v1/categorias/{categoria_id}/magnitudes"): lambda: {
    "origen": "NUEVA", "obligatoria": False, "magnitud": {"magnitud_id": str(uuid.uuid4()), "nombre": "Kilos G9",
                                                          "unidad_default": "kg", "precision_decimales": 2}}}


def _ruta_con_ids(path: str, ids: dict, cena, transf) -> str:
    def sustituir(m):
        nombre = m.group(1)
        if nombre == "hecho_id" and "/reparto" in path:
            return str(cena)
        if nombre == "hecho_id" and path.startswith("/v1/transferencias/"):
            return str(transf)
        if nombre == "hecho_id" and path.startswith("/v1/propiedades/") and "/gastos/" in path:
            return str(ids["gasto_propiedad"])
        return str(ids[nombre])
    return re.sub(r"\{(\w+)\}", sustituir, path) + CONSULTA.get(path, "")


def _rutas_con_parametros(app):
    for r in app.routes:
        path = getattr(r, "path", "")
        if path.startswith("/v1/") and "{" in path:
            for metodo in sorted(getattr(r, "methods", set()) - {"HEAD"}):
                yield metodo, path, r


def test_g9_ids_de_otro_owner_rechazados_sin_efectos(b):
    owner_a, actor_a = h.crear_tenant()
    cuenta_a = h.crear_cuenta(owner_a, [(actor_a, 100)])
    cli_a = h.cliente(owner_a)
    textos_b = {str(v) for k, v in b["ids"].items() if k != "capacidad"} | {str(b["cena"]), str(b["transferencia"])}
    detalle, fallos = [], []
    rutas = list(_rutas_con_parametros(cli_a.app))
    assert len(rutas) >= 50, len(rutas)
    for metodo, path, ruta in rutas:
        url = _ruta_con_ids(path, b["ids"], b["cena"], b["transferencia"])
        modelo = _modelo_cuerpo(ruta)
        cuerpo = CUERPOS[(metodo, path)]() if (metodo, path) in CUERPOS else fabricar(modelo, cuenta_a) if modelo else None
        antes = huella()
        r = cli_a.request(metodo, url, json=cuerpo, headers=h.AUTH)
        despues = huella()
        cambiadas = sorted(t for t in antes if antes[t] != despues.get(t))
        try:
            datos = r.json()
        except Exception:  # noqa: BLE001
            datos = None
        fuga = sorted(t for t in textos_b if t in json.dumps(datos)) if r.status_code < 300 else []
        indistinguible = None
        if r.status_code < 300 and metodo != "GET":
            # Solo se admite un 2xx de escritura si es IDENTICO al de un ID inexistente (sin oraculo de existencia).
            ajeno = re.sub(r"\{(\w+)\}", lambda m: "PAGAR_GASTO" if m.group(1) == "capacidad" else str(uuid.uuid4()), path) + CONSULTA.get(path, "")
            r2 = cli_a.request(metodo, ajeno, json=cuerpo, headers=h.AUTH)
            indistinguible = r2.status_code == r.status_code and r2.json() == datos
        fila = {"metodo": metodo, "ruta": path, "status": r.status_code, "indistinguible_de_inexistente": indistinguible,
                "codigo": (datos or {}).get("codigo") if isinstance(datos, dict) else None,
                "cuerpo_generado": modelo.__name__ if modelo else None, "tablas_cambiadas": cambiadas, "ids_de_B_en_respuesta": fuga}
        detalle.append(fila)
        if cambiadas or fuga or indistinguible is False:
            fallos.append(fila)
    salida = os.environ.get("G9_SALIDA")
    if salida:
        pathlib.Path(salida).mkdir(parents=True, exist_ok=True)
        pathlib.Path(salida, "g9_aislamiento.json").write_text(json.dumps(detalle, ensure_ascii=False, indent=1), encoding="utf-8")
    assert fallos == [], json.dumps(fallos, ensure_ascii=False, indent=1)


def test_g9_permitido_el_dueno_lee_lo_suyo(b):
    """Contraprueba: las lecturas con parametros, con los IDs de B desde el cliente de B, responden 200 o una
    respuesta de dominio (nunca 401/403/500): el rol real puede leer lo suyo con RLS."""
    detalle = []
    for metodo, path, _ in _rutas_con_parametros(b["cli"].app):
        if metodo != "GET":
            continue
        url = _ruta_con_ids(path, b["ids"], b["cena"], b["transferencia"])
        r = b["cli"].get(url, headers=h.AUTH)
        detalle.append({"ruta": path, "status": r.status_code})
    salida = os.environ.get("G9_SALIDA")
    if salida:
        pathlib.Path(salida, "g9_permitido.json").write_text(json.dumps(detalle, ensure_ascii=False, indent=1), encoding="utf-8")
    assert all(d["status"] == 200 for d in detalle), detalle


def test_g9_sin_security_definer_ni_rol_privilegiado():
    with psycopg.connect(h.dsn()) as c:
        definer = c.execute("SELECT p.proname, pg_get_userbyid(p.proowner) FROM pg_proc p JOIN pg_namespace n ON "
                            "n.oid = p.pronamespace WHERE p.prosecdef AND n.nspname = 'gapto' ORDER BY 1").fetchall()
    assert definer == [("fn_registrar_auditoria", "gapto_internal")], definer
    cambios_de_rol = []
    for f in (RAIZ / "backend" / "app").rglob("*.py"):
        for n, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            codigo = linea.split("#", 1)[0]
            if re.search(r"execute\(.*SET\s+(LOCAL\s+)?ROLE", codigo, re.I):
                cambios_de_rol.append(f"{f.relative_to(RAIZ)}:{n}:{codigo.strip()}")
    assert cambios_de_rol == ['backend\\app\\core\\unidad_trabajo.py:231:cursor.execute(f"SET LOCAL ROLE {self._rol_runtime}")'] or \
        cambios_de_rol == ['backend/app/core/unidad_trabajo.py:231:cursor.execute(f"SET LOCAL ROLE {self._rol_runtime}")'], cambios_de_rol



def _casos_cuerpo(a: dict, b: dict) -> list[tuple[str, str, dict, dict]]:
    """(descripcion, ruta, cuerpo de CONTROL con recursos de A, cuerpo con UN recurso de B). Mismo cuerpo salvo ese ID."""
    ia, ib = a["ids"], b["ids"]
    tipo = a["tipos"]["GASTO"]
    u = lambda: str(uuid.uuid4())  # noqa: E731

    def par(desc, ruta, f, clave):
        return (desc, ruta, f(ia), f({**ia, clave: ib[clave]}))

    def gasto(x, campo):
        c = h.intencion(x["cuenta_id"], intencion_id=u(), fecha_hecho="2026-10-05", importe="10.00")
        if campo == "categoria_id":
            c["categoria"] = {"estado": "CATEGORIA", "categoria_id": str(x["categoria_id"])}
        if campo in ("tercero_id", "contexto_id"):
            c[campo] = str(x[campo])
        return c

    def ingreso(x, campo):
        c = {"intencion_id": u(), "importe": "100.00", "moneda": "EUR", "fecha_hecho": "2026-10-05",
             "cuenta_id": str(x["cuenta_id"]), "presupuestable": True, "atribucion": "SOLO_MIO",
             "categoria": {"estado": "SIN_CATEGORIA"}, "nota": None}
        if campo == "tercero_id":
            c["tercero_id"] = str(x["tercero_id"])
        return c

    return [
        par("categoría hija bajo un padre", "/v1/categorias",
            lambda x: {"id": u(), "nombre": "Hija G9", "parent_id": str(x["categoria_id"]), "ambito": "GASTO",
                       "presupuestable_default": True, "icon_key": None}, "categoria_id"),
        par("preferencia con cuenta", "/v1/preferencias",
            lambda x: {"id": u(), "tipo_hecho_id": tipo, "cuenta_default_id": str(x["cuenta_id"])}, "cuenta_id"),
        par("preferencia con tercero", "/v1/preferencias",
            lambda x: {"id": u(), "tipo_hecho_id": tipo, "tercero_id": str(x["tercero_id"]),
                       "cuenta_default_id": str(ia["cuenta_id"])}, "tercero_id"),
        par("plantilla con categoría", "/v1/plantillas",
            lambda x: {"id": u(), "nombre": f"Plantilla G9 {u()[:8]}", "tipo_hecho_id": tipo, "categoria_id": str(x["categoria_id"])},
            "categoria_id"),
        par("plantilla con cuenta", "/v1/plantillas",
            lambda x: {"id": u(), "nombre": f"Plantilla G9 {u()[:8]}", "tipo_hecho_id": tipo, "cuenta_default_id": str(x["cuenta_id"])},
            "cuenta_id"),
        par("acceso de una plantilla", "/v1/acciones-rapidas",
            lambda x: {"id": u(), "plantilla_registro_id": str(x["plantilla_id"]), "nombre": "Acceso G9"}, "plantilla_id"),
        par("afinidad con tercero", "/v1/afinidades",
            lambda x: {"id": u(), "tercero_id": str(x["tercero_id"]), "categoria_id": str(ia["categoria_id"])}, "tercero_id"),
        par("afinidad con categoría", "/v1/afinidades",
            lambda x: {"id": u(), "tercero_id": str(ia["tercero_id"]), "categoria_id": str(x["categoria_id"])}, "categoria_id"),
        par("gasto pagado con cuenta", "/v1/intenciones/gasto-pagado", lambda x: gasto(x, "cuenta_id"), "cuenta_id"),
        par("gasto pagado con categoría", "/v1/intenciones/gasto-pagado", lambda x: gasto(x, "categoria_id"), "categoria_id"),
        par("gasto pagado con tercero", "/v1/intenciones/gasto-pagado", lambda x: gasto(x, "tercero_id"), "tercero_id"),
        par("gasto pagado con contexto", "/v1/intenciones/gasto-pagado", lambda x: gasto(x, "contexto_id"), "contexto_id"),
        par("ingreso con cuenta", "/v1/intenciones/ingreso-cobrado", lambda x: ingreso(x, "cuenta_id"), "cuenta_id"),
        par("ingreso con tercero", "/v1/intenciones/ingreso-cobrado", lambda x: ingreso(x, "tercero_id"), "tercero_id"),
        par("transferencia hacia una cuenta", "/v1/intenciones/transferencia",
            lambda x: {"intencion_id": u(), "importe": "5.00", "moneda": "EUR", "fecha_hecho": "2026-10-05",
                       "cuenta_origen_id": str(ia["cuenta_id"]), "cuenta_destino_id": str(x["ahorro_id"]), "nota": None},
            "ahorro_id"),
        par("transferencia desde una cuenta", "/v1/intenciones/transferencia",
            lambda x: {"intencion_id": u(), "importe": "5.00", "moneda": "EUR", "fecha_hecho": "2026-10-05",
                       "cuenta_origen_id": str(x["ahorro_id"]), "cuenta_destino_id": str(ia["cuenta_id"]), "nota": None},
            "ahorro_id"),
        par("propiedad con cotitular", "/v1/propiedades",
            lambda x: {"intencion_id": u(), "nombre": "Piso G9", "tipo_propiedad": "VIVIENDA",
                       "titularidad": {"modo": "COMPARTIDA", "desde": "2026-01-01", "partes": [
                           {"yo": True, "porcentaje": "50"}, {"tercero_id": str(x["persona_id"]), "porcentaje": "50"}]}},
            "persona_id"),
        par("gasto compartido con persona", "/v1/intenciones/gasto-compartido",
            lambda x: m3.cuerpo("20.00", pagado_por=m3.con_cuenta(ia["cuenta_id"]),
                                reparto=m3.repartir("10.00", (x["persona_id"], "10.00", "SI"))), "persona_id"),
        par("gasto compartido pagado con cuenta", "/v1/intenciones/gasto-compartido",
            lambda x: m3.cuerpo("20.00", pagado_por=m3.con_cuenta(x["cuenta_id"]),
                                reparto=m3.repartir("10.00", (ia["persona_id"], "10.00", "SI"))), "cuenta_id"),
    ]


def _recursos(owner, cli, cta, ahorro) -> dict:
    tipos = cli.get("/v1/preferencias", headers=h.AUTH).json()["tipos"]
    plt = uuid.uuid4()
    r = cli.post("/v1/plantillas", json={"id": str(plt), "nombre": "Base", "tipo_hecho_id": tipos["GASTO"],
                                                   "presupuestable_default": True}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return {"tipos": tipos, "ids": {"cuenta_id": cta, "ahorro_id": ahorro, "categoria_id": x5.categoria(owner, "Cat G9"),
                                    "tercero_id": x5.tercero(cli, "Tercero G9"), "contexto_id": x5.contexto(cli, "Ctx G9"),
                                    "plantilla_id": plt, "persona_id": m3.persona(cli, "Persona G9")}}


def test_g9_ids_de_otro_owner_en_el_cuerpo_rechazados_sin_efectos():
    """Escrituras SIN parametros de ruta con el ID de otro owner en el CUERPO. El mismo cuerpo con los recursos
    propios (control) debe dar 200: el rechazo con el de B se debe solo a ese ID; sin efectos en ninguna tabla."""
    a_owner, _, cli_a, cta_a, aho_a = m3.entorno()
    b_owner, _, cli_b, cta_b, aho_b = m3.entorno()
    a, b = _recursos(a_owner, cli_a, cta_a, aho_a), _recursos(b_owner, cli_b, cta_b, aho_b)
    detalle, fallos = [], []
    for desc, ruta, control, ajeno in _casos_cuerpo(a, b):
        rc = cli_a.post(ruta, json=control, headers=h.AUTH)
        antes = huella()
        rb = cli_a.post(ruta, json=ajeno, headers=h.AUTH)
        despues = huella()
        cambiadas = sorted(t for t in antes if antes[t] != despues.get(t))
        fila = {"caso": desc, "ruta": ruta, "control_status": rc.status_code, "ajeno_status": rb.status_code,
                "ajeno_codigo": (rb.json() or {}).get("codigo") if rb.headers.get("content-type", "").startswith("application/json") else None,
                "tablas_cambiadas": cambiadas}
        detalle.append(fila)
        if rc.status_code != 200 or rb.status_code < 300 or cambiadas:
            fallos.append({**fila, "control_cuerpo": rc.text[:300]})
    salida = os.environ.get("G9_SALIDA")
    if salida:
        pathlib.Path(salida, "g9_cuerpo.json").write_text(json.dumps(detalle, ensure_ascii=False, indent=1), encoding="utf-8")
    assert fallos == [], json.dumps(fallos, ensure_ascii=False, indent=1)
