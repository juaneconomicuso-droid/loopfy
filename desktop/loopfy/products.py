"""Produtos da loja para o painel do Loopfy.

O Loopfy abre o Gerenciador de LIVE, abre a tela "Adicionar produtos" e lê as respostas que o próprio TikTok
envia com a lista (só leitura; nada é adicionado nem alterado). Os produtos ficam em data/produtos.json,
neste computador. A extração é por forma dos dados (lista de objetos com id e título), não por nome de rota fixo.
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterator

from .browser import DATA

FILE = DATA / "produtos.json"
ID_KEYS = ("product_id", "id", "spu_id", "item_id")
TITLE_KEYS = ("title", "product_name", "name", "product_title")
IMG_RE = re.compile(r"^https?://", re.I)


def _walk_lists(obj: Any) -> Iterator[list]:
    if isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj):
            yield obj
        for x in obj[:500]:
            yield from _walk_lists(x)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_lists(v)


def _first(d: dict, keys: tuple[str, ...]) -> Any:
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return None


def _price(d: dict) -> str:
    for k, v in d.items():
        if "price" in k.lower() and isinstance(v, (str, int, float)) and str(v).strip():
            return str(v)
        if "price" in k.lower() and isinstance(v, dict):
            for kk in ("format_available_price", "format_price", "min_price", "price", "sale_price"):
                if v.get(kk):
                    return str(v[kk])
    return ""


def _image(d: dict) -> str:
    for k, v in d.items():
        if re.search(r"(image|cover|img|thumb)", k, re.I):
            if isinstance(v, str) and IMG_RE.match(v):
                return v
            if isinstance(v, dict):
                for x in v.values():
                    if isinstance(x, str) and IMG_RE.match(x):
                        return x
                    if isinstance(x, list) and x and isinstance(x[0], str) and IMG_RE.match(x[0]):
                        return x[0]
            if isinstance(v, list) and v:
                x = v[0]
                if isinstance(x, str) and IMG_RE.match(x):
                    return x
                if isinstance(x, dict):
                    for y in x.values():
                        if isinstance(y, str) and IMG_RE.match(y):
                            return y
    return ""


def extract(bodies: list[str]) -> list[dict]:
    """Junta, sem repetir, os produtos que aparecem em listas das respostas."""
    found: dict[str, dict] = {}
    for body in bodies:
        try:
            data = json.loads(body)
        except ValueError:
            continue
        for lst in _walk_lists(data):
            for it in lst:
                pid, title = _first(it, ID_KEYS), _first(it, TITLE_KEYS)
                if pid is None or not isinstance(title, str) or len(title) < 3:
                    continue
                pid = str(pid)
                cur = found.get(pid, {})
                found[pid] = {
                    "id": pid,
                    "title": title.strip()[:200],
                    "price": cur.get("price") or _price(it),
                    "image": cur.get("image") or _image(it),
                }
    return list(found.values())


def load() -> list[dict]:
    try:
        return json.loads(FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return []


def save(items: list[dict]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(items, ensure_ascii=False), "utf-8")
