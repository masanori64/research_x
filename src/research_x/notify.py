from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from importlib.resources import as_file, files


@dataclass(frozen=True)
class NotificationResult:
    beep_ok: bool
    voice_ok: bool
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.beep_ok or self.voice_ok


def notify_completion(
    message: str = "作業が終了しました",
    *,
    beep: bool = True,
    voice: bool = True,
) -> NotificationResult:
    errors: list[str] = []
    beep_ok = False
    voice_ok = False

    if beep:
        try:
            beep_ok = _beep()
        except Exception as exc:  # noqa: BLE001 - notification must not break caller work.
            errors.append(f"beep:{type(exc).__name__}: {exc}")

    if voice:
        try:
            voice_ok = _speak(message)
        except Exception as exc:  # noqa: BLE001 - notification must not break caller work.
            errors.append(f"voice:{type(exc).__name__}: {exc}")

    return NotificationResult(beep_ok=beep_ok, voice_ok=voice_ok, errors=tuple(errors))


def _beep() -> bool:
    if platform.system() == "Windows":
        import winsound

        with as_file(_completion_sound()) as sound_path:
            winsound.PlaySound(str(sound_path), winsound.SND_FILENAME)
            return True
    print("\a", end="", flush=True)
    return True


def _completion_sound():
    return files("research_x.assets").joinpath("completion.wav")


def _speak(message: str) -> bool:
    if platform.system() != "Windows":
        return False
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$speaker.Rate = 0; "
        "$speaker.Speak($args[0]);"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script, message],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
    )
    return completed.returncode == 0
