import { activate, keyHash, rateLimited } from "@/lib/license";
import { clientIp, json, readJson } from "@/lib/http";

export const runtime = "nodejs";

const str = (v: unknown, max: number) => (typeof v === "string" && v.length <= max ? v : "");

export async function POST(req: Request) {
  const ip = clientIp(req);
  if (!ip) return json({ ok: false, code: "no_ip" }, 400);
  if (rateLimited("act-ip:" + ip, 30, 10 * 60_000)) return json({ ok: false, code: "rate_limited" }, 429);

  const b = await readJson(req);
  const key = str(b?.key, 40).trim();
  const devicePub = str(b?.devicePub, 64);
  const fp = str(b?.fp, 64);
  const nonce = str(b?.nonce, 80);
  const sig = str(b?.sig, 100);
  if (key.length < 10 || !devicePub || !fp || !nonce || !sig) return json({ ok: false, code: "bad_request" }, 400);

  // tentativas por chave: barra adivinhação mesmo vindo de vários IPs
  if (rateLimited("act-key:" + keyHash(key), 10, 10 * 60_000)) return json({ ok: false, code: "rate_limited" }, 429);

  const r = await activate(key, { devicePub, fp, nonce, sig });
  return json(r, r.ok ? 200 : 403);
}
