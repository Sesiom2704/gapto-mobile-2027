# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_215_f05_07_mpg_atomicidad_multirregistro.py
# Ruta: tests/api/test_215_f05_07_mpg_atomicidad_multirregistro.py
# Descripcion: MANT-PRE-GATE · atomicidad de los comandos multirregistro de
#   F05-06 (F05 §64.3 F05-D050, AJ-04; R-CAT-RECHAZO-COMMIT §32.6/§35.7).
#   Inventario: C:/DEV/evidencia_f0507_gate/C/atomicidad/INVENTARIO_MULTIRREGISTRO.md
#
#   Para CADA comando multirregistro expuesto por F05-06 (M1, M2, M3, M4, M5
#   y M5-B) se barren TODOS sus puntos de inyeccion: el punto k es la k-esima
#   escritura auditada de la peticion (auditoria_repository.registrar, que
#   todo writer invoca en la MISMA transaccion justo despues de su mutacion).
#   En el punto k se deja terminar la escritura real y su auditoria y se lanza
#   un rechazo funcional (ErrorMotor VERSION_DESFASADA, 409): es decir, el
#   rechazo llega SIEMPRE despues de al menos una escritura. Oraculo, en este
#   orden:
#     1. ESTADO FISICO: foto de TODAS las tablas del schema gapto (recuento y
#        md5 del contenido ordenado, leida con un rol que no filtra por RLS,
#        para ver tambien escrituras en otro tenant) identica antes y despues;
#     2. la respuesta es el rechazo confirmado (409 VERSION_DESFASADA).
#   El barrido sigue con k+1 reenviando la MISMA intencion hasta que la
#   peticion ya no alcanza el punto k: esa ultima peticion debe confirmar
#   (200) y cambiar al menos dos tablas (el comando es multirregistro y el
#   reintento tras un rechazo completa el agregado sin restos del anterior).
#   El comando se ejecuta por HTTP (create_app) como gapto_runtime con RLS
#   (SET LOCAL ROLE de la UnidadDeTrabajo), nunca como superusuario.
#
#   Ningun comando de F05-06 admite efectos previos autorizados DENTRO de su
#   transaccion: la foto exige cero cambios. (Las altas de tercero/persona son
#   comandos HTTP propios y confirmados antes; aqui forman parte del fixture.)
#
#   Inventario cerrado: toda ruta POST de la app esta clasificada como comando
#   F05-06 de este barrido o como ajena a F05-06 con su bloque. Una ruta POST
#   nueva sin clasificar hace fallar `test_inventario_post_cerrado`.
#   Discriminacion: scripts/dev/mutantes_mant_pre_gate_atomicidad.py (cada
#   frontera convierte en valor un rechazo posterior a la primera escritura).
#   Exige GAPTO_TEST_DATABASE_URL (base desechable; estos tests confirman filas).
# Version: 0.1.0 (F05-07/GATE adenda 2, MANT-PRE-GATE atomicidad multirregistro)
# Version: 0.1.1 (F05-07/GATE adenda 2, integracion MANT-PRE-GATE: renumerado de test_212 a test_215;
#   test_212 es G9 de f05-gate-g2 y 213/214 son de F04-R3)
# ============================================================

from __future__ import annotations

import uuid

import psycopg
import pytest

import f05_05_helpers as x
import f05_06_m2_helpers as m2
import f05_06_m3_helpers as r3
import f05_06_m5_helpers as m5
import vs01_api_helpers as h

#: Tope de puntos de inyeccion por comando (defensa contra un bucle sin fin).
MAX_PUNTOS = 60
CODIGO_INYECTADO = "VERSION_DESFASADA"
MOTIVO = "F05-07 MANT-PRE-GATE fallo inyectado"


# ------------------------------------------------------------------ inyector
class _Inyector:
    """Envuelve auditoria_repository.registrar: la escritura auditada y su
    auditoria se ejecutan de verdad y, en la k-esima llamada de la peticion,
    se lanza el rechazo funcional (ErrorMotor) dentro de la transaccion."""

    def __init__(self, monkeypatch) -> None:
        from app.repositories import auditoria_repository as aud

        self._real = aud.registrar
        self.k: int | None = None
        self.llamadas = 0
        self.disparado = False
        monkeypatch.setattr(aud, "registrar", self._registrar)

    def armar(self, k: int) -> None:
        self.k, self.llamadas, self.disparado = k, 0, False

    def desarmar(self) -> None:
        self.k = None

    def _registrar(self, sesion, **kw):
        from app.core.errores import CodigoError, ErrorMotor

        resultado = self._real(sesion, **kw)
        if self.k is None:
            return resultado
        self.llamadas += 1
        if self.llamadas == self.k:
            self.disparado = True
            raise ErrorMotor(CodigoError.VERSION_DESFASADA, f"{MOTIVO} (punto {self.k}, tras escribir {kw['tabla']})")
        return resultado


@pytest.fixture()
def iny(monkeypatch):
    return _Inyector(monkeypatch)


# ------------------------------------------------------------------ oraculo fisico
def _foto() -> dict[str, tuple]:
    """(recuento, md5 del contenido ordenado) de cada tabla de gapto, leida con
    un rol que ignora la RLS (ve todos los tenants)."""
    with psycopg.connect(h.dsn()) as c:
        if not c.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user").fetchone()[0]:
            pytest.fail("El oraculo fisico necesita un rol que no filtre por RLS (superusuario del cluster desechable).")
        tablas = [f[0] for f in c.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'gapto' ORDER BY tablename").fetchall()]
        assert tablas, "schema gapto sin tablas"
        return {t: c.execute(
            f"SELECT count(*), md5(COALESCE(string_agg(x::text, '|' ORDER BY x::text), '')) FROM gapto.{t} x"
        ).fetchone() for t in tablas}


def _diferencias(antes: dict, despues: dict) -> list[str]:
    return sorted(t for t in set(antes) | set(despues) if antes.get(t) != despues.get(t))


def _barrido(cli, iny: _Inyector, url: str, cuerpo: dict) -> tuple[int, list[str]]:
    """Barre los puntos 1..N; devuelve (N, tablas cambiadas por la confirmacion)."""
    for k in range(1, MAX_PUNTOS + 1):
        antes = _foto()
        iny.armar(k)
        try:
            r = cli.post(url, json=cuerpo, headers=h.AUTH)
        finally:
            disparado = iny.disparado
            iny.desarmar()
        despues = _foto()
        cambios = _diferencias(antes, despues)
        if disparado:
            # 1. Estado fisico: el rechazo confirmado no deja escrituras parciales.
            assert cambios == [], f"punto {k}: escrituras parciales en {cambios} (respuesta {r.status_code} {r.text})"
            # 2. La respuesta es el rechazo, no un exito ni un 500.
            assert (r.status_code, r.json().get("codigo")) == (409, CODIGO_INYECTADO), f"punto {k}: {r.text}"
            continue
        assert r.status_code == 200, f"sin inyeccion en el punto {k} la peticion debe confirmar: {r.text}"
        assert k > 1, "el comando no llego a ninguna escritura auditada: no se ha probado nada"
        assert len(cambios) >= 2, f"el comando no es multirregistro: {cambios}"
        return k - 1, cambios
    pytest.fail(f"mas de {MAX_PUNTOS} puntos de inyeccion: revisar el barrido")


# ------------------------------------------------------------------ entorno y preparadores
@pytest.fixture()
def t():
    owner, actor, cli, cta, ahorro = m5.entorno()
    return owner, actor, cli, cta, ahorro


def _iid() -> str:
    return str(uuid.uuid4())


def _ed(cli, hid) -> dict:
    r = cli.get(f"/v1/hechos/{hid}/edicion", headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def _ok(r):
    assert r.status_code == 200, r.text
    return r


# M2 ·············································································
def p_m2_devolucion_cobrada(t):
    owner, actor, cli, cta, ahorro = t
    compra = m2.compra(cli, cta)
    return m2.url_devoluciones(compra), m2.cuerpo("40.00", abono=m2.cobrado(cta))


def p_m2_abono(t):
    owner, actor, cli, cta, ahorro = t
    compra = m2.compra(cli, cta)
    c, r = m2.devolver(cli, compra, importe="40.00")
    _ok(r)
    return m2.url_abono(c["intencion_id"]), {"intencion_id": _iid(), "cuenta_id": str(cta), "fecha": "2026-09-12"}


# M3 ·············································································
def p_m3_gasto_compartido(t):
    owner, actor, cli, cta, ahorro = t
    tania, carlos = r3.persona(cli, "Tania"), r3.persona(cli, "Carlos")  # sin actor: el alta perezosa va dentro
    return r3.GASTO_COMPARTIDO, r3.cuerpo(
        "44.50", pagado_por=r3.con_cuenta(cta), fecha=r3.FECHA_CENA, nota="Cena con amigos",
        reparto=r3.repartir("14.50", (tania, "15.00", "SI"), (carlos, "15.00", "NO")))


def _cena(t):
    owner, actor, cli, cta, ahorro = t
    tania, carlos = r3.persona(cli, "Tania"), r3.persona(cli, "Carlos")
    c, r = r3.cena(cli, cta, tania, carlos)
    _ok(r)
    return uuid.UUID(c["intencion_id"]), tania, carlos


def p_m3_cobro(t):
    owner, actor, cli, cta, ahorro = t
    hecho, _, _ = _cena(t)
    entidad = r3.entidad_de_posicion(owner, hecho)
    return f"/v1/posiciones/{entidad}/cobro", {"intencion_id": _iid(), "importe": "15.00", "cuenta_id": str(cta),
                                               "fecha": "2026-10-10"}


def p_m3_pago(t):
    owner, actor, cli, cta, ahorro = t
    tania = r3.persona(cli, "Tania")
    c, r = r3.peluqueria(cli, tania)
    _ok(r)
    entidad = r3.entidad_de_posicion(owner, uuid.UUID(c["intencion_id"]))
    return f"/v1/posiciones/{entidad}/pago", {"intencion_id": _iid(), "importe": "15.00", "cuenta_id": str(cta),
                                              "fecha": "2026-10-10"}


def p_m3_perdon(t):
    owner, actor, cli, cta, ahorro = t
    hecho, _, _ = _cena(t)
    entidad = r3.entidad_de_posicion(owner, hecho)
    return f"/v1/posiciones/{entidad}/perdon", {"intencion_id": _iid(), "importe": "15.00", "fecha": "2026-10-10"}


def p_m3_corregir_reparto(t):
    owner, actor, cli, cta, ahorro = t
    hecho, tania, _ = _cena(t)
    yo, ella = r3.atribucion_de(owner, hecho, actor), r3.atribucion_de(owner, hecho, r3.actor_de(owner, tania))
    return f"/v1/hechos/{hecho}/reparto", {
        "row_version": r3.version(owner, hecho), "motivo": "Otro dato mal elegido",
        "partes": [{"atribucion_id": str(yo), "importe": "9.50"}, {"atribucion_id": str(ella), "importe": "20.00"}]}


# M4 ·············································································
def p_m4_capacidad_activar(t):
    owner, actor, cli, cta, ahorro = t
    cuenta = h.crear_cuenta(owner, [(actor, 100)], capacidades=("PAGAR_GASTO",))
    rv = h.leer(owner, "SELECT row_version FROM gapto.cuentas WHERE id = %s", (cuenta,))[0][0]
    return f"/v1/cuentas/{cuenta}/capacidades/RECIBIR_INGRESO/activar", {"row_version": rv}


# M5 ·············································································
def p_m5_vincular(t):
    owner, actor, cli, cta, ahorro = t
    _, cabeza = m5.rodante(owner, cuenta_salida=cta)
    hecho = x.gasto(cli, cta, fecha="2026-10-01", importe="45.00")
    return f"/v1/previsiones/{cabeza}/vincular", {
        "intencion_id": _iid(), "row_version": m5.version(owner, cabeza), "hecho_id": str(hecho),
        "importe_a_vincular": "45.00", "marcar_realizada": True}


def p_m5_omitir(t):
    owner, actor, cli, cta, ahorro = t
    _, cabeza = m5.rodante(owner, cuenta_salida=cta)
    return f"/v1/previsiones/{cabeza}/omitir", {"intencion_id": _iid(), "row_version": m5.version(owner, cabeza),
                                                "motivo": "No hubo este mes"}


def p_m5_gasto_pagado_prevision(t):
    owner, actor, cli, cta, ahorro = t
    _, cabeza = m5.rodante(owner, cuenta_salida=cta)
    c = h.intencion(cta, fecha_hecho="2026-10-01", importe="45.00", concepto=None, intencion_id=_iid())
    c["prevision"] = m5.bloque(owner, cabeza, True)
    return m5.GASTO, c


def p_m5_ingreso_prevision(t):
    owner, actor, cli, cta, ahorro = t
    pid = m5.prevision(owner, "Nómina", tipo="INGRESO", importe="1500.00", cuenta_entrada=cta)
    return m5.INGRESO, {
        "intencion_id": _iid(), "importe": "1500.00", "moneda": "EUR", "fecha_hecho": "2026-10-01",
        "cuenta_id": str(cta), "presupuestable": True, "atribucion": "SOLO_MIO",
        "categoria": {"estado": "SIN_CATEGORIA"}, "nota": None, "prevision": m5.bloque(owner, pid, True)}


def p_m5_transferencia_prevision(t):
    owner, actor, cli, cta, ahorro = t
    pid = m5.prevision(owner, "Ahorro mensual", tipo="TRANSFERENCIA", importe="500.00", cuenta_salida=cta,
                       cuenta_entrada=ahorro)
    return m5.TRANSF, {
        "intencion_id": _iid(), "importe": "500.00", "moneda": "EUR", "fecha_hecho": "2026-10-01",
        "cuenta_origen_id": str(cta), "cuenta_destino_id": str(ahorro), "nota": None,
        "prevision": m5.bloque(owner, pid, True)}


def p_m5_gasto_compartido_prevision(t):
    owner, actor, cli, cta, ahorro = t
    _, cabeza = m5.rodante(owner, cuenta_salida=cta)
    tania = r3.persona(cli, "Tania")
    c = r3.cuerpo("45.00", pagado_por=r3.con_cuenta(cta), fecha="2026-10-01", nota="Seguro coche",
                  reparto=r3.repartir("15.00", (tania, "30.00", "SI")))
    c["prevision"] = m5.bloque(owner, cabeza, True)
    return r3.GASTO_COMPARTIDO, c


# M5-B ···········································································
def p_m5b_dar_por_realizada(t):
    owner, actor, cli, cta, ahorro = t
    _, cabeza = m5.rodante(owner, cuenta_salida=cta)
    _, r = m5.gasto_desde(cli, owner, cta, cabeza, "20.00", False, fecha="2026-10-01")
    _ok(r)
    return f"/v1/previsiones/{cabeza}/dar-por-realizada", {
        "intencion_id": _iid(), "row_version": m5.version(owner, cabeza), "motivo": "la factura definitiva fue menor"}


def p_m5b_reabrir(t):
    owner, actor, cli, cta, ahorro = t
    _, cabeza = m5.rodante(owner, cuenta_salida=cta)
    c, r = m5.omitir(cli, owner, cabeza)
    _ok(r)
    sucesor = uuid.uuid5(uuid.UUID(c["intencion_id"]), "sucesor")
    return f"/v1/previsiones/{cabeza}/reabrir", {
        "intencion_id": _iid(), "row_version": m5.version(owner, cabeza), "motivo": "la marqué por error",
        "sucesor_row_version": m5.version(owner, sucesor)}


# M1 ·············································································
def p_m1_corregir_pago(t):
    owner, actor, cli, cta, ahorro = t
    hid = x.gasto(cli, cta, importe="48.72")
    e = _ed(cli, hid)
    return f"/v1/hechos/{hid}/corregir-pago", {
        "intencion_id": _iid(), "row_version": e["row_version"],
        "movimiento_row_version": e["movimientos"][0]["row_version"], "motivo": "Importe mal tecleado",
        "error_de_registro": True, "importe": "47.82"}


def p_m1_corregir_transferencia(t):
    owner, actor, cli, cta, ahorro = t
    hid = x.transferencia(cli, cta, ahorro, importe="500.00")
    e = _ed(cli, hid)
    return f"/v1/transferencias/{hid}/corregir", {
        "intencion_id": _iid(), "row_version": e["row_version"],
        "movimientos_row_version": {m["movimiento_id"]: m["row_version"] for m in e["movimientos"]},
        "motivo": "Importe mal tecleado", "error_de_registro": True, "importe": "450.00"}


def p_m1_anular_duplicado(t):
    owner, actor, cli, cta, ahorro = t
    hid = x.gasto(cli, cta, importe="48.72")
    e = _ed(cli, hid)
    return f"/v1/hechos/{hid}/anular-duplicado", {
        "intencion_id": _iid(), "row_version": e["row_version"],
        "movimientos_row_version": {m["movimiento_id"]: m["row_version"] for m in e["movimientos"]},
        "motivo": "Lo registré dos veces", "duplicado_declarado": True}


def p_m1_corregir_categoria_v3(t):
    owner, actor, cli, cta, ahorro = t
    hogar, obras = x.categoria(owner, "Hogar"), x.categoria(owner, "Obras")
    hid = x.gasto(cli, cta, importe="65.00", categoria_id=hogar, concepto="FONTANERO BAÑO")
    m2.marcar_v3(owner, hid)
    e = _ed(cli, hid)
    return f"/v1/hechos/{hid}/corregir-categoria", {
        "intencion_id": _iid(), "row_version": e["row_version"], "motivo": "Categoría mal asignada en V3",
        "categoria_id": str(obras)}


#: id -> (plantilla de ruta POST, preparador). La plantilla es la de la app (inventario cerrado).
COMANDOS = {
    "M2_devolucion_cobrada": ("/v1/hechos/{origen_id}/devoluciones", p_m2_devolucion_cobrada),
    "M2_abono": ("/v1/hechos/{devolucion_id}/abono", p_m2_abono),
    "M3_gasto_compartido": ("/v1/intenciones/gasto-compartido", p_m3_gasto_compartido),
    "M3_cobro": ("/v1/posiciones/{entidad_id}/cobro", p_m3_cobro),
    "M3_pago": ("/v1/posiciones/{entidad_id}/pago", p_m3_pago),
    "M3_perdon": ("/v1/posiciones/{entidad_id}/perdon", p_m3_perdon),
    "M3_corregir_reparto": ("/v1/hechos/{hecho_id}/reparto", p_m3_corregir_reparto),
    "M4_capacidad_activar": ("/v1/cuentas/{cuenta_id}/capacidades/{capacidad}/activar", p_m4_capacidad_activar),
    "M5_vincular": ("/v1/previsiones/{prevision_id}/vincular", p_m5_vincular),
    "M5_omitir": ("/v1/previsiones/{prevision_id}/omitir", p_m5_omitir),
    "M5_gasto_pagado_prevision": ("/v1/intenciones/gasto-pagado", p_m5_gasto_pagado_prevision),
    "M5_ingreso_prevision": ("/v1/intenciones/ingreso-cobrado", p_m5_ingreso_prevision),
    "M5_transferencia_prevision": ("/v1/intenciones/transferencia", p_m5_transferencia_prevision),
    "M5_gasto_compartido_prevision": ("/v1/intenciones/gasto-compartido", p_m5_gasto_compartido_prevision),
    "M5B_dar_por_realizada": ("/v1/previsiones/{prevision_id}/dar-por-realizada", p_m5b_dar_por_realizada),
    "M5B_reabrir": ("/v1/previsiones/{prevision_id}/reabrir", p_m5b_reabrir),
    "M1_corregir_pago": ("/v1/hechos/{hecho_id}/corregir-pago", p_m1_corregir_pago),
    "M1_corregir_transferencia": ("/v1/transferencias/{hecho_id}/corregir", p_m1_corregir_transferencia),
    "M1_anular_duplicado": ("/v1/hechos/{hecho_id}/anular-duplicado", p_m1_anular_duplicado),
    "M1_corregir_categoria_v3": ("/v1/hechos/{hecho_id}/corregir-categoria", p_m1_corregir_categoria_v3),
}

#: Comandos multirregistro F05-06 cubiertos por la misma frontera que otro del
#: barrido (misma funcion transaccional, otra rama del motor). Se clasifican
#: para cerrar el inventario; la prueba de su frontera es la indicada.
CUBIERTOS_POR_FRONTERA = {
    "/v1/cuentas/{cuenta_id}/capacidades/{capacidad}/desactivar": "M4_capacidad_activar (capacidades.servicio.cambiar)",
}

#: Rutas POST ajenas a F05-06 (otro bloque, con su propia bateria de atomicidad
#: o de un solo registro). Clasificarlas aqui es explicito: una ruta nueva
#: debe entrar en COMANDOS (con su barrido) o aqui, con su motivo.
AJENAS_A_F05_06 = {
    "/v1/categorias": "F05-01", "/v1/categorias/{categoria_id}/renombrar": "F05-01",
    "/v1/categorias/{categoria_id}/mover": "F05-01", "/v1/categorias/{categoria_id}/desactivar": "F05-01 (test_164)",
    "/v1/categorias/{categoria_id}/reactivar": "F05-01", "/v1/categorias/{categoria_id}/orden": "F05-01",
    "/v1/categorias/{categoria_id}/ambito": "F05-01", "/v1/categorias/reordenar": "F05-01 S6-ORDEN",
    "/v1/categorias/onboarding": "F05-03 (test_181)", "/v1/categorias/{categoria_id}/icono": "F05-01",
    "/v1/categorias/{categoria_id}/magnitudes": "F05-01 S7-MAG (test_164)",
    "/v1/categorias/{categoria_id}/magnitudes/reordenar": "F05-01 S7-MAG (test_164)",
    "/v1/categorias/{categoria_id}/magnitudes/{asociacion_id}/obligatoria": "F05-01 S7-MAG (test_164)",
    "/v1/categorias/{categoria_id}/magnitudes/{asociacion_id}/retirar": "F05-01 S7-MAG (test_164)",
    "/v1/magnitudes/{magnitud_id}/renombrar": "F05-01 S7-MAG", "/v1/magnitudes/{magnitud_id}/deshabilitar": "F05-01 S7-MAG",
    "/v1/magnitudes/{magnitud_id}/rehabilitar": "F05-01 S7-MAG",
    "/v1/preferencias": "F05-02", "/v1/preferencias/{preferencia_id}/editar": "F05-02",
    "/v1/preferencias/{preferencia_id}/desactivar": "F05-02", "/v1/preferencias/{preferencia_id}/reactivar": "F05-02",
    "/v1/terceros": "F05-04", "/v1/terceros/{tercero_id}/editar": "F05-04",
    "/v1/terceros/{tercero_id}/desactivar": "F05-04", "/v1/terceros/{tercero_id}/reactivar": "F05-04",
    "/v1/contextos": "F05-04", "/v1/contextos/{contexto_id}/editar": "F05-04",
    "/v1/contextos/{contexto_id}/desactivar": "F05-04", "/v1/contextos/{contexto_id}/reactivar": "F05-04",
    "/v1/plantillas": "F05-03 (test_179)", "/v1/plantillas/{plantilla_id}/editar": "F05-03 (test_179)",
    "/v1/plantillas/{plantilla_id}/desactivar": "F05-03 (test_179)",
    "/v1/plantillas/{plantilla_id}/reactivar": "F05-03 (test_179)",
    "/v1/acciones-rapidas": "F05-03", "/v1/acciones-rapidas/reordenar": "F05-03",
    "/v1/acciones-rapidas/{accion_id}/editar": "F05-03", "/v1/acciones-rapidas/{accion_id}/desactivar": "F05-03",
    "/v1/afinidades": "F05-05", "/v1/afinidades/{afinidad_id}/retirar": "F05-05",
}


# ------------------------------------------------------------------ pruebas de fallo inyectado
@pytest.mark.parametrize("comando", list(COMANDOS))
def test_rechazo_tras_cada_escritura_no_deja_escrituras_parciales(t, iny, comando, record_property):
    owner, actor, cli, cta, ahorro = t
    plantilla, preparar = COMANDOS[comando]
    url, cuerpo = preparar(t)
    puntos, cambios = _barrido(cli, iny, url, cuerpo)
    # Para el inventario (junit): puntos de inyeccion barridos y tablas que escribe la confirmacion.
    record_property("puntos_inyeccion", puntos)
    record_property("tablas_escritas", ",".join(cambios))
    assert puntos >= 1, (comando, puntos, cambios)


# ------------------------------------------------------------------ inventario cerrado
def test_inventario_post_cerrado(t):
    owner, actor, cli, cta, ahorro = t
    rutas = {r.path for r in cli.app.routes if "POST" in (getattr(r, "methods", None) or set())}
    barridas = {plantilla for plantilla, _ in COMANDOS.values()}
    clasificadas = barridas | set(CUBIERTOS_POR_FRONTERA) | set(AJENAS_A_F05_06)
    assert not (barridas & set(AJENAS_A_F05_06)) and not (set(CUBIERTOS_POR_FRONTERA) & set(AJENAS_A_F05_06))
    assert rutas - clasificadas == set(), f"rutas POST sin clasificar en el inventario multirregistro: {rutas - clasificadas}"
    assert clasificadas - rutas == set(), f"el inventario cita rutas que ya no existen: {clasificadas - rutas}"
