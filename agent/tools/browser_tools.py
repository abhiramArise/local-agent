"""
Browser tool — full interaction (navigate, click, fill forms).

THIS IS THE HIGHEST-RISK TOOL IN THIS PROJECT. Read this before using it.

UNLIKE FILE WRITES, BROWSER ACTIONS CANNOT BE ROLLED BACK. A click on a
live website can submit a real order, send a real message, or change
real account settings — there is no snapshot-and-restore for that.

Because rollback is impossible here, the confirmation gate is not one
layer of defense among several — it is THE defense. Every navigate,
click, and fill action requires an explicit human "yes" before it
runs, with the actual target shown first. There is no blocklist here,
unlike shell_tools.py.

Read-only actions (browser_read) do NOT require confirmation.

REQUIRES: pip install playwright && playwright install chromium

The browser instance is a lazy singleton — launches on first use,
stays open across calls within the same run of main.py.
"""

from playwright.sync_api import sync_playwright

_playwright = None
_browser = None
_page = None


def _ensure_browser():
    """
    Launches the browser on first use. Reused for all subsequent calls
    — UNLESS the page/window was closed externally, in which case this
    detects that and relaunches automatically instead of failing forever.
    """
    global _playwright, _browser, _page
    if _page is None or _page.is_closed():
        try:
            if _browser is not None:
                _browser.close()
        except Exception:
            pass
        try:
            if _playwright is not None:
                _playwright.stop()
        except Exception:
            pass

        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(headless=False)
        _page = _browser.new_page()
    return _page


def _confirm(action_description: str) -> bool:
    print(f"\n[BROWSER] The agent wants to: {action_description}")
    print("This CANNOT be undone if it changes anything on the page.")
    confirm = input("Allow this? Type 'yes' to confirm: ").strip().lower()
    return confirm == "yes"


def browser_navigate(url: str) -> str:
    if not _confirm(f"navigate to {url}"):
        return f"CANCELLED: user declined navigation to {url}"
    try:
        page = _ensure_browser()
        page.goto(url, timeout=30000)
        return f"OK: navigated to {url} (page title: {page.title()})"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def browser_click(selector: str) -> str:
    if not _confirm(f"click the element matching selector: {selector}"):
        return f"CANCELLED: user declined click on {selector}"
    try:
        page = _ensure_browser()
        page.click(selector, timeout=10000)
        return f"OK: clicked {selector}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def browser_fill(selector: str, text: str) -> str:
    if not _confirm(f"type into the element matching selector '{selector}': {text!r}"):
        return f"CANCELLED: user declined filling {selector}"
    try:
        page = _ensure_browser()
        page.fill(selector, text, timeout=10000)
        return f"OK: filled {selector}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def browser_read(selector: str = None) -> str:
    try:
        page = _ensure_browser()
        if selector:
            text = page.locator(selector).inner_text(timeout=10000)
        else:
            text = page.inner_text("body", timeout=10000)
        return text[:3000]
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


BROWSER_TOOL_DISPATCH = {
    "browser_navigate": browser_navigate,
    "browser_click": browser_click,
    "browser_fill": browser_fill,
    "browser_read": browser_read,
}