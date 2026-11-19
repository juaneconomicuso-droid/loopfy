"""Operações durante a LIVE: ler a sala e a sacola, fixar produto (agora e automático) e timer de encerramento.

Roda na thread do navegador (a mesma do Playwright). As chamadas de API saem pelo fetch da própria página do
Gerenciador de LIVE, com a sessão da sua conta, como o painel do TikTok faz. O encerramento é feito pela tela
(botão de encerrar + confirmação), porque a chamada de encerrar não é conhecida.
"""
from __future__ import annotations

import json
import random
import re
import time
from typing import Callable

from playwright.sync_api import Page

from .browser import DATA

Log = Callable[[str, str], None]

FETCH_JS = """
async ({ path, method, body }) => {
  const COMMON = 'aid=253642&app_name=i18n_ecom_alliance&device_platform=web&user_language=pt-BR&locale=pt-BR';
  const url = location.origin + '/api/v1/streamer_desktop/' + path.replace(/^\\/+/, '') + (path.includes('?') ? '&' : '?') + COMMON;
  const opt = { method, credentials: 'include', headers: { accept: 'application/json, text/plain, */*', 'x-tt-store-region': 'br' } };
  if (method === 'POST') { opt.headers['content-type'] = 'application/json'; opt.body = JSON.stringify(body || {}); }
  const res = await fetch(url, opt);
  if (!res || typeof res.status !== 'number') return { status: 0, data: null };
  const txt = await res.text();
  let data = null; try { data = JSON.parse(txt); } catch (e) {}
  return { status: res.status, data, empty: !txt };
}
"""

VIOL_URL = ("https://webcast.tiktok.com/webcast/eco/violation_list/?aid=641989&app_name=i18n_ecom_alliance&device_platform=web"
            "&user_language=pt-BR&locale=pt-BR&webcast_language=pt-BR&webcast_locale=pt-BR&carrier_region=br")
VIOL_JS = """
async (url) => {
  const res = await fetch(url, { credentials: 'include', headers: { accept: 'application/json, text/plain, */*' } });
  if (!res || typeof res.status !== 'number') return { status: 0, data: null };
  const txt = await res.text(); let data = null; try { data = JSON.parse(txt); } catch (e) {}
  return { status: res.status, data };
}
"""
CHAT_BOX = re.compile(r"digite algo|type something|escreva", re.I)
CHAT_MIN_S = 30  # piso entre comentários, para não virar spam

END_BTN = re.compile(r"encerrar|finalizar|end live|fim da live", re.I)
CONFIRM_BTN = re.compile(r"^\s*(encerrar|confirmar|sim|finalizar|end)", re.I)
TIMER_PRESETS_MIN = (60, 120, 240, 360, 480)


def api(page: Page, path: str, method: str = "GET", body: dict | None = None) -> dict:
    return page.evaluate(FETCH_JS, {"path": path, "method": method, "body": body})


def ok(r: dict) -> bool:
    d = r.get("data") or {}
    return 200 <= r.get("status", 0) < 300 and d.get("code", 0) == 0 and not r.get("empty")


def room_id(page: Page) -> str | None:
    """'' = sem live no ar; None = falha de leitura (não decide nada)."""
    r = api(page, "live_room_info/get")
    if not ok(r):
        return None
    d = (r["data"].get("data") or {})
    info = d.get("live_room_info") if isinstance(d.get("live_room_info"), dict) else d
    rid = d.get("room_id") if isinstance(d.get("room_id"), str) else info.get("room_id")
    return rid if isinstance(rid, str) else ""


def bag_products(page: Page) -> list[dict] | None:
    """Produtos que já estão na sacola da LIVE."""
    r = api(page, "live_product/list")
    if not ok(r):
        return None
    prods = ((r["data"].get("data") or {}).get("products"))
    if not isinstance(prods, list):
        return None
    out = []
    for i, p in enumerate(prods):
        if isinstance(p, dict) and p.get("product_id") is not None:
            out.append({"id": str(p["product_id"]), "title": str(p.get("title", ""))[:120], "price": str(p.get("format_available_price", "")), "n": i + 1})
    return out


def catalog(page: Page) -> list[dict] | None:
    """Produtos da sua sacolinha (lista do 'Adicionar produtos'), lidos direto da API do TikTok, sem rolar a tela."""
    items: dict[str, dict] = {}
    off = 0
    for _ in range(40):
        r = api(page, f"search_product/list?offset={off}&size=20&scene=1&origin=2&page_scene=3")
        if not ok(r):
            return list(items.values()) if items else None
        d = (r["data"].get("data") or {})
        prods = d.get("products")
        if not isinstance(prods, list) or not prods:
            break
        for p in prods:
            if not isinstance(p, dict) or p.get("product_id") is None:
                continue
            cover = (p.get("cover") or {}).get("url_list") or (p.get("cover") or {}).get("thumb_url_list") or [""]
            items[str(p["product_id"])] = {
                "id": str(p["product_id"]), "title": str(p.get("title", "")).strip()[:200],
                "price": str(p.get("format_available_price", "")), "image": cover[0] if cover else "",
                "available": p.get("stock_status", 1) == 1,
            }
        if not d.get("has_more"):
            break
        off += len(prods)
    return list(items.values())


def pin(page: Page, rid: str, product_id: str, on: bool = True) -> bool:
    return ok(api(page, "live_product/pin", "POST", {"room_id": str(rid), "product_id": str(product_id), "op": 1 if on else 2}))


TEMPLATE = DATA / "add-template.json"


def _load_template() -> dict | None:
    try:
        t = json.loads(TEMPLATE.read_text("utf-8"))
        return t if isinstance(t, dict) and isinstance(t.get("body"), dict) else None
    except (OSError, ValueError):
        return None


def _is_id(v) -> bool:
    return isinstance(v, str) and v.isdigit() and len(v) >= 10


def _fill(obj, ids: list[str], room: str):
    """Troca, num corpo aprendido, os produtos antigos pelos novos (e a sala pela atual)."""
    if isinstance(obj, list):
        if obj and all(_is_id(x) for x in obj):
            return list(ids)
        return [_fill(x, ids, room) for x in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "room_id" and room:
                out[k] = room
            elif _is_id(v) and "product" in k.lower():
                out[k] = ids[0]
            else:
                out[k] = _fill(v, ids, room)
        return out
    return obj


def learn_add_request(req) -> None:
    """Guarda o corpo da chamada de adicionar produto feita pela própria tela (para repetir igual)."""
    try:
        if req.method != "POST" or "streamer_desktop/live_product/add" not in req.url:
            return
        body = json.loads(req.post_data or "")
        if isinstance(body, dict):
            DATA.mkdir(parents=True, exist_ok=True)
            TEMPLATE.write_text(json.dumps({"body": body, "at": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False), "utf-8")
    except Exception:  # noqa: BLE001
        pass


def _add_batch(page: Page, ids: list[str], room: str = "") -> tuple[list[str], str]:
    """Coloca produtos na sacola da LIVE. Devolve (ids confirmados na sacola, detalhe do último erro).

    Usa o formato aprendido da própria tela, se houver; senão tenta formatos prováveis. Cada tentativa é conferida
    lendo a sacola de novo, então 'sucesso' só vale se o produto realmente apareceu lá.
    """
    ids = [str(i) for i in ids]
    before = {p["id"] for p in (bag_products(page) or [])}
    want = [i for i in ids if i not in before]
    if not want:
        return ids, ""
    tpl = _load_template()
    cands: list[dict] = []
    # formato real visto na tela do TikTok (04/11 e 13/11): lista product_info com um objeto por produto
    entry = {"product_type": 1, "source_from": 0, "main_plan_id": "", "label_detail_info": [], "labels": []}
    if tpl and isinstance(tpl["body"].get("product_info"), list) and tpl["body"]["product_info"] and isinstance(tpl["body"]["product_info"][0], dict):
        entry = {k: v for k, v in tpl["body"]["product_info"][0].items() if k != "product_id"}
    real = {k: v for k, v in (tpl["body"] if tpl else {"need_product_info": True}).items() if k != "product_info"}
    real.update(room_id=room or real.get("room_id", ""))
    real["product_info"] = [{"product_id": i, **entry} for i in want]
    cands.append(real)
    if tpl:
        cands.append(_fill(tpl["body"], want, room))
    base = {"room_id": room} if room else {}
    for key in ("product_ids", "product_id_list", "products"):
        cands.append({**base, key: want, "location": 1})
        cands.append({**base, key: want})
    detail = ""
    for body in cands:
        r = api(page, "live_product/add?page_scene=3", "POST", body)
        d = r.get("data") or {}
        detail = f"HTTP {r.get('status')} code={d.get('code')} {str(d.get('message') or d.get('msg') or '')[:80]}"
        now = {p["id"] for p in (bag_products(page) or [])}
        if all(i in now for i in want):
            return ids, ""
        if ok(r) and (now - before):
            return [i for i in ids if i in now], ""
        if d.get("code") == 0 and not ok(r):
            continue
    return [i for i in ids if i in {p["id"] for p in (bag_products(page) or [])}], detail


def add_to_bag(page: Page, ids: list[str], room: str = "") -> tuple[list[str], str]:
    """Coloca vários produtos (em lotes de 20). Se um lote falha, tenta um por um, para um item esgotado não travar os outros."""
    ids = list(dict.fromkeys(str(i) for i in ids))[:150]
    done: list[str] = []
    detail = ""
    for k in range(0, len(ids), 20):
        chunk = ids[k:k + 20]
        got, detail = _add_batch(page, chunk, room)
        done += got
        miss = [i for i in chunk if i not in got]
        if miss and len(chunk) > 1:
            for i in miss:
                g1, detail = _add_batch(page, [i], room)
                done += g1
    return [i for i in ids if i in set(done)], ("" if len(done) == len(ids) else detail)


def end_live(page: Page) -> bool:
    """Clica em encerrar e confirma. Devolve True se a tela confirmou o fluxo (a checagem final é a sala sumir)."""
    btn = page.get_by_role("button", name=END_BTN)
    if not btn.count():
        btn = page.locator('[aria-label*="ncerrar" i], [title*="ncerrar" i]')
    if not btn.count():
        return False
    btn.first.click()
    page.wait_for_timeout(900)
    dlg = page.get_by_role("dialog")
    scope = dlg.last if dlg.count() else page
    conf = scope.get_by_role("button", name=CONFIRM_BTN)
    if not conf.count():
        return False
    conf.last.click()
    page.wait_for_timeout(1500)
    return True


def violations_active(page: Page) -> int | None:
    """Quantidade de restrições ativas na conta (webcast/eco/violation_list). None = não deu para ler."""
    r = page.evaluate(VIOL_JS, VIOL_URL)
    d = r.get("data") or {}
    if r.get("status") != 200 or d.get("status_code", 0) != 0:
        return None
    n = (d.get("data") or {}).get("active_count")
    return int(n) if isinstance(n, int) else None


def send_comment(page: Page, text: str) -> bool:
    """Escreve no campo de chat do Console de LIVE e envia (pela tela, como você faria)."""
    box = page.get_by_placeholder(CHAT_BOX)
    if not box.count():
        return False
    box.first.fill(text[:100])
    box.first.press("Enter")
    page.wait_for_timeout(400)
    return True


def snapshot_failure(page: Page, tag: str) -> str:
    out = DATA / f"tela-{tag}-{time.strftime('%Y%m%d-%H%M%S')}.txt"
    try:
        out.write_text(f"URL: {page.url}\n\n" + page.locator("body").aria_snapshot(timeout=5000), encoding="utf-8")
    except Exception:  # noqa: BLE001
        out.write_text(f"URL: {page.url}\n(sem leitura)", encoding="utf-8")
    return out.name


class LiveOps:
    """Estado e rotinas do painel: sala, sacola, fixação automática e timer."""

    def __init__(self, log: Log) -> None:
        self.log = log
        self.reset()

    def reset(self) -> None:
        self.room = ""
        self.products: list[dict] = []
        self.pinned: dict | None = None
        self.auto = {"on": False, "sec": 45, "mode": "ordem", "ids": []}
        self.timer = {"state": "idle", "total": 0, "end_at": 0.0, "left": 0.0, "warned": set(), "fail": 0, "next_try": 0.0}
        self.guard = {"on": False, "action": "end", "sec": 10, "baseline": None, "deadline": 0.0, "t_poll": 0.0, "fail": 0, "next_try": 0.0}
        self.chat = {"on": False, "msgs": [], "min": 45, "max": 90, "random": True, "next": 0.0, "idx": 0, "last": -1, "fail": 0}
        self.stop_clip = False
        self._t_room = self._t_list = self._t_auto = 0.0
        self._rot = 0
        self._warned_pool = False

    def configure(self, cfg: dict) -> None:
        """Aplica o que está salvo na configuração ao começar uma sessão."""
        g = cfg.get("guard") or {}
        self.guard.update(on=bool(g.get("on")), action=g.get("action", "end"), sec=int(g.get("sec", 10)))
        c = cfg.get("chat") or {}
        self.chat.update(msgs=list(c.get("msgs", [])), min=int(c.get("min", 45)), max=int(c.get("max", 90)), random=bool(c.get("random", True)))

    # ---- o que a interface mostra ----
    def snapshot(self) -> dict:
        t = self.timer
        left = max(0, int(t["end_at"] - time.time())) if t["state"] == "running" else int(t["left"])
        g, c = self.guard, self.chat
        return {
            "room": self.room, "products": self.products, "pinned": self.pinned,
            "auto": self.auto, "timer": {"state": t["state"], "left": left, "total": int(t["total"])},
            "guard": {"on": g["on"], "action": g["action"], "sec": g["sec"], "alert": bool(g["deadline"]), "left": max(0, int(g["deadline"] - time.time())) if g["deadline"] else 0},
            "chat": {"on": c["on"], "n": len(c["msgs"])},
        }

    # ---- comandos vindos da interface ----
    def handle(self, kind: str, data: dict, page: Page) -> None:
        if kind == "refresh":
            self._t_room = self._t_list = 0.0
        elif kind == "pin":
            self._pin(page, str(data["id"]))
        elif kind == "bag_add":
            ids = [str(x) for x in data.get("ids", []) if x]
            if not ids:
                return
            done, detail = add_to_bag(page, ids, self.room)
            self._t_list = 0.0
            miss = [i for i in ids if i not in done]
            if not miss:
                self.log("ok", f"{len(ids)} produto(s) colocado(s) na sacola.")
            else:
                self.log("err" if not done else "warn", f"{len(done)} de {len(ids)} entraram na sacola. {detail}")
                if not _load_template():
                    self.log("info", "Dica: adicione um produto à mão uma vez no Gerenciador de LIVE; o Loopfy aprende o formato e repete.")
        elif kind == "unpin":
            if self.pinned and self.room and pin(page, self.room, self.pinned["id"], False):
                self.log("ok", "Produto desafixado.")
                self.pinned = None
            else:
                self.log("warn", "Não foi possível desafixar.")
        elif kind == "auto":
            ids = [str(x) for x in data.get("ids", [])]
            self.auto = {"on": bool(data.get("on")), "sec": max(10, min(120, int(data.get("sec", 45)))), "mode": data.get("mode", "ordem") if data.get("mode") in ("ordem", "aleatorio") else "ordem", "ids": ids}
            self._t_auto = 0.0
            self.log("info", "Fixação automática ligada." if self.auto["on"] else "Fixação automática desligada.")
        elif kind == "guard_set":
            self.guard.update(on=bool(data.get("on")), action="pause" if data.get("action") == "pause" else "end", sec=max(3, min(30, int(data.get("sec", 10)))), baseline=None, deadline=0.0, t_poll=0.0)
            self.log("info", "Proteção contra violação ligada." if self.guard["on"] else "Proteção contra violação desligada.")
        elif kind == "guard_cancel":
            if self.guard["deadline"]:
                self.guard.update(deadline=0.0, baseline=None, t_poll=0.0, fail=0)
                self.log("info", "Falso alarme: ação cancelada. A proteção continua vigiando.")
        elif kind == "chat_set":
            msgs = [str(m).strip()[:100] for m in data.get("msgs", []) if str(m).strip()][:50]
            self.chat.update(on=bool(data.get("on")) and bool(msgs), msgs=msgs, min=max(CHAT_MIN_S, int(data.get("min", 45))), max=max(CHAT_MIN_S, int(data.get("max", 90))), random=bool(data.get("random", True)), next=0.0)
            self.log("info", f"Comentários automáticos ligados ({len(msgs)} mensagens)." if self.chat["on"] else "Comentários automáticos desligados.")
        elif kind == "timer_start":
            minutes = max(1, min(24 * 60, int(data["minutes"])))
            self.timer.update(state="running", total=minutes * 60, end_at=time.time() + minutes * 60, left=minutes * 60, warned=set(), fail=0, next_try=0.0)
            self.log("ok", f"Timer armado: a LIVE será encerrada em {minutes} min.")
        elif kind == "timer_pause" and self.timer["state"] == "running":
            self.timer.update(state="paused", left=max(0, self.timer["end_at"] - time.time()))
            self.log("info", "Timer pausado.")
        elif kind == "timer_resume" and self.timer["state"] == "paused":
            self.timer.update(state="running", end_at=time.time() + self.timer["left"])
            self.log("info", "Timer retomado.")
        elif kind == "timer_cancel":
            self.timer.update(state="idle", total=0, left=0, end_at=0.0)
            self.log("info", "Timer cancelado.")

    # ---- rotina periódica ----
    def tick(self, page: Page) -> None:
        if getattr(self, "_listened", None) is not page:
            self._listened = page
            page.on("request", learn_add_request)
        now = time.time()
        if now - self._t_room > 15:
            self._t_room = now
            rid = room_id(page)
            if rid is not None:
                if rid != self.room:
                    self.log("ok" if rid else "info", "LIVE detectada." if rid else "Nenhuma LIVE no ar.")
                    if not rid:
                        self.pinned = None
                self.room = rid
        if now - self._t_list > 30:
            self._t_list = now
            prods = bag_products(page)
            if prods is not None:
                self.products = prods
        self._tick_auto(page, now)
        self._tick_chat(page, now)
        self._tick_guard(page, now)
        self._tick_timer(page, now)

    def _pin(self, page: Page, pid: str) -> bool:
        if not self.room:
            self.log("warn", "Sem LIVE no ar: inicie a LIVE antes de fixar.")
            return False
        if pin(page, self.room, pid):
            item = next((p for p in self.products if p["id"] == pid), {"id": pid, "title": pid})
            self.pinned = {"id": pid, "title": item["title"], "at": time.time()}
            self.log("ok", f"Fixado: {item['title'][:50]}")
            return True
        self.log("err", "O TikTok não aceitou a fixação (ela só vale com a LIVE no ar e o produto na sacola).")
        return False

    def _tick_auto(self, page: Page, now: float) -> None:
        a = self.auto
        if not (a["on"] and self.room and self.products) or now - self._t_auto < a["sec"]:
            return
        self._t_auto = now
        pool = [p["id"] for p in self.products if not a["ids"] or p["id"] in a["ids"]]
        if not pool:
            if not self._warned_pool:
                self._warned_pool = True
                self.log("warn", "Troca automática sem itens: nenhum produto marcado está na sacola da LIVE. Use 'Colocar marcados na sacola'.")
            return
        self._warned_pool = False
        if a["mode"] == "aleatorio" and len(pool) > 1:
            choices = [x for x in pool if not self.pinned or x != self.pinned["id"]]
            pid = random.choice(choices)
        else:
            pid = pool[self._rot % len(pool)]
            self._rot += 1
        self._pin(page, pid)

    def _tick_timer(self, page: Page, now: float) -> None:
        t = self.timer
        if t["state"] != "running":
            return
        left = t["end_at"] - now
        for mark, text in ((300, "5 minutos"), (60, "1 minuto")):
            if left <= mark and mark not in t["warned"] and t["total"] > mark:
                t["warned"].add(mark)
                self.log("warn", f"Faltam {text} para o encerramento automático da LIVE.")
        if left > 0 or now < t["next_try"]:
            return
        self.log("warn", "Tempo esgotado.")
        if self._attempt_end(page, now, t, "pelo timer") in ("done", "gave_up"):
            self.timer.update(state="idle", total=0, left=0, end_at=0.0)

    def _attempt_end(self, page: Page, now: float, holder: dict, why: str) -> str:
        """Tenta encerrar pela tela. 'done' | 'retry' (tenta de novo em 10 s) | 'gave_up' (6 falhas)."""
        self.log("warn", f"Encerrando a LIVE ({why})…")
        done = False
        try:
            done = end_live(page)
        except Exception as e:  # noqa: BLE001
            self.log("err", f"Erro ao encerrar: {str(e).splitlines()[0]}")
        if done and room_id(page) in ("", None):
            self.log("ok", f"LIVE encerrada ({why}).")
            self.room, self.pinned = "", None
            return "done"
        holder["fail"] = holder.get("fail", 0) + 1
        holder["next_try"] = now + 10
        if holder["fail"] == 1:
            self.log("err", f"Não consegui encerrar pela tela. Estrutura salva em {snapshot_failure(page, 'encerrar')}. ENCERRE A LIVE MANUALMENTE.")
        if holder["fail"] >= 6:
            self.log("err", "Desisti de encerrar automaticamente depois de 6 tentativas. A LIVE continua no ar.")
            return "gave_up"
        return "retry"

    # ---- proteção contra violação ----
    def _tick_guard(self, page: Page, now: float) -> None:
        g = self.guard
        if not (g["on"] and self.room):
            g["baseline"] = None if not self.room else g["baseline"]
            return
        if g["deadline"]:
            if now < g["deadline"] or now < g["next_try"]:
                return
            if g["action"] == "pause":
                self.auto["on"] = False
                self.chat["on"] = False
                self.log("warn", "Proteção: automações pausadas (fixação e comentários). A LIVE continua no ar.")
                g.update(deadline=0.0, baseline=None)
                self.stop_clip = True  # o gui para o vídeo da marca
                return
            if self._attempt_end(page, now, g, "proteção contra violação") in ("done", "gave_up"):
                g.update(deadline=0.0, baseline=None, fail=0)
            return
        if now - g["t_poll"] < 20:
            return
        g["t_poll"] = now
        n = violations_active(page)
        if n is None:
            return
        if g["baseline"] is None:
            g["baseline"] = n
            self.log("info", f"Proteção ligada ({n} restrição(ões) já existente(s) na conta).")
        elif n > g["baseline"]:
            g["deadline"] = now + g["sec"]
            g["fail"] = 0
            self.log("err", f"RESTRIÇÃO NOVA DETECTADA no TikTok. {'Encerrando a LIVE' if g['action'] == 'end' else 'Pausando as automações'} em {g['sec']} s. Clique em 'Falso alarme' para cancelar.")
        elif n < g["baseline"]:
            g["baseline"] = n

    # ---- comentários automáticos (digitados no chat da própria tela) ----
    def _tick_chat(self, page: Page, now: float) -> None:
        c = self.chat
        if not (c["on"] and self.room and c["msgs"]) or now < c["next"]:
            return
        lo = max(CHAT_MIN_S, c["min"])
        c["next"] = now + random.uniform(lo, max(lo, c["max"]))
        if c["random"] and len(c["msgs"]) > 1:
            choices = [i for i in range(len(c["msgs"])) if i != c["last"]]
            idx = random.choice(choices)
        else:
            idx = c["idx"] % len(c["msgs"])
            c["idx"] += 1
        try:
            sent = send_comment(page, c["msgs"][idx])
        except Exception:  # noqa: BLE001
            sent = False
        if sent:
            c["last"], c["fail"] = idx, 0
            self.log("ok", f"Comentário enviado: {c['msgs'][idx][:40]}")
            return
        c["fail"] += 1
        if c["fail"] >= 3:
            c["on"] = False
            self.log("err", f"Não achei o campo de chat do Console de LIVE; desliguei os comentários automáticos. Estrutura salva em {snapshot_failure(page, 'chat')}.")
