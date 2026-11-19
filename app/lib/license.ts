import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

/*
 * Licenciamento do Loopfy (servidor).
 * - Chaves de licença: só HMAC-SHA256 com pepper secreto; a chave em claro existe uma vez, na criação.
 * - Identidade do aparelho = par Ed25519 gerado NO aparelho. A cada ativação o servidor emite um desafio
 *   (nonce assinado, 2 min) e o aparelho prova que tem a chave privada. machineId = SHA-256 da pública.
 *   Copiar só o "id" não basta; o cliente protege a privada com DPAPI (preso ao usuário do Windows).
 * - Token de ativação = payload JSON + assinatura Ed25519 do servidor, TTL curto.
 * - Não existe teste grátis: só chave de licença paga ativa o software.
 * Armazenamento em arquivo = desenvolvimento. Em produção use Postgres (Supabase): o arquivo local não
 * funciona em hospedagem serverless nem com mais de uma instância.
 */

const TOKEN_TTL_S = 12 * 3600;
const NONCE_TTL_S = 120;

export type Device = { id: string; pub: string; fps: string[]; firstSeen: number; lastSeen: number };
export type License = {
  plan: "mensal" | "trimestral" | "vitalicio";
  status: "active" | "revoked";
  expiresAt: number | null;
  maxDevices: number;
  devices: Device[];
  note?: string;
  createdAt: number;
};
type Db = { licenses: Record<string, License> };

function env(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`Variável de ambiente ausente: ${name}`);
  return v;
}
const privateKey = () =>
  crypto.createPrivateKey({ key: Buffer.from(env("LOOPFY_PRIVATE_KEY_B64"), "base64"), format: "der", type: "pkcs8" });

/* ---------- armazenamento (dev: arquivo) ---------- */
const FILE = path.join(process.cwd(), "data", "licenses.json");
let chain: Promise<unknown> = Promise.resolve();
const empty = (): Db => ({ licenses: {} });

function readDb(): Db {
  let raw: string;
  try {
    raw = fs.readFileSync(FILE, "utf8");
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === "ENOENT") return empty();
    throw e; // qualquer outro erro NÃO pode virar "banco vazio" (apagaria todas as licenças)
  }
  const db = JSON.parse(raw) as Partial<Db>;
  return { ...empty(), ...db } as Db;
}
function writeDb(db: Db) {
  fs.mkdirSync(path.dirname(FILE), { recursive: true });
  try { fs.copyFileSync(FILE, FILE + ".bak"); } catch { /* primeiro uso */ }
  const tmp = FILE + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(db), { mode: 0o600 });
  fs.renameSync(tmp, FILE);
}
/** Serializa o acesso. Só reescreve o arquivo quando `fn` chama touch(). */
export function withDb<T>(fn: (db: Db, touch: () => void) => T | Promise<T>): Promise<T> {
  const run = chain.then(async () => {
    const db = readDb();
    let dirty = false;
    const out = await fn(db, () => { dirty = true; });
    if (dirty) writeDb(db);
    return out;
  });
  chain = run.catch(() => undefined);
  return run;
}

/* ---------- chaves de licença ---------- */
const ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"; // Crockford, sem I L O U

export function newLicenseKey(): string {
  const bytes = crypto.randomBytes(20);
  let s = "";
  for (let i = 0; i < 20; i++) s += ALPHABET[bytes[i] & 31]; // 20 símbolos x 5 bits = 100 bits
  return "LPFY-" + s.match(/.{4}/g)!.join("-");
}
export const normalizeKey = (k: string) => k.toUpperCase().replace(/[^0-9A-Z]/g, "").replace(/^LPFY/, "");
export const keyHash = (k: string) => crypto.createHmac("sha256", env("LOOPFY_KEY_PEPPER")).update(normalizeKey(k)).digest("hex");
const pepperHmac = (s: string) => crypto.createHmac("sha256", env("LOOPFY_KEY_PEPPER")).update(s).digest("hex");

/* ---------- desafio (sem estado) e prova de posse da chave do aparelho ---------- */
export function newChallenge(): string {
  const ts = Math.floor(Date.now() / 1000);
  const rnd = crypto.randomBytes(12).toString("hex");
  return `${ts}.${rnd}.${pepperHmac(`nonce|${ts}|${rnd}`).slice(0, 32)}`;
}
function nonceValid(n: string): boolean {
  const m = /^(\d{9,11})\.([0-9a-f]{24})\.([0-9a-f]{32})$/.exec(n);
  if (!m) return false;
  const age = Math.floor(Date.now() / 1000) - Number(m[1]);
  if (age < -5 || age > NONCE_TTL_S) return false;
  return safeEqual(pepperHmac(`nonce|${m[1]}|${m[2]}`).slice(0, 32), m[3]);
}
const SPKI_PREFIX = Buffer.from("302a300506032b6570032100", "hex");

export type DeviceProof = { devicePub: string; fp: string; nonce: string; sig: string; purpose: "activate" };

/** Valida desafio + assinatura. Devolve o machineId (SHA-256 da pública) ou null. */
export function verifyProof(p: DeviceProof): string | null {
  if (!B64_RE.test(p.devicePub) || !HEX64_RE.test(p.fp) || !nonceValid(p.nonce)) return null;
  const raw = Buffer.from(p.devicePub, "base64");
  if (raw.length !== 32) return null;
  try {
    const pub = crypto.createPublicKey({ key: Buffer.concat([SPKI_PREFIX, raw]), format: "der", type: "spki" });
    const msg = Buffer.from(`loopfy|${p.purpose}|${p.nonce}|${p.fp}`);
    const sig = Buffer.from(p.sig, "base64");
    if (sig.length !== 64 || !crypto.verify(null, msg, pub, sig)) return null;
  } catch {
    return null;
  }
  return crypto.createHash("sha256").update(raw).digest("hex");
}

/* ---------- token ---------- */
export function signToken(p: { lic: string; plan: string; dev: string; capExp?: number | null }) {
  const iat = Math.floor(Date.now() / 1000);
  let exp = iat + TOKEN_TTL_S;
  if (p.capExp) exp = Math.min(exp, p.capExp);
  const payload = { v: 1, lic: p.lic.slice(0, 12), plan: p.plan, dev: p.dev, iat, exp, jti: crypto.randomBytes(8).toString("hex") };
  const body = Buffer.from(JSON.stringify(payload));
  const sig = crypto.sign(null, body, privateKey());
  return { token: `${body.toString("base64url")}.${sig.toString("base64url")}`, exp };
}

/* ---------- validações e utilitários ---------- */
export const HEX64_RE = /^[0-9a-f]{64}$/;
export const B64_RE = /^[A-Za-z0-9+/]{43}=$/;

export function safeEqual(a: string, b: string): boolean {
  const ha = crypto.createHash("sha256").update(a).digest();
  const hb = crypto.createHash("sha256").update(b).digest();
  return crypto.timingSafeEqual(ha, hb);
}

/* limite de tentativas em memória (produção: Redis/Upstash). Mapa com teto para não crescer sem fim. */
const hits = new Map<string, number[]>();
export function rateLimited(bucket: string, max: number, windowMs: number): boolean {
  const now = Date.now();
  const arr = (hits.get(bucket) ?? []).filter((t) => now - t < windowMs);
  arr.push(now);
  hits.delete(bucket);
  hits.set(bucket, arr);
  if (hits.size > 5000) {
    let n = 0;
    for (const k of hits.keys()) { hits.delete(k); if (++n >= 1000) break; } // descarta os mais antigos
  }
  return arr.length > max;
}

/* ---------- operações ---------- */
export type ActivateResult =
  | { ok: true; token: string; exp: number; plan: string }
  | { ok: false; code: "invalid" | "expired" | "device_limit" | "bad_proof" };

export function activate(key: string, proof: Omit<DeviceProof, "purpose">): Promise<ActivateResult> {
  const machineId = verifyProof({ ...proof, purpose: "activate" });
  if (!machineId) return Promise.resolve({ ok: false, code: "bad_proof" });
  const h = keyHash(key);
  return withDb((db, touch) => {
    const lic = db.licenses[h];
    const now = Math.floor(Date.now() / 1000);
    if (!lic || lic.status !== "active") return { ok: false, code: "invalid" } as const;
    if (lic.expiresAt && lic.expiresAt < now) return { ok: false, code: "expired" } as const;

    let dev = lic.devices.find((d) => d.id === machineId);
    if (!dev) {
      if (lic.devices.length >= lic.maxDevices) return { ok: false, code: "device_limit" } as const;
      dev = { id: machineId, pub: proof.devicePub, fps: [], firstSeen: now, lastSeen: now };
      lic.devices.push(dev);
      touch();
    }
    if (!dev.fps.includes(proof.fp) && dev.fps.length < 5) { dev.fps.push(proof.fp); touch(); } // sinal, não bloqueia
    if (now - dev.lastSeen > 3600) { dev.lastSeen = now; touch(); }
    const { token, exp } = signToken({ lic: h, plan: lic.plan, dev: machineId, capExp: lic.expiresAt });
    return { ok: true, token, exp, plan: lic.plan } as const;
  });
}

export function createLicense(plan: License["plan"], days: number | null, maxDevices: number, note?: string) {
  const key = newLicenseKey();
  const now = Math.floor(Date.now() / 1000);
  return withDb((db, touch) => {
    db.licenses[keyHash(key)] = { plan, status: "active", expiresAt: days ? now + days * 86400 : null, maxDevices, devices: [], note, createdAt: now };
    touch();
    return key;
  });
}

export function revokeLicense(key: string) {
  const h = keyHash(key);
  return withDb((db, touch) => {
    if (!db.licenses[h]) return false;
    db.licenses[h].status = "revoked";
    touch();
    return true;
  });
}

/** Suporte: libera as vagas de aparelho de uma licença (ex.: cliente trocou de computador). */
export function resetDevices(key: string) {
  const h = keyHash(key);
  return withDb((db, touch) => {
    if (!db.licenses[h]) return false;
    db.licenses[h].devices = [];
    touch();
    return true;
  });
}

