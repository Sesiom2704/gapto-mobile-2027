# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_159_f05_01_icono_categoria.py
# Ruta: tests/api/test_159_f05_01_icono_categoria.py
# Descripcion: Bateria de S6-ICONO (F05-D013 §27.3; AJ-ICON-01..08, Q5-Q7):
#   biblioteca v1 (coherencia interna y validacion exacta), comando
#   POST /v1/categorias/{id}/icono (orden AJ-ICON-04, row_version, misma clave
#   sin escritura, null, categoria deshabilitada, respuesta perdida, tenant) y
#   `icon_key` en el alta (Q6). La idempotencia del alta con icono esta en
#   test_155 y la espera del advisory en test_156.
#   Todo rechazo se comprueba SIN escritura (icon_key, row_version y
#   auditoria intactos). Base local desechable 0001..0340 (estos tests
#   confirman filas). Datos sinteticos, creados como gapto_owner con la GUC
#   del tenant (WM 12C.7).
#
#   v0.2.0 (F05-01 S6-ICONO-AJ (AJ-S6ICONO-02, AJ-S6ICONO-03)): D3 fijada (en
#   el alta la clave se valida ANTES de la idempotencia AJ-S4-05: un id
#   existente con clave no publicada es ICONO_CATEGORIA_NO_VALIDO, nunca
#   IDENTIDAD_REUTILIZADA ni idempotente; mutante I22) y defensa residual del
#   CHECK de 0340 ejercitada sin API ni biblioteca, via _escribir sobre
#   actualizar e insertar, traducida por identidad de constraint (AJ-S4-07;
#   mutante I23).
# Version: 0.2.0
# ============================================================

from __future__ import annotations

import json
import re
import uuid

import pytest

import f05_01_helpers as fh
import vs01_api_helpers as h
from app.categorias import iconos
from app.categorias import repositorio as repo
from app.categorias import servicio

B = fh.BASE
ICONO_NO_VALIDO = "ICONO_CATEGORIA_NO_VALIDO"

#: F09 §12.97.9 (PUBLICADA, version 1), copiada aqui para el test cruzado.
BIBLIOTECA_F09_V1 = (
    "compras.carrito", "compras.cesta", "compras.ropa",
    "comida.restaurante", "comida.cafe",
    "hogar.casa", "hogar.luz", "hogar.agua", "hogar.gas", "hogar.internet", "hogar.reparaciones",
    "transporte.coche", "transporte.bus", "transporte.avion", "transporte.viaje",
    "salud.corazon", "salud.farmacia", "salud.deporte",
    "personal.peluqueria", "personal.mascota", "personal.educacion", "personal.movil",
    "ocio.regalo", "ocio.libro", "ocio.musica", "ocio.cine",
    "finanzas.dinero", "finanzas.impuestos", "finanzas.seguro", "finanzas.suscripcion",
)

NO_PUBLICADAS = (
    " compras.carrito", "compras.carrito ", "Compras.carrito", "COMPRAS.CARRITO", "compras.Carrito",
    "compras.coche", "star", "", "compras", "pricetag-outline", "categoriaIconoFallback", "cart-outline",
)


# ------------------------------------------------------------------ biblioteca (sin BD)
def test_biblioteca_v1_coincide_con_f09():
    assert iconos.ICONOS_CATEGORIA_VERSION == 1
    assert len(BIBLIOTECA_F09_V1) == 30 and iconos.CLAVES_PUBLICADAS == frozenset(BIBLIOTECA_F09_V1)
    assert iconos.CLAVES_ACTIVAS == iconos.CLAVES_PUBLICADAS
    assert iconos.CLAVES_ACTIVAS <= iconos.CLAVES_PUBLICADAS


def test_biblioteca_coherencia_interna_formato_y_longitud():
    assert iconos.PATRON == r"^[a-z]+\.[a-z_]+$" and iconos.LONGITUD_MAXIMA == 80
    for clave in iconos.CLAVES_PUBLICADAS:
        assert re.fullmatch(iconos.PATRON, clave) and len(clave) <= iconos.LONGITUD_MAXIMA, clave


def test_biblioteca_sin_reserva_ni_presentacion():
    """AJ-ICON-08: solo claves; el icono de reserva no es clave."""
    assert "pricetag-outline" not in iconos.CLAVES_PUBLICADAS
    assert "categoriaIconoFallback" not in iconos.CLAVES_PUBLICADAS
    assert not any("-outline" in c for c in iconos.CLAVES_PUBLICADAS)


def test_validacion_exacta():
    assert iconos.icono_valido(None) is True
    for clave in BIBLIOTECA_F09_V1:
        assert iconos.icono_valido(clave) is True, clave
    for clave in NO_PUBLICADAS:
        assert iconos.icono_valido(clave) is False, repr(clave)


# ------------------------------------------------------------------ comando
@pytest.fixture()
def ctx():
    owner, actor = h.crear_tenant()
    return owner, actor, h.cliente(owner)


def _icono(cli, cid, icon_key, row_version):
    return fh.cmd(cli, f"{B}/{cid}/icono", {"icon_key": icon_key, "row_version": row_version})


def _fila(owner, cid) -> tuple:
    return h.leer(owner, "SELECT icon_key, row_version, enabled, parent_id, nombre, ambito, orden, "
                         "presupuestable_default FROM gapto.categorias_financieras WHERE id=%s", (cid,))[0]


def _auditorias_icono(owner, cid) -> list[tuple]:
    return h.leer(owner, "SELECT accion, datos_antes->>'icon_key', datos_despues->>'icon_key', "
                         "(datos_antes->>'row_version')::int, (datos_despues->>'row_version')::int "
                         "FROM gapto.auditoria WHERE tabla='categorias_financieras' AND registro_id=%s "
                         "AND motivo='F05-01 ICONO' ORDER BY created_at, id", (cid,))


def _codigo(r) -> str:
    return r.json().get("codigo")


def test_clave_publicada_persiste_y_audita(ctx):
    owner, _, cli = ctx
    cid, _ = fh.alta(cli, "Super")
    r = _icono(cli, cid, "compras.carrito", 1)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["idempotente"] is False and cuerpo["modificadas"] == [str(cid)]
    assert cuerpo["categoria"]["icon_key"] == "compras.carrito" and cuerpo["categoria"]["row_version"] == 2
    assert _fila(owner, cid)[:2] == ("compras.carrito", 2)
    assert _auditorias_icono(owner, cid) == [("ACTUALIZAR", None, "compras.carrito", 1, 2)]
    assert [(a, m) for a, m, _ in fh.auditorias(owner, cid)] == [("CREAR", "F05-01 ALTA"),
                                                                  ("ACTUALIZAR", "F05-01 ICONO")]
    # La lectura del arbol devuelve la clave tal cual.
    arbol = cli.get(B, headers=h.AUTH).json()["categorias"]
    assert next(n for n in arbol if n["id"] == str(cid))["icon_key"] == "compras.carrito"


def test_cambio_entre_claves_y_null_deja_null(ctx):
    owner, _, cli = ctx
    cid = fh.crear_categoria(owner, "Luz", "GASTO", icon_key="hogar.luz")
    assert _icono(cli, cid, "hogar.casa", 1).status_code == 200
    r = _icono(cli, cid, None, 2)
    assert r.status_code == 200 and r.json()["categoria"]["icon_key"] is None
    assert _fila(owner, cid)[:2] == (None, 3)
    assert _auditorias_icono(owner, cid) == [("ACTUALIZAR", "hogar.luz", "hogar.casa", 1, 2),
                                             ("ACTUALIZAR", "hogar.casa", None, 2, 3)]


@pytest.mark.parametrize("clave", NO_PUBLICADAS)
def test_clave_no_publicada_rechazada_sin_escritura(ctx, clave):
    owner, _, cli = ctx
    cid = fh.crear_categoria(owner, "Cesta", "GASTO", icon_key="compras.cesta")
    antes = _fila(owner, cid)
    r = _icono(cli, cid, clave, 1)
    assert r.status_code == 422 and _codigo(r) == ICONO_NO_VALIDO, r.text
    assert r.json()["reintentable"] is False
    assert _fila(owner, cid) == antes and fh.auditorias(owner, cid) == []


def test_misma_clave_idempotente_sin_update_ni_auditoria(ctx):
    owner, _, cli = ctx
    cid = fh.crear_categoria(owner, "Cafe", "GASTO", icon_key="comida.cafe")
    r = _icono(cli, cid, "comida.cafe", 1)
    assert r.status_code == 200 and r.json()["idempotente"] is True and r.json()["modificadas"] == []
    assert r.json()["categoria"]["row_version"] == 1
    sin = fh.crear_categoria(owner, "Sin icono", "GASTO")
    r = _icono(cli, sin, None, 1)
    assert r.status_code == 200 and r.json()["idempotente"] is True
    for c, clave in ((cid, "comida.cafe"), (sin, None)):
        assert _fila(owner, c)[:2] == (clave, 1) and fh.auditorias(owner, c) == []


@pytest.mark.parametrize("clave", ["comida.cafe", "ocio.cine", None, "no.publicada"])
def test_row_version_desfasado_aunque_la_clave_coincida(ctx, clave):
    """AJ-ICON-04: la version se controla ANTES de validar y de comparar."""
    owner, _, cli = ctx
    cid = fh.crear_categoria(owner, "Cafe", "GASTO", icon_key="comida.cafe")
    assert fh.cmd(cli, f"{B}/{cid}/orden", {"orden": 5, "row_version": 1}).status_code == 200
    antes = _fila(owner, cid)
    r = _icono(cli, cid, clave, 1)
    assert r.status_code == 409 and _codigo(r) == "VERSION_DESFASADA", r.text
    assert _fila(owner, cid) == antes and _auditorias_icono(owner, cid) == []


def test_categoria_deshabilitada_admite_el_cambio_sin_reactivar(ctx):
    owner, _, cli = ctx
    padre = fh.crear_categoria(owner, "Padre", "AMBOS", enabled=False)
    cid = fh.crear_categoria(owner, "Hija", "INGRESO", parent_id=padre, enabled=False, orden=7)
    antes = _fila(owner, cid)
    r = _icono(cli, cid, "finanzas.dinero", 1)
    assert r.status_code == 200, r.text
    despues = _fila(owner, cid)
    assert despues[:2] == ("finanzas.dinero", 2)
    assert despues[2:] == antes[2:]  # enabled, parent, nombre, ambito, orden y presupuestable intactos
    assert despues[2] is False
    assert _auditorias_icono(owner, cid) == [("ACTUALIZAR", None, "finanzas.dinero", 1, 2)]
    assert _fila(owner, padre)[:3] == (None, 1, False)


def test_respuesta_perdida_reintento_tras_commit_es_version_desfasada(ctx):
    """Q5 (deuda F10-03): el reintento con el row_version ya consumido no se
    reconoce como idempotente."""
    owner, _, cli = ctx
    cid, _ = fh.alta(cli, "Gimnasio")
    assert _icono(cli, cid, "salud.deporte", 1).status_code == 200
    r = _icono(cli, cid, "salud.deporte", 1)
    assert r.status_code == 409 and _codigo(r) == "VERSION_DESFASADA"
    assert _fila(owner, cid)[:2] == ("salud.deporte", 2) and len(_auditorias_icono(owner, cid)) == 1


@pytest.mark.parametrize("origen", ["INEXISTENTE", "AJENA"])
@pytest.mark.parametrize("clave", ["ocio.libro", "no.publicada"])
def test_categoria_inexistente_o_de_otro_tenant(ctx, origen, clave):
    _, _, cli = ctx
    if origen == "AJENA":
        otro, _ = h.crear_tenant()
        cid = fh.crear_categoria(otro, "Ajena", "GASTO")
    else:
        otro, cid = None, uuid.uuid4()
    r = _icono(cli, cid, clave, 1)
    assert r.status_code == 404 and _codigo(r) == "AGREGADO_NO_ENCONTRADO", r.text
    if otro is not None:
        assert _fila(otro, cid)[:2] == (None, 1) and fh.auditorias(otro, cid) == []


@pytest.mark.parametrize("cuerpo", [
    {"row_version": 1},
    {"icon_key": "ocio.libro"},
    {"icon_key": 7, "row_version": 1},
    {"icon_key": "ocio.libro", "row_version": 1, "enabled": True},
])
def test_cuerpo_estructuralmente_invalido_422(ctx, cuerpo):
    owner, _, cli = ctx
    cid = fh.crear_categoria(owner, "Libros", "GASTO")
    r = fh.cmd(cli, f"{B}/{cid}/icono", cuerpo)
    assert r.status_code == 422 and _codigo(r) == "ENTRADA_INVALIDA", r.text
    assert _fila(owner, cid)[:2] == (None, 1) and fh.auditorias(owner, cid) == []


# ------------------------------------------------------------------ alta (Q6)
def _alta(cli, nombre, **icono):
    cid = uuid.uuid4()
    r = fh.cmd(cli, B, {"id": str(cid), "nombre": nombre, "parent_id": None, "ambito": "GASTO",
                        "presupuestable_default": False, **icono})
    return cid, r


@pytest.mark.parametrize("icono,esperado", [({}, None), ({"icon_key": None}, None),
                                            ({"icon_key": "ocio.regalo"}, "ocio.regalo")])
def test_alta_con_icono_omitido_null_o_publicado(ctx, icono, esperado):
    owner, _, cli = ctx
    cid, r = _alta(cli, "Regalos", **icono)
    assert r.status_code == 200, r.text
    assert r.json()["categoria"]["icon_key"] == esperado
    assert _fila(owner, cid)[:2] == (esperado, 1)
    despues = h.leer(owner, "SELECT datos_despues FROM gapto.auditoria WHERE registro_id=%s "
                            "AND motivo='F05-01 ALTA'", (cid,))
    datos = despues[0][0] if isinstance(despues[0][0], dict) else json.loads(despues[0][0])
    assert datos["icon_key"] == esperado


@pytest.mark.parametrize("clave", ["Ocio.regalo", "ocio.regalo ", "ocio.juguete", "star"])
def test_alta_con_icono_no_publicado_rechazada_sin_escritura(ctx, clave):
    owner, _, cli = ctx
    cid, r = _alta(cli, "Juguetes", icon_key=clave)
    assert r.status_code == 422 and _codigo(r) == ICONO_NO_VALIDO, r.text
    assert h.leer(owner, "SELECT count(*) FROM gapto.categorias_financieras WHERE id=%s", (cid,)) == [(0,)]
    assert fh.auditorias(owner, cid) == []


@pytest.mark.parametrize("previa", ["MISMA_SALVO_ICONO", "OTRA_INTENCION"])
@pytest.mark.parametrize("clave", ["ocio.juguete", "Ocio.regalo"])
def test_alta_con_id_existente_y_clave_no_publicada_es_icono_no_valido(ctx, previa, clave):
    """D3: la clave se valida antes de la idempotencia del alta (AJ-S4-05)."""
    owner, _, cli = ctx
    cid, r = _alta(cli, "Juguetes" if previa == "MISMA_SALVO_ICONO" else "Otra")
    assert r.status_code == 200, r.text
    r = fh.cmd(cli, B, {"id": str(cid), "nombre": "Juguetes", "parent_id": None, "ambito": "GASTO",
                        "presupuestable_default": False, "icon_key": clave})
    assert r.status_code == 422 and _codigo(r) == ICONO_NO_VALIDO, r.text
    assert _fila(owner, cid)[:2] == (None, 1)
    assert [(a, m) for a, m, _ in fh.auditorias(owner, cid)] == [("CREAR", "F05-01 ALTA")]


# ------------------------------------------------------------------ defensa residual (AJ-S4-07)
@pytest.mark.parametrize("valor", ["", " hogar.casa"])
def test_defensa_residual_check_icon_key_traducida_por_identidad(ctx, valor):
    """Sin API ni biblioteca: el CHECK de 0340 se traduce por su nombre de
    constraint a ICONO_CATEGORIA_NO_VALIDO, dentro de un savepoint y sin
    escritura (inalcanzable por la API mientras la biblioteca valide antes)."""
    owner, _, _ = ctx
    cid = fh.crear_categoria(owner, "Agua", "GASTO", icon_key="hogar.agua")
    antes = _fila(owner, cid)
    nuevo = uuid.uuid4()

    def operacion(s):
        return (
            servicio._escribir(s, lambda: repo.actualizar(s, cid, {"icon_key": valor})),
            servicio._escribir(s, lambda: repo.insertar(
                s, categoria_id=nuevo, parent_id=None, nombre="X", ambito="GASTO",
                presupuestable_default=False, icon_key=valor)),
        )

    esperado = servicio.Rechazo(ICONO_NO_VALIDO)
    assert fh.en_transaccion(owner, operacion) == (esperado, esperado)
    assert _fila(owner, cid) == antes
    assert h.leer(owner, "SELECT count(*) FROM gapto.categorias_financieras WHERE id=%s", (nuevo,)) == [(0,)]
    assert fh.auditorias(owner, cid) == [] and fh.auditorias(owner, nuevo) == []
