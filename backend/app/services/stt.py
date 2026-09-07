"""Speech-to-Text (STT) Service Integration Module

Provides asynchronous integration with Groq Whisper STT API (https://api.groq.com/openai/v1/audio/transcriptions).
Enforces credential isolation, connection timeouts, audio format flexibility,
and quota preservation with zero automatic retry loops.
"""

from typing import Optional
import httpx

from backend.app.config import Settings, get_settings
from backend.app.models.schemas import TranscriptionResponse


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
        self._client = client
        self._timeout = httpx.Timeout(timeout=15.0, connect=5.0)

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

        files = {
            "file": (filename, audio_bytes, mime_type),
        }
        data = {
            "model": resolved_model,
            "response_format": "json",
        }
        if language:
            data["language"] = language

        created_client = False
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=self._timeout)
            created_client = True

        try:
            response = await client.post(
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
        finally:
            if created_client:
                await client.aclose()


# Default service instance
default_stt_service = GroqSTTService()
