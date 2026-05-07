/**
 * Lightweight JWT verification for Cloudflare Workers.
 * Uses the Web Crypto API — no external dependencies required.
 */

export interface JwtPayload {
  sub: string;
  role: string;
  type: string;
  exp: number;
  iat?: number;
}

function base64urlDecode(input: string): Uint8Array {
  const base64 = input.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
  const binary = atob(padded);
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

async function importKey(secret: string): Promise<CryptoKey> {
  const enc = new TextEncoder();
  return crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"],
  );
}

/**
 * Verify a HS256 JWT and return its payload.
 * Throws a Response with 401 status on any failure.
 */
export async function verifyJwt(token: string, secret: string): Promise<JwtPayload> {
  const parts = token.split(".");
  if (parts.length !== 3) {
    throw new Response("Malformed token", { status: 401 });
  }

  const [headerB64, payloadB64, signatureB64] = parts;
  const data = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const signature = base64urlDecode(signatureB64);

  const key = await importKey(secret);
  const valid = await crypto.subtle.verify("HMAC", key, signature, data);
  if (!valid) {
    throw new Response("Invalid token signature", { status: 401 });
  }

  const payload: JwtPayload = JSON.parse(
    new TextDecoder().decode(base64urlDecode(payloadB64)),
  ) as JwtPayload;

  if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) {
    throw new Response("Token expired", { status: 401 });
  }

  if (payload.type !== "access") {
    throw new Response("Wrong token type", { status: 401 });
  }

  return payload;
}

/**
 * Extract the Bearer token from an Authorization header.
 */
export function extractBearerToken(request: Request): string | null {
  const auth = request.headers.get("Authorization");
  if (!auth?.startsWith("Bearer ")) return null;
  return auth.slice(7);
}
