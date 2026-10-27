# ============================================================
# GAPTO MOBILE 2027
# Fichero: lanzar_mutantes_rv3_p5.py
# Ruta: scripts/dev/lanzar_mutantes_rv3_p5.py
# Descripcion: MANT-PRE-BATERIA C. Completa la copia temporal del arnes
#   certificado con su propio fichero, requerido por el preflight P12.
#   No modifica el arnes, mutantes, discriminantes ni criterio de veredicto.
# Version: 0.1.0 (MANT-PRE-BATERIA)
# ============================================================
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys

RAIZ = Path(__file__).resolve().parents[2]
REL = Path('scripts/mutantes/rv3_p5.py')
SHA_CERTIFICADO = '3fa1fc7c02fa66073b32a85843831f7d722d7783142e388e1fa53642a1f54196'

def main() -> int:
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
