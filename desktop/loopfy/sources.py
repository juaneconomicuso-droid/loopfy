"""Seleção automática das fontes de vídeo e de áudio na tela "Configuração de áudio e vídeo" da LIVE.

O Loopfy só escolhe, nas listas que o próprio TikTok mostra, os dispositivos que VOCÊ configurou
(por exemplo "OBS Virtual Camera" para o vídeo e um microfone para o áudio). O que é enviado por esses
dispositivos é responsabilidade de quem opera a live. Não há aqui nenhuma lógica para disfarçar o conteúdo.
"""
from __future__ import annotations

import json
import re
import time
from typing import Callable

from playwright.sync_api import BrowserContext, Page

from .browser import DATA

CONFIG = DATA / "config.json"
DEFAULTS = {
    "video": "Loopfy Câmera",
    "audio": "Loopfy Microfone",
    "autostart": False,
    "camera": "",  # parte do nome da câmera REAL (vazio = a primeira encontrada)
    "mic": "",     # parte do nome do microfone REAL (vazio = o primeiro)
    "duck": 25,    # % do microfone enquanto um vídeo toca
    "clipVol": 100,  # % do áudio do vídeo
    "selected": [],  # ids dos produtos escolhidos para a LIVE
    "seq": [],       # ids dos vídeos marcados para a sequência (vazio = todos)
    "guard": {"on": False, "action": "end", "sec": 10},
    "chat": {"msgs": [], "min": 45, "max": 90, "random": True},
    "clips": [],
}
ORIGINS = ["https://shop.tiktok.com", "https://seller-br.tiktok.com"]

LABEL_VIDEO = "Fonte de vídeo"
LABEL_AUDIO = "Fonte de áudio"
PLACEHOLDER = "Selecionar fonte"


def load_config() -> dict:
    try:
        cfg = {**DEFAULTS, **json.loads(CONFIG.read_text("utf-8"))}
    except (OSError, ValueError):
        return dict(DEFAULTS)
    # configuração antiga (antes do mixer próprio): apontava para "OBS Virtual Camera" e/ou sem fonte de áudio.
    # O Loopfy só funciona com as fontes dele; volta para elas.
    if not cfg["audio"].strip() or "obs" in cfg["video"].lower():
        cfg["video"], cfg["audio"] = DEFAULTS["video"], DEFAULTS["audio"]
    return cfg


def _pct(v) -> int:
    try:
        return max(0, min(100, int(float(v))))
    except (TypeError, ValueError):
        return 100


def _guard(g) -> dict:
    g = g if isinstance(g, dict) else {}
    return {"on": bool(g.get("on")), "action": "pause" if g.get("action") == "pause" else "end", "sec": max(3, min(30, int(g.get("sec", 10) or 10)))}


def _chat(c) -> dict:
    c = c if isinstance(c, dict) else {}
    msgs = [str(m).strip()[:100] for m in c.get("msgs", []) if str(m).strip()][:50]
    lo = max(30, int(c.get("min", 45) or 45))
    return {"msgs": msgs, "min": lo, "max": max(lo, int(c.get("max", 90) or 90)), "random": bool(c.get("random", True))}


def save_config(cfg: dict) -> dict:
    DATA.mkdir(parents=True, exist_ok=True)
    old = load_config()
    clips = cfg.get("clips", old.get("clips", []))
    clean = {
        "video": str(cfg.get("video", old["video"]))[:120].strip(),
        "audio": str(cfg.get("audio", old["audio"]))[:120].strip(),
        "autostart": bool(cfg.get("autostart", old["autostart"])),
        "camera": str(cfg.get("camera", old["camera"]))[:120].strip(),
        "mic": str(cfg.get("mic", old["mic"]))[:120].strip(),
        "duck": _pct(cfg.get("duck", old["duck"])),
        "clipVol": _pct(cfg.get("clipVol", old["clipVol"])),
        "selected": [str(x)[:40] for x in cfg.get("selected", old["selected"]) if x][:200],
        "seq": [str(x)[:20] for x in cfg.get("seq", old["seq"]) if x][:60],
        "guard": _guard(cfg.get("guard", old["guard"])),
        "chat": _chat(cfg.get("chat", old["chat"])),
        "clips": [
            {"id": str(c["id"])[:20], "name": str(c["name"])[:60], "path": str(c["path"])}
            for c in clips if isinstance(c, dict) and {"id", "name", "path"} <= c.keys()
        ],
    }
    CONFIG.write_text(json.dumps(clean, ensure_ascii=False), "utf-8")
    return clean


def grant_media(ctx: BrowserContext) -> None:
    """Pré-autoriza câmera e microfone para o TikTok neste perfil (evita o aviso do navegador)."""
    ctx.grant_permissions(["camera", "microphone"], origin=ORIGINS[0])


def _snapshot_failure(page: Page) -> str:
    out = DATA / f"tela-falha-{time.strftime('%Y%m%d-%H%M%S')}.txt"
    try:
        out.write_text(f"URL: {page.url}\n\n" + page.locator("body").aria_snapshot(timeout=5000), encoding="utf-8")
    except Exception:  # noqa: BLE001
        out.write_text(f"URL: {page.url}\n(sem leitura)", encoding="utf-8")
    return out.name


def _wait_modal(page: Page, log: Callable[[str, str], None], timeout_s: int = 180) -> bool:
    """Espera a tela de fontes aparecer. Se houver um botão claro de iniciar a LIVE, não clica: o usuário decide."""
    log("info", "Aguardando a tela 'Configuração de áudio e vídeo'. Coloque o item na sacola e clique em Iniciar LIVE.")
    end = time.time() + timeout_s
    while time.time() < end:
        if page.get_by_text(LABEL_VIDEO, exact=True).count() and page.get_by_text(LABEL_AUDIO, exact=True).count():
            return True
        page.wait_for_timeout(700)
    return False


def _open_trigger(page: Page, label: str, which: int) -> None:
    """Abre a lista da fonte: o campo 'Selecionar fonte' (ou já preenchido) logo abaixo do rótulo."""
    lab = page.get_by_text(label, exact=True).first
    box = lab.bounding_box()
    if not box:
        raise RuntimeError(f"Rótulo '{label}' sem posição na tela")
    # candidatos: campos de seleção visíveis; escolhe o primeiro cujo topo está abaixo do rótulo
    cands = page.locator('[role="combobox"], .arco-select, [class*="select"] input, [class*="Select"]').all()
    best = None
    best_dy = 1e9
    for c in cands:
        try:
            b = c.bounding_box()
        except Exception:  # noqa: BLE001
            continue
        if not b or b["width"] < 80:
            continue
        dy = b["y"] - (box["y"] + box["height"])
        if -4 <= dy < best_dy and abs(b["x"] - box["x"]) < 40:
            best, best_dy = c, dy
    if best is None:  # plano B: clica no texto do espaço reservado na ordem em que aparece
        best = page.get_by_text(PLACEHOLDER).nth(which if page.get_by_text(PLACEHOLDER).count() > which else 0)
    best.click()
    page.wait_for_timeout(400)


def _choose(page: Page, name: str) -> list[str]:
    """Escolhe a opção cujo nome contém `name`; devolve as opções vistas (para diagnóstico)."""
    opts = page.get_by_role("option").all()
    seen: list[str] = []
    for o in opts:
        try:
            seen.append(o.inner_text(timeout=1000).strip())
        except Exception:  # noqa: BLE001
            pass
    target = page.get_by_role("option", name=re.compile(re.escape(name), re.I))
    if not target.count():
        target = page.get_by_text(re.compile(re.escape(name), re.I))
    if not target.count():
        return seen
    target.first.click()
    page.wait_for_timeout(500)
    return []


def select_sources(page: Page, cfg: dict, log: Callable[[str, str], None]) -> bool:
    video, audio = cfg.get("video", "").strip(), cfg.get("audio", "").strip()
    if not video or not audio:
        log("warn", "Preencha o nome da fonte de vídeo e da fonte de áudio antes.")
        return False
    if not _wait_modal(page, log):
        log("warn", f"A tela de fontes não apareceu a tempo. Estrutura salva em {_snapshot_failure(page)}.")
        return False
    for label, name, which in ((LABEL_VIDEO, video, 0), (LABEL_AUDIO, audio, 1)):
        try:
            _open_trigger(page, label, which)
            seen = _choose(page, name)
        except Exception as e:  # noqa: BLE001
            log("err", f"{label}: {str(e).splitlines()[0]}. Estrutura salva em {_snapshot_failure(page)}.")
            return False
        if seen:
            log("warn", f"{label}: '{name}' não está na lista. Opções vistas: {', '.join(seen) or '(nenhuma)'}")
            page.keyboard.press("Escape")
            return False
        log("ok", f"{label}: '{name}' selecionado.")
    return True
