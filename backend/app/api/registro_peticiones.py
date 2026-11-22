# ============================================================
# GAPTO MOBILE 2027
# Fichero: registro_peticiones.py
# Ruta: backend/app/api/registro_peticiones.py
# Descripcion: Registro de peticiones HTTP en JSONL (AJ-05 ampliado + R-C7-07; diseno v0.2 §6; dictamen R2 AJ-R2-07).
#
#   Que es: trazabilidad OPERATIVA de mejor esfuerzo. Dos eventos por peticion: RECIBIDA (antes del enrutado, sin
#   ruta) y TERMINADA (plantilla de ruta resuelta o NO_RESUELTA). RECIBIDA prueba que el backend registro la
#   recepcion; TERMINADA, una finalizacion observada. Ninguna prueba que el cliente recibiera la respuesta, y una
#   RECIBIDA sin TERMINADA no prueba por si sola una caida (tambien puede ser un fallo del registro).
#
#   Que NO es: auditoria durable. La confirmacion de escrituras la da `gapto.auditoria` en la base.
#   - Sin fsync por evento: cada linea se escribe y se vacia (flush) al buffer del sistema operativo, que no es lo
#     mismo que sincronizarla en almacenamiento fisico. Una caida del sistema o un corte de energia pueden perder las
#     ultimas lineas; un lector tolera una ultima linea truncada.
#   - Un solo proceso uvicorn (vigente): un cerrojo serializa la escritura entre hilos del proceso. Con varios
#     procesos escribiendo el mismo fichero el registro NO es valido (riesgo declarado).
#   - Rotacion diaria por fecha UTC en el nombre (`peticiones-AAAAMMDD.jsonl`) y retencion de 30 dias: al cambiar de
#     dia se borran los ficheros `peticiones-*.jsonl` con fecha anterior a la retencion. Nada mas se borra.
#   - Directorio `GAPTO_LOG_DIR`, FUERA del repositorio y solo del usuario del backend (ENV-DEV:
#     C:\DEV\gapto-envdev\logs).
#
#   Fallos de almacenamiento:
#   - Al ARRANCAR (fail-closed): `RegistroPeticiones.abrir` escribe una linea real de comprobacion, la relee y
#     verifica su contenido; si no puede, lanza `RegistroNoDisponible` y el backend no arranca.
#   - EN MARCHA (fail-open): un fallo de escritura (disco lleno, permisos, fichero bloqueado...) NUNCA altera el codigo
#     HTTP, el cuerpo, las cabeceras funcionales ni el resultado transaccional, tampoco si ocurre durante una excepcion
#     del backend. Se cuenta (`fallos`) y se avisa por consola con un texto fijo: sin cuerpo, sin mensaje de la
#     excepcion, sin cabeceras, sin token ni DSN.
#
#   Contenido: nunca cuerpo, importes, conceptos, `Authorization`, token ni DSN (tampoco dentro de mensajes de
#   excepcion: solo se registra el NOMBRE del tipo). Las cabeceras del cliente se aceptan solo como UUID canonico de
#   36 caracteres; si no, `INVALIDO`. JSON con `json.dumps` (sin interpolar texto).
# Version: 0.1.0 (F06 T4 · AJ-05 ampliado + R-C7-07, mandato b4ff6b70…)
# ============================================================

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import sys
import threading
import uuid
from typing import Any, Callable

RETENCION_DIAS = 30
PREFIJO = "peticiones-"
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
AVISO_CONSOLA = "AVISO gapto: no se ha podido escribir el registro de peticiones (la respuesta no cambia)."


class RegistroNoDisponible(RuntimeError):
    """El registro no se puede escribir al arrancar: el backend no arranca (fail-closed)."""


def uuid_de_cabecera(valor: str | None) -> str | None:
    """`None` si no viene; el UUID canonico (minusculas, 36 caracteres) si lo es; `INVALIDO` en cualquier otro caso."""
    if valor is None:
        return None
    v = valor.strip().lower()
    return v if len(v) == 36 and _UUID.match(v) else "INVALIDO"


class RegistroPeticiones:
    """Escritor JSONL de un proceso. Usar `abrir` (comprueba la escritura real al arrancar)."""

    def __init__(self, directorio: pathlib.Path, *, hoy: Callable[[], dt.date] | None = None,
                 consola: Callable[[str], None] | None = None) -> None:
        self._dir = directorio
        self._hoy = hoy or (lambda: dt.datetime.now(dt.timezone.utc).date())
        self._consola = consola or (lambda texto: print(texto, file=sys.stderr, flush=True))
        self._cerrojo = threading.Lock()
        self._fecha_purgada: dt.date | None = None
        self.fallos = 0

    @classmethod
    def abrir(cls, directorio: str | os.PathLike, **kw: Any) -> "RegistroPeticiones":
        """Fail-closed: escribe una linea REAL de comprobacion, la relee y verifica su contenido."""
        d = pathlib.Path(directorio)
        registro = cls(d, **kw)
        marca = str(uuid.uuid4())
        try:
            d.mkdir(parents=True, exist_ok=True)
            registro._escribir_linea({"evento": "ARRANQUE", "comprobacion": marca})
            ultima = registro.fichero_actual().read_text(encoding="utf-8").splitlines()[-1]
            if json.loads(ultima).get("comprobacion") != marca:
                raise RegistroNoDisponible("la linea de comprobacion no coincide")
        except RegistroNoDisponible:
            raise
        except Exception as exc:  # noqa: BLE001
            raise RegistroNoDisponible(f"no se puede escribir el registro de peticiones ({type(exc).__name__})") from None
        return registro

    def fichero_actual(self) -> pathlib.Path:
        return self._dir / f"{PREFIJO}{self._hoy():%Y%m%d}.jsonl"

    def _purgar(self, hoy: dt.date) -> None:
        if self._fecha_purgada == hoy:
            return
        self._fecha_purgada = hoy
        limite = hoy - dt.timedelta(days=RETENCION_DIAS)
        for f in self._dir.glob(f"{PREFIJO}*.jsonl"):
            try:
                fecha = dt.datetime.strptime(f.name[len(PREFIJO):-len(".jsonl")], "%Y%m%d").date()
            except ValueError:
                continue
            if fecha < limite:
                f.unlink(missing_ok=True)

    def _escribir_linea(self, evento: dict[str, Any]) -> None:
        linea = json.dumps({"hora_utc": dt.datetime.now(dt.timezone.utc).isoformat(), **evento},
                           ensure_ascii=False, default=str, separators=(",", ":"))
        with self._cerrojo:
            self._purgar(self._hoy())
            with open(self.fichero_actual(), "a", encoding="utf-8") as f:
                f.write(linea + "\n")
                f.flush()   # al buffer del sistema operativo; sin fsync (ver cabecera)

    def escribir(self, evento: dict[str, Any]) -> None:
        """Fail-open: nunca lanza. Un fallo se cuenta y se avisa con un texto fijo, sin datos de la peticion."""
        try:
            self._escribir_linea(evento)
        except BaseException:  # noqa: BLE001 - nada del registro puede alterar la respuesta
            self.fallos += 1
            try:
                self._consola(AVISO_CONSOLA)
            except BaseException:  # noqa: BLE001
                pass


def desde_entorno(entorno: dict[str, str] | None = None) -> RegistroPeticiones:
    """Para `create_app_desde_entorno`: exige `GAPTO_LOG_DIR` y comprueba la escritura (fail-closed)."""
    env = os.environ if entorno is None else entorno
    directorio = env.get("GAPTO_LOG_DIR", "").strip()
    if not directorio:
        raise RegistroNoDisponible("falta GAPTO_LOG_DIR (directorio del registro de peticiones, fuera del repositorio)")
    repo = pathlib.Path(__file__).resolve().parents[3]
    destino = pathlib.Path(directorio).resolve()
    if destino == repo or repo in destino.parents:
        raise RegistroNoDisponible("GAPTO_LOG_DIR no puede estar dentro del repositorio")
    return RegistroPeticiones.abrir(directorio)
