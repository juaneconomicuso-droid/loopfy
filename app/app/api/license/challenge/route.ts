import { newChallenge, rateLimited } from "@/lib/license";
import { clientIp, json } from "@/lib/http";

export const runtime = "nodejs";

/** Emite um desafio sem estado (nonce assinado, 2 min). O aparelho assina com sua chave privada. */
export async function POST(req: Request) {
  const ip = clientIp(req);
  if (!ip) return json({ ok: false, code: "no_ip" }, 400);
  if (rateLimited("chal-ip:" + ip, 60, 10 * 60_000)) return json({ ok: false, code: "rate_limited" }, 429);
  return json({ ok: true, nonce: newChallenge() });
}
