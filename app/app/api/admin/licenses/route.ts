import { createLicense, rateLimited, resetDevices, revokeLicense, safeEqual } from "@/lib/license";
import { clientIp, json, readJson } from "@/lib/http";

export const runtime = "nodejs";

function authorized(req: Request): boolean {
  const expected = process.env.LOOPFY_ADMIN_TOKEN;
  if (!expected || expected.length < 32) return false;
  const h = req.headers.get("authorization") ?? "";
  const got = h.startsWith("Bearer ") ? h.slice(7) : "";
  return safeEqual(got, expected);
}

/** Cria licença. Corpo: { plan, days|null, maxDevices, note? }. Devolve a chave em claro uma única vez. */
export async function POST(req: Request) {
  if (rateLimited("adm:" + (clientIp(req) ?? "x"), 20, 10 * 60_000)) return json({ ok: false }, 429);
  if (!authorized(req)) return json({ ok: false }, 401);

  const b = await readJson(req);
  const plan = b?.plan;
  if (plan !== "mensal" && plan !== "trimestral" && plan !== "vitalicio") return json({ ok: false, code: "bad_plan" }, 400);
  const days = b?.days === null ? null : Number(b?.days);
  if (days !== null && !(Number.isInteger(days) && days > 0 && days <= 3650)) return json({ ok: false, code: "bad_days" }, 400);
  const maxDevices = Number(b?.maxDevices ?? 1);
  if (!Number.isInteger(maxDevices) || maxDevices < 1 || maxDevices > 50) return json({ ok: false, code: "bad_devices" }, 400);
  const note = typeof b?.note === "string" ? b.note.slice(0, 120) : undefined;

  const key = await createLicense(plan, days, maxDevices, note);
  return json({ ok: true, key });
}

/** Libera as vagas de aparelho de uma licença (suporte). Corpo: { key }. */
export async function PATCH(req: Request) {
  if (rateLimited("adm:" + (clientIp(req) ?? "x"), 20, 10 * 60_000)) return json({ ok: false }, 429);
  if (!authorized(req)) return json({ ok: false }, 401);
  const b = await readJson(req);
  const key = typeof b?.key === "string" ? b.key : "";
  if (!key) return json({ ok: false, code: "bad_request" }, 400);
  return json({ ok: await resetDevices(key) });
}

/** Revoga licença. Corpo: { key }. */
export async function DELETE(req: Request) {
  if (rateLimited("adm:" + (clientIp(req) ?? "x"), 20, 10 * 60_000)) return json({ ok: false }, 429);
  if (!authorized(req)) return json({ ok: false }, 401);
  const b = await readJson(req);
  const key = typeof b?.key === "string" ? b.key : "";
  if (!key) return json({ ok: false, code: "bad_request" }, 400);
  return json({ ok: await revokeLicense(key) });
}
