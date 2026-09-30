# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_155_f05_01_gestion_categorias.py
# Ruta: tests/api/test_155_f05_01_gestion_categorias.py
# Descripcion: Gestion del arbol de categorias (F05-01, S4; C06; diseno S4
#   v0.2 con AJ-S4-01..07 y AJ-S4-04 bis). Casos deterministas:
#     - alta, idempotencia exacta (row_version 1) y reintento tardio (AJ-S4-05);
#     - unicidad normalizada NULL-safe con exclusion propia (AJ-S4-06);
#     - padre no valido y cadena de ancestros habilitada (AJ-S4-03);
#     - desactivar: modos, RAMA a traves de intermedios deshabilitados
#       (AJ-S4-02), reactivacion sin cascada (Q4);
#     - mover: ciclo, descendiente, colision bajo destino, D-122 (presupuesto
#       no BORRADOR) y D-121 (BOLSA sin prioridad) traducidos por identidad
#       fisica (AJ-S4-07);
#     - orden y cambio de ambito con confirmacion del uso (C06);
#     - matriz de auditoria accion/motivo y request_id comun en RAMA.
#   Base local desechable 0001..0340 (estos tests confirman filas).
#
#   v0.2.0 (F05-01 S6-ICONO (F05-D013), Q6): la idempotencia del alta
#   (AJ-S4-05) compara tambien `icon_key`: misma clave -> idempotente; otra
#   clave, o clave frente a omitido -> IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION.
#
#   v0.3.0 (F05-01 S6-ICONO-AJ (AJ-S6ICONO-01)): el antiguo
#   test_no_hay_escritura_de_icon_key_ni_presupuestable_default solo
#   comprobaba el status 422 y, tras S6-ICONO, su alta con icon_key pasaba por
#   coincidencia (ICONO_CATEGORIA_NO_VALIDO en vez de ENTRADA_INVALIDA). Se
#   sustituye por dos tests que comprueban el codigo: renombrar sigue sin
#   admitir icon_key ni presupuestable_default (422 estructural, sin
#   escritura), y el alta con una clave no publicada es
#   ICONO_CATEGORIA_NO_VALIDO y no estructural. Este segundo solapa con
#   test_159[star] a proposito: fija el cambio de semantica de este test ya
#   aceptado.
# Version: 0.3.0
# ============================================================

from __future__ import annotations

import uuid

import pytest

import f05_01_helpers as fh
import vs01_api_helpers as h

B = fh.BASE


@pytest.fixture()
def ctx():
    owner, actor = h.crear_tenant()
    return owner, actor, h.cliente(owner)


def _codigo(r) -> str:
    return r.json().get("codigo")


# ------------------------------------------------------------ alta
def test_alta_persiste_nombre_visible_y_audita_crear(ctx):
    owner, _, cli = ctx
    cid, r = fh.alta(cli, "  Hogar   y  casa ")
    assert r.status_code == 200, r.text
    assert r.json()["idempotente"] is False and r.json()["categoria"]["row_version"] == 1
    assert fh.estado(owner, cid)[2] == "Hogar y casa"
    assert [(a, m) for a, m, _ in fh.auditorias(owner, cid)] == [("CREAR", "F05-01 ALTA")]


def test_alta_idempotente_solo_sin_evolucion_posterior(ctx):
    owner, _, cli = ctx
    cid, r = fh.alta(cli, "Ropa")
    _, r2 = fh.alta(cli, "Ropa", cid=cid)
    assert r2.status_code == 200 and r2.json()["idempotente"] is True
    _, r3 = fh.alta(cli, "Ropa distinta", cid=cid)
    assert r3.status_code == 409 and _codigo(r3) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    # Evolucion legitima posterior: el reintento tardio ya no es idempotente.
    assert fh.cmd(cli, f"{B}/{cid}/orden", {"orden": 3, "row_version": 1}).status_code == 200
    assert fh.cmd(cli, f"{B}/{cid}/orden", {"orden": 0, "row_version": 2}).status_code == 200
    _, r4 = fh.alta(cli, "Ropa", cid=cid)
    assert r4.status_code == 409 and _codigo(r4) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert len(fh.auditorias(owner, cid)) == 3


def _alta_con_icono(cli, cid: uuid.UUID, nombre: str, **icono):
    return fh.cmd(cli, B, {"id": str(cid), "nombre": nombre, "parent_id": None, "ambito": "GASTO",
                           "presupuestable_default": True, **icono})


def test_alta_idempotente_compara_icon_key(ctx):
    owner, _, cli = ctx
    cid = uuid.uuid4()
    assert _alta_con_icono(cli, cid, "Bus", icon_key="transporte.bus").status_code == 200
    r = _alta_con_icono(cli, cid, "Bus", icon_key="transporte.bus")
    assert r.status_code == 200 and r.json()["idempotente"] is True
    for otra in ({"icon_key": "transporte.coche"}, {"icon_key": None}, {}):
        r = _alta_con_icono(cli, cid, "Bus", **otra)
        assert r.status_code == 409 and _codigo(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION", otra
    # Alta sin icono: el reintento con una clave tampoco es la misma intencion.
    sin = uuid.uuid4()
    assert _alta_con_icono(cli, sin, "Tren").status_code == 200
    assert _alta_con_icono(cli, sin, "Tren", icon_key=None).json()["idempotente"] is True
    r = _alta_con_icono(cli, sin, "Tren", icon_key="transporte.viaje")
    assert r.status_code == 409 and _codigo(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"
    assert h.leer(owner, "SELECT id, icon_key FROM gapto.categorias_financieras WHERE id = ANY(%s) ORDER BY nombre",
                  ([cid, sin],)) == [(cid, "transporte.bus"), (sin, None)]
    assert len(fh.auditorias(owner, cid)) == 1 and len(fh.auditorias(owner, sin)) == 1


def test_alta_con_id_de_otro_tenant_no_revela_y_no_escribe(ctx):
    owner, _, cli = ctx
    otro, _ = h.crear_tenant()
    ajena = fh.crear_categoria(otro, "Ajena", "GASTO")
    _, r = fh.alta(cli, "Mia", cid=ajena)
    assert r.status_code == 409 and _codigo(r) == "IDENTIDAD_REUTILIZADA_CON_OTRA_INTENCION"


@pytest.mark.parametrize("variante", ["cafe", "CAFÉ", "  Café  ", "ｃａｆé", "Cafe\u0301"])
def test_unicidad_normalizada_en_raiz_null_safe(ctx, variante):
    _, _, cli = ctx
    assert fh.alta(cli, "Café")[1].status_code == 200
    _, r = fh.alta(cli, variante)
    assert r.status_code == 409 and _codigo(r) == "CATEGORIA_NOMBRE_DUPLICADO"


def test_unicidad_por_hermanos_activos_y_nivel(ctx):
    owner, _, cli = ctx
    padre, _ = fh.alta(cli, "Ocio")
    assert fh.alta(cli, "Cine", parent_id=padre)[1].status_code == 200
    assert fh.alta(cli, "Cine")[1].status_code == 200  # otro nivel: raiz
    vieja = fh.crear_categoria(owner, "Teatro", "GASTO", parent_id=padre, enabled=False)
    assert fh.alta(cli, "teatro", parent_id=padre)[1].status_code == 200  # la inactiva no cuenta
    assert vieja


def test_renombrar_excluye_el_propio_nodo_y_detecta_colision(ctx):
    owner, _, cli = ctx
    a, _ = fh.alta(cli, "Luz")
    fh.alta(cli, "Agua")
    assert fh.cmd(cli, f"{B}/{a}/renombrar", {"nombre": "LUZ", "row_version": 1}).status_code == 200
    r = fh.cmd(cli, f"{B}/{a}/renombrar", {"nombre": "agua", "row_version": 2})
    assert r.status_code == 409 and _codigo(r) == "CATEGORIA_NOMBRE_DUPLICADO"
    assert fh.estado(owner, a)[2] == "LUZ"


@pytest.mark.parametrize("origen", ["INEXISTENTE", "AJENO"])
def test_padre_no_valido(ctx, origen):
    _, _, cli = ctx
    if origen == "AJENO":
        otro, _ = h.crear_tenant()
        padre = fh.crear_categoria(otro, "Ajena", "GASTO")
    else:
        padre = uuid.uuid4()
    _, r = fh.alta(cli, "Hija", parent_id=padre)
    assert r.status_code == 422 and _codigo(r) == "CATEGORIA_PADRE_NO_VALIDO"


@pytest.mark.parametrize("deshabilitado", ["PADRE", "ABUELO"])
def test_alta_bajo_rama_deshabilitada(ctx, deshabilitado):
    owner, _, cli = ctx
    abuelo = fh.crear_categoria(owner, "Abuelo", "GASTO", enabled=deshabilitado != "ABUELO")
    padre = fh.crear_categoria(owner, "Padre", "GASTO", parent_id=abuelo, enabled=deshabilitado != "PADRE")
    _, r = fh.alta(cli, "Nieto", parent_id=padre)
    assert r.status_code == 409 and _codigo(r) == "CATEGORIA_PADRE_DESHABILITADO"


# ------------------------------------------------------------ desactivar / reactivar
def test_desactivar_sin_modo_rama_con_hijos_activos_rechaza(ctx):
    owner, _, cli = ctx
    p, _ = fh.alta(cli, "Casa")
    fh.alta(cli, "Luz", parent_id=p)
    r = fh.cmd(cli, f"{B}/{p}/desactivar", {"modo": "SOLO_SI_SIN_HIJOS_ACTIVOS", "row_version": 1})
    assert r.status_code == 409 and _codigo(r) == "CATEGORIA_TIENE_HIJOS_ACTIVOS"
    assert fh.estado(owner, p)[0] is True


def test_desactivar_rama_atraviesa_intermedios_deshabilitados(ctx):
    """Raiz activa -> intermedio deshabilitado (legacy) -> nieto activo: el
    nieto TAMBIEN se desactiva (AJ-S4-02). Una auditoria por nodo modificado,
    todas DESACTIVAR_RAMA con el mismo request_id."""
    owner, _, cli = ctx
    raiz = fh.crear_categoria(owner, "Raiz", "GASTO")
    inter = fh.crear_categoria(owner, "Inter", "GASTO", parent_id=raiz, enabled=False)
    nieto = fh.crear_categoria(owner, "Nieto", "GASTO", parent_id=inter)
    # Segunda cadena: el intermedio deshabilitado esta en el nivel 2.
    hijo = fh.crear_categoria(owner, "Hijo", "GASTO", parent_id=raiz)
    inter2 = fh.crear_categoria(owner, "Inter2", "GASTO", parent_id=hijo, enabled=False)
    bisnieto = fh.crear_categoria(owner, "Bisnieto", "GASTO", parent_id=inter2)
    r = fh.cmd(cli, f"{B}/{raiz}/desactivar", {"modo": "RAMA", "row_version": 1})
    assert r.status_code == 200, r.text
    assert set(r.json()["modificadas"]) == {str(raiz), str(nieto), str(hijo), str(bisnieto)}
    assert fh.estado(owner, bisnieto)[0] is False
    assert fh.estado(owner, nieto)[0] is False and fh.estado(owner, raiz)[0] is False
    auds = [x for c in (raiz, nieto, hijo, bisnieto) for x in fh.auditorias(owner, c)]
    assert [(a, m) for a, m, _ in auds] == [("ACTUALIZAR", "F05-01 DESACTIVAR_RAMA")] * 4
    assert len({rid for _, _, rid in auds}) == 1 and auds[0][2] is not None
    assert fh.auditorias(owner, inter) == [] and fh.auditorias(owner, inter2) == []  # no se modificaron


def test_reactivar_no_es_cascada_y_exige_ancestros(ctx):
    owner, _, cli = ctx
    p, _ = fh.alta(cli, "Viajes")
    hi, _ = fh.alta(cli, "Hoteles", parent_id=p)
    assert fh.cmd(cli, f"{B}/{p}/desactivar", {"modo": "RAMA", "row_version": 1}).status_code == 200
    r = fh.cmd(cli, f"{B}/{hi}/reactivar", {"row_version": 2})
    assert r.status_code == 409 and _codigo(r) == "CATEGORIA_PADRE_DESHABILITADO"
    assert fh.cmd(cli, f"{B}/{p}/reactivar", {"row_version": 2}).status_code == 200
    assert fh.estado(owner, hi)[0] is False  # sin cascada (Q4)
    assert fh.cmd(cli, f"{B}/{hi}/reactivar", {"row_version": 2}).status_code == 200
    assert [m for _, m, _ in fh.auditorias(owner, hi)] == ["F05-01 ALTA", "F05-01 DESACTIVAR_RAMA", "F05-01 REACTIVAR"]


def test_reactivar_con_colision_normalizada(ctx):
    owner, _, cli = ctx
    vieja = fh.crear_categoria(owner, "Musica", "GASTO", enabled=False)
    fh.alta(cli, "MÚSICA")
    r = fh.cmd(cli, f"{B}/{vieja}/reactivar", {"row_version": 1})
    assert r.status_code == 409 and _codigo(r) == "CATEGORIA_NOMBRE_DUPLICADO"


# ------------------------------------------------------------ mover
def test_mover_a_si_mismo_o_a_un_descendiente(ctx):
    _, _, cli = ctx
    a, _ = fh.alta(cli, "A")
    b, _ = fh.alta(cli, "B", parent_id=a)
    c, _ = fh.alta(cli, "C", parent_id=b)
    for destino in (a, c):
        r = fh.cmd(cli, f"{B}/{a}/mover", {"parent_id": str(destino), "row_version": 1})
        assert r.status_code == 422 and _codigo(r) == "CATEGORIA_PADRE_NO_VALIDO"


def test_mover_bajo_abuelo_deshabilitado_y_colision_en_destino(ctx):
    owner, _, cli = ctx
    abuelo = fh.crear_categoria(owner, "Abuelo", "GASTO", enabled=False)
    padre = fh.crear_categoria(owner, "Padre", "GASTO", parent_id=abuelo)
    nodo, _ = fh.alta(cli, "Suelta")
    r = fh.cmd(cli, f"{B}/{nodo}/mover", {"parent_id": str(padre), "row_version": 1})
    assert r.status_code == 409 and _codigo(r) == "CATEGORIA_PADRE_DESHABILITADO"
    destino, _ = fh.alta(cli, "Destino")
    fh.alta(cli, "suelta", parent_id=destino)
    r = fh.cmd(cli, f"{B}/{nodo}/mover", {"parent_id": str(destino), "row_version": 1})
    assert r.status_code == 409 and _codigo(r) == "CATEGORIA_NOMBRE_DUPLICADO"
    assert fh.cmd(cli, f"{B}/{nodo}/mover", {"parent_id": None, "row_version": 1}).status_code == 200


def test_mover_bloqueado_por_presupuesto_congelado_d122(ctx):
    owner, _, cli = ctx
    x, _ = fh.alta(cli, "Alimentacion")
    y, _ = fh.alta(cli, "Super", parent_id=x)
    fh.crear_presupuesto(owner, [(1, [(x, True)])], estado_final="ACTIVO")
    r = fh.cmd(cli, f"{B}/{y}/mover", {"parent_id": None, "row_version": 1})
    assert r.status_code == 409 and _codigo(r) == "CATEGORIA_MOVIMIENTO_BLOQUEADO_POR_PRESUPUESTO"
    assert fh.estado(owner, y)[1] == x and fh.rv(owner, y) == 1


def test_mover_que_solapa_bolsas_sin_prioridad_d121(ctx):
    owner, _, cli = ctx
    x, _ = fh.alta(cli, "X")
    y, _ = fh.alta(cli, "Y")
    fh.crear_presupuesto(owner, [(None, [(x, True)]), (None, [(y, True)])])
    r = fh.cmd(cli, f"{B}/{y}/mover", {"parent_id": str(x), "row_version": 1})
    assert r.status_code == 409 and _codigo(r) == "CATEGORIA_MOVIMIENTO_BLOQUEADO_POR_PRESUPUESTO"
    assert fh.estado(owner, y)[1] is None


# ------------------------------------------------------------ orden / ambito / version
def test_orden_rango_y_version(ctx):
    owner, _, cli = ctx
    a, _ = fh.alta(cli, "A")
    for valor in (-1, 32768):
        r = fh.cmd(cli, f"{B}/{a}/orden", {"orden": valor, "row_version": 1})
        assert r.status_code == 422
    assert fh.cmd(cli, f"{B}/{a}/orden", {"orden": 32767, "row_version": 1}).status_code == 200
    r = fh.cmd(cli, f"{B}/{a}/orden", {"orden": 1, "row_version": 1})
    assert r.status_code == 409 and _codigo(r) == "VERSION_DESFASADA"
    assert fh.estado(owner, a)[4] == 32767


def test_cambio_de_ambito_exige_confirmar_el_uso_vigente(ctx):
    owner, actor, cli = ctx
    cuenta = h.crear_cuenta(owner, [(actor, 100)])
    cat, _ = fh.alta(cli, "Regalos")
    cuerpo = h.intencion(cuenta, categoria={"estado": "CATEGORIA", "categoria_id": str(cat)})
    assert cli.post("/v1/intenciones/gasto-pagado", json=cuerpo, headers=h.AUTH).status_code == 200
    r = fh.cmd(cli, f"{B}/{cat}/ambito", {"ambito": "INGRESO", "confirmacion_uso": {}, "row_version": 1})
    assert r.status_code == 409 and _codigo(r) == "CAMBIO_AMBITO_REQUIERE_CONFIRMACION"
    assert r.json()["detalle"] == {"efectos_activos": {"GASTO": 1}}
    r = fh.cmd(cli, f"{B}/{cat}/ambito", {"ambito": "INGRESO", "confirmacion_uso": {"GASTO": 1}, "row_version": 1})
    assert r.status_code == 200
    # La historia no cambia: el efecto conserva su categoria y naturaleza.
    assert h.leer(owner, "SELECT tipo_efecto, categoria_id FROM gapto.hecho_efectos WHERE hecho_id=%s",
                  (uuid.UUID(cuerpo["intencion_id"]),)) == [("GASTO", cat)]


def test_matriz_de_auditoria_por_operacion(ctx):
    owner, _, cli = ctx
    a, _ = fh.alta(cli, "Matriz")
    pasos = [
        ("renombrar", {"nombre": "Matriz 2"}), ("mover", {"parent_id": None}), ("orden", {"orden": 2}),
        ("ambito", {"ambito": "AMBOS", "confirmacion_uso": {}}),
        ("desactivar", {"modo": "SOLO_SI_SIN_HIJOS_ACTIVOS"}), ("reactivar", {}),
    ]
    for version, (op, cuerpo) in enumerate(pasos, start=1):
        assert fh.cmd(cli, f"{B}/{a}/{op}", dict(cuerpo, row_version=version)).status_code == 200, op
    assert [(ac, m) for ac, m, _ in fh.auditorias(owner, a)] == [
        ("CREAR", "F05-01 ALTA"), ("ACTUALIZAR", "F05-01 RENOMBRAR"), ("ACTUALIZAR", "F05-01 MOVER"),
        ("ACTUALIZAR", "F05-01 ORDEN"), ("ACTUALIZAR", "F05-01 AMBITO"), ("ACTUALIZAR", "F05-01 DESACTIVAR"),
        ("ACTUALIZAR", "F05-01 REACTIVAR"),
    ]
    snap = h.leer(owner, "SELECT datos_antes->>'enabled', datos_despues->>'enabled' FROM gapto.auditoria "
                         "WHERE registro_id=%s AND motivo='F05-01 DESACTIVAR'", (a,))
    assert snap == [("true", "false")]


@pytest.mark.parametrize("extra", [{"icon_key": "hogar.casa"}, {"presupuestable_default": False}])
def test_renombrar_no_admite_icon_key_ni_presupuestable_default(ctx, extra):
    owner, _, cli = ctx
    a, _ = fh.alta(cli, "Iconos")
    r = fh.cmd(cli, f"{B}/{a}/renombrar", {"nombre": "X", "row_version": 1, **extra})
    assert r.status_code == 422 and _codigo(r) == "ENTRADA_INVALIDA", r.text
    assert h.leer(owner, "SELECT nombre, row_version, icon_key, presupuestable_default "
                         "FROM gapto.categorias_financieras WHERE id=%s", (a,)) == [("Iconos", 1, None, True)]
    assert [(ac, m) for ac, m, _ in fh.auditorias(owner, a)] == [("CREAR", "F05-01 ALTA")]


def test_alta_con_icon_key_no_publicado_es_icono_no_valido_y_no_estructural(ctx):
    owner, _, cli = ctx
    cid = uuid.uuid4()
    r = fh.cmd(cli, fh.BASE, {"id": str(cid), "nombre": "Y", "parent_id": None, "ambito": "GASTO",
                              "presupuestable_default": True, "icon_key": "star"})
    assert r.status_code == 422 and _codigo(r) == "ICONO_CATEGORIA_NO_VALIDO", r.text
    assert h.leer(owner, "SELECT count(*) FROM gapto.categorias_financieras WHERE id=%s", (cid,)) == [(0,)]
    assert fh.auditorias(owner, cid) == []
