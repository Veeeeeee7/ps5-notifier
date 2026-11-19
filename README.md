# PS5 restock watcher

Checks the PlayStation Direct page for the
[Certified Refurbished PS5 Digital Edition](https://direct.playstation.com/en-us/buy-consoles/certified-refurbished-playstation5-digital-edition-console)
and emails you through Gmail the moment it becomes buyable.

It opens the page in headless Chromium (Playwright) because the raw HTML contains every
button state at once; only the site's JavaScript reveals which one is real.

| Status | Meaning | Email? |
|---|---|---|
| `AVAILABLE` | "Add" to cart is showing | yes |
| `SIGN_IN_TO_BUY` | "Sign In to Buy" is showing | yes |
| `PS_PLUS_ONLY` | "PS Plus Required" is showing | yes |
| `LOW_STOCK` | "Low stock" is showing | yes |
| `QUEUE` | redirected to a waiting room | yes |
| `COMING_SOON` | "Coming Soon" | no |
| `UNAVAILABLE` | "Currently Unavailable" | no |
| `UNKNOWN` | the check failed; ignored, the saved status is kept | no |

You get **one email per transition into a buyable state**. It re-arms once the console
goes back to not buyable. The last status is kept in `state.json` next to the script.

## Step 1: get a Gmail App Password

1. Turn on 2-Step Verification for your Google account: <https://myaccount.google.com/security>.
2. Go to <https://myaccount.google.com/apppasswords>, create one named "PS5 watcher",
   and copy the 16-character password.
3. Copy `.env.example` to `.env` and fill in `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD`.
   `.env` is git-ignored. Never commit it.

## Step 2: run it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

```bash
python ps5_watch.py --dry-run      # check now, print JSON, no email, no state
python ps5_watch.py --test-email   # send yourself a test email
python ps5_watch.py                # real check: emails if it just became buyable
python ps5_watch.py --loop 120     # keep checking every 120 s (minimum 60)
```

Python 3.10+ is required.

## Step 3: run it for free on GitHub Actions

Follow [GITHUB_SETUP.md](GITHUB_SETUP.md). The workflow in
`.github/workflows/ps5-watch.yml` runs every ~5 minutes and carries `state.json`
between runs with `actions/cache`.

## Options

| Variable | Purpose |
|---|---|
| `GMAIL_ADDRESS` | Gmail account that sends the alert |
| `GMAIL_APP_PASSWORD` | Gmail App Password for that account |
| `NOTIFY_TO` | optional: send alerts to a different address |
| `ALERT_ON_ANY_CHANGE` | optional: `1` to also email on any status change |

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The tests are offline: they never open the page or send email.
