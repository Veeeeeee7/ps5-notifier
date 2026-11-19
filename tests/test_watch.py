"""Offline tests for ps5_watch: no network, no real email."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ps5_watch  # noqa: E402


@pytest.fixture
def watcher(monkeypatch, tmp_path):
    """Patch check/send_email/STATE_FILE; returns a helper to drive runs."""
    monkeypatch.setattr(ps5_watch, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(ps5_watch, "ENV_FILE", tmp_path / "no.env")
    monkeypatch.delenv("ALERT_ON_ANY_CHANGE", raising=False)

    class Watcher:
        emails: list[tuple[str, str]] = []
        state_file = tmp_path / "state.json"
        next_status = "UNKNOWN"

        def run(self, status, argv=()):
            self.next_status = status
            assert ps5_watch.main(list(argv)) == 0

        def saved_status(self):
            return json.loads(self.state_file.read_text())["status"]

    w = Watcher()
    w.emails = []
    monkeypatch.setattr(ps5_watch, "check", lambda: (w.next_status, "$349.99, TEST"))
    monkeypatch.setattr(ps5_watch, "send_email", lambda subject, body: w.emails.append((subject, body)))
    return w


def test_transition_sequence_sends_two_emails(watcher):
    sent_after = []
    for status in ["COMING_SOON", "UNKNOWN", "SIGN_IN_TO_BUY", "AVAILABLE", "UNAVAILABLE", "QUEUE"]:
        watcher.run(status)
        sent_after.append(len(watcher.emails))
    assert sent_after == [0, 0, 1, 1, 1, 2]
    assert "sign in to buy" in watcher.emails[0][0]
    assert "queue" in watcher.emails[1][0]


def test_first_run_already_buyable_sends_one_email(watcher):
    assert not watcher.state_file.exists()
    watcher.run("AVAILABLE")
    assert len(watcher.emails) == 1
    assert watcher.saved_status() == "AVAILABLE"


def test_unknown_does_not_overwrite_state(watcher):
    watcher.run("COMING_SOON")
    before = watcher.state_file.read_text()
    watcher.run("UNKNOWN")
    assert watcher.saved_status() == "COMING_SOON"
    assert watcher.state_file.read_text() == before
    assert watcher.emails == []


def test_unknown_on_first_run_writes_no_state(watcher):
    watcher.run("UNKNOWN")
    assert not watcher.state_file.exists()


@pytest.mark.parametrize("flag, expected", [("1", 1), (None, 0)])
def test_alert_on_any_change(watcher, monkeypatch, flag, expected):
    if flag is not None:
        monkeypatch.setenv("ALERT_ON_ANY_CHANGE", flag)
    watcher.run("COMING_SOON")
    watcher.run("UNAVAILABLE")
    assert len(watcher.emails) == expected


def test_dry_run_never_emails_or_writes_state(watcher, capsys):
    watcher.run("AVAILABLE", argv=["--dry-run"])
    assert watcher.emails == []
    assert not watcher.state_file.exists()
    assert json.loads(capsys.readouterr().out)["status"] == "AVAILABLE"


def test_dry_run_leaves_existing_state_alone(watcher):
    watcher.run("COMING_SOON")
    watcher.run("AVAILABLE", argv=["--dry-run"])
    assert watcher.saved_status() == "COMING_SOON"
    assert watcher.emails == []


@pytest.mark.parametrize("status", sorted(ps5_watch.BUYABLE))
def test_each_buyable_status_email_content(watcher, status):
    watcher.run(status)
    assert len(watcher.emails) == 1
    subject, body = watcher.emails[0]
    assert "PS5" in subject or "PS Direct" in subject
    assert ps5_watch.PRODUCT_URL in body


def test_failed_email_does_not_save_state(watcher, monkeypatch):
    def boom(subject, body):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(ps5_watch, "send_email", boom)
    watcher.next_status = "AVAILABLE"
    with pytest.raises(RuntimeError):
        ps5_watch.main([])
    assert not watcher.state_file.exists()  # so the next run tries the email again
