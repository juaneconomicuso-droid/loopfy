"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

type Product = { id: string; name: string; price: number; pinned: boolean };
type Comment = { id: string; text: string; everySec: number };
type LogItem = { id: string; at: string; text: string; kind: "info" | "sale" | "block" | "warn" };
type State = {
  products: Product[];
  comments: Comment[];
  words: string[];
  profiles: string[];
  telegramChat: string;
  alertOnSale: boolean;
  logs: LogItem[];
  live: boolean;
};

const KEY = "loopfy:v1";
const uid = () => Math.random().toString(36).slice(2, 9);
const brl = (n: number) => n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const now = () => new Date().toLocaleTimeString("pt-BR");

const initial: State = {
  products: [
    { id: uid(), name: "Kit Skincare Premium", price: 149.9, pinned: true },
    { id: uid(), name: "Tênis Runner X3", price: 289, pinned: false },
    { id: uid(), name: "Fone Bluetooth Pro", price: 199.9, pinned: false },
  ],
  comments: [
    { id: uid(), text: "Cupom só agora! 🔥", everySec: 20 },
    { id: uid(), text: "Últimas unidades, garanta a sua!", everySec: 35 },
  ],
  words: ["shop", "loja", "achadinhos"],
  profiles: [],
  telegramChat: "",
  alertOnSale: true,
  logs: [],
  live: false,
};

const input =
  "w-full rounded-lg border border-line bg-surface2 px-3 py-2 text-sm outline-none focus:border-violet";
const btn = "rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-surface2";

export default function Painel() {
  const [s, setS] = useState<State>(initial);
  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState<"live" | "produtos" | "comentarios" | "moderacao" | "alertas">("live");
  const sRef = useRef(s);
  sRef.current = s;

  useEffect(() => {
    try {
      const raw = localStorage.getItem(KEY);
      if (raw) setS({ ...JSON.parse(raw), live: false });
    } catch {}
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      localStorage.setItem(KEY, JSON.stringify(s));
    } catch {}
  }, [s, ready]);

  const log = useCallback((text: string, kind: LogItem["kind"] = "info") => {
    setS((p) => ({ ...p, logs: [{ id: uid(), at: now(), text, kind }, ...p.logs].slice(0, 200) }));
  }, []);

  // Simulação de uma live em andamento: dispara os comentários agendados e testa a moderação.
  useEffect(() => {
    if (!s.live) return;
    const timers = sRef.current.comments.map((c) =>
      setInterval(() => log(`Comentário enviado: “${c.text}”`), Math.max(c.everySec, 3) * 1000),
    );
    const sim = setInterval(() => {
      const cur = sRef.current;
      const spam = ["compre na minha loja!", "achadinhos aqui", "que lindo esse produto"];
      const msg = spam[Math.floor(Math.random() * spam.length)];
      const hit = cur.words.find((w) => w && msg.toLowerCase().includes(w.toLowerCase()));
      if (hit) log(`Mensagem bloqueada (palavra “${hit}”): ${msg}`, "block");
      else if (Math.random() < 0.4 && cur.products.length) {
        const pinned = cur.products.find((p) => p.pinned) ?? cur.products[0];
        log(`Venda simulada · ${pinned.name} · ${brl(pinned.price)}`, "sale");
      }
    }, 9000);
    return () => {
      timers.forEach(clearInterval);
      clearInterval(sim);
    };
  }, [s.live, s.comments, log]);

  const toggleLive = () => {
    const next = !s.live;
    setS((p) => ({ ...p, live: next }));
    log(next ? "Live iniciada (modo simulação)" : "Live encerrada", next ? "info" : "warn");
  };

  const pin = (id: string) => {
    const p = s.products.find((x) => x.id === id);
    setS((st) => ({ ...st, products: st.products.map((x) => ({ ...x, pinned: x.id === id })) }));
    if (p) log(`Produto fixado: ${p.name}`);
  };

  const move = (i: number, d: -1 | 1) =>
    setS((st) => {
      const a = [...st.products];
      const j = i + d;
      if (j < 0 || j >= a.length) return st;
      [a[i], a[j]] = [a[j], a[i]];
      return { ...st, products: a };
    });

  const tabs = [
    ["live", "Ao vivo"],
    ["produtos", "Produtos"],
    ["comentarios", "Comentários"],
    ["moderacao", "Moderação"],
    ["alertas", "Alertas"],
  ] as const;

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface/60">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
          <Link href="/"><Image src="/loopfy-logo.png" alt="Loopfy" width={460} height={185} className="h-9 w-auto" /></Link>
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${s.live ? "bg-red-500/15 text-red-400" : "bg-surface2 text-muted"}`}>
            {s.live ? "● AO VIVO (simulação)" : "Live parada"}
          </span>
        </div>
      </header>

      <div className="mx-auto max-w-5xl px-4 py-6">
        <div className="mb-5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-200">
          Modo simulação: os dados ficam salvos neste navegador e a live é simulada. A conexão real com a plataforma de live
          entra na próxima etapa.
        </div>

        <nav className="mb-6 flex flex-wrap gap-2">
          {tabs.map(([k, l]) => (
            <button key={k} onClick={() => setTab(k)} className={`rounded-full px-4 py-2 text-sm ${tab === k ? "grad-bg font-semibold text-white" : "border border-line text-muted hover:text-white"}`}>
              {l}
            </button>
          ))}
        </nav>

        {tab === "live" && (
          <div className="grid gap-5 md:grid-cols-5">
            <section className="card p-5 md:col-span-2">
              <button onClick={toggleLive} className={`w-full rounded-lg py-3 font-semibold ${s.live ? "bg-red-500/80 text-white" : "grad-bg text-white"}`}>
                {s.live ? "Encerrar live" : "Iniciar live"}
              </button>
              <h3 className="mb-3 mt-6 text-sm font-semibold text-muted">Produtos fixados</h3>
              <ul className="space-y-2">
                {s.products.map((p) => (
                  <li key={p.id} className="flex items-center justify-between rounded-lg bg-surface2 px-3 py-2 text-sm">
                    <span>
                      {p.name}
                      <span className="block text-xs text-muted">{brl(p.price)}</span>
                    </span>
                    {p.pinned ? (
                      <span className="rounded-full bg-violet/20 px-2 py-0.5 text-xs text-violet">Fixado</span>
                    ) : (
                      <button className={btn} onClick={() => pin(p.id)}>Fixar</button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
            <section className="card p-5 md:col-span-3">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-muted">Log de eventos</h3>
                <button className={btn} onClick={() => setS((p) => ({ ...p, logs: [] }))}>Limpar</button>
              </div>
              <ul className="max-h-96 space-y-1.5 overflow-auto font-mono text-sm">
                {s.logs.length === 0 && <li className="text-muted">Nenhum evento ainda. Inicie a live.</li>}
                {s.logs.map((l) => (
                  <li key={l.id} className="flex gap-3 rounded bg-surface2 px-3 py-1.5">
                    <span className="text-cyan">{l.at}</span>
                    <span className={l.kind === "sale" ? "text-emerald-400" : l.kind === "block" ? "text-amber-300" : l.kind === "warn" ? "text-red-400" : ""}>{l.text}</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        )}

        {tab === "produtos" && (
          <ProductsTab s={s} setS={setS} move={move} pin={pin} />
        )}

        {tab === "comentarios" && <CommentsTab s={s} setS={setS} />}

        {tab === "moderacao" && (
          <div className="grid gap-5 md:grid-cols-2">
            <TagBox title="Palavras bloqueadas" items={s.words} onChange={(words) => setS((p) => ({ ...p, words }))} placeholder="ex.: promoção externa" />
            <TagBox title="Perfis bloqueados" items={s.profiles} onChange={(profiles) => setS((p) => ({ ...p, profiles }))} placeholder="@perfil" />
          </div>
        )}

        {tab === "alertas" && (
          <section className="card max-w-xl space-y-4 p-6">
            <label className="block text-sm">
              <span className="mb-1 block text-muted">Chat ID do Telegram</span>
              <input className={input} value={s.telegramChat} onChange={(e) => setS((p) => ({ ...p, telegramChat: e.target.value }))} placeholder="123456789" />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={s.alertOnSale} onChange={(e) => setS((p) => ({ ...p, alertOnSale: e.target.checked }))} />
              Avisar no Telegram a cada venda confirmada
            </label>
            <p className="text-xs text-muted">O envio real depende do bot do Telegram e do servidor, que entram na próxima etapa.</p>
          </section>
        )}
      </div>
    </div>
  );
}

function ProductsTab({ s, setS, move, pin }: { s: State; setS: React.Dispatch<React.SetStateAction<State>>; move: (i: number, d: -1 | 1) => void; pin: (id: string) => void }) {
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const add = () => {
    const v = parseFloat(price.replace(",", "."));
    if (!name.trim() || !isFinite(v)) return;
    setS((p) => ({ ...p, products: [...p.products, { id: uid(), name: name.trim(), price: v, pinned: false }] }));
    setName("");
    setPrice("");
  };
  return (
    <section className="card p-5">
      <div className="mb-4 flex flex-wrap gap-2">
        <input className={`${input} flex-1`} placeholder="Nome do produto" value={name} onChange={(e) => setName(e.target.value)} />
        <input className={`${input} w-32`} placeholder="Preço" value={price} onChange={(e) => setPrice(e.target.value)} />
        <button className="grad-bg rounded-lg px-4 text-sm font-semibold text-white" onClick={add}>Adicionar</button>
      </div>
      <ul className="space-y-2">
        {s.products.map((p, i) => (
          <li key={p.id} className="flex items-center gap-2 rounded-lg bg-surface2 px-3 py-2 text-sm">
            <span className="flex-1">{p.name} <span className="text-muted">· {brl(p.price)}</span></span>
            <button className={btn} onClick={() => move(i, -1)} aria-label="Subir">↑</button>
            <button className={btn} onClick={() => move(i, 1)} aria-label="Descer">↓</button>
            <button className={btn} onClick={() => pin(p.id)}>{p.pinned ? "Fixado" : "Fixar"}</button>
            <button className={btn} onClick={() => setS((st) => ({ ...st, products: st.products.filter((x) => x.id !== p.id) }))}>Remover</button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function CommentsTab({ s, setS }: { s: State; setS: React.Dispatch<React.SetStateAction<State>> }) {
  const [text, setText] = useState("");
  const [sec, setSec] = useState("30");
  const add = () => {
    const n = parseInt(sec, 10);
    if (!text.trim() || !n) return;
    setS((p) => ({ ...p, comments: [...p.comments, { id: uid(), text: text.trim(), everySec: n }] }));
    setText("");
  };
  return (
    <section className="card p-5">
      <div className="mb-4 flex flex-wrap gap-2">
        <input className={`${input} flex-1`} placeholder="Texto do comentário" value={text} onChange={(e) => setText(e.target.value)} />
        <input className={`${input} w-28`} placeholder="a cada (s)" value={sec} onChange={(e) => setSec(e.target.value)} />
        <button className="grad-bg rounded-lg px-4 text-sm font-semibold text-white" onClick={add}>Adicionar</button>
      </div>
      <ul className="space-y-2">
        {s.comments.map((c) => (
          <li key={c.id} className="flex items-center gap-2 rounded-lg bg-surface2 px-3 py-2 text-sm">
            <span className="flex-1">{c.text} <span className="text-muted">· a cada {c.everySec}s</span></span>
            <button className={btn} onClick={() => setS((st) => ({ ...st, comments: st.comments.filter((x) => x.id !== c.id) }))}>Remover</button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function TagBox({ title, items, onChange, placeholder }: { title: string; items: string[]; onChange: (v: string[]) => void; placeholder: string }) {
  const [v, setV] = useState("");
  const add = () => {
    const t = v.trim();
    if (t && !items.includes(t)) onChange([...items, t]);
    setV("");
  };
  return (
    <section className="card p-5">
      <h3 className="mb-3 text-sm font-semibold text-muted">{title}</h3>
      <div className="mb-3 flex gap-2">
        <input className={input} placeholder={placeholder} value={v} onChange={(e) => setV(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} />
        <button className="grad-bg rounded-lg px-4 text-sm font-semibold text-white" onClick={add}>Add</button>
      </div>
      <div className="flex flex-wrap gap-2">
        {items.length === 0 && <span className="text-sm text-muted">Nada bloqueado.</span>}
        {items.map((i) => (
          <button key={i} onClick={() => onChange(items.filter((x) => x !== i))} className="rounded-full bg-surface2 px-3 py-1 text-sm hover:line-through" title="Clique para remover">
            {i} ×
          </button>
        ))}
      </div>
    </section>
  );
}
