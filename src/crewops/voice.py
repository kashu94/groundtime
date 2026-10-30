"""The assistant's answers read aloud, with Amazon Polly in Indian English.

Speech is made on the server, where the MCP server's role allows Polly, so the web app needs
no AWS credentials for it. Only the assistant's own answer is ever spoken, never text a caller
sends, and each user gets a limited number of answers read aloud in a window, so a loop in a
browser can't run up a bill. When speech fails or is paused the answer is still on screen.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

DEFAULT_VOICE = "Kajal"
"""Polly's Indian English neural voice."""
DEFAULT_ENGINE = "neural"
FALLBACK = ("Aditi", "standard")
"""Used if the neural voice isn't available in the region."""
MAX_SPOKEN_CHARS = 1500
PER_USER = 40
WINDOW_SECONDS = 600.0

log = logging.getLogger(__name__)


def spoken(text: str) -> str:
    """The answer as it should sound: no list marks or symbols, arrows read as words."""
    text = re.sub(r"^\s*[-*•·]\s*", "", text, flags=re.MULTILINE)
    text = text.replace("→", " to ").replace("–", " to ").replace("&", " and ")
    text = re.sub(r"[*_`#>|]", "", text)
    text = re.sub(r"\s*\n\s*", ". ", text.strip())
    text = re.sub(r"\.{2,}", ".", text)
    return re.sub(r"\s{2,}", " ", text)[:MAX_SPOKEN_CHARS]


class Voice:
    def __init__(
        self,
        client: Any,
        *,
        voice: str = DEFAULT_VOICE,
        engine: str = DEFAULT_ENGINE,
        per_user: int = PER_USER,
        window_seconds: float = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """``client`` is a Polly client."""
        self.client = client
        self.voice, self.engine = voice, engine
        self.per_user, self.window = per_user, window_seconds
        self.clock = clock
        self._spoken: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _allow(self, user: str) -> bool:
        now = self.clock()
        with self._lock:
            times = self._spoken.setdefault(user, deque())
            while times and now - times[0] > self.window:
                times.popleft()
            if len(times) >= self.per_user:
                return False
            times.append(now)
            return True

    def speak(self, user: str, text: str) -> bytes | None:
        """MP3 of ``text``, or None when it can't be spoken now (paused for this user, or
        Polly unavailable)."""
        words = spoken(text)
        if not words or not self._allow(user):
            return None
        for voice, engine in ((self.voice, self.engine), FALLBACK):
            try:
                out = self.client.synthesize_speech(
                    Text=words,
                    OutputFormat="mp3",
                    VoiceId=voice,
                    Engine=engine,
                    LanguageCode="en-IN",
                )
                return out["AudioStream"].read()
            except Exception as exc:  # Polly; the answer stays on screen
                log.warning("speech with %s/%s failed: %s", voice, engine, type(exc).__name__)
        return None


def polly(region: str) -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(
        "polly",
        region_name=region,
        config=Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 1}),
    )
