"""Text-to-speech module for navigation guidance."""

from __future__ import annotations

import subprocess
import threading
import queue
import re


class VoiceOutput:
    """Mac say command wrapper with queue and speed control.
    
    Usage:
        voice = VoiceOutput(speed=140, voice="Ting-Ting")
        voice.speak("点底部我的淘宝")
        voice.speak("选退货退款")
        voice.stop()  # Clear queue and stop
    """

    def __init__(self, speed: int = 140, voice: str = "Ting-Ting"):
        """Args:
            speed: Words per minute. Default 140 (slower than normal 180).
            voice: Mac TTS voice name. Ting-Ting for Chinese female.
        """
        self.speed = speed
        self.voice = voice
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._start_worker()

    def _start_worker(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _worker(self):
        while not self._stop_event.is_set():
            try:
                text = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if text is None:  # poison pill
                break
            self._do_speak(text)

    def _do_speak(self, text: str) -> None:
        """Execute say command."""
        # Clean text: remove emojis, special chars
        clean = self._clean_text(text)
        if not clean:
            return
        try:
            subprocess.run(
                ["say", "-v", self.voice, "-r", str(self.speed), clean],
                capture_output=True,
                timeout=30,
            )
        except Exception:
            pass

    @staticmethod
    def _clean_text(text: str) -> str:
        """Remove characters that confuse TTS."""
        # Remove emojis and special symbols
        text = re.sub(r'[🔊⚠️✅⏹❌\n]', '', text)
        # Remove quotes that may break shell command
        text = text.replace('"', '').replace("'", "")
        return text.strip()

    def speak(self, text: str) -> None:
        """Queue a text to speak."""
        if text:
            self._queue.put(text)

    def speak_now(self, text: str) -> None:
        """Speak immediately, bypassing queue."""
        self._do_speak(text)

    def stop(self) -> None:
        """Clear queue and stop."""
        self._stop_event.set()
        # Clear queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        # Kill any running say process
        try:
            subprocess.run(["pkill", "-f", f"say -v {self.voice}"], capture_output=True)
        except Exception:
            pass

    def wait_empty(self, timeout: float = 10.0) -> bool:
        """Wait until queue is empty."""
        try:
            self._queue.join()
            return True
        except Exception:
            return False


def list_voices() -> list[str]:
    """List available Mac TTS voices."""
    try:
        result = subprocess.run(
            ["say", "-v", "?"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        voices = []
        for line in result.stdout.split("\n"):
            if "zh" in line.lower() or "ting" in line.lower():
                voices.append(line.split()[0] if line.split() else line)
        return voices
    except Exception:
        return []
