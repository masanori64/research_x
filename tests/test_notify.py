import research_x.notify as notify


def test_notify_completion_uses_enabled_channels(monkeypatch) -> None:
    calls = []

    def fake_beep() -> bool:
        calls.append("beep")
        return True

    def fake_speak(message: str) -> bool:
        calls.append(("speak", message))
        return True

    monkeypatch.setattr(notify, "_beep", fake_beep)
    monkeypatch.setattr(notify, "_speak", fake_speak)

    result = notify.notify_completion("done")

    assert result.ok
    assert result.beep_ok is True
    assert result.voice_ok is True
    assert calls == ["beep", ("speak", "done")]


def test_notify_completion_collects_errors(monkeypatch) -> None:
    def broken_beep() -> bool:
        raise RuntimeError("no device")

    monkeypatch.setattr(notify, "_beep", broken_beep)
    monkeypatch.setattr(notify, "_speak", lambda _message: False)

    result = notify.notify_completion("done")

    assert not result.ok
    assert result.beep_ok is False
    assert result.voice_ok is False
    assert result.errors
