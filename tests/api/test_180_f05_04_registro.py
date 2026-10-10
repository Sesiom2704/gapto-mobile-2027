# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_180_f05_04_registro.py
# Ruta: tests/api/test_180_f05_04_registro.py
# Descripcion: Registro por tipo de F05-04 (J2 §1.7; F05 §46.3 A2..A6/A9,
#   §46.4 R1..R3; F05-D032 C3). Casos §46.7 de backend:
#     1 gasto con tercero (VENDEDOR, principal) y preferencia por tercero;
#     2/28 «No lo sé» sin fila en hecho_magnitudes;
#     3/4/5 ingreso cobrado (C-14) con categoria INGRESO, AMBOS y AMBOS bajo
#       un padre GASTO; rol OTRO del tercero; sin aportaciones;
#     6/7/8 entre cuentas (OP-10): cero efectos, signos, misma cuenta,
#       liquidacion de la tarjeta (destino CREDITO) y origen sin capacidad;
#     10/30 tipo sellado: un UUID usado con un tipo choca con otro;
#     12 contexto: hecho_entidades RELACIONADO_CON, efecto NULL, no principal;
#     17/23 cambios entre carga y confirmacion (tercero, contexto, categoria,
#       cuenta) -> rechazo sin escritura;
#     18/22 IDs de otro owner sin efectos;
#     19/20 ninguna posicion: ningun modulo F05 invoca OP-12A ni serializa
#       ResultadoPosicion;
#     24 transferencia atomica ante fallo inyectado;
#     25 fallo del registro despues del alta independiente del tercero;
#     26 reintentos idempotentes y guarda de replay propia de OP-10;
#     nota canonica (omitida, "", espacios -> NULL en hecho y movimiento).
# Version: 0.1.0 (F05-03/F05-04 J2 §1.7)
# ============================================================

from __future__ import annotations

import ast
import pathlib
import uuid
from decimal import Decimal as D

import pytest

import f05_01_helpers as fh
import f05_02_helpers as ph
import vs01_api_helpers as h

GASTO = "/v1/intenciones/gasto-pagado"
INGRESO = "/v1/intenciones/ingreso-cobrado"
TRANSF = "/v1/intenciones/transferencia"
FECHA = "2026-09-24"


@pytest.fixture()
def t():
    owner, actor, cli = ph.tenant()
    corriente = h.crear_cuenta(owner, [(actor, 100)], tipo="CORRIENTE")
    ahorro = h.crear_cuenta(owner, [(actor, 100)], tipo="AHORRO")
    credito = h.crear_cuenta(owner, [(actor, 100)], tipo="CREDITO", naturaleza="PASIVO")
    return owner, actor, cli, corriente, ahorro, credito


def ingreso(cuenta, **cambios):
    base = {"intencion_id": str(uuid.uuid4()), "importe": "1500.00", "moneda": "EUR", "fecha_hecho": FECHA,
            "cuenta_id": str(cuenta), "presupuestable": True, "atribucion": "SOLO_MIO",
            "categoria": {"estado": "SIN_CATEGORIA"}}
    base.update({k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in cambios.items()})
    return base


def transf(origen, destino, **cambios):
    base = {"intencion_id": str(uuid.uuid4()), "importe": "500.00", "moneda": "EUR", "fecha_hecho": FECHA,
            "cuenta_origen_id": str(origen), "cuenta_destino_id": str(destino)}
    base.update(cambios)
    return base


def _cat(owner, nombre, ambito="GASTO", **kw):
    return ph.categoria(owner, nombre, ambito=ambito, **kw)


def _tercero(cli, nombre="ALDI"):
    tid = uuid.uuid4()
    assert cli.post("/v1/terceros", json={"id": str(tid), "nombre": nombre}, headers=h.AUTH).status_code == 200
    return tid


def _contexto(cli, nombre="Finde Cartagena"):
    cid = uuid.uuid4()
    r = cli.post("/v1/contextos", json={"id": str(cid), "nombre": nombre, "tipo_contexto": "VIAJE"}, headers=h.AUTH)
    assert r.status_code == 200
    return cid


def _hecho(owner, hid):
    f = h.leer(owner, "SELECT t.codigo, h.importe_total, h.concepto, h.presupuestable FROM gapto.hechos_financieros h "
                      "JOIN gapto.tipos_hecho t ON t.id = h.tipo_hecho_id WHERE h.id=%s", (hid,))
    return f[0] if f else None


def _efectos(owner, hid):
    return h.leer(owner, "SELECT tipo_efecto, importe_delta, estado_atribucion, categoria_id FROM gapto.hecho_efectos "
                         "WHERE hecho_id=%s", (hid,))


def _movimientos(owner, hid):
    return sorted(h.leer(owner, "SELECT m.cuenta_id, m.importe, m.descripcion FROM gapto.movimientos_tesoreria m "
                                "JOIN gapto.hecho_movimientos_tesoreria hm ON hm.movimiento_tesoreria_id = m.id "
                                "WHERE hm.hecho_id=%s", (hid,)), key=lambda x: x[1])


def _vinculos(owner, hid):
    terceros = h.leer(owner, "SELECT tercero_id, rol_en_hecho, principal FROM gapto.hecho_terceros WHERE hecho_id=%s",
                      (hid,))
    entidades = h.leer(owner, "SELECT entidad_id, tipo_relacion, efecto_id, principal FROM gapto.hecho_entidades "
                              "WHERE hecho_id=%s", (hid,))
    return terceros, entidades


def _nada(owner, hid):
    return _hecho(owner, uuid.UUID(hid) if isinstance(hid, str) else hid) is None


# ------------------------------------------------------------------ gasto con tercero, contexto y «No lo se»
def test_caso1_y_12_gasto_con_tercero_y_contexto(t):
    owner, _, cli, corriente, _, _ = t
    ter, ctx = _tercero(cli), _contexto(cli)
    cuerpo = h.intencion(corriente, tercero_id=str(ter), contexto_id=str(ctx))
    r = cli.post(GASTO, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    hid = uuid.UUID(cuerpo["intencion_id"])
    assert _vinculos(owner, hid) == ([(ter, "VENDEDOR", True)], [(ctx, "RELACIONADO_CON", None, False)])
    assert cli.post(GASTO, json=cuerpo, headers=h.AUTH).json()["idempotente"] is True
    assert cli.get("/v1/terceros", headers=h.AUTH).json()["terceros"][0]["usos"] == 1


def test_caso1_preferencia_por_tercero_en_la_propuesta(t):
    owner, _, cli, corriente, _, _ = t
    efectivo = h.crear_cuenta(owner, [(t[1], 100)], tipo="EFECTIVO")
    ter = _tercero(cli)
    pid, r = ph.alta(cli, tercero_id=ter, cuenta_default_id=efectivo)
    assert r.status_code == 200, r.text
    c = cli.get("/v1/registro/propuesta", params={"tipo": "GASTO", "fecha": FECHA, "tercero_id": str(ter)},
                headers=h.AUTH).json()["campos"]
    assert c["cuenta"]["valor"] == str(efectivo) and c["cuenta"]["origen"]["preferencia_id"] == str(pid)


def test_sin_tercero_ni_contexto_no_hay_vinculos(t):
    owner, _, cli, corriente, _, _ = t
    cuerpo = h.intencion(corriente)
    assert cli.post(GASTO, json=cuerpo, headers=h.AUTH).status_code == 200
    assert _vinculos(owner, uuid.UUID(cuerpo["intencion_id"])) == ([], [])


def _con_magnitud_obligatoria(owner):
    cat = _cat(owner, "Combustible")
    mag = h.crear_magnitud(owner, "Litros")
    h.crear_asociacion(owner, cat, mag, obligatoria=True)
    return cat, mag


def test_caso2_y_28_no_lo_se_sin_fila_de_magnitud(t):
    owner, _, cli, corriente, _, _ = t
    cat, mag = _con_magnitud_obligatoria(owner)
    sin = h.intencion(corriente, categoria={"estado": "CATEGORIA", "categoria_id": str(cat)})
    r = cli.post(GASTO, json=sin, headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "MAGNITUD_OBLIGATORIA_AUSENTE"
    cuerpo = h.intencion(corriente, categoria={"estado": "CATEGORIA", "categoria_id": str(cat),
                                               "desconocidas": [str(mag)]})
    r = cli.post(GASTO, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    hid = uuid.UUID(cuerpo["intencion_id"])
    assert h.leer(owner, "SELECT count(*) FROM gapto.hecho_magnitudes WHERE hecho_id=%s", (hid,))[0][0] == 0


def test_no_lo_se_validaciones(t):
    owner, _, cli, corriente, _, _ = t
    cat, mag = _con_magnitud_obligatoria(owner)
    ajena = h.crear_magnitud(owner, "Otra")
    cuerpo = h.intencion(corriente, categoria={"estado": "CATEGORIA", "categoria_id": str(cat),
                                               "desconocidas": [str(ajena)]})
    r = cli.post(GASTO, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "MAGNITUD_NO_ADMITIDA"
    for desconocidas, magnitudes in (([str(mag), str(mag)], []), ([str(mag)], [{"magnitud_id": str(mag), "valor": "3"}])):
        cuerpo = h.intencion(corriente, categoria={"estado": "CATEGORIA", "categoria_id": str(cat),
                                                   "desconocidas": desconocidas, "magnitudes": magnitudes})
        assert cli.post(GASTO, json=cuerpo, headers=h.AUTH).status_code == 422


# ------------------------------------------------------------------ ingreso cobrado (C-14)
def test_caso3_ingreso_composicion_c14(t):
    owner, actor, cli, corriente, _, _ = t
    nomina = _cat(owner, "Nómina", ambito="INGRESO")
    empresa = _tercero(cli, "Empresa SA")
    cuerpo = ingreso(corriente, categoria={"estado": "CATEGORIA", "categoria_id": str(nomina)}, tercero_id=empresa,
                     nota="  Nómina de septiembre ")
    r = cli.post(INGRESO, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["tipo"] == "INGRESO" and r.json()["estado_atribucion"] == "COMPLETA"
    hid = uuid.UUID(cuerpo["intencion_id"])
    assert _hecho(owner, hid) == ("INGRESO", D("1500.0000"), "Nómina de septiembre", True)
    assert _efectos(owner, hid) == [("INGRESO", D("1500.0000"), "COMPLETA", nomina)]
    assert _movimientos(owner, hid) == [(corriente, D("1500.0000"), "Nómina de septiembre")]
    assert h.leer(owner, "SELECT importe_asignado FROM gapto.hecho_movimientos_tesoreria WHERE hecho_id=%s",
                  (hid,)) == [(D("1500.0000"),)]
    assert h.leer(owner, "SELECT count(*) FROM gapto.hecho_aportaciones_pago WHERE hecho_id=%s", (hid,))[0][0] == 0
    assert _vinculos(owner, hid)[0] == [(empresa, "OTRO", True)]
    assert cli.post(INGRESO, json=cuerpo, headers=h.AUTH).json()["idempotente"] is True


def test_ingreso_sin_indicar_y_nota_canonica(t):
    owner, _, cli, corriente, _, _ = t
    for nota in (None, "", "   "):
        cuerpo = ingreso(corriente, atribucion="SIN_INDICAR", **({} if nota is None else {"nota": nota}))
        r = cli.post(INGRESO, json=cuerpo, headers=h.AUTH)
        assert r.status_code == 200 and r.json()["estado_atribucion"] == "NO_DISPONIBLE"
        hid = uuid.UUID(cuerpo["intencion_id"])
        assert _hecho(owner, hid)[2] is None and _movimientos(owner, hid)[0][2] is None


@pytest.mark.parametrize("caso", ["ambos", "ambos_bajo_gasto"])
def test_caso4_y_5_categorias_ambos(t, caso):
    owner, _, cli, corriente, _, _ = t
    if caso == "ambos":
        cat = _cat(owner, "Alquileres", ambito="AMBOS")
    else:
        padre = _cat(owner, "Administración, impuestos y tasas")
        cat = _cat(owner, "IRPF / Renta", ambito="AMBOS", parent_id=padre)
        r = cli.post(INGRESO, json=ingreso(corriente, categoria={"estado": "CATEGORIA", "categoria_id": str(padre)}),
                     headers=h.AUTH)
        assert r.status_code == 409 and r.json()["codigo"] == "CATEGORIA_NO_ELEGIBLE"
    r = cli.post(INGRESO, json=ingreso(corriente, categoria={"estado": "CATEGORIA", "categoria_id": str(cat)}),
                 headers=h.AUTH)
    assert r.status_code == 200, r.text
    r = cli.post(GASTO, json=h.intencion(corriente, categoria={"estado": "CATEGORIA", "categoria_id": str(cat)}),
                 headers=h.AUTH)
    assert r.status_code == 200, r.text


def test_ingreso_exige_recibir_ingreso_y_categoria_de_ingreso(t):
    owner, _, cli, corriente, ahorro, credito = t
    for cuenta in (ahorro, credito):
        cuerpo = ingreso(cuenta)
        r = cli.post(INGRESO, json=cuerpo, headers=h.AUTH)
        assert r.status_code == 422 and r.json()["codigo"] == "CUENTA_DESCONOCIDA" and _nada(owner, cuerpo["intencion_id"])
    gasto = _cat(owner, "Supermercado")
    r = cli.post(INGRESO, json=ingreso(corriente, categoria={"estado": "CATEGORIA", "categoria_id": str(gasto)}),
                 headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "CATEGORIA_NO_ELEGIBLE"
    for extra in ({"financiacion": {"estado": "NO_DETERMINADA"}}, {"concepto": "x"}, {"origenes": {}}):
        assert cli.post(INGRESO, json={**ingreso(corriente), **extra}, headers=h.AUTH).status_code == 422


# ------------------------------------------------------------------ entre cuentas (OP-10)
def test_caso6_transferencia_cero_efectos(t):
    owner, _, cli, corriente, ahorro, _ = t
    cuerpo = transf(corriente, ahorro, nota="A ahorro")
    r = cli.post(TRANSF, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 200, r.text
    hid = uuid.UUID(cuerpo["intencion_id"])
    assert _hecho(owner, hid) == ("TRANSFERENCIA", D("500.0000"), "A ahorro", False)
    assert _efectos(owner, hid) == []
    assert _movimientos(owner, hid) == [(corriente, D("-500.0000"), "A ahorro"), (ahorro, D("500.0000"), "A ahorro")]
    assert cli.post(TRANSF, json=cuerpo, headers=h.AUTH).json()["idempotente"] is True


def test_caso7_misma_cuenta(t):
    owner, _, cli, corriente, _, _ = t
    cuerpo = transf(corriente, corriente)
    r = cli.post(TRANSF, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 422 and r.json()["codigo"] == "MISMA_CUENTA" and _nada(owner, cuerpo["intencion_id"])


def test_caso8_liquidacion_de_la_tarjeta_y_capacidades(t):
    owner, _, cli, corriente, ahorro, credito = t
    r = cli.post(TRANSF, json=transf(corriente, credito), headers=h.AUTH)  # destino CREDITO: TRANSFERIR_ENTRADA
    assert r.status_code == 200, r.text
    cuerpo = transf(credito, corriente)  # CREDITO no tiene TRANSFERIR_SALIDA
    r = cli.post(TRANSF, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 422 and r.json()["codigo"] == "CUENTA_DESCONOCIDA" and _nada(owner, cuerpo["intencion_id"])
    sin = h.crear_cuenta(owner, [(t[1], 100)], capacidades=("TRANSFERIR_SALIDA",))
    cuerpo = transf(corriente, sin)  # destino sin TRANSFERIR_ENTRADA
    r = cli.post(TRANSF, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 422 and _nada(owner, cuerpo["intencion_id"])


@pytest.mark.parametrize("cambio", [{"importe": "501.00"}, {"nota": "otra"}, {"fecha_hecho": "2026-09-23"},
                                    "invertir"])
def test_guarda_de_replay_propia_de_op10(t, cambio):
    owner, _, cli, corriente, ahorro, _ = t
    cuerpo = transf(corriente, ahorro, nota="x")
    assert cli.post(TRANSF, json=cuerpo, headers=h.AUTH).status_code == 200
    if cambio == "invertir":
        otro = {**cuerpo, "cuenta_origen_id": cuerpo["cuenta_destino_id"], "cuenta_destino_id": cuerpo["cuenta_origen_id"]}
    else:
        otro = {**cuerpo, **cambio}
    r = cli.post(TRANSF, json=otro, headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert _movimientos(owner, uuid.UUID(cuerpo["intencion_id"]))[0][1] == D("-500.0000")


def test_caso24_transferencia_atomica_ante_fallo_inyectado(t, monkeypatch):
    from app.repositories import transferencias_repository as repo_transf

    owner, _, cli, corriente, ahorro, _ = t
    def fallar(*a, **k):
        raise RuntimeError("fallo inyectado tras crear el hecho y las patas")

    monkeypatch.setattr(repo_transf, "insertar_si_no_existe", fallar)
    cuerpo = transf(corriente, ahorro)
    r = cli.post(TRANSF, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 500 and _nada(owner, cuerpo["intencion_id"])
    assert h.leer(owner, "SELECT count(*) FROM gapto.movimientos_tesoreria")[0][0] == 0


# ------------------------------------------------------------------ tipo sellado (casos 10 y 30)
def test_uuid_de_un_tipo_no_sirve_para_otro(t):
    owner, _, cli, corriente, ahorro, _ = t
    g = h.intencion(corriente)
    assert cli.post(GASTO, json=g, headers=h.AUTH).status_code == 200
    r = cli.post(INGRESO, json=ingreso(corriente, intencion_id=g["intencion_id"]), headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    r = cli.post(TRANSF, json=transf(corriente, ahorro, intencion_id=g["intencion_id"]), headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    tr = transf(corriente, ahorro)
    assert cli.post(TRANSF, json=tr, headers=h.AUTH).status_code == 200
    r = cli.post(GASTO, json=h.intencion(corriente, intencion_id=tr["intencion_id"]), headers=h.AUTH)
    assert r.status_code == 409 and r.json()["codigo"] == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert _efectos(owner, uuid.UUID(tr["intencion_id"])) == []


# ------------------------------------------------------------------ cambios entre carga y confirmacion (17, 23)
@pytest.mark.parametrize("que", ["tercero", "contexto", "categoria", "cuenta"])
def test_caso17_desactivado_entre_carga_y_confirmacion(t, que):
    owner, _, cli, corriente, _, _ = t
    ter, ctx, cat = _tercero(cli), _contexto(cli), _cat(owner, "Super")
    cuerpo = h.intencion(corriente, tercero_id=str(ter), contexto_id=str(ctx),
                         categoria={"estado": "CATEGORIA", "categoria_id": str(cat)})
    if que == "tercero":
        h.como_owner(owner, "UPDATE gapto.terceros SET enabled=false WHERE id=%s", (ter,))
        codigo = "TERCERO_NO_DISPONIBLE"
    elif que == "contexto":
        h.como_owner(owner, "UPDATE gapto.entidades SET enabled=false WHERE id=%s", (ctx,))
        codigo = "CONTEXTO_NO_DISPONIBLE"
    elif que == "categoria":
        h.como_owner(owner, "UPDATE gapto.categorias_financieras SET enabled=false WHERE id=%s", (cat,))
        codigo = "CATEGORIA_NO_ELEGIBLE"
    else:
        h.como_owner(owner, "DELETE FROM gapto.cuenta_capacidades WHERE cuenta_id=%s AND capacidad_codigo='PAGAR_GASTO'",
                     (corriente,))
        codigo = "CUENTA_DESCONOCIDA"
    r = cli.post(GASTO, json=cuerpo, headers=h.AUTH)
    assert r.json()["codigo"] == codigo and _nada(owner, cuerpo["intencion_id"])


def test_caso18_ids_de_otro_owner(t):
    owner, _, cli, corriente, _, _ = t
    otro, otro_actor, cli_otro = ph.tenant()
    ter, ctx = _tercero(cli_otro), _contexto(cli_otro)
    cuenta = h.crear_cuenta(otro, [(otro_actor, 100)])
    for campos, codigo in (({"tercero_id": str(ter)}, "TERCERO_NO_DISPONIBLE"),
                           ({"contexto_id": str(ctx)}, "CONTEXTO_NO_DISPONIBLE")):
        cuerpo = h.intencion(corriente, **campos)
        r = cli.post(GASTO, json=cuerpo, headers=h.AUTH)
        assert r.json()["codigo"] == codigo and _nada(owner, cuerpo["intencion_id"])
    cuerpo = ingreso(cuenta)
    assert cli.post(INGRESO, json=cuerpo, headers=h.AUTH).json()["codigo"] == "CUENTA_DESCONOCIDA"
    cuerpo = transf(corriente, cuenta)
    assert cli.post(TRANSF, json=cuerpo, headers=h.AUTH).json()["codigo"] == "CUENTA_DESCONOCIDA"
    assert h.leer(otro, "SELECT count(*) FROM gapto.hechos_financieros")[0][0] == 0


def test_caso25_fallo_del_registro_no_deshace_el_alta_del_tercero(t):
    owner, _, cli, corriente, _, _ = t
    ter = _tercero(cli, "Nuevo")
    cuerpo = h.intencion(corriente, tercero_id=str(ter), fecha_hecho="2099-01-01")
    r = cli.post(GASTO, json=cuerpo, headers=h.AUTH)
    assert r.status_code == 422 and r.json()["codigo"] == "FECHA_FUTURA"
    assert h.leer(owner, "SELECT nombre FROM gapto.terceros WHERE id=%s", (ter,)) == [("Nuevo",)]


# ------------------------------------------------------------------ fronteras negativas (19, 20; C7)
F05 = [p for d in ("api", "comun", "terceros", "contextos", "plantillas", "preferencias", "categorias", "magnitudes")
       for p in sorted((pathlib.Path(__file__).resolve().parents[2] / "backend" / "app" / d).rglob("*.py"))]


def test_caso19_20_ninguna_ruta_f05_crea_ni_expone_posiciones():
    for p in F05:
        arbol = ast.parse(p.read_text(encoding="utf-8"))
        nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
        nombres |= {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
        for imp in (n for n in ast.walk(arbol) if isinstance(n, (ast.ImportFrom, ast.Import))):
            nombres |= {a.name for a in imp.names}
            if isinstance(imp, ast.ImportFrom) and imp.module:
                nombres.add(imp.module)
        vedados = nombres & {"PosicionesService", "crear_posicion", "ResultadoPosicion", "app.core.modelos_posicion",
                             "app.services.posiciones_service", "DatosAltaPosicion"}
        assert not vedados, f"{p.name} toca posiciones: {sorted(vedados)}"


def test_ningun_esquema_http_serializa_posiciones(t):
    _, _, cli, _, _, _ = t
    esquema = cli.app.openapi()
    texto = str(esquema)
    for prohibido in ("ResultadoPosicion", "posicion_id", "DatosAltaPosicion"):
        assert prohibido not in texto


def test_fecha_futura_en_ingreso_y_transferencia(t):
    owner, _, cli, corriente, ahorro, _ = t
    for ruta, cuerpo in ((INGRESO, ingreso(corriente, fecha_hecho="2099-01-01")),
                         (TRANSF, transf(corriente, ahorro, fecha_hecho="2099-01-01"))):
        r = cli.post(ruta, json=cuerpo, headers=h.AUTH)
        assert r.status_code == 422 and r.json()["codigo"] == "FECHA_FUTURA" and _nada(owner, cuerpo["intencion_id"])
