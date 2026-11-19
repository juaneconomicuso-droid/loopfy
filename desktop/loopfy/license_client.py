"""Cliente de licença do Loopfy Desktop.

Princípios:
- A interface NUNCA é a trava. Quem decide é o servidor (assina o token) e o motor (confere a assinatura antes
  de cada operação, via @requires_license). Esconder uma tela ou mudar uma variável não libera nada.
- A identidade do aparelho é um par Ed25519 gerado aqui. A chave privada fica protegida pelo DPAPI do Windows
  (presa ao usuário do Windows), então copiar a pasta de dados para outro computador não leva a identidade junto.
- Falha fechada: sem token válido nenhuma operação inicia. Parar uma operação sempre é permitido.
- Chave pública do servidor embutida no código; servidor só HTTPS (exceto localhost em modo de desenvolvimento).
"""
from __future__ import annotations

import base64
import ctypes
import functools
import hashlib
import json
import os
import platform
import sys
import time
import uuid
from ctypes import wintypes
from urllib.parse import urlsplit

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .browser import DATA

PUBLIC_KEY_B64 = "cxfQuNOcEkisgfkTdQixoEvOCzv3MtH7ecmG1SWGXCU="  # chave PÚBLICA do servidor (pode ser pública)
PROD_SERVER = "https://loopfy.example.com"  # trocar pelo domínio real antes de distribuir
STATE = DATA / "license.bin"
RENEW_BEFORE_S = 6 * 3600
CLOCK_SLACK_S = 300
_ENTROPY = b"loopfy-desktop-v1"


class LicenseError(RuntimeError):
    pass


def _server() -> str:
    url = PROD_SERVER
    if os.environ.get("LOOPFY_DEV") == "1" and os.environ.get("LOOPFY_SERVER"):
        url = os.environ["LOOPFY_SERVER"]
    p = urlsplit(url)
    local = p.hostname in ("localhost", "127.0.0.1")
    if p.scheme != "https" and not (local and os.environ.get("LOOPFY_DEV") == "1"):
        raise LicenseError("Servidor de licença precisa usar HTTPS.")
    return url.rstrip("/")


# ---------------- proteção do estado em disco (DPAPI) ----------------
class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    inb = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    ent = _Blob(len(_ENTROPY), ctypes.cast(ctypes.create_string_buffer(_ENTROPY, len(_ENTROPY)), ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(inb), None, ctypes.byref(ent), None, None, 0, ctypes.byref(out))
    if not ok:
        raise OSError("DPAPI falhou")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _load() -> dict:
    try:
        raw = STATE.read_bytes()
    except FileNotFoundError:
        return {}
    try:
        data = _dpapi(raw, False) if sys.platform == "win32" else raw
        return json.loads(data)
    except (OSError, ValueError) as e:
        # arquivo existe mas não abre (outro usuário/PC ou corrompido): NÃO recria a identidade em silêncio
        raise LicenseError("Dados de licença ilegíveis neste usuário/computador. Reative a licença.") from e


def _save(st: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(st).encode()
    raw = _dpapi(raw, True) if sys.platform == "win32" else raw
    tmp = STATE.with_suffix(".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, STATE)  # escrita atômica


def _device_key(st: dict) -> Ed25519PrivateKey:
    if not st.get("priv"):
        k = Ed25519PrivateKey.generate()
        st["priv"] = base64.b64encode(k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())).decode()
        _save(st)
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(st["priv"]))


def _pub_raw(k: Ed25519PrivateKey) -> bytes:
    return k.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def machine_id() -> str:
    return hashlib.sha256(_pub_raw(_device_key(_load()))).hexdigest()


def fingerprint() -> str:
    """Sinal auxiliar (não é a identidade). Usa o MachineGuid do Windows, estável entre trocas de rede."""
    guid = ""
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                guid = winreg.QueryValueEx(k, "MachineGuid")[0]
        except OSError:
            pass
    sig = "|".join([platform.system(), platform.machine(), guid or platform.node(), str(os.cpu_count() or 0)])
    return hashlib.sha256(sig.encode()).hexdigest()


# ---------------- token ----------------
def _b64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def verify_token(token: str, st: dict | None = None) -> dict | None:
    """Payload se assinatura, validade, aparelho e relógio conferem; senão None."""
    st = st if st is not None else _load()
    try:
        body_b64, sig_b64 = token.split(".")
        body = _b64u(body_b64)
        Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY_B64)).verify(_b64u(sig_b64), body)
        p = json.loads(body)
    except (ValueError, InvalidSignature):
        return None
    now = time.time()
    if now < float(st.get("lastSeen", 0)) - CLOCK_SLACK_S:
        return None  # relógio voltou: não estende token
    me = hashlib.sha256(_pub_raw(_device_key(st))).hexdigest()
    if p.get("v") != 1 or p.get("dev") != me or int(p.get("exp", 0)) <= now:
        return None
    return p


# ---------------- rede ----------------
def _post(path: str, body: dict) -> dict:
    try:
        r = requests.post(_server() + path, json=body, timeout=10)
        return r.json()
    except (requests.RequestException, ValueError):
        return {"ok": False, "code": "network"}


def _proof(st: dict, purpose: str) -> dict | None:
    ch = _post("/api/license/challenge", {})
    if not ch.get("ok"):
        return None
    k = _device_key(st)
    fp = fingerprint()
    sig = k.sign(f"loopfy|{purpose}|{ch['nonce']}|{fp}".encode())
    return {"devicePub": base64.b64encode(_pub_raw(k)).decode(), "fp": fp, "nonce": ch["nonce"], "sig": base64.b64encode(sig).decode()}


def _accept(st: dict, r: dict) -> None:
    if r.get("ok") and verify_token(r["token"], st):
        st["token"] = r["token"]
        st["lastSeen"] = max(float(st.get("lastSeen", 0)), time.time())
        _save(st)


def activate(key: str) -> dict:
    st = _load()
    pr = _proof(st, "activate")
    if not pr:
        return {"ok": False, "code": "network"}
    r = _post("/api/license/activate", {"key": key, **pr})
    if r.get("ok"):
        st["key"] = key  # fica só dentro do arquivo protegido por DPAPI
        _accept(st, r)
    return r


def authorize() -> dict | None:
    """Devolve o payload do token válido ou None. Renova em silêncio quando falta pouco para vencer."""
    st = _load()
    p = verify_token(st["token"], st) if st.get("token") else None
    if p and p["exp"] - time.time() >= RENEW_BEFORE_S:
        st["lastSeen"] = max(float(st.get("lastSeen", 0)), time.time()); _save(st)
        return p
    if st.get("key"):
        r = activate(st["key"])
        if r.get("ok"):
            return verify_token(_load()["token"])
        if r.get("code") in ("invalid", "expired", "device_limit"):
            st = _load(); st.pop("token", None); _save(st)  # servidor recusou de verdade
            return None
    return p  # rede fora: vale o que ainda não venceu


def requires_license(fn):
    """Trava de verdade: o motor confere a assinatura a cada chamada, independente da interface."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        if not authorize():
            raise LicenseError("Sem licença válida. Ative com: python -m loopfy license --key SUA-CHAVE")
        return fn(*a, **kw)
    return wrapper
