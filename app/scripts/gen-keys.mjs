// Gera o par Ed25519 da licença, o pepper das chaves e o token de admin.
// Uso: node scripts/gen-keys.mjs  -> imprime as linhas para .env.local e a chave pública da extensão.
import crypto from "node:crypto";

const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");
const priv = privateKey.export({ type: "pkcs8", format: "der" }).toString("base64");
const pubRaw = publicKey.export({ type: "spki", format: "der" }).subarray(-32).toString("base64");

console.log("# --- cole em app/.env.local (nunca commitar) ---");
console.log(`LOOPFY_PRIVATE_KEY_B64=${priv}`);
console.log(`LOOPFY_KEY_PEPPER=${crypto.randomBytes(32).toString("hex")}`);
console.log(`LOOPFY_ADMIN_TOKEN=${crypto.randomBytes(32).toString("hex")}`);
console.log("# --- chave PÚBLICA (vai embutida na extensão, pode ser pública) ---");
console.log(`PUBLIC_KEY_B64=${pubRaw}`);
