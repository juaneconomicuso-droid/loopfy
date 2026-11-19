"""Ponte Python do mixer: injeta mixer.js na página, serve os vídeos da marca e recebe os comandos do operador.

Regras de projeto (de propósito): a base da live é câmera e microfone reais; o clipe só toca quando o operador
manda, uma vez, sem loop e sem sequência automática. Os arquivos ficam no computador e são servidos à página
por uma rota interna do navegador controlado (https://loopfy.clips/c/<id>), sem abrir porta de rede.
"""
from __future__ import annotations

import json
import mimetypes
import re
import uuid
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import BrowserContext, Route

from .sources import load_config, save_config

UI_DIR = Path(__file__).with_name("ui")
CLIP_HOST = "https://loopfy.clips"
ALLOWED = {".mp4", ".m4v", ".mov", ".webm"}
MAX_CLIP_BYTES = 400 * 1024 * 1024
CHUNK = 8 * 1024 * 1024
_RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def add_clip(path: str) -> dict:
    p = Path(path)
    if p.suffix.lower() not in ALLOWED:
        return {"ok": False, "msg": f"Formato não suportado ({p.suffix}). Use mp4, mov ou webm."}
    if not p.is_file():
        return {"ok": False, "msg": "Arquivo não encontrado."}
    if p.stat().st_size > MAX_CLIP_BYTES:
        return {"ok": False, "msg": "Arquivo acima de 400 MB. Comprima o vídeo."}
    cfg = load_config()
    if any(c["path"] == str(p) for c in cfg["clips"]):
        return {"ok": True, "cfg": cfg}
    cfg["clips"].append({"id": uuid.uuid4().hex[:10], "name": p.stem[:60], "path": str(p)})
    return {"ok": True, "cfg": save_config(cfg)}


def remove_clip(clip_id: str) -> dict:
    cfg = load_config()
    cfg["clips"] = [c for c in cfg["clips"] if c["id"] != clip_id]
    return {"ok": True, "cfg": save_config(cfg)}


def move_clip(clip_id: str, delta: int) -> dict:
    """Sobe (-1) ou desce (+1) um vídeo na ordem da sequência."""
    cfg = load_config()
    clips = cfg["clips"]
    i = next((k for k, c in enumerate(clips) if c["id"] == clip_id), None)
    if i is not None and 0 <= i + delta < len(clips):
        clips[i], clips[i + delta] = clips[i + delta], clips[i]
        cfg = save_config({"clips": clips})
    return {"ok": True, "cfg": cfg}


def _lookup(clip_id: str) -> Path | None:
    for c in load_config()["clips"]:
        if c["id"] == clip_id and Path(c["path"]).is_file():
            return Path(c["path"])
    return None


def _serve(route: Route) -> None:
    req = route.request
    cors = {"Access-Control-Allow-Origin": "*", "Accept-Ranges": "bytes"}
    if req.method == "OPTIONS":
        route.fulfill(status=204, headers={**cors, "Access-Control-Allow-Headers": "range"})
        return
    clip_id = unquote(urlsplit(req.url).path.rsplit("/c/", 1)[-1])
    path = _lookup(clip_id)
    if not path:
        route.fulfill(status=404, headers=cors, body="")
        return
    size = path.stat().st_size
    ctype = mimetypes.guess_type(path.name)[0] or "video/mp4"
    start, end, status = 0, size - 1, 200
    if size > CHUNK and not req.headers.get("range"):
        end, status = CHUNK - 1, 206
    m = _RANGE.fullmatch(req.headers.get("range", "") or "")
    if m:
        a, b = m.group(1), m.group(2)
        if a:
            start = int(a)
            end = int(b) if b else size - 1
        elif b:
            start = max(0, size - int(b))
        end = min(end, size - 1, start + CHUNK - 1)  # devolve em pedaços: não carrega o arquivo inteiro na memória
        status = 206
    with path.open("rb") as f:
        f.seek(start)
        body = f.read(end - start + 1)
    headers = {**cors, "Content-Type": ctype, "Content-Length": str(len(body))}
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    route.fulfill(status=status, headers=headers, body=body)


def install(ctx: BrowserContext, cfg: dict | None = None) -> None:
    """Chamar antes de abrir a página da LIVE."""
    cfg = cfg or load_config()
    pre = "window.__LOOPFY_CFG=" + json.dumps({
        "camera": cfg.get("camera", ""), "mic": cfg.get("mic", ""), "clipHost": CLIP_HOST,
        "duck": cfg.get("duck", 25) / 100, "clipVol": cfg.get("clipVol", 100) / 100,
    }) + ";\n"
    ctx.add_init_script(pre + (UI_DIR / "mixer.js").read_text("utf-8"))
    ctx.route(CLIP_HOST + "/**", _serve)
