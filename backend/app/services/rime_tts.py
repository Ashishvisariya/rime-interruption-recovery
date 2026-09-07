"""Rime Labs TTS Service Integration Module

Provides asynchronous integration with the genuine Rime Labs TTS API (https://users.rime.ai/v1/rime-tts).
Enforces zero credential leakage, connection timeouts, turn context association,
and strict quota preservation with no automatic retry loops.
"""

import json
from typing import Optional, Tuple
import httpx

from backend.app.config import Settings, get_settings
from backend.app.models.schemas import RimeTTSMetadata


class RimeTTSError(Exception):
    """Base exception for Rime TTS failures with sanitized messages."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class RimeTTSService:
    """Service client for Rime Labs Text-to-Speech API."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self._settings = settings or get_settings()
        self._client = client
        self._timeout = httpx.Timeout(timeout=10.0, connect=5.0)

    def _resolve_accept_header(self, audio_format: str) -> str:
        """Map audio format string to HTTP Accept MIME type."""
        fmt = audio_format.lower().strip()
        if fmt in ("mp3", "mpeg"):
            return "audio/mpeg"
        if fmt == "wav":
            return "audio/wav"
        if fmt in ("pcm", "raw"):
            return "audio/pcm"
        if fmt == "ogg":
            return "audio/ogg"
        return f"audio/{fmt}"

    async def synthesize(
        self,
        text: str,
        session_id: str,
        turn_id: int,
        model_id: Optional[str] = None,
        speaker: Optional[str] = None,
        audio_format: Optional[str] = None,
        lang: Optional[str] = None,
    ) -> Tuple[bytes, RimeTTSMetadata]:
        """Synthesize text into speech using Rime Labs TTS API.

        Args:
            text: Text to synthesize.
            session_id: ID of the active conversation session.
            turn_id: Monotonic ID of the turn initiating the synthesis.
            model_id: Rime model identifier (defaults to configured default, e.g. 'coda').
            speaker: Speaker voice name (defaults to configured default, e.g. 'celeste').
            audio_format: Desired audio format (defaults to configured default, e.g. 'mp3').
            lang: Language code (e.g. 'en').

        Returns:
            Tuple of (raw_audio_bytes, RimeTTSMetadata).

        Raises:
            ValueError: If input is invalid or RIME_API_KEY is not configured.
            RimeTTSError: If API request fails, times out, or returns empty audio.
        """
        if not text or not text.strip():
            raise ValueError("TTS synthesis text cannot be empty.")

        api_key = self._settings.rime_api_key
        if not api_key or not api_key.strip():
            raise ValueError(
                "RIME_API_KEY is not configured. Ensure credentials are set in environment."
            )

        resolved_model = model_id or self._settings.rime_default_model
        resolved_speaker = speaker or self._settings.rime_default_speaker
        resolved_format = (audio_format or self._settings.rime_default_format).lower()
        api_url = self._settings.rime_api_url

        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "Accept": self._resolve_accept_header(resolved_format),
        }

        payload = {
            "speaker": resolved_speaker,
            "text": text.strip(),
            "modelId": resolved_model,
            "audioFormat": resolved_format,
        }
        if lang:
            payload["lang"] = lang

        created_client = False
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=self._timeout)
            created_client = True

        try:
            response = await client.post(
                api_url,
                headers=headers,
                json=payload,
            )

            # Handle non-2xx responses safely without echoing secret headers
            if response.status_code != 200:
                err_detail = "Unknown error"
                try:
                    err_json = response.json()
                    err_detail = err_json.get("detail") or err_json.get("message") or str(err_json)
                except Exception:
                    err_detail = response.text[:200] if response.text else "No response body"

                raise RimeTTSError(
                    f"Rime API returned HTTP {response.status_code}: {err_detail}",
                    status_code=response.status_code,
                )

            audio_bytes = response.content
            if not audio_bytes or len(audio_bytes) == 0:
                raise RimeTTSError("Rime API returned empty audio content.")

            metadata = RimeTTSMetadata(
                session_id=session_id,
                turn_id=turn_id,
                provider="rime",
                model_id=resolved_model,
                speaker=resolved_speaker,
                audio_format=resolved_format,
                audio_bytes_length=len(audio_bytes),
                status="SUCCESS",
            )

            return audio_bytes, metadata

        except httpx.TimeoutException as exc:
            raise RimeTTSError(f"Rime TTS request timed out: {type(exc).__name__}") from None
        except httpx.RequestError as exc:
            raise RimeTTSError(f"Rime TTS network connection error: {type(exc).__name__}") from None
        finally:
            if created_client:
                await client.aclose()


# Default service instance
default_rime_service = RimeTTSService()
