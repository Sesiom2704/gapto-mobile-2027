# ============================================================
# GAPTO MOBILE 2027
# Fichero: f06_01_b2_helpers.py
# Ruta: tests/api/f06_01_b2_helpers.py
# Descripcion: Helpers de las pruebas de B2 · Compra (F06 T1-F06 B2 N1). Siembra O2′ de los oraculos v0.2
#   (200.000 € con arras y firma desde C1, ITP, notaria y agencia; YO 60 / A 40) con fechas de 2026 (el reloj de
#   las pruebas es 2026-10-10 y las participaciones de cuenta de vs01_api_helpers empiezan el 2026-01-01):
#     escritura 2026-03-20 (= corte de O2′), arras 2026-02-15, agencia economica 2026-02-28 (antes de la
#     titularidad, que empieza en la escritura: caso de la fecha de escritura, AJ-TR1-10), ITP y notaria con
#     fecha economica 2026-03-20.
#   C1 cuenta corriente 100 % propia; C2 cuenta corriente compartida 50 % YO / 50 % A (liquidez atribuible).
#   Huella de estado de las tablas de la compra y de la auditoria (O6.14 bis) leida como superusuario solo para
#   comparar. Los consumidores de 0352 se activan en el propio test con `habilitar_0352(monkeypatch)`.
# Version: 0.1.0 (F06 T1-F06 B2 N1)
# ============================================================

from __future__ import annotations

import hashlib
import uuid

import psycopg

import f05_05_helpers as x5
import f06_01_b1_helpers as b
import vs01_api_helpers as h

HOY = b.HOY
ESCRITURA = "2026-03-20"
CORTE = "2026-03-20"
#: tablas de la compra + auditoria + propiedad (O6.14 bis: rechazos y replay sin escrituras ni auditoria)
TABLAS_COMPRA = ("hechos_financieros", "hecho_efectos", "efecto_atribuciones", "hecho_entidades", "hecho_relaciones",
                 "movimientos_tesoreria", "hecho_movimientos_tesoreria", "propiedades", "entidades",
                 "propiedad_valoraciones", "auditoria", "entidad_participaciones", "efecto_cuentas")


def habilitar_0352(monkeypatch, valor: bool = True) -> None:
    from app.patrimonio import habilitacion
    monkeypatch.setattr(habilitacion, "CONSUMIDORES_0352_HABILITADOS", valor)


def huella() -> str:
    return b.huella(TABLAS_COMPRA)


def leer_coste(cli, pid, a_fecha: str | None = None) -> dict:
    r = cli.get(f"/v1/propiedades/{pid}/coste", params={"a_fecha": a_fecha} if a_fecha else None, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()["coste"]


def titularidad_en(cli, pid, fecha: str) -> list[dict]:
    r = cli.get(f"/v1/propiedades/{pid}/titularidad-en-fecha", params={"fecha": fecha}, headers=h.AUTH)
    assert r.status_code == 200, r.text
    return r.json()["partes"]


class Lab:
    """Owner, cliente con reloj HOY, propiedad P (YO 60 / A 40 desde la escritura), C1 propia y C2 compartida."""

    def __init__(self, titularidad_desde: str = ESCRITURA, fecha_adquisicion: str | None = ESCRITURA,
                 titularidad: dict | None = None):
        self.owner, self.actor, self.cli, self.c1, _ = x5.entorno(b.RELOJ)
        self.ta = b.tercero(self.cli, "Ana")
        tit = titularidad or b.compartida([b.yo("60"), b.de(self.ta, "40")], desde=titularidad_desde)
        p = b.crear(self.cli, b.alta(tit, fecha_adquisicion=fecha_adquisicion))
        self.pid = p["id"]
        partes = p["titularidad"]["partes"]
        self.yo = next((x["actor_id"] for x in partes if x["yo"]), str(self.actor))
        self.a = next((x["actor_id"] for x in partes if not x["yo"]), None)
        self.c2 = h.crear_cuenta(self.owner, [(self.actor, 50), (uuid.UUID(self.a), 50)]) if self.a else self.c1

    def version(self) -> int:
        return b.leer(self.cli, self.pid)["row_version"]

    def propuesta(self, fecha: str = ESCRITURA, criterio: str = "TITULARIDAD_EN_FECHA_ESCRITURA") -> dict:
        partes = [{"actor_id": p["actor_id"], "porcentaje": p["porcentaje"]} for p in titularidad_en(self.cli, self.pid, fecha)]
        return {"criterio": criterio, "fecha_referencia": fecha, "partes": partes}

    def peticion(self, *, intencion_id=None, gastos: list[dict] | None = None, atribucion: dict | None = None,
                 completitud=None, version: int | None = None, **extra) -> dict:
        cuerpo = {
            "intencion_id": str(intencion_id or uuid.uuid4()),
            "row_version_esperada": self.version() if version is None else version,
            "fecha_escritura": ESCRITURA, "precio": "200000.00",
            "pagos_propios": [
                {"linea_id": str(uuid.uuid4()), "rol": "ARRAS", "cuenta_id": str(self.c1), "fecha_pago": "2026-02-15",
                 "importe": "20000.00"},
                {"linea_id": str(uuid.uuid4()), "rol": "FIRMA", "cuenta_id": str(self.c1), "fecha_pago": ESCRITURA,
                 "importe": "180000.00"}],
            "gastos": self.gastos_o2() if gastos is None else gastos,
            "atribucion": atribucion or {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": self.propuesta()},
        }
        if completitud is not None:
            cuerpo["completitud_adquisicion"] = completitud
        cuerpo.update(extra)
        return cuerpo

    def gastos_o2(self) -> list[dict]:
        return [self.gasto("ITP", "12000.00", ESCRITURA, "2026-03-25"),
                self.gasto("NOTARIA_REGISTRO_GESTORIA", "1200.00", ESCRITURA, "2026-03-30"),
                self.gasto("AGENCIA", "3630.00", "2026-02-28", "2026-02-28", cuenta=self.c2)]

    def gasto(self, concepto: str, importe: str, economica: str, pago: str, cuenta=None, linea_id=None,
              nota: str | None = None) -> dict:
        g = {"linea_id": str(linea_id or uuid.uuid4()), "concepto": concepto, "cuenta_id": str(cuenta or self.c1),
             "fecha_economica": economica, "fecha_pago": pago, "importe": importe}
        if nota is not None:
            g["nota"] = nota
        return g

    def compra(self, cuerpo: dict, cli=None):
        return (cli or self.cli).post(f"/v1/propiedades/{self.pid}/compra", json=cuerpo, headers=h.AUTH)

    def gasto_posterior(self, cuerpo: dict, cli=None):
        return (cli or self.cli).post(f"/v1/propiedades/{self.pid}/compra/gastos", json=cuerpo, headers=h.AUTH)

    def peticion03(self, linea: dict, *, intencion_id=None, atribucion: dict | None = None, completitud=None,
                   huella_vista: str | None = None, version: int | None = None) -> dict:
        cuerpo = {"intencion_id": str(intencion_id or uuid.uuid4()),
                  "row_version_esperada": self.version() if version is None else version, "linea": linea,
                  "atribucion": atribucion or {"modo": "SEGUN_TITULARIDAD_ACEPTADA", "propuesta_vista": self.propuesta(
                      linea["fecha_economica"], "TITULARIDAD_EN_FECHA_ECONOMICA")}}
        if completitud is not None:
            cuerpo["completitud_adquisicion"] = completitud
        if huella_vista is not None:
            cuerpo["huella_conjunto_vista"] = huella_vista
        return cuerpo

    def declarar(self, ambito: str, completo: bool, fecha_corte: str | None = None, huella: str | None = None,
                 intencion_id=None, version: int | None = None, cli=None):
        cuerpo = {"intencion_id": str(intencion_id or uuid.uuid4()),
                  "row_version_esperada": self.version() if version is None else version, "ambito": ambito,
                  "completo": completo}
        if fecha_corte is not None:
            cuerpo["fecha_corte"] = fecha_corte
        if huella is not None:
            cuerpo["huella_conjunto_vista"] = huella
        return (cli or self.cli).post(f"/v1/propiedades/{self.pid}/completitud", json=cuerpo, headers=h.AUTH)

    def coste(self, a_fecha: str | None = None) -> dict:
        return leer_coste(self.cli, self.pid, a_fecha)

    def sql(self, sql: str, params: tuple = ()) -> list[tuple]:
        return h.leer(self.owner, sql, params)


def auditorias(owner, request_id) -> list[tuple]:
    return h.leer(owner, "SELECT tabla, accion FROM gapto.auditoria WHERE request_id = %s ORDER BY created_at",
                  (str(request_id),))


def como_owner(owner, sql: str, params: tuple = ()) -> None:
    """Fixture declarado (oraculos O6.16, O6.19, O6.21, O10.22, O10.24): SQL bajo gapto_owner con la GUC."""
    with psycopg.connect(h.dsn()) as c, c.transaction():
        c.execute("SET LOCAL ROLE gapto_owner")
        c.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
        c.execute(sql, params)


def sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ writers certificados por servicio (laboratorio)
def unidad():
    import contextlib

    from app.core.unidad_trabajo import UnidadDeTrabajo

    @contextlib.contextmanager
    def abrir():
        with psycopg.connect(h.dsn()) as c:
            yield c
    return UnidadDeTrabajo(abrir, rol_runtime="gapto_runtime", max_intentos=3, espera_inicial_s=0.001)


def ctx(owner):
    from app.core.contexto import ContextoOperacion
    return ContextoOperacion.de_usuario(owner, request_id=uuid.uuid4())


def hecho_version(owner, hecho_id) -> int:
    return h.leer(owner, "SELECT row_version FROM gapto.hechos_financieros WHERE id = %s", (hecho_id,))[0][0]


def op21_importe(owner, hecho_id, efecto_id, importe: str):
    """OP-21 generico por servicio (no hay ruta, §II.7): cambia importe_delta conservando efecto_id."""
    import decimal

    from app.patrimonio.atribucion import repartir
    from app.services.correcciones_service import CorreccionesService, DatosCorreccion
    atrs = h.leer(owner, "SELECT id, porcentaje_aplicado FROM gapto.efecto_atribuciones WHERE efecto_id = %s "
                         "ORDER BY actor_id", (efecto_id,))
    nuevo = decimal.Decimal(importe)
    cambios = {}
    if atrs:
        reparto = repartir(nuevo.quantize(decimal.Decimal("0.01")), [(a, p) for a, p in atrs])
        cambios = {a: {"importe_atribuido": reparto[a]} for a, _ in atrs}
    datos = DatosCorreccion(hecho_id=hecho_id, row_version_esperada=hecho_version(owner, hecho_id), motivo="lab B2",
                            efectos_a_actualizar={efecto_id: {"importe_delta": nuevo}},
                            atribuciones_a_actualizar=cambios)
    return CorreccionesService(unidad()).corregir(ctx(owner), datos)


def op03_anular(owner, hecho_id):
    from app.services.hechos_service import HechosService
    from app.services.previsiones_service import impacto_correccion_ancla
    return HechosService(unidad(), impacto_ancla=impacto_correccion_ancla).anular_hecho(
        ctx(owner), hecho_id=hecho_id, row_version_esperada=hecho_version(owner, hecho_id), motivo_anulacion="lab B2")


def op02_fecha(owner, hecho_id, fecha: str):
    import datetime as dt

    from app.core.modelos import CamposCorreccion
    from app.services.hechos_service import HechosService
    from app.services.previsiones_service import impacto_correccion_ancla
    return HechosService(unidad(), impacto_ancla=impacto_correccion_ancla).corregir_hecho(
        ctx(owner), hecho_id=hecho_id, row_version_esperada=hecho_version(owner, hecho_id),
        campos=CamposCorreccion(fecha_hecho=dt.date.fromisoformat(fecha)), motivo="lab B2")


def componente_fixture(owner, pid, fecha: str, importe: str, causa: str = "ADQUISICION", *, tipo: str | None = None,
                       nivel_efecto: bool = True) -> tuple[uuid.UUID, uuid.UUID]:
    """Componente escrito «por otra via» (SQL como gapto_owner con la GUC): sustituye a C-MEJ-02 (B3) en MEJORAS,
    a un hecho de otro tipo (O10.22) o a un AFECTA_A de nivel hecho (O10.24). Sin pago ni atribucion."""
    hecho, ef = uuid.uuid4(), uuid.uuid4()
    tipo = tipo or ("ADQUISICION_PATRIMONIAL" if causa == "ADQUISICION" else "MEJORA_PATRIMONIAL")
    with psycopg.connect(h.dsn()) as c, c.transaction():
        c.execute("SELECT set_config('gapto.owner_user_id', %s, true)", (str(owner),))
        c.execute("SET LOCAL ROLE gapto_owner")
        tid = c.execute("SELECT id FROM gapto.tipos_hecho WHERE codigo = %s", (tipo,)).fetchone()[0]
        c.execute("INSERT INTO gapto.hechos_financieros (id, owner_user_id, tipo_hecho_id, fecha_hecho, moneda, "
                  "presupuestable, estado_localizacion, importe_total, concepto) VALUES (%s, %s, %s, %s, 'EUR', "
                  "false, 'NO_APLICA', %s, 'fixture')", (hecho, owner, tid, fecha, importe))
        c.execute("INSERT INTO gapto.hecho_efectos (id, hecho_id, tipo_efecto, importe_delta, estado_atribucion, "
                  "causa_valor_activo) VALUES (%s, %s, 'VALOR_ACTIVO', %s, 'NO_DISPONIBLE', %s)",
                  (ef, hecho, importe, causa))
        c.execute("INSERT INTO gapto.hecho_entidades (id, hecho_id, efecto_id, entidad_id, tipo_relacion, principal, "
                  "owner_user_id) VALUES (%s, %s, %s, %s, 'AFECTA_A', true, %s)",
                  (uuid.uuid4(), hecho, ef if nivel_efecto else None, pid, owner))
    return hecho, ef


def hechos_de_la_compra(owner, pid) -> list[tuple]:
    """(hecho, efecto, fecha, importe) de los componentes de adquisicion de la propiedad."""
    return h.leer(owner, "SELECT h.id, e.id, h.fecha_hecho, e.importe_delta FROM gapto.hechos_financieros h "
                         "JOIN gapto.hecho_efectos e ON e.hecho_id = h.id JOIN gapto.hecho_entidades x ON "
                         "x.hecho_id = h.id AND x.efecto_id = e.id AND x.entidad_id = %s "
                         "WHERE e.causa_valor_activo = 'ADQUISICION' ORDER BY h.fecha_hecho, e.importe_delta", (pid,))
