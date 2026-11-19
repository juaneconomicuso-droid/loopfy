"""Loopfy Desktop — linha de comando.

  python -m loopfy login      abre o navegador controlado para você entrar na conta (uma vez)
  python -m loopfy status     abre o Gerenciador de LIVE e diz se a conta tem acesso
  python -m loopfy discover   grava as chamadas do TikTok e procura a chave de transmissão
  python -m loopfy license --key LPFY-...   ativa uma licença   |   license   mostra o estado
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright

from . import browser, discover, license_client


def cmd_login(_a) -> int:
    with sync_playwright() as pw:
        ctx = browser.open_session(pw)
        browser.current_page(ctx).goto(browser.SELLER_HOME)
        print("Entre na sua conta na janela do navegador. Quando terminar, feche a janela.")
        try:
            ctx.pages[0].wait_for_event("close", timeout=0)
        except Exception:
            pass
        ctx.close()
    return 0


def cmd_status(_a) -> int:
    with sync_playwright() as pw:
        ctx = browser.open_session(pw)
        page = browser.current_page(ctx)
        page.goto(browser.LIVE_MANAGER, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        url = page.url
        print("URL final:", url)
        msg = browser.diagnose_url(url)
        print(msg or "Gerenciador de LIVE acessível.")
        ctx.close()
    return 1 if msg else 0


@license_client.requires_license
def _discover_session() -> None:
    with sync_playwright() as pw:
        ctx = browser.open_session(pw)
        discover.run(ctx, browser.LIVE_MANAGER)
        ctx.close()


def cmd_discover(_a) -> int:
    try:
        _discover_session()
    except license_client.LicenseError as e:
        print(e)
        return 2
    return 0


def _unused_old_discover(_a) -> int:
    with sync_playwright() as pw:
        ctx = browser.open_session(pw)
        discover.run(ctx, browser.LIVE_MANAGER)
        ctx.close()
    return 0


def cmd_license(a) -> int:
    if a.key:
        r = license_client.activate(a.key)
    else:
        p = license_client.authorize()
        print("Licença ativa:" if p else "Sem licença válida.", p or "")
        return 0 if p else 1
    print({k: v for k, v in r.items() if k != "token"})
    return 0 if r.get("ok") else 1


def cmd_gui(_a) -> int:
    from . import gui
    return gui.main()


def main() -> int:
    if len(sys.argv) == 1:  # sem argumentos: abre a janela
        return cmd_gui(None)
    ap = argparse.ArgumentParser(prog="loopfy")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gui").set_defaults(fn=cmd_gui)
    sub.add_parser("login").set_defaults(fn=cmd_login)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("discover").set_defaults(fn=cmd_discover)
    lp = sub.add_parser("license")
    lp.add_argument("--key")
    lp.set_defaults(fn=cmd_license)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
