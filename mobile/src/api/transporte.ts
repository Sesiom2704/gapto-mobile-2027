// ============================================================
// GAPTO MOBILE 2027
// Fichero: transporte.ts
// Ruta: mobile/src/api/transporte.ts
// Descripción: Guarda de transporte del cliente (F06 T4 · token BETA_LOCAL, mandato 4f0e40af… §2.6; dictamen AJ-TOK-05, M-TOK-10). HTTP sin cifrar solo se admite hacia una dirección de red PRIVADA (loopback, 10/8, 172.16/12, 192.168/16, `localhost`); cualquier otra dirección exige `https` (TLS con la validación de certificado del sistema). Si la URL de la API no cumple, la app no envía la credencial ni ninguna petición (lo aplica `credencial.ts`). No convierte HTTP en seguro: es la excepción temporal de BETA_LOCAL (R-TOK-02).
// Versión: 0.1.0 (F06 T4 · token BETA_LOCAL)
// ============================================================

/** Partes mínimas de una URL absoluta; null si no es http(s) o no se puede leer. Sin `URL` (soporte parcial en RN). */
export function partesUrl(url: string): { esquema: 'http' | 'https'; host: string } | null {
  const m = /^(https?):\/\/(\[[0-9a-fA-F:.]+\]|[^/:?#\s@]+)(?::(\d{1,5}))?(?:[/?#]|$)/.exec(url.trim());
  if (!m) return null;
  return { esquema: m[1].toLowerCase() as 'http' | 'https', host: m[2].toLowerCase() };
}

function octetos(host: string): number[] | null {
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host);
  if (!m) return null;
  const o = m.slice(1).map(Number);
  return o.every((n) => n >= 0 && n <= 255) ? o : null;
}

/** true si el host es loopback o de una red privada (RFC 1918). */
export function hostPrivado(host: string): boolean {
  if (host === 'localhost' || host === '[::1]') return true;
  const o = octetos(host);
  if (!o) return false;
  const [a, b] = o;
  return a === 127 || a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
}

/** Transporte permitido: `https` hacia cualquier host, o `http` solo hacia una red privada. */
export function transportePermitido(url: string): boolean {
  const p = partesUrl(url);
  if (!p) return false;
  if (p.esquema === 'https') return true;
  return hostPrivado(p.host);
}
