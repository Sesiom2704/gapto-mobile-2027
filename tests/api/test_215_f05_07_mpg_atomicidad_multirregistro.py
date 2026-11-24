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
# Version: 0.2.0 (F05-D052 paso 2; F05 §66.A): comando nuevo C03_gasto_reembolsable
#   (POST /v1/intenciones/gasto-reembolsable: writer de actor + OP-22) en el barrido,
#   con una empresa sin actor (el alta perezosa va dentro de la transaccion).
# Version: 0.3.0 (F06-01 B1 Propiedad, lote 12; PR1-01, CC-R1-07): las cuatro rutas POST
#   de B1 (alta con cotitular sin actor, editar, titularidad con cotitular nuevo y
#   valoracion) entran en el barrido: son multirregistro (actor + entidad + subtipo +
#   participaciones o valoracion + auditoria) y el inventario cerrado las exige.
# Version: 0.4.0 (F06 T1-F06 B2 N1; adaptacion declarada y minima por la regla permanente de T1-F06, decision 2
#   de Moises del 2026-11-12 `e0adb0be…`): las rutas POST de B2 entran en el inventario cerrado. La compra y el
#   gasto de la compra despues (OP-22 por raiz + PARTE_DE + valoraciones + version + auditoria) son
#   multirregistro y entran en el barrido; C-PROP-05 (/completitud) se clasifica como ajena: consumidor de 0352
#   con la habilitacion bloqueada (404 sin escribir, O10.29). Nada de F05 cambia.
# Version: 0.5.0 (F06 T1-F06 B3 N1; adaptacion declarada y minima por la regla v2 de T1-F06, decision de Moises del
#   2026-11-12 `5b54258a…`, mandato B3 N1 §5.1): las tres rutas POST de B3 entran en el inventario cerrado y en el
#   barrido (lista cerrada): C-MEJ-01 con derecho de cobro confirmado (OP-22 + posicion + auditoria), C-MEJ-02 (OP-22
#   sin pago) y C-MEJ-03 (tipo del hecho, efecto destino, atribuciones, vinculo y retiradas, con auditoria por paso).
#   Ninguna ruta ni comando previo cambia.
# Version: 0.5.1 (F06 T2-F06 · B1-R; adaptacion declarada y minima por L-06 ampliada, decision de Moises del lote 34
#   `d593a15d…`, solo test_inventario_post_cerrado): la ruta POST nueva de C-PROP-03bis se clasifica en el
#   inventario cerrado como ajena a F05-06, con su bateria de atomicidad propia (test_260, O-B1R-19). Ninguna ruta
#   ni comando previo cambia.
# Version: 0.5.2 (F06 T2-F06 · CAT-VIV; adaptacion declarada y minima por L-06 ampliada, solo
#   test_inventario_post_cerrado): la ruta POST nueva de C-CAT-VIV-01 (/v1/categorias/{categoria_id}/vivienda) se
#   clasifica como ajena a F05-06 junto a las de F05-01 (una sola escritura de catalogo bajo advisory, como /icono;
#   O-CV-02 en test_280). Ninguna ruta ni comando previo cambia.
# Version: 0.6.0 (F06 T2-F06 A3-0352 · L-06 ampliada (b0d56b0d…), solo test_inventario_post_cerrado y su barrido):
#   C-PROP-05 (/completitud) deja de ser «consumidor de 0352 no habilitado (404, O10.29)»: A3-0352 lo habilita (L-05).
#   Escribe la terna (propiedades), row_version (entidades) y la auditoria en una transaccion: sale de AJENAS_A_F05_06
#   y ENTRA en el barrido de fallo inyectado (B2_completitud: propiedad con fecha de adquisicion y compra, declaracion
#   ADQUISICION con la huella vigente). El discriminante se SUSTITUYE por uno mas fuerte (rechazo tras su escritura
#   auditada sin escrituras parciales). Ninguna otra ruta ni comando cambia.
# Version: 0.6.1 (F06 T3-F06 bloque 2 F06-01H, paso 4; L-06-T3 del mandato v1.1 §5.1, solo test_inventario_post_cerrado):
#   la ruta POST nueva de W-HIP-00 (/v1/hipotecas/cuadro, contrato v0.4 §3.1 y §7.1) se clasifica como ajena a F05-06:
#   POST SIN ESCRITURA (no abre transaccion; huella de toda la base identica en test_288). Ninguna otra ruta ni
#   comando cambia; el barrido no cambia.
# Version: 0.6.2 (F06 T3-F06 bloque 2 F06-01H, paso 6; L-06-T3 del mandato v1.1 §5.1, solo test_inventario_post_cerrado):
#   la ruta POST de W-HIP-02 (/v1/hipotecas/{financiacion_id}/cuotas/{numero}/pago, contrato v0.4 §3.4 y §7.1) se
#   clasifica como ajena a F05-06: atomicidad propia (una transaccion de UnidadDeTrabajo, OP-22 adscrito; rechazo =
#   estado identico, test_293). Ninguna otra ruta ni comando cambia; el barrido no cambia.
# Version: 0.6.3 (F06 T3-F06 bloque 2 F06-01H, paso 7; L-06-T3 del mandato v1.1 §5.1, solo test_inventario_post_cerrado):
#   la ruta POST de W-HIP-03/04 (/v1/hipotecas/{financiacion_id}/revision, contrato v0.4 §3.5 y §7.1) se clasifica
#   como ajena a F05-06: atomicidad propia (una transaccion de UnidadDeTrabajo; rechazo y defecto CUADRO_NO_CUADRA
#   tras escribir = estado identico, test_294 O-H25). Ninguna otra ruta ni comando cambia; el barrido no cambia.
# Version: 0.6.4 (F06 T3-F06 bloque 3 F06-02/03, paso 8; L-06-T3 del mandato v1.2 §5, añadido en el handoff, solo
#   test_inventario_post_cerrado): las 23 rutas POST de contratos, servicios y terceros (contratos/rutas.py) se
#   clasifican como ajenas a F05-06: atomicidad propia (savepoint de ejecutar_escritura; rechazo = estado identico,
#   test_300..306). Ninguna otra ruta ni comando cambia; el barrido no cambia.
# Version: 0.6.5 (F06 T6 · fila 76, levantamiento del STOP D de test_215 autorizado por Moises (v1.0), solo
#   test_inventario_post_cerrado): la ruta POST nueva de S5 (/v1/preferencias/ambos, «Ambos» al recordar) se clasifica
#   como ajena a F05-06 con atomicidad propia: las dos preferencias van en UNA transaccion de UnidadDeTrabajo (todas o
#   ninguna; test_321 con fallo inyectado en la segunda escritura: cero filas y cero auditoria; M-S5-01 MUERTO).
#   Ninguna otra entrada se quita, reclasifica ni relaja; la logica de la guarda y el barrido no cambian.
# ============================================================

from __future__ import annotations

import uuid

import psycopg
import pytest

import f05_05_helpers as x
import f05_06_m2_helpers as m2
import f05_06_m3_helpers as r3
import f05_06_m5_helpers as m5
import f05_d052_c03_helpers as c03
import f06_01_b1_helpers as b1
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


def p_c03_gasto_reembolsable(t):
    owner, actor, cli, cta, ahorro = t
    empresa = c03.tercero(cli, "Empresa SL")  # sin actor: el alta perezosa va dentro
    return c03.RUTA, c03.cuerpo(cta, empresa, "40.00", importe="60.00")


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


# F06-01 B1 ······································································
def p_b1_alta_propiedad(t):
    owner, actor, cli, cta, ahorro = t
    cotitular = b1.tercero(cli, "Elena Cotitular")  # sin actor: el writer de actores va dentro
    return "/v1/propiedades", b1.alta(b1.compartida([b1.yo("50"), b1.de(cotitular, "50")]))


def _propiedad(t):
    owner, actor, cli, cta, ahorro = t
    return b1.crear(cli, b1.alta())


def p_b1_editar_propiedad(t):
    prop = _propiedad(t)
    return f"/v1/propiedades/{prop['id']}/editar", {"intencion_id": _iid(), "row_version_esperada": prop["row_version"],
                                                    "nombre": "Piso Gran Vía 2", "habitaciones": 3}


def p_b1_titularidad(t):
    owner, actor, cli, cta, ahorro = t
    prop = _propiedad(t)
    cotitular = b1.tercero(cli, "Marta Cotitular")  # sin actor: el writer de actores va dentro
    return f"/v1/propiedades/{prop['id']}/titularidad", b1.cambio(
        prop, b1.compartida([b1.yo("60"), b1.de(cotitular, "40")], desde="2026-11-01"))


def p_b1_valoracion(t):
    prop = _propiedad(t)
    return f"/v1/propiedades/{prop['id']}/valoraciones", b1.valoracion(prop)


# F06-01 B2 ······································································
def _compra_b2(t, prop):
    owner, actor, cli, cta, ahorro = t
    return {"intencion_id": _iid(), "row_version_esperada": prop["row_version"], "fecha_escritura": "2026-03-20",
            "precio": "1000.00", "pagos_propios": [{"linea_id": _iid(), "rol": "FIRMA", "cuenta_id": str(cta),
                                                    "fecha_pago": "2026-03-20", "importe": "1000.00"}],
            "gastos": [{"linea_id": _iid(), "concepto": "ITP", "cuenta_id": str(cta), "fecha_economica": "2026-03-20",
                        "fecha_pago": "2026-03-20", "importe": "60.00"}],
            "atribucion": {"modo": "MANUAL", "partes": [{"actor_id": str(actor), "porcentaje": "100"}]}}


def p_b2_compra(t):
    prop = _propiedad(t)
    return f"/v1/propiedades/{prop['id']}/compra", _compra_b2(t, prop)


def p_b2_completitud(t):
    """A3-0352: C-PROP-05 habilitado. Propiedad con fecha de adquisicion (R15-a) y compra; declaracion de ADQUISICION
    con la huella vigente al corte."""
    owner, actor, cli, cta, ahorro = t
    prop = b1.crear(cli, b1.alta(fecha_adquisicion="2026-01-01"))
    r = cli.post(f"/v1/propiedades/{prop['id']}/compra", json=_compra_b2(t, prop), headers=h.AUTH)
    assert r.status_code == 200, r.text
    prop = r.json()["propiedad"]
    coste = cli.get(f"/v1/propiedades/{prop['id']}/coste", params={"a_fecha": "2026-03-20"}, headers=h.AUTH)
    assert coste.status_code == 200, coste.text
    return f"/v1/propiedades/{prop['id']}/completitud", {
        "intencion_id": _iid(), "row_version_esperada": prop["row_version"], "ambito": "ADQUISICION", "completo": True,
        "fecha_corte": "2026-03-20", "huella_conjunto_vista": coste.json()["coste"]["ADQUISICION"]["huella_conjunto"]}


def p_b2_gasto_posterior(t):
    owner, actor, cli, cta, ahorro = t
    prop = _propiedad(t)
    r = cli.post(f"/v1/propiedades/{prop['id']}/compra", json=_compra_b2(t, prop), headers=h.AUTH)
    assert r.status_code == 200, r.text
    prop = r.json()["propiedad"]
    return f"/v1/propiedades/{prop['id']}/compra/gastos", {
        "intencion_id": _iid(), "row_version_esperada": prop["row_version"],
        "linea": {"linea_id": _iid(), "concepto": "OTRO", "cuenta_id": str(cta), "fecha_economica": "2026-04-02",
                  "fecha_pago": "2026-04-02", "importe": "40.00"},
        "atribucion": {"modo": "MANUAL", "partes": [{"actor_id": str(actor), "porcentaje": "100"}]}}


# F06-01 B3 ······································································
def _propiedad_b3(t):
    owner, actor, cli, cta, ahorro = t
    cotitular = b1.tercero(cli, "Tomás Cotitular")
    prop = b1.crear(cli, b1.alta(b1.compartida([b1.yo("50"), b1.de(cotitular, "50")], desde="2026-01-01")))
    partes = [{"actor_id": p["actor_id"], "porcentaje": p["porcentaje"]} for p in prop["titularidad"]["partes"]]
    otro = next(p["actor_id"] for p in prop["titularidad"]["partes"] if not p["yo"])
    return prop, partes, otro


def _gasto_b3(t, prop, partes, otro, clase="MEJORA", deuda="SI"):
    owner, actor, cli, cta, ahorro = t
    return {"intencion_id": _iid(), "propiedad_id": prop["id"], "clase": clase, "importe": "300.00",
            "fecha_hecho": "2026-05-15", "cuenta_id": str(cta),
            "atribucion": {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": {
                "criterio": "TITULARIDAD_EN_FECHA_HECHO", "fecha_referencia": "2026-05-15", "partes": partes}},
            "deuda": [{"actor_id": otro, "me_debe": deuda}],
            "derechos_confirmados": [{"actor_id": otro, "importe": "150.00"}] if deuda == "SI" else []}


def p_b3_gasto_propiedad(t):
    prop, partes, otro = _propiedad_b3(t)
    return "/v1/intenciones/gasto-propiedad", _gasto_b3(t, prop, partes, otro)


def p_b3_mejora_historica(t):
    prop, partes, otro = _propiedad_b3(t)
    return f"/v1/propiedades/{prop['id']}/mejoras-historicas", {
        "intencion_id": _iid(), "row_version_esperada": prop["row_version"], "descripcion": "Cocina",
        "importe": "3000.00", "fecha": "2026-02-10",
        "atribucion": {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": {
            "criterio": "TITULARIDAD_EN_FECHA_HECHO", "fecha_referencia": "2026-02-10", "partes": partes}},
        "deuda": [{"actor_id": otro, "me_debe": "NO"}]}


def p_b3_corregir_clase(t):
    owner, actor, cli, cta, ahorro = t
    prop, partes, otro = _propiedad_b3(t)
    alta = _gasto_b3(t, prop, partes, otro, deuda="NO")
    assert cli.post("/v1/intenciones/gasto-propiedad", json=alta, headers=h.AUTH).status_code == 200
    base = f"/v1/propiedades/{prop['id']}/gastos/{alta['intencion_id']}"
    g = cli.get(base, headers=h.AUTH).json()
    comparacion = cli.get(f"{base}/impacto-correccion", params={"clase_nueva": "REPARACION", "presupuestable": "true"},
                          headers=h.AUTH).json()["comparacion"]
    categoria = x.categoria(owner, "Hogar B3")
    return f"{base}/corregir-clase", {
        "intencion_id": g["intencion_correccion_id"], "row_version_esperada": g["row_version"],
        "clase_nueva": "REPARACION", "motivo": "Error de captura", "categoria_id": str(categoria),
        "presupuestable": True, "comparacion_vista": comparacion}


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
    "C03_gasto_reembolsable": ("/v1/intenciones/gasto-reembolsable", p_c03_gasto_reembolsable),
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
    "B1_alta_propiedad": ("/v1/propiedades", p_b1_alta_propiedad),
    "B1_editar_propiedad": ("/v1/propiedades/{propiedad_id}/editar", p_b1_editar_propiedad),
    "B1_titularidad": ("/v1/propiedades/{propiedad_id}/titularidad", p_b1_titularidad),
    "B1_valoracion": ("/v1/propiedades/{propiedad_id}/valoraciones", p_b1_valoracion),
    "B2_compra": ("/v1/propiedades/{propiedad_id}/compra", p_b2_compra),
    "B2_gasto_posterior": ("/v1/propiedades/{propiedad_id}/compra/gastos", p_b2_gasto_posterior),
    "B2_completitud": ("/v1/propiedades/{propiedad_id}/completitud", p_b2_completitud),
    "B3_gasto_propiedad": ("/v1/intenciones/gasto-propiedad", p_b3_gasto_propiedad),
    "B3_mejora_historica": ("/v1/propiedades/{propiedad_id}/mejoras-historicas", p_b3_mejora_historica),
    "B3_corregir_clase": ("/v1/propiedades/{propiedad_id}/gastos/{hecho_id}/corregir-clase", p_b3_corregir_clase),
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
    "/v1/categorias/{categoria_id}/vivienda": "F06 T2-F06 CAT-VIV C-CAT-VIV-01: una escritura de catalogo (test_280 "
                                              "O-CV-02)",
    "/v1/propiedades/{propiedad_id}/titularidad/inicio": "F06 T2-F06 B1-R C-PROP-03bis: atomicidad propia (savepoint "
                                                          "de comando; test_260 O-B1R-19 y O-B1R-05..08)",
    "/v1/hipotecas/cuadro": "F06 T3-F06 F06-01H W-HIP-00: POST SIN ESCRITURA (vista previa del cuadro; test_288, "
                            "huella de toda la base identica antes y despues)",
    "/v1/hipotecas/{financiacion_id}/cuotas/{numero}/pago": "F06 T3-F06 F06-01H W-HIP-02: atomicidad propia (una "
                                                            "transaccion, OP-22 adscrito; test_293 estado identico)",
    "/v1/hipotecas/{financiacion_id}/revision": "F06 T3-F06 F06-01H W-HIP-03/04: atomicidad propia (una transaccion; "
                                                "test_294 O-H25 estado identico, tambien tras CUADRO_NO_CUADRA)",
    **{ruta: "F06 T3-F06 bloque 3 F06-02/03: atomicidad propia (una transaccion de UnidadDeTrabajo; la escritura va en "
             "el savepoint de ejecutar_escritura y un rechazo deja el estado identico, test_300..306; sucesor con fallo "
             "inyectado, test_302 O-3)"
       for ruta in ("/v1/intenciones/contrato-alquiler", "/v1/contratos/{contrato_id}/editar",
                    "/v1/contratos/{contrato_id}/terminar", "/v1/contratos/{contrato_id}/corregir-terminacion",
                    "/v1/contratos/{contrato_id}/formalizar", "/v1/contratos/{contrato_id}/cancelar",
                    "/v1/contratos/{contrato_id}/sucesor", "/v1/contratos/{contrato_id}/personas",
                    "/v1/contratos/{contrato_id}/personas/{persona_id}/cerrar",
                    "/v1/contratos/{contrato_id}/personas/{persona_id}/corregir",
                    "/v1/contratos/{contrato_id}/clausula", "/v1/contratos/{contrato_id}/clausula/{version_id}/corregir",
                    "/v1/intenciones/servicio", "/v1/servicios/{servicio_id}/editar", "/v1/servicios/{servicio_id}/baja",
                    "/v1/contratos/{contrato_id}/servicios/{servicio_id}", "/v1/terceros/{tercero_id}/roles",
                    "/v1/terceros/{tercero_id}/clasificaciones", "/v1/clasificaciones-tercero",
                    "/v1/clasificaciones-tercero/{clasificacion_id}/renombrar",
                    "/v1/clasificaciones-tercero/{clasificacion_id}/mover",
                    "/v1/clasificaciones-tercero/{clasificacion_id}/desactivar",
                    "/v1/clasificaciones-tercero/{clasificacion_id}/reactivar")},
    "/v1/preferencias/ambos": "F06 T6 S5 «Ambos»: atomicidad propia (una transaccion de UnidadDeTrabajo, todas o "
                              "ninguna; test_321 fallo inyectado en la segunda escritura sin filas ni auditoria)",
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
