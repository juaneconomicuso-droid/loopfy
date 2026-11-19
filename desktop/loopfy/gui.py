"""Loopfy Desktop — interface gráfica.

Janela nativa (pywebview + WebView2) com a interface em HTML/JS. O Playwright vive numa thread própria, porque
sua API síncrona só funciona na thread que o criou; a interface conversa com ela por uma fila de tarefas.
A interface não decide nada de licença: toda tarefa do navegador passa por @requires_license no motor.
"""
from __future__ import annotations

import json
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import webview
from playwright.sync_api import sync_playwright

from . import browser, discover, license_client, live, mixer, products, sources
from .license_client import LicenseError, requires_license

UI = Path(__file__).with_name("ui") / "index.html"
ACCOUNT_FILE = browser.DATA / "account.json"
LIVE_KINDS = {"guard_set", "guard_cancel", "chat_set", "refresh", "bag_add", "pin", "unpin", "auto", "timer_start", "timer_pause", "timer_resume", "timer_cancel"}

LIC_MSG = {
    "invalid": "Chave inválida ou desativada.",
    "expired": "Esta licença expirou.",
    "device_limit": "Esta licença já está em uso no número máximo de computadores.",
    "bad_proof": "Não foi possível validar este computador. Tente de novo.",
    "rate_limited": "Muitas tentativas. Aguarde alguns minutos.",
    "network": "Não consegui falar com o servidor de licença. Ele está ligado?",
    "bad_request": "Chave em formato inválido.",
}


class Worker(threading.Thread):
    """Dono do Playwright: executa uma tarefa do navegador por vez."""

    def __init__(self, log):
        super().__init__(daemon=True)
        self.q: queue.Queue = queue.Queue()
        self.log = log
        self.busy = ""
        self.stop = threading.Event()

    def run(self) -> None:
        with sync_playwright() as pw:
            self.pw = pw
            while True:
                name, fn = self.q.get()
                self.busy = name
                self.stop.clear()
                try:
                    fn()
                except LicenseError as e:
                    self.log("err", str(e))
                except Exception as e:  # noqa: BLE001 — qualquer falha vira aviso, nunca derruba a janela
                    self.log("err", f"Erro: {str(e).splitlines()[0] if str(e) else type(e).__name__}")
                finally:
                    self.busy = ""

    def submit(self, name: str, fn) -> bool:
        if self.busy or not self.q.empty():
            return False
        self.q.put((name, fn))
        return True


class Api:
    """Métodos chamados pelo JavaScript (window.pywebview.api.*)."""

    def __init__(self) -> None:
        self._log: list[dict] = []
        self._lock = threading.Lock()
        self.worker = Worker(self._add)
        self.worker.start()
        self.rec: discover.Recorder | None = None
        self.secrets: dict[str, str] = {}
        self.map_flag = threading.Event()
        self.cmds: queue.Queue = queue.Queue()
        self.ops = live.LiveOps(self._add)
        self.frame: str | None = None
        self.mixer_state: dict | None = None
        self.muted = False

    # ---- registro ----
    def _add(self, kind: str, text: str) -> None:
        with self._lock:
            self._log.append({"i": len(self._log), "t": time.strftime("%H:%M:%S"), "kind": kind, "text": text})

    def poll(self, since: int = 0) -> dict:
        with self._lock:
            new = self._log[since:]
        rec = self.rec
        return {
            "log": new,
            "account": self.account_state(),
            "live": self.ops.snapshot(),
            "frame": self.frame if self.worker.busy == "prepare" else None,
            "mixer": self.mixer_state if self.worker.busy == "prepare" else None,
            "busy": self.worker.busy,
            "found": [{"tag": t, "masked": discover.mask(v)} for t, v in (rec.found.items() if rec else [])],
            "n": rec.n if rec else 0,
        }

    # ---- licença ----
    def license_state(self) -> dict:
        try:
            p = license_client.authorize()
        except LicenseError as e:
            return {"active": False, "error": str(e)}
        if not p:
            return {"active": False}
        return {"active": True, "plan": p.get("plan"), "exp": p.get("exp")}

    def activate(self, key: str) -> dict:
        key = (key or "").strip()
        if len(key) < 10:
            return {"ok": False, "msg": "Cole a chave de licença completa."}
        r = license_client.activate(key)
        if r.get("ok"):
            self._add("ok", "Licença ativada.")
            return {"ok": True}
        return {"ok": False, "msg": LIC_MSG.get(r.get("code", ""), "Não foi possível ativar.")}

    # ---- navegador ----
    # ---- estado da conta: o login é feito uma vez; depois aparece "conectada" ----
    def account_state(self) -> dict:
        try:
            return json.loads(ACCOUNT_FILE.read_text("utf-8"))
        except (OSError, ValueError):
            return {"connected": False}

    def _mark_session(self, ok: bool) -> None:
        browser.DATA.mkdir(parents=True, exist_ok=True)
        ACCOUNT_FILE.write_text(json.dumps({"connected": ok, "at": time.strftime("%d/%m %H:%M")}), "utf-8")

    def _require_session(self, page) -> None:
        """Se o TikTok mandou para o login, a sessão caiu: marca como desconectada e avisa."""
        if any(x in page.url for x in ("login", "passport")):
            self._mark_session(False)
            raise RuntimeError("A sessão do TikTok expirou. Clique em 'Entrar na conta' para conectar de novo.")
        self._mark_session(True)

    def login(self) -> dict:
        @requires_license
        def job() -> None:
            self._add("info", "Abrindo o navegador. Entre na sua conta do TikTok; o Loopfy percebe sozinho quando você entrar.")
            ctx = browser.open_session(self.worker.pw)
            connected = False
            try:
                browser.current_page(ctx).goto(browser.SELLER_HOME)
                since = None
                while ctx.pages and not self.worker.stop.is_set():
                    pg = ctx.pages[0]
                    pg.wait_for_timeout(700)
                    url = pg.url
                    logged = "tiktok.com" in url and not any(x in url for x in ("login", "passport", "signup", "verify"))
                    since = (since or time.time()) if logged else None
                    if since and time.time() - since > 3:
                        connected = True
                        break
            except Exception:
                pass
            finally:
                try:
                    ctx.close()
                except Exception:
                    pass
            if connected:
                self._mark_session(True)
                self._add("ok", "Conta conectada. Você não precisa entrar de novo neste computador.")
            else:
                self._add("warn", "A janela foi fechada antes de terminar o login.")

        return self._start("login", job)

    def check(self) -> dict:
        @requires_license
        def job() -> None:
            self._add("info", "Abrindo o Gerenciador de LIVE…")
            ctx = browser.open_session(self.worker.pw)
            try:
                page = browser.current_page(ctx)
                page.goto(browser.LIVE_MANAGER, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                msg = browser.diagnose_url(page.url)
                self._mark_session(not any(x in page.url for x in ("login", "passport")))
                self._add("warn" if msg else "ok", msg or "Gerenciador de LIVE acessível com esta conta.")
            finally:
                ctx.close()

        return self._start("check", job)

    def discover_start(self) -> dict:
        @requires_license
        def job() -> None:
            self.secrets = {}
            rec = discover.Recorder(on_candidate=lambda tag, v: self._found(tag, v))
            self.rec = rec
            self._add("info", "Gravando. No navegador, abra a tela de transmitir por software / chave de transmissão.")
            ctx = browser.open_session(self.worker.pw)
            rec.attach(ctx)
            try:
                browser.current_page(ctx).goto(browser.LIVE_MANAGER)
                while ctx.pages and not self.worker.stop.is_set():
                    ctx.pages[0].wait_for_timeout(300)
            except Exception:
                pass
            finally:
                try:
                    ctx.close()
                except Exception:
                    pass
            self._add("ok", f"Gravação encerrada: {rec.n} respostas, {len(rec.found)} candidato(s).")

        return self._start("discover", job)

    def discover_stop(self) -> dict:
        self.worker.stop.set()
        return {"ok": True}

    # ---- clipes da marca (tocam só por comando do operador) ----
    @staticmethod
    def _live_page(ctx):
        """A aba do Seller Center (se o TikTok abrir uma janela extra, não usamos ela)."""
        for pg in ctx.pages:
            if "tiktok.com" in pg.url and "/streamer" in pg.url:
                return pg
        return ctx.pages[0] if ctx.pages else None

    @staticmethod
    def _mixer_frame(page):
        """Acha onde o mixer realmente abriu a câmera (outra aba ou quadro interno da página da LIVE)."""
        pages = [page] + [p for p in page.context.pages if p is not page]
        for pg in pages:
            for fr in pg.frames:
                try:
                    if fr.evaluate("!!(window.__loopfy && window.__loopfy.status().built)"):
                        return fr
                except Exception:  # noqa: BLE001
                    continue
        return None

    @staticmethod
    def _mixer_error(page) -> str:
        """Motivo de a câmera Loopfy não ter aberto + o que o navegador enxerga de câmeras/microfones."""
        for pg in [page] + [p for p in page.context.pages if p is not page]:
            for fr in pg.frames:
                try:
                    st = fr.evaluate("window.__loopfy ? window.__loopfy.status() : null")
                    if st and st.get("error"):
                        devs = fr.evaluate("window.__loopfy.devices()")
                        return f"{st['error']} Dispositivos que o navegador vê: {'; '.join(devs) or 'nenhum'}."
                except Exception:  # noqa: BLE001
                    continue
        return ""

    def _drain_cmds(self, page) -> None:
        orig_page = page
        while True:
            try:
                kind, clip = self.cmds.get_nowait()
            except queue.Empty:
                return
            try:
                if kind in LIVE_KINDS:
                    self.ops.handle(kind, clip, orig_page)
                    continue
                page = self._mixer_frame(orig_page)
                if page is None:
                    if kind in ("seq", "play"):
                        why = self._mixer_error(orig_page)
                        self._add("err", why or "A LIVE ainda não está usando a 'Loopfy Câmera'. Selecione 'Loopfy Câmera' e 'Loopfy Microfone' na LIVE (ou clique em Iniciar LIVE) e tente de novo.")
                    continue
                if False:
                    pass
                elif kind == "mute":
                    page.evaluate("(on) => window.__loopfy && window.__loopfy.setMute(on)", bool(clip["on"]))
                    self.muted = bool(clip["on"])
                elif kind == "levels":
                    page.evaluate("([d, c]) => window.__loopfy && window.__loopfy.setLevels(d / 100, c / 100)", [clip["duck"], clip["clipVol"]])
                elif kind == "seq":
                    page.evaluate("(l) => window.__loopfy.playSeq(l)", [{"id": c["id"], "name": c["name"]} for c in clip["clips"]])
                    self._add("ok", f"Sequência no ar: {len(clip['clips'])} vídeo(s), uma vez cada, na ordem (o microfone continua ao vivo).")
                elif kind == "play":
                    page.evaluate("([id, name]) => window.__loopfy.play(id, name)", [clip["id"], clip["name"]])
                    self._add("ok", f"Clipe no ar: {clip['name']} (o microfone continua ao vivo).")
                elif kind == "stop":
                    page.evaluate("window.__loopfy && window.__loopfy.stop()")
            except Exception as e:  # noqa: BLE001
                self._add("err", f"Não foi possível tocar o clipe: {str(e).splitlines()[0]}. A fonte 'Loopfy Câmera' está selecionada na LIVE?")

    # ---- painel da LIVE: fixar produto e timer (só valem com a LIVE preparada) ----
    def _live_cmd(self, kind: str, data: dict | None = None) -> dict:
        if self.worker.busy != "prepare":
            return {"ok": False, "msg": "Clique em Preparar LIVE primeiro: o painel da LIVE funciona na mesma janela do navegador."}
        self.cmds.put((kind, data or {}))
        return {"ok": True}

    def guard_set(self, on: bool, action: str, sec: int) -> dict:
        cfg = sources.save_config({"guard": {"on": on, "action": action, "sec": sec}})
        if self.worker.busy == "prepare":
            self.cmds.put(("guard_set", cfg["guard"]))
        return {"ok": True, "cfg": cfg}

    def guard_cancel(self) -> dict:
        return self._live_cmd("guard_cancel")

    def chat_set(self, on: bool, msgs: list, mn: int, mx: int, rnd: bool) -> dict:
        cfg = sources.save_config({"chat": {"msgs": msgs, "min": mn, "max": mx, "random": rnd}})
        if self.worker.busy == "prepare":
            self.cmds.put(("chat_set", {**cfg["chat"], "on": on}))
        elif on:
            return {"ok": False, "msg": "Os comentários automáticos ligam com a LIVE preparada. As mensagens ficaram salvas.", "cfg": cfg}
        return {"ok": True, "cfg": cfg}

    def set_mute(self, on: bool) -> dict:
        return self._live_cmd("mute", {"on": bool(on)})

    def start_live(self) -> dict:
        """Um clique: abre o navegador, seleciona as fontes Loopfy e clica em Iniciar LIVE."""
        return self.prepare_live(True)

    def live_pin(self, product_id: str) -> dict:
        return self._live_cmd("pin", {"id": product_id})

    def live_bag_add(self, ids: list) -> dict:
        return self._live_cmd("bag_add", {"ids": [str(i) for i in (ids or [])][:150]})

    def live_import(self) -> dict:
        """Com a LIVE preparada: coloca na sacola da LIVE todos os produtos já importados que ainda não estão nela."""
        ids = [p["id"] for p in products.load()]
        if not ids:
            return {"ok": False, "msg": "Nada importado ainda. Importe a sacolinha com o navegador fechado primeiro."}
        self._live_cmd("bag_add", {"ids": ids})
        return self._live_cmd("refresh")

    def live_unpin(self) -> dict:
        return self._live_cmd("unpin")

    def live_refresh(self) -> dict:
        return self._live_cmd("refresh")

    def live_auto(self, on: bool, sec: int, mode: str, ids: list) -> dict:
        return self._live_cmd("auto", {"on": on, "sec": sec, "mode": mode, "ids": ids})

    def timer_start(self, minutes: int) -> dict:
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            return {"ok": False, "msg": "Informe os minutos."}
        return self._live_cmd("timer_start", {"minutes": minutes})

    def timer_pause(self) -> dict:
        return self._live_cmd("timer_pause")

    def timer_resume(self) -> dict:
        return self._live_cmd("timer_resume")

    def timer_cancel(self) -> dict:
        return self._live_cmd("timer_cancel")

    def clip_play(self, clip_id: str) -> dict:
        clip = next((c for c in sources.load_config()["clips"] if c["id"] == clip_id), None)
        if not clip or self.worker.busy != "prepare":
            return {"ok": False, "msg": "Clique em Preparar LIVE e selecione as fontes antes de tocar um clipe."}
        self.cmds.put(("play", clip))
        return {"ok": True}

    def clip_seq(self, ids: list) -> dict:
        """Toca os vídeos marcados em sequência (uma vez cada, na ordem da lista). Sem loop."""
        if self.worker.busy != "prepare":
            return {"ok": False, "msg": "Inicie a LIVE (ou Só preparar) antes de tocar a sequência."}
        by_id = {c["id"]: c for c in sources.load_config()["clips"]}
        chosen = [by_id[i] for i in ids if i in by_id]
        if not chosen:
            return {"ok": False, "msg": "Marque pelo menos um vídeo para a sequência."}
        self.cmds.put(("seq", {"clips": chosen}))
        return {"ok": True}

    def clip_move(self, clip_id: str, delta: int) -> dict:
        return mixer.move_clip(clip_id, -1 if delta < 0 else 1)

    def set_levels(self, duck: int, clip_vol: int) -> dict:
        """Salva e, se a LIVE estiver preparada, aplica na hora os volumes do microfone e do vídeo."""
        cfg = sources.save_config({"duck": duck, "clipVol": clip_vol})
        if self.worker.busy == "prepare":
            self.cmds.put(("levels", {"duck": cfg["duck"], "clipVol": cfg["clipVol"]}))
        return {"ok": True, "cfg": cfg}

    def clip_stop(self) -> dict:
        self.cmds.put(("stop", None))
        return {"ok": True}

    def clip_add(self) -> dict:
        win = webview.windows[0] if webview.windows else None
        if not win:
            return {"ok": False, "msg": "Janela indisponível."}
        paths = win.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True, file_types=("Vídeos (*.mp4;*.mov;*.webm;*.m4v)",))
        last = {"ok": True, "cfg": sources.load_config()}
        for p in paths or []:
            last = mixer.add_clip(p)
            if not last.get("ok"):
                self._add("warn", last.get("msg", "Arquivo recusado."))
        return last

    def clip_remove(self, clip_id: str) -> dict:
        return mixer.remove_clip(clip_id)

    def get_config(self) -> dict:
        return sources.load_config()

    def set_config(self, cfg: dict) -> dict:
        return {"ok": True, "cfg": sources.save_config(cfg or {})}

    def prepare_live(self, autostart: bool | None = None) -> dict:
        """Abre o Gerenciador de LIVE, autoriza câmera/microfone e seleciona as fontes configuradas.
        autostart=True também clica em Iniciar LIVE; False/None para na prévia (o padrão salvo vale se None)."""
        @requires_license
        def job() -> None:
            cfg = sources.load_config()
            if autostart is not None:
                cfg["autostart"] = bool(autostart)  # só desta vez; não altera o que está salvo
            ctx = browser.open_session(self.worker.pw)
            try:
                sources.grant_media(ctx)
                mixer.install(ctx, cfg)  # fontes virtuais "Loopfy Câmera/Microfone" + rota dos clipes
                page = browser.current_page(ctx)
                page.goto(browser.LIVE_MANAGER)
                page.wait_for_timeout(3000)
                self._require_session(page)
                self._fill_bag(page, cfg)
                ok = sources.select_sources(page, cfg, self._add)
                if ok and cfg.get("autostart"):
                    btn = page.get_by_role("button", name="Iniciar LIVE")
                    if btn.count() and btn.last.is_enabled():
                        btn.last.click()
                        self._add("ok", "LIVE iniciada.")
                    else:
                        self._add("warn", "Botão 'Iniciar LIVE' indisponível (sacola vazia ou fonte sem imagem).")
                elif ok:
                    self._add("ok", "Fontes selecionadas. Confira a prévia e clique em Iniciar LIVE.")
                # mantém o navegador aberto até o usuário fechar (ou clicar em Encerrar) e atende os comandos de clipe
                last = ""
                self.ops.reset()
                self.ops.configure(cfg)
                while ctx.pages and not self.worker.stop.is_set():
                    self._live_page(ctx).wait_for_timeout(400)
                    self._drain_cmds(self._live_page(ctx))
                    try:
                        self.ops.tick(self._live_page(ctx))
                        if self.ops.stop_clip:
                            self.ops.stop_clip = False
                            mf = self._mixer_frame(self._live_page(ctx))
                            if mf:
                                mf.evaluate("window.__loopfy.stop()")
                    except Exception as e:  # noqa: BLE001 — falha de leitura não derruba a sessão
                        if "closed" in str(e).lower():
                            break
                    try:
                        mf = self._mixer_frame(self._live_page(ctx))
                        st = mf.evaluate("window.__loopfy.status()") if mf else None
                        self.frame = mf.evaluate("window.__loopfy.frame()") if mf else None
                        self.mixer_state = st
                    except Exception:
                        st = None
                    cur = (st or {}).get("status", "")
                    if cur != last and last == "playing" and cur in ("ended", "error", "stopped"):
                        self._add("info" if cur != "error" else "err", {"ended": "Clipe terminou.", "stopped": "Clipe parado.", "error": "Erro ao tocar o clipe."}[cur])
                    last = cur
            except Exception as e:  # noqa: BLE001
                self._add("err", f"Erro: {str(e).splitlines()[0] if str(e) else type(e).__name__}")
            finally:
                try:
                    ctx.close()
                except Exception:
                    pass

        return self._start("prepare", job)

    def _fill_bag(self, page, cfg: dict) -> None:
        """Garante na sacola da LIVE os produtos escolhidos (marcados), para poder fixar e trocar."""
        try:
            known = {p["id"] for p in products.load()}
            want = [i for i in cfg.get("selected", []) if i in known]
            have = {p["id"] for p in (live.bag_products(page) or [])}
            miss = [i for i in want if i not in have]
            if miss:
                done, detail = live.add_to_bag(page, miss, "")
                self._add("ok" if len(done) == len(miss) else "warn", f"{len(done)} de {len(miss)} produto(s) marcados colocados na sacola." + (f" {detail}" if detail else ""))
        except Exception as e:  # noqa: BLE001
            self._add("warn", f"Não consegui conferir a sacola: {str(e).splitlines()[0]}")

    # ---- produtos ----
    def products_list(self) -> list:
        return products.load()

    def products_sync(self) -> dict:
        """Abre 'Adicionar produtos', rola a lista e lê as respostas do TikTok. Só leitura."""
        @requires_license
        def job() -> None:
            bodies: list[str] = []
            calls: list[dict] = []

            def on_resp(resp) -> None:
                try:
                    if "/api/" not in resp.url or "json" not in resp.headers.get("content-type", ""):
                        return
                    txt = resp.text()[:400_000]
                except Exception:
                    return
                bodies.append(txt)
                calls.append({"m": resp.request.method, "path": resp.url.split("?")[0].split(".com")[-1], "status": resp.status, "req": (resp.request.post_data or "")[:600]})

            self._add("info", "Abrindo o Gerenciador de LIVE para ler seus produtos…")
            ctx = browser.open_session(self.worker.pw)
            try:
                ctx.on("response", on_resp)
                page = browser.current_page(ctx)
                page.goto(browser.LIVE_MANAGER, wait_until="domcontentloaded")
                page.wait_for_timeout(6000)
                self._require_session(page)
                api_items = live.catalog(page)
                if api_items:
                    # caminho direto: a mesma lista que o 'Adicionar produtos' mostra, sem depender da tela
                    products.save(api_items)
                    ok_items = [i for i in api_items if i.get("available", True)]
                    self._add("ok", f"{len(api_items)} produto(s) lidos da sua sacolinha" + (f" ({len(api_items) - len(ok_items)} esgotado(s)/indisponível(is) ficam de fora da sacola)." if len(ok_items) != len(api_items) else "."))
                    done, detail = live.add_to_bag(page, [i["id"] for i in ok_items], "")
                    self._add("ok" if len(done) == len(ok_items) else "warn", f"{len(done)} de {len(ok_items)} produto(s) na sacola da LIVE." + (f" {detail}" if detail else ""))
                    return
                self._add("warn", "A leitura direta falhou; tentando pela tela.")
                btn = page.get_by_role("button", name=re.compile(r"adicionar produtos?", re.I))
                exact = re.compile(r"^\s*Adicionar produtos\s*$", re.I)
                btn = page.get_by_role("button", name=exact)
                if not btn.count():
                    page.get_by_text(re.compile(r"^\s*\+?\s*Adicionar\s*$")).first.click()  # abre o menu "+ Adicionar"
                    page.wait_for_timeout(700)
                    btn = page.get_by_text(exact)
                if not btn.count():
                    raise RuntimeError("Não achei o botão 'Adicionar produtos' no Console de LIVE.")
                btn.first.click()
                page.wait_for_timeout(4000)
                # rola a lista para carregar todos os produtos (até estabilizar)
                dlg = page.get_by_role("dialog")
                box = (dlg.last.bounding_box() if dlg.count() else None) or {"x": 400, "y": 200, "width": 600, "height": 400}
                cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                stable, last_n = 0, -1
                for _ in range(40):
                    page.mouse.move(cx, cy)
                    page.mouse.wheel(0, 1400)
                    page.wait_for_timeout(900)
                    n = len(products.extract(bodies))
                    stable = stable + 1 if n == last_n else 0
                    last_n = n
                    if stable >= 3:
                        break
                items = products.extract(bodies)
                products.save(items)
                # diagnóstico local para ajustar a automação (sem valores digitados)
                try:
                    snap = (dlg.last if dlg.count() else page.locator("body")).aria_snapshot(timeout=5000)
                except Exception as e:  # noqa: BLE001
                    snap = f"(sem leitura: {e})"
                (browser.DATA / "diag-produtos.txt").write_text(
                    "CHAMADAS\n" + "\n".join(f"{c['m']} {c['path']} {c['status']} {c['req']}" for c in calls) + "\n\nTELA\n" + snap, encoding="utf-8")
                page.keyboard.press("Escape")
                if items:
                    # importar = trazer para o painel E colocar na sacola da LIVE (senão não dá para selecionar/fixar lá)
                    page.wait_for_timeout(800)
                    done, detail = live.add_to_bag(page, [i["id"] for i in items], "")
                    self._add("ok" if len(done) == len(items) else "warn", f"{len(done)} de {len(items)} produto(s) na sacola da LIVE." + (f" {detail}" if detail else ""))
                self._add("ok" if items else "warn", f"{len(items)} produto(s) lidos." if items else "Nenhum produto reconhecido. Salvei um diagnóstico em data\\diag-produtos.txt.")
            finally:
                ctx.close()

        return self._start("products", job)

    def map_start(self) -> dict:
        """Abre o Gerenciador de LIVE e fica esperando; 'Capturar tela' salva a estrutura da tela aberta."""
        @requires_license
        def job() -> None:
            self._add("info", "Navegador aberto. Vá até a tela que quer mapear e clique em 'Capturar tela'.")
            ctx = browser.open_session(self.worker.pw)
            try:
                browser.current_page(ctx).goto(browser.LIVE_MANAGER)
                while ctx.pages and not self.worker.stop.is_set():
                    self._live_page(ctx).wait_for_timeout(300)
                    if self.map_flag.is_set():
                        self.map_flag.clear()
                        self._snapshot(self._live_page(ctx))
            except Exception:
                pass
            finally:
                try:
                    ctx.close()
                except Exception:
                    pass
            self._add("ok", "Mapeamento encerrado.")

        return self._start("map", job)

    def map_capture(self) -> dict:
        self.map_flag.set()
        return {"ok": True}

    def _snapshot(self, page) -> None:
        """Salva textos e papéis dos elementos da tela (sem valores digitados). Fica só neste computador."""
        out = browser.DATA / f"tela-{time.strftime('%Y%m%d-%H%M%S')}.txt"
        parts = [f"URL: {page.url}\n"]
        for fr in page.frames:
            try:
                snap = fr.locator("body").aria_snapshot(timeout=5000)
                parts.append(f"\n=== frame {fr.url}\n{snap}")
            except Exception as e:  # noqa: BLE001
                parts.append(f"\n=== frame {fr.url}\n(sem leitura: {str(e).splitlines()[0]})")
        out.write_text("".join(parts), encoding="utf-8")
        self._add("ok", f"Tela capturada: {out.name}")

    def _found(self, tag: str, value: str) -> None:
        self.secrets[tag] = value
        self._add("ok", f"Candidato a chave encontrado: {tag}")

    def copy_secret(self, tag: str) -> dict:
        v = self.secrets.get(tag) or (self.rec.found.get(tag) if self.rec else None)
        if not v:
            return {"ok": False}
        subprocess.run(["clip"], input=v.encode("utf-8"), check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self._add("ok", "Valor copiado para a área de transferência. Não compartilhe.")
        return {"ok": True}

    def _start(self, name: str, job) -> dict:
        if not self.worker.submit(name, job):
            return {"ok": False, "msg": "Já há uma tarefa do navegador em andamento."}
        return {"ok": True}


def main() -> int:
    api = Api()
    webview.create_window("Loopfy", str(UI), js_api=api, width=1360, height=820, min_size=(1100, 680), background_color="#030309")
    webview.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())
