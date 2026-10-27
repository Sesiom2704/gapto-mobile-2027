# ============================================================
# GAPTO MOBILE 2027
# Fichero: lanzar_mutantes_rv3_p5.py
# Ruta: scripts/dev/lanzar_mutantes_rv3_p5.py
# Descripcion: MANT-PRE-BATERIA C. Completa la copia temporal del arnes
#   certificado con su propio fichero, requerido por el preflight P12.
#   No modifica el arnes, mutantes, discriminantes ni criterio de veredicto.
# Version: 0.1.0 (MANT-PRE-BATERIA)
# Version: 0.2.0 (F05-D053 paso 2; F05 §67.3, AJ-F0507G4-07): preflight del
#   laboratorio ANTES de leer el arnes: GAPTO_RV3_IMPORT_URL es obligatoria, en
#   formato clave=valor (test_rv3_031 la parte por espacios) y solo contra un
#   PostgreSQL local de loopback (nunca Neon, Supabase ni otro host: nunca
#   produccion). Si no se cumple, aborta con STOP-RV3P5-PREFLIGHT y rc=2 sin
#   cargar el arnes ni mutar nada, asi que no puede producir un VIVO (M161).
# ============================================================
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import sys
from typing import Mapping

RAIZ = Path(__file__).resolve().parents[2]
REL = Path('scripts/mutantes/rv3_p5.py')
SHA_CERTIFICADO = '3fa1fc7c02fa66073b32a85843831f7d722d7783142e388e1fa53642a1f54196'
VARIABLE_LABORATORIO = 'GAPTO_RV3_IMPORT_URL'
HOSTS_LOCALES = {'127.0.0.1', 'localhost', '::1'}


class PreflightRV3P5(SystemExit):
    """Aborto del preflight: rc=2 y el motivo en el mensaje (nunca un veredicto de mutante)."""

    def __init__(self, motivo: str) -> None:
        print(f'STOP-RV3P5-PREFLIGHT: {motivo}. No se muta nada.', file=sys.stderr, flush=True)
        super().__init__(2)
        self.motivo = motivo


def preflight_laboratorio(entorno: Mapping[str, str]) -> str:
    """§67.3: el laboratorio RV3_IMPORT es obligatorio y local. Sin el, los tests
    fisicos se omiten y M161 sale VIVO (hueco de entorno, no de tests)."""
    dsn = (entorno.get(VARIABLE_LABORATORIO) or '').strip()
    if not dsn:
        raise PreflightRV3P5(f'falta {VARIABLE_LABORATORIO} (laboratorio RV3_IMPORT local)')
    if '://' in dsn:
        raise PreflightRV3P5(f'{VARIABLE_LABORATORIO} debe ir en formato clave=valor, no como URL')
    from psycopg import conninfo
    try:
        partes = conninfo.conninfo_to_dict(dsn)
    except Exception:
        raise PreflightRV3P5(f'{VARIABLE_LABORATORIO} no es una cadena de conexion valida') from None
    hosts = [h.strip().lower() for h in str(partes.get('host') or '').split(',')]
    if not hosts or any(h not in HOSTS_LOCALES for h in hosts) or partes.get('hostaddr'):
        raise PreflightRV3P5(f'{VARIABLE_LABORATORIO} solo admite un PostgreSQL local de loopback (nunca produccion)')
    if not partes.get('dbname'):
        raise PreflightRV3P5(f'{VARIABLE_LABORATORIO} sin dbname')
    return dsn


def main() -> int:
    preflight_laboratorio(os.environ)
    fuente = RAIZ / REL
    bruto = fuente.read_bytes()
    if hashlib.sha256(bruto).hexdigest() != SHA_CERTIFICADO:
        raise SystemExit('STOP-RV3P5: el arnes no coincide con su hash certificado')
    spec = importlib.util.spec_from_file_location('rv3_p5_certificado', fuente)
    assert spec is not None and spec.loader is not None
    arnes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arnes)
    copia_original = arnes._copia
    preparadas = 0

    def copia_completa() -> Path:
        nonlocal preparadas
        destino = copia_original()
        fichero = destino / REL
        fichero.parent.mkdir(parents=True, exist_ok=True)
        fichero.write_bytes(bruto)
        if hashlib.sha256(fichero.read_bytes()).hexdigest() != SHA_CERTIFICADO:
            raise RuntimeError('STOP-RV3P5: copia del arnes no identica')
        preparadas += 1
        return destino

    # Unica adaptacion: preparacion de la copia. El motor de mutacion y sus
    # tests se ejecutan mediante main del fichero certificado, sin cambios.
    arnes._copia = copia_completa
    print(f'ARNES_CERTIFICADO SHA256={SHA_CERTIFICADO}', flush=True)
    rc = arnes.main(sys.argv[1:])
    print(f'COPIAS_COMPLETADAS={preparadas}; arnes_original_intacto={fuente.read_bytes() == bruto}', flush=True)
    return rc

if __name__ == '__main__':
    raise SystemExit(main())
