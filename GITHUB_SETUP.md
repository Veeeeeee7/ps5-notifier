# Putting the PS5 watcher on GitHub (your guide)

Do this **after** Claude Code has finished `PLAN.md`: tests passing and the test email received.
It takes about 10 minutes. When you're done, GitHub checks the page every ~5 minutes, 24/7, for free.

**You'll need:** a GitHub account, `git` installed, and the Gmail App Password you already used
in `.env`.

---

## 1. Create an empty repo on GitHub

1. Go to <https://github.com/new>.
2. Name it, e.g. `ps5-restock-watcher`.
3. Choose **Public**. Public repos get unlimited free Actions minutes. Your password won't be
   in the code; it goes into Secrets in step 3.
   - Want it private? That works, but then change `*/5` to `*/30` in
     `.github/workflows/ps5-watch.yml` first. A check every 5 minutes would use up the
     2,000 free minutes a month that private repos get.
4. **Leave every "Initialize" box unchecked** (no README, .gitignore, or license), so the
   first push doesn't conflict.
5. Click **Create repository** and keep the page open. You'll need its URL.

## 2. Push the code

In a terminal, from inside the `ps5-watcher` folder:

```bash
git init -b main
git add .
git status
```

**Check the `git status` output before committing.** These must **not** be listed:
`.env`, `state.json`, `.venv/`. If one of them appears, stop: something is wrong with
`.gitignore`. Your password is in `.env`.

```bash
git commit -m "PS5 restock watcher"
git remote add origin https://github.com/<your-username>/ps5-restock-watcher.git
git push -u origin main
```

**If the push asks for a password or gets rejected:**
- GitHub doesn't accept your account password over HTTPS. The easiest fix is to install the
  GitHub CLI and run `gh auth login`, then push again.
- If you use a personal access token, it needs the **`workflow`** scope. Without it, GitHub
  refuses to accept files in `.github/workflows/`, and the push fails with an error that mentions "workflow".

Refresh the repo page. You should see `ps5_watch.py` and a `.github` folder.

## 3. Add your Gmail secrets

In the repo: **Settings → Secrets and variables → Actions → New repository secret**.
Add these:

| Name | Value |
|---|---|
| `GMAIL_ADDRESS` | your Gmail address |
| `GMAIL_APP_PASSWORD` | the 16-character App Password (spaces are fine) |
| `NOTIFY_TO` | *optional:* a different address to send alerts to |

Names must match exactly (all caps, underscores). Once saved, a secret can't be viewed again,
only replaced. That's normal.

## 4. Turn it on and send a test email

1. Open the **Actions** tab. If GitHub asks, click **"I understand my workflows, go ahead and enable them."**
2. Click **PS5 restock watch** on the left, then **Run workflow** on the right.
3. **Check the "Send a test email" box**, then click the green **Run workflow** button.
4. Wait ~1–2 minutes for a green check, then look for **"✅ PS5 watcher test"** in Gmail
   (check Spam the first time and mark it "Not spam" so real alerts land in your inbox).

## 5. Run a real check

1. **Run workflow** again, this time with the box **unchecked**.
2. When it finishes, click the run, then **check**, then expand the **Check page** step.
3. You should see a line like:
   ```
   status=COMING_SOON (was None) $349.99, COMING SOON
   ```
   A warning about "cache not found" on the first run is normal.

## 6. Confirm the schedule is running

Come back in ~15–30 minutes. The Actions tab should show new runs labeled **Scheduled**.
GitHub often starts these a few minutes late. That's expected.

You're done. When the console goes on sale, you'll get an email like
**"🎮 PS5 Refurbished is ON SALE - sign in to buy"** with the link.
Stay signed in to your PlayStation account in your browser so you can check out fast.

---

## Something's wrong?

| What you see | What to do |
|---|---|
| Red ❌ run with `SMTPAuthenticationError` | The App Password secret is wrong. Re-create it at <https://myaccount.google.com/apppasswords> and update `GMAIL_APP_PASSWORD`. |
| Runs are green but every log says `status=UNKNOWN` | Sony is probably blocking GitHub's servers. The fallback is running it on your own computer: `python ps5_watch.py --loop 120`. |
| No "Scheduled" runs after an hour | Make sure the workflow file is on the `main` branch, and that Actions is allowed under Settings → Actions → General. |
| You get an email from GitHub saying a run failed | Open the run and read the red step. Usually it's a one-off network hiccup; if it happens again and again, check the rows above. |

GitHub also emails you whenever a run fails, so if something breaks you'll find out.

## When you've bought it 🎉

Turn the watcher off so it stops running: **Actions → PS5 restock watch → "···" (top right) → Disable workflow**.
(Or delete the repo.) Also delete the App Password at <https://myaccount.google.com/apppasswords>
since you won't need it anymore.

GitHub also pauses scheduled workflows on its own after **60 days** with no commits, and it
emails you first. If you're still waiting by then, click **Enable workflow** to keep it going.
