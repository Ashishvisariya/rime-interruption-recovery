"""Speech-to-Text (STT) Service Integration Module

Provides asynchronous integration with Groq Whisper STT API (https://api.groq.com/openai/v1/audio/transcriptions).
Enforces credential isolation, connection timeouts, audio format flexibility,
and quota preservation with zero automatic retry loops.
"""

import logging
import time
from typing import Optional
import httpx

from backend.app.config import Settings, get_settings
from backend.app.models.schemas import TranscriptionResponse

logger = logging.getLogger(__name__)


class STTError(Exception):
    """Base exception for STT transcription failures with sanitized error messages."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class GroqSTTService:
    """Service client for Groq Whisper Speech-to-Text API."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self._settings = settings or get_settings()
        self._timeout = httpx.Timeout(timeout=15.0, connect=5.0)
        # Use a persistent client for connection reuse (avoids ~1.5s TLS handshake per call)
        self._client = client or httpx.AsyncClient(timeout=self._timeout)
        self._owns_client = client is None

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        mime_type: str = "audio/wav",
        language: Optional[str] = "en",
        model: Optional[str] = None,
        session_id: Optional[str] = None,
        turn_id: Optional[int] = None,
    ) -> TranscriptionResponse:
        """Transcribe speech audio into text using Groq Whisper.

        Args:
            audio_bytes: Raw binary audio data.
            filename: Name of the audio file/container (e.g. 'audio.webm', 'audio.wav').
            mime_type: MIME type of the audio stream.
            language: Language code for transcription (e.g. 'en').
            model: Whisper model override (defaults to configured model, e.g. 'whisper-large-v3').
            session_id: Associated session ID if applicable.
            turn_id: Associated turn ID if applicable.

        Returns:
            TranscriptionResponse containing transcribed text and metadata.

        Raises:
            ValueError: If audio data is empty or GROQ_API_KEY is not configured.
            STTError: If API request fails, times out, or returns an unprocessable response.
        """
        if not audio_bytes or len(audio_bytes) == 0:
            raise ValueError("Audio data for transcription cannot be empty.")

        api_key = self._settings.groq_api_key
        if not api_key or not api_key.strip():
            raise ValueError(
                "GROQ_API_KEY is not configured. Ensure credentials are set in environment."
            )

        resolved_model = model or self._settings.groq_stt_model
        api_url = self._settings.groq_stt_url

        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
        }

        # 1. Determine actual audio container & format from magic bytes
        detected_ext = None
        detected_mime = None
        if audio_bytes.startswith(b"RIFF") and b"WAVE" in audio_bytes[:16]:
            detected_ext, detected_mime = "wav", "audio/wav"
        elif audio_bytes.startswith(b"\x1a\x45\xdf\xa3"):
            detected_ext, detected_mime = "webm", "audio/webm"
        elif audio_bytes.startswith(b"OggS"):
            detected_ext, detected_mime = "ogg", "audio/ogg"
        elif audio_bytes.startswith(b"ID3") or audio_bytes.startswith(b"\xff\xfb") or audio_bytes.startswith(b"\xff\xf3") or audio_bytes.startswith(b"\xff\xf2"):
            detected_ext, detected_mime = "mp3", "audio/mpeg"
        elif len(audio_bytes) > 8 and audio_bytes[4:8] == b"ftyp":
            detected_ext, detected_mime = "m4a", "audio/mp4"

        # Resolve filename and mime type to match the real format
        if detected_ext and detected_mime:
            resolved_ext = filename.split(".")[-1].lower() if "." in filename else ""
            resolved_filename = filename if resolved_ext == detected_ext else f"audio.{detected_ext}"
            resolved_mime = detected_mime
        else:
            resolved_filename = filename or "audio.webm"
            resolved_mime = mime_type or "audio/webm"

        # Minimal required logs: [STT] mime= [STT] bytes= [STT] filename=
        logger.info(f"[STT] mime={resolved_mime} bytes={len(audio_bytes)} filename={resolved_filename}")
        print(f"[STT] mime={resolved_mime} bytes={len(audio_bytes)} filename={resolved_filename}")

        files = {
            "file": (resolved_filename, audio_bytes, resolved_mime),
        }
        data = {
            "model": resolved_model,
            "response_format": "json",
            "temperature": 0.0,
        }
        if language:
            data["language"] = language

        t_start = time.perf_counter()
        try:
            response = await self._client.post(
                api_url,
                headers=headers,
                files=files,
                data=data,
            )

            # Handle non-2xx responses without leaking secret headers
            if response.status_code != 200:
                err_detail = "Unknown error"
                try:
                    err_json = response.json()
                    err_detail = (
                        err_json.get("error", {}).get("message")
                        or err_json.get("detail")
                        or str(err_json)
                    )
                except Exception:
                    err_detail = response.text[:200] if response.text else "No response body"

                raise STTError(
                    f"Groq STT API returned HTTP {response.status_code}: {err_detail}",
                    status_code=response.status_code,
                )

            res_json = response.json()
            transcribed_text = res_json.get("text", "").strip()
            latency_ms = (time.perf_counter() - t_start) * 1000.0
            logger.info(f"[STT] stt_completed: turn_id={turn_id}, transcript='{transcribed_text}', latency_ms={latency_ms:.1f}")

            return TranscriptionResponse(
                session_id=session_id,
                turn_id=turn_id,
                text=transcribed_text,
                provider="groq",
                model=resolved_model,
                status="SUCCESS",
            )

        except httpx.TimeoutException as exc:
            raise STTError(f"Groq STT request timed out: {type(exc).__name__}") from None
        except httpx.RequestError as exc:
            raise STTError(f"Groq STT network connection error: {type(exc).__name__}") from None


# Default service instance
default_stt_service = GroqSTTService()
