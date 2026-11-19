import { NextResponse } from "next/server";

/**
 * IP do cliente vindo SÓ de cabeçalho que o proxy de hospedagem define (o cliente não consegue forjar).
 * Vercel: x-vercel-forwarded-for · Cloudflare: cf-connecting-ip · nginx: x-real-ip.
 * Atrás de proxy próprio que anexa ao X-Forwarded-For, defina LOOPFY_TRUST_XFF=1 (usa o ÚLTIMO valor, o do proxy).
 * Em produção, sem IP confiável a requisição é recusada (nunca cai num balde "unknown" compartilhado).
 */
export function clientIp(req: Request): string | null {
  const h = req.headers;
  const direct = h.get("x-vercel-forwarded-for") || h.get("cf-connecting-ip") || h.get("x-real-ip");
  if (direct) return direct.split(",")[0].trim();
  if (process.env.LOOPFY_TRUST_XFF === "1") {
    const xf = h.get("x-forwarded-for");
    if (xf) return xf.split(",").pop()!.trim();
  }
  return process.env.NODE_ENV === "production" ? null : "dev-local";
}

export function json(body: unknown, status = 200) {
  return NextResponse.json(body, {
    status,
    headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" },
  });
}

/** Lê JSON exigindo application/json e abortando o stream ao passar do limite (vale também para chunked). */
export async function readJson(req: Request, maxBytes = 2048): Promise<Record<string, unknown> | null> {
  const ct = (req.headers.get("content-type") ?? "").toLowerCase();
  if (!ct.startsWith("application/json")) return null;
  const declared = Number(req.headers.get("content-length") ?? 0);
  if (declared > maxBytes || !req.body) return null;

  const reader = req.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBytes) {
      await reader.cancel().catch(() => undefined);
      return null;
    }
    chunks.push(value);
  }
  try {
    const v = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}
