# Plan for Claude Code: build & test the PS5 restock watcher locally

**Scope:** local only. Do **not** run `git init`, create a repo, push, or touch GitHub.
The user will publish it to GitHub himself afterwards by following `GITHUB_SETUP.md`.

## Context

`ps5_watch.py` (already written and checked against the live page) opens the PlayStation
Direct page for the Certified Refurbished PS5 Digital Edition (SKU `1000036980`) in headless
Chromium, reads which purchase button is showing, and emails the owner via Gmail SMTP when
the console becomes buyable.

- **Why a headless browser:** the raw HTML contains every button state (Coming Soon, Add,
  Sign In to Buy, Currently Unavailable, ...) with a `hide` class, and the site's JS un-hides
  the real one. Plain `curl` + diffing can't detect a restock. Don't "simplify" it into that.
- **Statuses:**
  - Trigger an email: `AVAILABLE`, `SIGN_IN_TO_BUY`, `PS_PLUS_ONLY`, `LOW_STOCK`, `QUEUE`
  - No email: `COMING_SOON` (live state on 2026-11-18), `UNAVAILABLE`
  - `UNKNOWN` = a failed check. It never emails and never overwrites the saved status.
- **Email rule:** one email per transition *into* a buyable state; re-armed after leaving it.
- **State:** `state.json` next to the script. In GitHub Actions it's carried between runs with `actions/cache`.

## Files already present
`ps5_watch.py`, `.github/workflows/ps5-watch.yml`, `requirements.txt`, `.env.example`,
`.gitignore`, `README.md`, `GITHUB_SETUP.md` (the user's guide; leave it alone), `PLAN.md`.

## Steps

### 1. Environment
```bash
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```
Python 3.10+ is required. Use the venv for everything below.

### 2. Live check (no secrets needed)
```bash
python ps5_watch.py --dry-run
```
- **Pass:** JSON with a real `status` (expected `COMING_SOON`) and `detail` containing `$349.99`.
  Any non-`UNKNOWN` status is fine if the page has changed since.
- **Fail:** `UNKNOWN`. Retry once. If it persists, inspect the *rendered* page (Playwright:
  dump `.productHero-component .button-placeholder` outerHTML after load) to see whether
  Sony renamed the classes, and report to the user before changing the detection JS.

### 3. Add an automated test: `tests/test_watch.py` (pytest, offline)
Add `pytest` to a new `requirements-dev.txt` (keep `requirements.txt` runtime-only, since CI installs it).
The tests must not hit the network or send email. Monkeypatch `ps5_watch.check` and
`ps5_watch.send_email`, and point `ps5_watch.STATE_FILE` at `tmp_path`.

Cases:
1. **Transition sequence:** `COMING_SOON → UNKNOWN → SIGN_IN_TO_BUY → AVAILABLE → UNAVAILABLE → QUEUE`
   sends exactly **2** emails (at `SIGN_IN_TO_BUY` and `QUEUE`).
2. **First run already buyable** (no state file, status `AVAILABLE`) sends 1 email.
3. **UNKNOWN doesn't overwrite state:** after `COMING_SOON` then `UNKNOWN`, `state.json` still says `COMING_SOON`.
4. **`ALERT_ON_ANY_CHANGE=1`:** `COMING_SOON → UNAVAILABLE` sends 1 email; without the flag it sends 0.
5. **`--dry-run` never emails or writes state**, even on a buyable status.
6. **Each buyable status** produces a subject line containing "PS5" or "PS Direct", and a body containing the product URL.

Run `pytest -q`; all tests must pass. If a test exposes a real bug, fix it in `ps5_watch.py`
with the smallest change that works, and tell the user what changed.

### 4. Real email test (needs the user)
- Ask the user to create `.env` from `.env.example` with their Gmail address and Gmail App
  Password (README "Step 1" explains how to get one). **Don't read, print, or `cat` `.env`**,
  and never ask them to paste the password into the chat.
- Then run `python ps5_watch.py --test-email` and ask the user to confirm the
  "✅ PS5 watcher test" email arrived (check Spam the first time).
- On `SMTPAuthenticationError`: the app password is wrong, or 2-Step Verification is off.

### 5. End-to-end run with state
```bash
rm -f state.json
python ps5_watch.py          # real run: should log status=... (was None) and create state.json
python ps5_watch.py          # second run: (was COMING_SOON), no email
rm -f state.json             # leave the folder clean for publishing
```

### 6. Workflow sanity check (no GitHub)
- Validate that `.github/workflows/ps5-watch.yml` parses as YAML.
- If `actionlint` is available (or installable via `go install`/`brew`), run it. Otherwise skip and say so.
- **Don't** run the workflow or `act`.

### 7. Clean up & report
- Delete `state.json` and `__pycache__/`. Leave `.venv/` and `.env` (both git-ignored).
- Confirm `.gitignore` covers `.env`, `state.json`, `__pycache__/`, `.venv/`, `.pytest_cache/`
  (add `.pytest_cache/` if missing).
- Report to the user:
  - the live status
  - test results
  - whether the test email arrived
  - any code changes made

  Then tell them they're ready for `GITHUB_SETUP.md`.

## Acceptance criteria
- [ ] `--dry-run` returns a non-UNKNOWN status from the live page
- [ ] `pytest -q` passes, covering cases 1–6
- [ ] Test email received by the user
- [ ] Two consecutive real runs behave as described in step 5
- [ ] Workflow YAML parses; the folder is clean (no `state.json`, no caches)

## Don'ts
- No git, no GitHub, no `gh` commands.
- Never read, echo, log, or commit the contents of `.env`.
- Don't loop the live check faster than every 60 seconds while testing.
- Don't rewrite the detection approach or the email/state logic beyond fixing a demonstrated bug.
