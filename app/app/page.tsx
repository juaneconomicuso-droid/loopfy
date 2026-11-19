import Image from "next/image";
import Link from "next/link";

const features = [
  {
    t: "Fixação de produtos na hora certa",
    d: "Monte a sequência de ofertas, fixe, troque e reordene a vitrine da live sem tocar no celular.",
    hot: true,
  },
  {
    t: "Operação multi-conta",
    d: "Gerencie várias contas e lives a partir de um único painel, com cada operação separada.",
  },
  {
    t: "Parada de segurança",
    d: "Ao detectar um aviso de violação da plataforma, a live é encerrada na hora para proteger sua conta.",
  },
  {
    t: "Comentários programados",
    d: "Agende mensagens de oferta, cupom e prova social para entrar no momento certo do roteiro.",
  },
  {
    t: "Moderação automática",
    d: "Bloqueie palavras-chave e perfis indesejados, como concorrentes e spam, antes que apareçam no chat.",
  },
  {
    t: "Alertas de venda",
    d: "Cada venda confirmada vira um aviso no Telegram, com som diferente por faixa de valor.",
  },
];

const steps = [
  ["1", "Conecte sua loja", "Cadastre a conta e os produtos que entram na live."],
  ["2", "Monte o roteiro", "Defina ordem dos produtos, comentários e regras de moderação."],
  ["3", "Acompanhe ao vivo", "Veja o log de eventos e receba as vendas no Telegram."],
];

const plans = [
  {
    n: "Mensal",
    p: "147",
    u: "/mês",
    d: "Para começar a organizar suas lives.",
    items: ["1 chave de acesso", "Painel completo", "Moderação e comentários", "Alertas no Telegram"],
  },
  {
    n: "Trimestral",
    p: "397",
    u: "/trimestre",
    d: "Para quem vende toda semana.",
    items: ["4 chaves de acesso", "Tudo do Mensal", "Suporte prioritário", "Economia vs. mensal"],
    best: true,
  },
  {
    n: "Vitalício",
    p: "997",
    u: "pagamento único",
    d: "Acesso definitivo ao Loopfy.",
    items: ["Chaves ilimitadas", "Atualizações futuras", "Suporte prioritário", "Call de implementação"],
  },
];

const logs = [
  ["21:04:12", "Live iniciada · roteiro carregado"],
  ["21:05:48", "Comentário enviado: “Cupom só agora! 🔥”"],
  ["21:06:21", "Perfil bloqueado pela moderação"],
  ["21:07:03", "Venda confirmada · R$ 149,90"],
  ["21:08:55", "Palavra bloqueada no chat"],
  ["21:10:17", "Alerta enviado no Telegram"],
];

export default function Home() {
  return (
    <main className="relative overflow-hidden">
      <header className="sticky top-0 z-30 border-b border-line/60 bg-bg/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Image src="/loopfy-logo.png" alt="Loopfy" width={460} height={185} className="h-10 w-auto" priority />
          <nav className="hidden gap-8 text-sm text-muted md:flex">
            <a href="#recursos" className="hover:text-white">Recursos</a>
            <a href="#como-funciona" className="hover:text-white">Como funciona</a>
            <a href="#planos" className="hover:text-white">Planos</a>
          </nav>
          <Link href="/painel" className="grad-bg rounded-full px-5 py-2 text-sm font-semibold text-white">
            Entrar no painel
          </Link>
        </div>
      </header>

      <section className="glow">
        <div className="mx-auto max-w-4xl px-4 pb-20 pt-20 text-center md:pt-28">
          <span className="inline-block rounded-full border border-line bg-surface px-4 py-1 text-xs text-muted">
            Live Commerce Automation
          </span>
          <h1 className="mt-6 text-4xl font-extrabold leading-tight md:text-6xl">
            Sua operação de lives <span className="grad-text">em movimento.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-muted">
            Organize produtos, comentários, moderação e alertas de venda em um painel só. Menos tarefa manual na live,
            mais atenção no que vende.
          </p>
          <div className="mt-9 flex flex-wrap justify-center gap-3">
            <Link href="/painel" className="grad-bg rounded-full px-7 py-3 font-semibold text-white">
              Testar o painel
            </Link>
            <a href="#como-funciona" className="rounded-full border border-line px-7 py-3 font-semibold hover:bg-surface">
              Ver como funciona
            </a>
          </div>
        </div>

        <div className="mx-auto max-w-3xl px-4 pb-20">
          <div className="card p-5">
            <div className="mb-4 flex items-center justify-between text-sm">
              <span className="text-muted">Live · @minhaloja</span>
              <span className="rounded-full bg-red-500/15 px-3 py-1 text-xs font-semibold text-red-400">● AO VIVO</span>
            </div>
            <ul className="space-y-2 font-mono text-sm">
              {logs.map(([h, t]) => (
                <li key={h} className="flex gap-3 rounded-lg bg-surface2 px-3 py-2">
                  <span className="text-cyan">{h}</span>
                  <span>{t}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-muted">Exemplo ilustrativo do log de eventos.</p>
          </div>
        </div>
      </section>

      <section id="recursos" className="mx-auto max-w-6xl px-4 py-20">
        <h2 className="text-center text-3xl font-bold md:text-4xl">Tudo que a sua live precisa</h2>
        <p className="mx-auto mt-3 max-w-xl text-center text-muted">Seis recursos pensados para quem vende por live todos os dias.</p>
        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {features.map((f) => (
            <div key={f.t} className={`card p-6 ${f.hot ? "border-violet/60" : ""}`}>
              {f.hot && <span className="mb-3 inline-block rounded-full bg-violet/20 px-3 py-1 text-xs font-semibold text-violet">Mais usado</span>}
              <h3 className="text-lg font-semibold">{f.t}</h3>
              <p className="mt-2 text-sm text-muted">{f.d}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="como-funciona" className="border-y border-line bg-surface/50">
        <div className="mx-auto max-w-5xl px-4 py-20">
          <h2 className="text-center text-3xl font-bold md:text-4xl">Como funciona</h2>
          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {steps.map(([n, t, d]) => (
              <div key={n} className="text-center">
                <div className="grad-bg mx-auto flex h-12 w-12 items-center justify-center rounded-full text-lg font-bold">{n}</div>
                <h3 className="mt-4 font-semibold">{t}</h3>
                <p className="mt-2 text-sm text-muted">{d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="planos" className="mx-auto max-w-6xl px-4 py-20">
        <h2 className="text-center text-3xl font-bold md:text-4xl">Escolha o seu plano</h2>
        <p className="mt-3 text-center text-muted">Valores de referência. Ajustáveis antes do lançamento.</p>
        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {plans.map((p) => (
            <div key={p.n} className={`card flex flex-col p-7 ${p.best ? "border-cyan/60" : ""}`}>
              {p.best && <span className="mb-3 w-fit rounded-full bg-cyan/15 px-3 py-1 text-xs font-semibold text-cyan">Mais escolhido</span>}
              <h3 className="text-xl font-semibold">{p.n}</h3>
              <p className="mt-1 text-sm text-muted">{p.d}</p>
              <p className="mt-5 text-4xl font-extrabold">
                <span className="text-lg font-semibold text-muted">R$ </span>
                {p.p} <span className="text-sm font-medium text-muted">{p.u}</span>
              </p>
              <ul className="mt-5 flex-1 space-y-2 text-sm">
                {p.items.map((i) => (
                  <li key={i} className="flex gap-2"><span className="text-cyan">✓</span>{i}</li>
                ))}
              </ul>
              <Link href="/painel" className={`mt-6 rounded-full py-3 text-center font-semibold ${p.best ? "grad-bg text-white" : "border border-line hover:bg-surface2"}`}>
                Começar com {p.n}
              </Link>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-line py-10 text-center text-sm text-muted">
        <Image src="/loopfy-logo.png" alt="Loopfy" width={460} height={185} className="mx-auto h-9 w-auto" />
        <p className="mt-4">Loopfy · Live Commerce Automation</p>
        <p className="mt-1">Use de acordo com os termos de cada plataforma de live.</p>
      </footer>
    </main>
  );
}
