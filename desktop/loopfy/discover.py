"""Descoberta: grava as respostas JSON do TikTok enquanto você navega e procura a chave de transmissão.

Só LÊ o que a sua própria sessão já recebe. Nada é enviado a servidor nenhum. Valores sensíveis das URLs e
qualquer chave/URL de transmissão encontrada no corpo são MASCARADOS antes de gravar em disco; os valores
reais ficam só na memória do programa, para você copiar. O arquivo de captura (desktop/data) ainda pode ter
dados da conta e de clientes: não compartilhe e apague quando terminar.
"""
from __future__ import annotations

import json
import re
import time
from urllib.parse import parse_qsl, urlsplit, urlunsplit, urlencode

from playwright.sync_api import BrowserContext, Response

from .browser import DATA

SENSITIVE_QS = re.compile(r"(token|bogus|signature|sign|cookie|auth|ttwid|verify)", re.I)
RTMP_RE = re.compile(r"rtmps?://[^\s\"'\\]+", re.I)
KEY_NAMES = re.compile(r"(stream_?key|push_?url|rtmp_?push|stream_?url|push_?stream|stream_?name)", re.I)
HOSTS = ("tiktok.com", "tiktokv.com", "byteoversea.com", "tiktokcdn.com")
MAX_BODY = 40_000


def _clean_url(url: str) -> str:
    p = urlsplit(url)
    qs = [(k, "***" if SENSITIVE_QS.search(k) else v) for k, v in parse_qsl(p.query, keep_blank_values=True)]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(qs), ""))


def mask(v: str) -> str:
    return v if len(v) <= 12 else v[:8] + "…" + f"({len(v)} car.)"


def _walk(obj, path="$"):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:200]):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, obj


def find_candidates(body: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    try:
        data = json.loads(body)
    except ValueError:
        data = None
    if data is not None:
        for path, val in _walk(data):
            if isinstance(val, str) and (KEY_NAMES.search(path) or RTMP_RE.search(val)):
                out.append((path, val))
    else:
        out += [("(texto)", m.group(0)) for m in RTMP_RE.finditer(body)]
    return out


class Recorder:
    """Liga-se a um contexto do navegador e grava/analisa as respostas até ser parado."""

    def __init__(self, on_candidate=None):
        DATA.mkdir(parents=True, exist_ok=True)
        self.path = DATA / f"discovery-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
        self.found: dict[str, str] = {}  # tag -> valor real (só em memória)
        self.n = 0
        self.on_candidate = on_candidate

    def attach(self, ctx: BrowserContext) -> None:
        ctx.on("response", self._on_response)

    def _on_response(self, resp: Response) -> None:
        try:
            host = urlsplit(resp.url).netloc
            if not any(host == h or host.endswith("." + h) for h in HOSTS):
                return
            ctype = resp.headers.get("content-type", "")
            if "json" not in ctype and "text" not in ctype:
                return
            body = resp.text()[:MAX_BODY]
        except Exception:
            return
        self.n += 1
        cands = find_candidates(body)
        for _, secret in cands:  # nunca grava a chave/URL de transmissão em claro
            if len(secret) >= 8:
                body = body.replace(secret, mask(secret))
        rec = {
            "t": time.time(),
            "method": resp.request.method,
            "status": resp.status,
            "url": _clean_url(resp.url),
            "body": body,
            "candidates": [p for p, _ in cands],
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        for path, val in cands:
            tag = f"{urlsplit(resp.url).path} {path}"
            if tag not in self.found:
                self.found[tag] = val
                if self.on_candidate:
                    self.on_candidate(tag, val)


def run(ctx: BrowserContext, start_url: str) -> None:
    """Versão de linha de comando (mantida para uso sem interface)."""
    rec = Recorder(on_candidate=lambda tag, v: print(f"  [candidato] {tag} = {mask(v)}"))
    rec.attach(ctx)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(start_url)
    print(f"Gravando respostas do TikTok em {rec.path}")
    input("Navegue até a tela de transmissão e aperte Enter aqui quando terminar… ")
    print(f"{rec.n} respostas gravadas, {len(rec.found)} candidato(s).")
