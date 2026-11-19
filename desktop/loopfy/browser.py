"""Navegador controlado do Loopfy.

Abre o Chrome instalado com um perfil PRÓPRIO (desktop/profile), separado do seu Chrome do dia a dia.
O login na conta do TikTok é feito por você, à mão, dentro dessa janela; a sessão fica salva no perfil.
O Loopfy não lê nem guarda sua senha e não tenta contornar captcha ou verificação de segurança.
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import BrowserContext, Playwright

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "profile"
DATA = ROOT / "data"

SELLER_HOME = "https://seller-br.tiktok.com/"
LIVE_MANAGER = "https://shop.tiktok.com/streamer/live"


def open_session(pw: Playwright) -> BrowserContext:
    PROFILE.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    try:
        return pw.chromium.launch_persistent_context(
            str(PROFILE),
            channel="chrome",  # usa o Chrome já instalado; não baixa outro navegador
            headless=False,
            viewport=None,
            args=["--start-maximized"],
        )
    except Exception as e:  # noqa: BLE001
        if "sess" in str(e).lower() or "Target page" in str(e):
            raise RuntimeError("O navegador do Loopfy já está aberto em outra janela. Feche-o e tente de novo.") from None
        raise


def current_page(ctx: BrowserContext):
    return ctx.pages[0] if ctx.pages else ctx.new_page()


def diagnose_url(url: str) -> str | None:
    """Traduz a URL atual em um diagnóstico legível. None = sem problema aparente."""
    if "/streamer/nopermission" in url:
        return (
            "O TikTok respondeu 'sem permissão' para o Gerenciador de LIVE. Causas comuns: a conta logada não tem "
            "acesso à LIVE no Seller Center, o login foi feito numa conta/região diferente, ou a sessão não "
            "completou a verificação. Confirme no Chrome normal, com a mesma conta, que o Gerenciador de LIVE abre."
        )
    if "login" in url or "passport" in url:
        return "Sessão sem login. Entre na conta na janela aberta e tente de novo."
    return None
