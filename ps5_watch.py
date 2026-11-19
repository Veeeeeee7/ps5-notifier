#!/usr/bin/env python3
"""Watch PlayStation Direct for the Certified Refurbished PS5 Digital Edition
and send an email (Gmail SMTP) when it becomes buyable.

Usage:
    python ps5_watch.py               # one check; emails on a transition into a buyable state
    python ps5_watch.py --dry-run     # one check; prints JSON, never emails or writes state
    python ps5_watch.py --test-email  # send a test email and exit
    python ps5_watch.py --loop 120    # keep checking every 120 seconds (minimum 60)

Why a headless browser: the raw HTML contains every button state (Coming Soon,
Add, Sign In to Buy, Currently Unavailable, ...) with a `hide` class, and the
site's JavaScript un-hides the real one. Fetching the HTML alone can't tell
them apart.
"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

SKU = "1000036980"
PRODUCT_URL = (
    "https://direct.playstation.com/en-us/buy-consoles/"
    "certified-refurbished-playstation5-digital-edition-console"
)
PRODUCT_NAME = "PS5 Refurbished"

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "state.json"
ENV_FILE = HERE / ".env"

BUYABLE = {"AVAILABLE", "SIGN_IN_TO_BUY", "PS_PLUS_ONLY", "LOW_STOCK", "QUEUE"}
NOT_BUYABLE = {"COMING_SOON", "UNAVAILABLE"}
UNKNOWN = "UNKNOWN"

HEADLINES = {
    "AVAILABLE": "add to cart now",
    "SIGN_IN_TO_BUY": "sign in to buy",
    "PS_PLUS_ONLY": "PS Plus members can buy",
    "LOW_STOCK": "low stock, hurry",
    "QUEUE": "join the queue now",
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# The hero has one .button-placeholder per layout (mobile + desktop), each
# holding every possible state; all but the live one carry the `hide` class.
# We look at class names rather than on-screen visibility, because the layout
# that doesn't match the viewport is hidden by CSS regardless of stock.
PLACEHOLDERS = ".productHero-component .button-placeholder"

# Checked in order: the first state that is un-hidden wins.
STATE_SELECTORS = [
    ("LOW_STOCK", ".js-low-stock-wrpr"),
    ("AVAILABLE", ".add-to-cart"),
    ("SIGN_IN_TO_BUY", ".js-login-to-purchase"),
    ("PS_PLUS_ONLY", ".ps-plus-required-btn"),
    ("COMING_SOON", ".js-coming-soon-wrpr"),
    ("UNAVAILABLE", ".js-out-stock-wrpr, .js-currently-unavailable-wrpr"),
]

DETECT_JS = """
([placeholders, stateSelectors, sku]) => {
  const all = [...document.querySelectorAll(placeholders)];
  if (!all.length) return null;
  const mine = all.filter(p => p.querySelector(`[data-product-code="${sku}"]`));
  const boxes = mine.length ? mine : all;
  const shown = el => !el.closest('.hide');
  const text = el => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();

  let found = null;
  for (const [status, selector] of stateSelectors) {
    for (const box of boxes) {
      const el = [...box.querySelectorAll(selector)].find(shown);
      if (el) { found = { status, label: text(el) }; break; }
    }
    if (found) break;
  }
  if (!found) return null;

  let price = '';
  for (const el of document.querySelectorAll(`.js-actual-price[data-product-code="${sku}"]`)) {
    const part = c => (el.querySelector(c)?.textContent || '').trim();
    const whole = part('.js-actual-price-whole');
    if (whole) {
      price = (part('.js-actual-price-symbol') || '$') + whole + '.' + (part('.js-actual-price-fraction') || '00');
      break;
    }
  }
  return { ...found, price };
}
"""


def load_env(path: Path = ENV_FILE) -> None:
    """Load KEY=VALUE lines from .env without overriding real environment variables."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    print(f"[{stamp}] {message}", flush=True)


def check() -> tuple[str, str]:
    """Open the product page and return (status, detail). Never raises."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return UNKNOWN, "playwright is not installed (pip install -r requirements.txt)"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=os.environ.get("CHROME_PATH") or None)
            try:
                context = browser.new_context(
                    user_agent=USER_AGENT,
                    locale="en-US",
                    viewport={"width": 1366, "height": 900},
                )
                page = context.new_page()
                response = page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=60_000)

                if "queue" in page.url.split("?")[0].lower().replace(PRODUCT_URL.lower(), ""):
                    return "QUEUE", f"redirected to a waiting room: {page.url.split('?')[0]}"
                if response is not None and response.status >= 400:
                    return UNKNOWN, f"HTTP {response.status}"

                args = [PLACEHOLDERS, STATE_SELECTORS, SKU]
                try:
                    handle = page.wait_for_function(DETECT_JS, arg=args, timeout=45_000)
                    result = handle.json_value()
                except Exception:
                    result = None
                    if "queue" in page.url.split("?")[0].lower().replace(PRODUCT_URL.lower(), ""):
                        return "QUEUE", f"redirected to a waiting room: {page.url.split('?')[0]}"
                if not result:
                    title = (page.title() or "").strip()
                    return UNKNOWN, f"no purchase button became visible (page title: {title!r})"

                label = result["label"].upper() or result["status"]
                detail = ", ".join(x for x in (result.get("price"), label) if x)
                return result["status"], detail
            finally:
                browser.close()
    except Exception as exc:  # network errors, timeouts, browser crashes
        return UNKNOWN, f"{type(exc).__name__}: {exc}".splitlines()[0][:300]


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(status: str, detail: str) -> None:
    state = {
        "status": status,
        "detail": detail,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def build_email(status: str, detail: str, previous: str | None) -> tuple[str, str]:
    if status in BUYABLE:
        subject = f"🎮 {PRODUCT_NAME} is ON SALE - {HEADLINES[status]}"
        lead = "The Certified Refurbished PS5 Digital Edition looks buyable on PlayStation Direct right now."
    else:
        subject = f"PS Direct: {PRODUCT_NAME} changed to {status.replace('_', ' ').title()}"
        lead = "The Certified Refurbished PS5 Digital Edition page changed on PlayStation Direct."
    body = (
        f"{lead}\n\n"
        f"Status: {status} (was {previous})\n"
        f"Page says: {detail}\n\n"
        f"Buy here: {PRODUCT_URL}\n\n"
        "Stock can go fast. Sign in to your PlayStation account before checking out.\n"
    )
    return subject, body


def send_email(subject: str, body: str) -> None:
    address = os.environ.get("GMAIL_ADDRESS", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
    to = os.environ.get("NOTIFY_TO", "").strip() or address
    if not address or not password:
        raise RuntimeError(
            "GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set (in .env locally, or as GitHub secrets)."
        )
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = address
    msg["To"] = to
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(address, password)
        smtp.send_message(msg)


def alert_on_any_change() -> bool:
    return os.environ.get("ALERT_ON_ANY_CHANGE", "").strip().lower() in {"1", "true", "yes", "on"}


def should_email(status: str, previous: str | None) -> bool:
    if status in BUYABLE and previous not in BUYABLE:
        return True
    return alert_on_any_change() and previous is not None and status != previous


def run_once(dry_run: bool = False) -> str:
    status, detail = check()

    if dry_run:
        print(json.dumps({"status": status, "detail": detail, "url": PRODUCT_URL}, indent=2))
        return status

    previous = load_state().get("status")
    log(f"status={status} (was {previous}) {detail}")

    if status == UNKNOWN:
        return status  # a failed check: no email, saved status untouched

    if should_email(status, previous):
        subject, body = build_email(status, detail, previous)
        send_email(subject, body)  # if this raises, state is not saved and the next run retries
        log(f"email sent: {subject}")

    save_state(status, detail)
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PS5 restock watcher for PlayStation Direct")
    parser.add_argument("--dry-run", action="store_true", help="check and print JSON; no email, no state")
    parser.add_argument("--test-email", action="store_true", help="send a test email and exit")
    parser.add_argument("--loop", type=int, metavar="SECONDS", help="keep checking at this interval (min 60)")
    args = parser.parse_args(argv)

    load_env()

    if args.test_email:
        send_email(
            "✅ PS5 watcher test",
            "Email delivery works. You'll get a message like this when the "
            f"{PRODUCT_NAME} goes on sale.\n\n{PRODUCT_URL}\n",
        )
        log("test email sent")
        return 0

    if args.loop:
        interval = max(60, args.loop)
        log(f"checking every {interval}s; press Ctrl+C to stop")
        while True:
            try:
                run_once(dry_run=args.dry_run)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                log(f"run failed: {type(exc).__name__}: {exc}")
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                return 0

    run_once(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
