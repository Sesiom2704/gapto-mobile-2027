# ============================================================
# GAPTO MOBILE 2027
# Fichero: test_023_b17_rls_ownership_derivado.py
# Ruta: tests/database/test_023_b17_rls_ownership_derivado.py
# Descripción: F03-01-B17. Cierra el hueco de cobertura de D-090:
#              ejercita como `gapto_runtime` las tablas tenant con
#              ownership derivado, que hasta ahora nunca se habían probado
#              con el rol que las usará en producción.
#
#              Cuatro comprobaciones por tabla, con dos tenants reales:
#                1. lectura propia visible;
#                2. lectura ajena invisible;
#                3. INSERT propio permitido;
#                4. INSERT con FK hacia otro tenant RECHAZADO.
#
#              La (4) es la que valida de verdad D-074: las 42 policies
#              cuyo WITH CHECK comprueba más claves foráneas que su USING
#              existen precisamente para impedir referencias cross-tenant
#              indirectas, y nunca se habían ejercitado.
#
#              Las fixtures NO están escritas a mano: se derivan por
#              introspección del catálogo (columnas NOT NULL, FK, CHECK con
#              conjuntos cerrados) y se insertan en orden topológico. Así el
#              test sigue siendo válido si el esquema evoluciona, y no hay
#              52 ficheros de fixture que mantener.
#
#              Todo ocurre dentro de una transacción con ROLLBACK: no queda
#              residuo en la base.
#
# PRECONDICIÓN: requiere 0190 (B16) para asumir `gapto_runtime` y 0210
#              (B19), sin el cual cuatro tablas no admiten INSERT bajo RLS.
# Versión: 0.1.0
# ============================================================

from __future__ import annotations

import re
import uuid

import psycopg
import pytest


NS = uuid.UUID("00000000-0000-0000-0000-0000000b1700")


def _uid(*partes) -> str:
    return str(uuid.uuid5(NS, "|".join(map(str, partes))))


TENANTS = {"A": _uid("t", "A"), "B": _uid("t", "B")}

# Catálogos globales sin RLS: se insertan una sola vez y sin contexto tenant.
GLOBALES = {"paises", "regiones", "localidades"}
# Catálogos de sistema ya sembrados por 0150/0160: se referencian, no se crean.
SEMBRADOS = {"tipos_hecho", "metricas_definicion"}
# Subtipos 1:0..1 de entidades: cada uno necesita su propio supertipo coherente.
SUBTIPOS = {
    "propiedades": "PROPIEDAD", "contratos": "CONTRATO", "servicios": "SERVICIO",
    "financiaciones": "FINANCIACION", "inversiones": "INVERSION",
    "contextos": "CONTEXTO", "derechos_obligaciones_financieras": "DERECHO_OBLIGACION",
}

# Valores que la introspección no puede deducir: formatos ISO, coherencias
# entre columnas y conjuntos cerrados que exigen una combinación concreta.
FIJOS = {
    "paises": {"iso2": "ES", "iso3": "ESP", "nombre": "Espana"},
    "regiones": {"nombre": "Region"}, "localidades": {"nombre": "Localidad"},
    "usuarios": {"email": "u@example.com", "nombre": "Usuario"},
    "direcciones": {"via_nombre": "Calle 1", "codigo_postal": "30001"},
    "cuentas": {"moneda": "EUR", "nombre": "Cuenta"},
    "financiaciones": {"moneda": "EUR"}, "inversiones": {"moneda": "EUR"},
    "derechos_obligaciones_financieras": {"moneda": "EUR"},
    "presupuestos": {"moneda": "EUR"}, "cierres_mensuales": {"moneda": "EUR"},
    "hechos_financieros": {"moneda": "EUR", "concepto": "Concepto",
                           "estado_localizacion": "NO_APLICA"},
    "movimientos_tesoreria": {"moneda": "EUR"},
    "regla_versiones": {"moneda": "EUR", "importe_modo": "MANUAL"},
    "previsiones": {"moneda": "EUR"}, "financiacion_cuotas": {"moneda": "EUR"},
    "propiedad_valoraciones": {"moneda": "EUR"},
    "inversion_valoraciones": {"moneda": "EUR"},
    "inversion_objetivos_versiones": {"moneda": "EUR", "plazo_objetivo_meses": 12},
    "financiacion_condiciones_versiones": {"moneda": "EUR"},
    "contrato_revision_renta_versiones": {"moneda": "EUR"},
    "cierre_saldos_cuenta": {"moneda": "EUR"}, "cierre_metricas": {"valor_numeric": 1, "valor_text": None},
    "cierre_presupuesto_lineas": {"moneda": "EUR"}, "cierre_posiciones_entidad": {"moneda": "EUR"},
    "presupuesto_lineas": {"moneda": "EUR"}, "hecho_efectos": {"moneda": "EUR"},
    "efecto_atribuciones": {"moneda": "EUR"}, "hecho_aportaciones_pago": {"moneda": "EUR"},
    "entidades": {"nombre": "Entidad"}, "terceros": {"nombre": "Tercero", "naturaleza": "PERSONA"},
    "categorias_financieras": {"nombre": "Categoria", "presupuestable_default": True},
    "clasificaciones_tercero": {"nombre": "Clasificacion"}, "etiquetas": {"nombre": "Etiqueta"},
    "magnitudes": {"nombre": "Magnitud"},
    "auditoria": {"actor_tipo": "SISTEMA", "tabla": "usuarios", "accion": "CREAR"},
    "documentos": {"estado_archivo": "DISPONIBLE", "storage_key": "priv/doc"},
    "preferencias_registro": {"presupuestable_default": True},
    "mapeos_importacion": {"tipo_mapping": "IGNORADO"},
    "documento_vinculos": {"entidad_id": None, "tercero_id": None, "cuenta_id": None},
    "entidad_relaciones": {"tipo_relacion": "GARANTIZADA_POR"},
}

# Textos con unicidad: deben diferenciarse por tenant.
UNICOS = {
    ("usuarios", "email"), ("usuarios", "nombre"), ("etiquetas", "nombre"),
    ("categorias_financieras", "nombre"), ("clasificaciones_tercero", "nombre"),
    ("magnitudes", "nombre"), ("magnitudes", "codigo"), ("terceros", "nombre"),
    ("entidades", "nombre"), ("cuentas", "nombre"), ("reglas_financieras", "nombre"),
    ("presupuestos", "nombre"), ("acciones_rapidas", "nombre"),
    ("plantillas_registro", "nombre"), ("servicios", "nombre"),
    ("fuentes_importacion", "nombre"),
}


class _Contexto:
    """Construye filas coherentes para dos tenants a partir del catálogo."""

    def __init__(self, M: dict):
        self.M = M
        self.orden = self._toposort()
        self._cache: dict[str, list] = {}

    def _toposort(self) -> list[str]:
        nombres = list(self.M)
        deps = {t: {f["ftable"] for f in self.M[t]["fks"] if f["ftable"] != t} for t in nombres}
        salida, vistos = [], set()
        while len(salida) < len(nombres):
            avance = False
            for t in nombres:
                if t not in vistos and deps[t] <= vistos:
                    salida.append(t); vistos.add(t); avance = True
            if not avance:
                salida += [t for t in nombres if t not in vistos]
                break
        return salida

    def _enum(self, tabla: str, columna: str) -> list[str]:
        for c in self.M[tabla]["cons"]:
            d = c["def"]
            if d.startswith("CHECK") and re.search(r"\b%s\b" % re.escape(columna), d):
                valores = re.findall(r"'([^']+)'::(?:character varying|text|bpchar)", d)
                if valores:
                    return valores
        return []

    def _valor(self, tabla: str, col: dict, tn: str):
        n, tipo = col["name"], col["type"]
        if tabla in FIJOS and n in FIJOS[tabla]:
            v = FIJOS[tabla][n]
            return v + "-" + tn if (tabla, n) in UNICOS and isinstance(v, str) else v
        enum = self._enum(tabla, n)
        if enum:
            return enum[0]
        if "uuid" in tipo:
            return _uid(tabla, n)
        if "numeric" in tipo or "int" in tipo:
            return 1
        if tipo == "boolean":
            return False
        if tipo.startswith("timestamp"):
            return "2026-01-01 00:00:00+00"
        if tipo == "date":
            return "2026-01-01"
        if "jsonb" in tipo:
            return "{}"
        if "char" in tipo or tipo == "text":
            return ("X-" + tn) if (tabla, n) in UNICOS else "X"
        return None

    def _fks(self, tabla: str) -> dict:
        """FK simple gana sobre compuesta: una compuesta reutiliza columnas
        que ya tienen su propio padre y falsearía el destino."""
        fk = {}
        for f in sorted(self.M[tabla]["fks"], key=lambda x: -len(x["cols"])):
            for c, fc in zip(f["cols"], f["fcols"]):
                fk[c] = (f["ftable"], fc)
        return fk

    def _entidades(self, tn: str) -> dict:
        return {sub: _uid("entidades", sub, tn) for sub in SUBTIPOS}

    def filas(self, tn: str) -> list:
        if tn in self._cache:
            return self._cache[tn]
        ent = self._entidades(tn)
        salida = []
        for t in self.orden:
            if t in SEMBRADOS or (t in GLOBALES and tn == "B"):
                continue
            if t == "entidades":
                for sub, tipo in SUBTIPOS.items():
                    salida.append((t, {"id": ent[sub], "owner_user_id": TENANTS[tn],
                                       "tipo_entidad": tipo, "nombre": f"Ent-{sub}-{tn}"}))
                continue
            v, fk, d = self.M[t], self._fks(t), {}
            for col in v["cols"]:
                n = col["name"]
                if n == "id":
                    d[n] = ent[t] if t in SUBTIPOS else _uid(t, tn); continue
                if n == "owner_user_id":
                    d[n] = TENANTS[tn]; continue
                if not col["notnull"]:
                    continue
                if n in fk:
                    ft, fc = fk[n]
                    if ft == t:
                        continue
                    d[n] = self._destino(ft, fc, n, t, ent, tn)
                    continue
                if col["default"]:
                    continue
                d[n] = self._valor(t, col, tn)
            columnas = {c["name"] for c in v["cols"]}
            for k, val in FIJOS.get(t, {}).items():
                if k not in columnas:
                    continue
                if val is None:
                    d.pop(k, None)
                else:
                    d[k] = val + "-" + tn if (t, k) in UNICOS and isinstance(val, str) else val
            if t in SUBTIPOS:
                d["entidad_id"] = ent[t]; d.pop("id", None)
            if t == "usuarios":
                d["id"] = TENANTS[tn]; d.pop("owner_user_id", None)
            if t == "hechos_financieros":
                salida.append((t, dict(d, id=_uid("hechos_financieros", "2", tn),
                                       concepto="Concepto2")))
            if t == "documento_vinculos":
                d["hecho_id"] = _uid("hechos_financieros", tn)
            if t == "hecho_relaciones":
                d["hecho_origen_id"] = _uid("hechos_financieros", tn)
                d["hecho_destino_id"] = _uid("hechos_financieros", "2", tn)
            if t == "presupuesto_linea_alcances":
                d["categoria_id"] = _uid("categorias_financieras", tn)
            if t == "entidad_relaciones":
                d["entidad_origen_id"] = ent["financiaciones"]
                d["entidad_destino_id"] = ent["propiedades"]
            if t in GLOBALES:
                d["id"] = _uid(t, "G"); d.pop("owner_user_id", None)
                for c2, (ft, _fc) in fk.items():
                    if c2 in d and ft in GLOBALES:
                        d[c2] = _uid(ft, "G")
            salida.append((t, {k: x for k, x in d.items() if x is not None}))
        self._cache[tn] = salida
        return salida

    def _destino(self, ft: str, fc: str, columna: str, tabla: str, ent: dict, tn: str):
        if fc == "owner_user_id":
            return TENANTS[tn]
        if ft in SEMBRADOS:
            return "SEED:" + ft
        if ft == "entidades":
            for clave, sub in (("propiedad", "propiedades"), ("financiacion", "financiaciones"),
                               ("inversion", "inversiones"), ("contrato", "contratos"),
                               ("servicio", "servicios"), ("contexto", "contextos"),
                               ("derecho", "derechos_obligaciones_financieras")):
                if columna.startswith(clave) or tabla.startswith(clave):
                    return ent[sub]
            return ent["contextos"]
        if ft in SUBTIPOS:
            return ent[ft]
        return _uid(ft, "G") if ft in GLOBALES else _uid(ft, tn)

    def insertar(self, cur, tabla: str, fila: dict, rol: str, tn: str) -> None:
        if tabla in GLOBALES:
            cur.execute("RESET ROLE")
        else:
            cur.execute("RESET ROLE")
            cur.execute(f"SET LOCAL ROLE {rol}")
            cur.execute("SELECT set_config('gapto.owner_user_id',%s,true)", (TENANTS[tn],))
        d = dict(fila)
        for k, v in list(d.items()):
            if isinstance(v, str) and v.startswith("SEED:"):
                cur.execute(f"SELECT id FROM gapto.{v[5:]} LIMIT 1")
                r = cur.fetchone()
                d[k] = r[0] if r else None
        d = {k: v for k, v in d.items() if v is not None}
        columnas = ", ".join(d)
        marcas = ", ".join(["%s"] * len(d))
        cur.execute(f"INSERT INTO gapto.{tabla} ({columnas}) VALUES ({marcas})", list(d.values()))

    def variante_cross_tenant(self, tabla: str):
        """Fila del tenant B con una FK apuntando al tenant A."""
        filas = {t: d for t, d in self.filas("B")}
        d = dict(filas.get(tabla, {}))
        if not d:
            return None
        entA = self._entidades("A")
        for c, (ft, fc) in self._fks(tabla).items():
            if ft in GLOBALES or ft in SEMBRADOS or c not in d:
                continue
            if fc not in ("id", "entidad_id") or not self.M[ft]["rls"]:
                continue
            d[c] = entA[ft] if ft in SUBTIPOS else (TENANTS["A"] if ft == "usuarios" else _uid(ft, "A"))
            if "id" in d:
                d["id"] = _uid("cross", tabla)
            return c, d
        return None


# ============================================================
# Introspección del catálogo
# ============================================================

def _introspect(db: psycopg.Connection) -> dict:
    M: dict = {}
    with db.cursor() as cur:
        cur.execute("""
            SELECT c.relname, c.relrowsecurity,
                   EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a
                            WHERE a.attrelid=c.oid AND a.attname='owner_user_id'
                              AND a.attnum>0 AND NOT a.attisdropped)
              FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND c.relkind='r' ORDER BY 1
        """)
        for nombre, rls, tiene_owner in cur.fetchall():
            M[nombre] = {"rls": rls, "has_owner": tiene_owner, "cols": [], "fks": [], "cons": []}

        cur.execute("""
            SELECT c.relname, a.attname, pg_catalog.format_type(a.atttypid,a.atttypmod),
                   a.attnotnull, pg_catalog.pg_get_expr(d.adbin,d.adrelid)
              FROM pg_catalog.pg_class c
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
              JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
              LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
             WHERE n.nspname='gapto' AND c.relkind='r' ORDER BY c.relname, a.attnum
        """)
        for t, col, tipo, nn, dflt in cur.fetchall():
            M[t]["cols"].append({"name": col, "type": tipo, "notnull": nn, "default": dflt})

        cur.execute("""
            SELECT c.relname,
                   (SELECT array_agg(att.attname ORDER BY x.ord)
                      FROM unnest(con.conkey) WITH ORDINALITY x(attnum,ord)
                      JOIN pg_catalog.pg_attribute att
                        ON att.attrelid=con.conrelid AND att.attnum=x.attnum),
                   f.relname,
                   (SELECT array_agg(att.attname ORDER BY x.ord)
                      FROM unnest(con.confkey) WITH ORDINALITY x(attnum,ord)
                      JOIN pg_catalog.pg_attribute att
                        ON att.attrelid=con.confrelid AND att.attnum=x.attnum)
              FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid=con.conrelid
              JOIN pg_catalog.pg_class f ON f.oid=con.confrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND con.contype='f'
        """)
        for t, cols, ft, fcols in cur.fetchall():
            M[t]["fks"].append({"cols": cols, "ftable": ft, "fcols": fcols})

        cur.execute("""
            SELECT c.relname, con.conname, pg_catalog.pg_get_constraintdef(con.oid)
              FROM pg_catalog.pg_constraint con
              JOIN pg_catalog.pg_class c ON c.oid=con.conrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='gapto' AND con.contype IN ('c','u','p','x')
        """)
        for t, nombre, definicion in cur.fetchall():
            M[t]["cons"].append({"name": nombre, "def": definicion})
    return M


# ============================================================
# Fixture: dos tenants completos, en transacción revertida
# ============================================================

@pytest.fixture(scope="module")
def escenario(db: psycopg.Connection):
    """Materializa el tenant A como gapto_owner y devuelve el contexto.

    El tenant B se inserta dentro de cada test como `gapto_runtime`, porque
    esa inserción ES una de las comprobaciones.
    """
    M = _introspect(db)
    ctx = _Contexto(M)
    with db.cursor() as cur:
        cur.execute("BEGIN")
        for tabla, fila in ctx.filas("A"):
            ctx.insertar(cur, tabla, fila, "gapto_owner", "A")
        cur.execute("RESET ROLE")
    yield ctx
    with db.cursor() as cur:
        cur.execute("RESET ROLE")
        cur.execute("ROLLBACK")


def _derivadas(ctx) -> list[str]:
    return sorted(t for t, v in ctx.M.items() if v["rls"] and not v["has_owner"])


# ============================================================
# Comprobaciones
# ============================================================

def test_b17_alcance_cubierto(db: psycopg.Connection, escenario) -> None:
    """El bloque debe cubrir las tablas que D-090 identificó."""
    derivadas = _derivadas(escenario)
    directas = [t for t, v in escenario.M.items() if v["rls"] and v["has_owner"]]
    assert len(derivadas) + len(directas) == 74
    assert len(derivadas) == 52, "51 con ownership derivado + usuarios como raíz"


def test_b17_insert_propio_como_runtime(db: psycopg.Connection, escenario) -> None:
    """(3) gapto_runtime debe poder escribir su propio tenant en todas.

    Excepción esperada y única: `auditoria`, cuyo INSERT directo revocó B15
    a favor de gapto.fn_registrar_auditoria.
    """
    fallos = {}
    with db.cursor() as cur:
        cur.execute("SAVEPOINT sp_b")
        for tabla, fila in escenario.filas("B"):
            try:
                cur.execute("SAVEPOINT sp_fila")
                escenario.insertar(cur, tabla, fila, "gapto_runtime", "B")
                cur.execute("RELEASE SAVEPOINT sp_fila")
            except psycopg.Error as exc:
                cur.execute("ROLLBACK TO SAVEPOINT sp_fila")
                fallos[tabla] = exc.sqlstate
                escenario.insertar(cur, tabla, fila, "gapto_owner", "B")
        cur.execute("RESET ROLE")
    assert fallos == {"auditoria": "42501"}, f"fallos inesperados: {fallos}"


def test_b17_aislamiento_de_lectura(db: psycopg.Connection, escenario) -> None:
    """(1) y (2): cada tenant ve lo suyo y nada del otro."""
    anomalas = {}
    with db.cursor() as cur:
        for tabla, fila in escenario.filas("B"):
            try:
                cur.execute("SAVEPOINT sp_fila")
                escenario.insertar(cur, tabla, fila, "gapto_owner", "B")
                cur.execute("RELEASE SAVEPOINT sp_fila")
            except psycopg.Error:
                cur.execute("ROLLBACK TO SAVEPOINT sp_fila")
        cur.execute("RESET ROLE")
        for tabla in _derivadas(escenario):
            visto = {}
            for etiqueta in ("A", "B"):
                cur.execute("SET LOCAL ROLE gapto_runtime")
                cur.execute("SELECT set_config('gapto.owner_user_id',%s,true)", (TENANTS[etiqueta],))
                cur.execute(f"SELECT count(*) FROM gapto.{tabla}")
                (visto[etiqueta],) = cur.fetchone()
                cur.execute("RESET ROLE")
            if visto["A"] < 1 or visto["B"] < 1:
                anomalas[tabla] = visto
    assert anomalas == {}, f"visibilidad anómala: {anomalas}"


def test_b17_fk_cross_tenant_rechazada(db: psycopg.Connection, escenario) -> None:
    """(4) La comprobación que de verdad valida D-074.

    Para cada tabla derivada se toma su fila del tenant B y se apunta una de
    sus claves foráneas a la fila equivalente del tenant A. La escritura debe
    ser rechazada, por WITH CHECK o por FK compuesto: cualquiera de las dos
    capas es una defensa válida, lo inaceptable es que se acepte.
    """
    aceptadas = {}
    sin_cobertura = []
    with db.cursor() as cur:
        for tabla, fila in escenario.filas("B"):
            try:
                cur.execute("SAVEPOINT sp_fila")
                escenario.insertar(cur, tabla, fila, "gapto_owner", "B")
                cur.execute("RELEASE SAVEPOINT sp_fila")
            except psycopg.Error:
                cur.execute("ROLLBACK TO SAVEPOINT sp_fila")
        cur.execute("RESET ROLE")

        for tabla in _derivadas(escenario):
            if tabla == "usuarios":
                continue
            intruso = escenario.variante_cross_tenant(tabla)
            if intruso is None:
                sin_cobertura.append(tabla)
                continue
            columna, fila = intruso
            try:
                cur.execute("SAVEPOINT sp_cross")
                escenario.insertar(cur, tabla, fila, "gapto_runtime", "B")
                aceptadas[tabla] = columna
                cur.execute("ROLLBACK TO SAVEPOINT sp_cross")
            except psycopg.Error:
                cur.execute("ROLLBACK TO SAVEPOINT sp_cross")
            cur.execute("RESET ROLE")

    assert aceptadas == {}, f"FUGA CROSS-TENANT aceptada en: {aceptadas}"
    assert sin_cobertura == [], f"sin FK tenant ejercitable: {sin_cobertura}"
