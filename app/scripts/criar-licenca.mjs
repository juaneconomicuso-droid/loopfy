// Cria uma licença de TESTE no servidor local e imprime a chave (aparece uma única vez).
// Uso (com o servidor rodando: npm run dev -- -p 3100):  node scripts/criar-licenca.mjs [mensal|trimestral|vitalicio] [dias]
// Lê o token de admin de app/.env.local. Esse arquivo NÃO está no GitHub: copie-o do computador de origem.
import fs from "node:fs";

const SERVER = process.env.LOOPFY_SERVER || "http://localhost:3100";
const env = fs.existsSync(".env.local") ? fs.readFileSync(".env.local", "utf8") : "";
const token = (env.match(/^LOOPFY_ADMIN_TOKEN=(.+)$/m) || [])[1]?.trim();
if (!token) { console.error("Sem LOOPFY_ADMIN_TOKEN: copie o app/.env.local do computador onde o Loopfy já funciona."); process.exit(1); }

const plan = process.argv[2] || "mensal";
const days = plan === "vitalicio" ? null : Number(process.argv[3] || 30);
const r = await fetch(SERVER + "/api/admin/licenses", {
  method: "POST",
  headers: { "content-type": "application/json", authorization: "Bearer " + token },
  body: JSON.stringify({ plan, days, maxDevices: 2, note: "teste" }),
}).catch((e) => { console.error("Servidor fora do ar em " + SERVER + ". Rode antes: npm run dev -- -p 3100\n" + e.message); process.exit(1); });
const d = await r.json().catch(() => ({}));
if (!d.ok) { console.error("Falhou (HTTP " + r.status + "):", JSON.stringify(d)); process.exit(1); }
console.log("Chave de licença de teste (guarde, aparece só agora):\n" + d.key);
