"""Groq LLM Service Module

Provides conversational text generation using Groq's chat completion API.
Designed specifically for spoken dialogue: concise, speech-friendly phrasing,
no markdown clutter, safe error handling, and strict decoupling from session/interruption logic.
"""

import time
from typing import Any, Dict, List, Optional
import httpx

from backend.app.config import Settings, get_settings
from backend.app.models.schemas import ChatMessage


VOICE_SYSTEM_PROMPT = (
    "You are a concise voice assistant. "
    "Give your answer directly in 1 to 2 short sentences without thought steps, reasoning process, or preamble. "
    "Do NOT use markdown formatting, bullet points, asterisks, hashtags, or emojis, as your response will be read aloud by text-to-speech."
)


class GroqLLMServiceError(Exception):
    """Base exception for Groq LLM service errors."""
    pass


class GroqLLMService:
    """Independent service wrapper for Groq LLM Chat Completions API."""

    def __init__(self, app_settings: Optional[Settings] = None, timeout_seconds: float = 15.0):
        self.settings = app_settings or get_settings()
        self.timeout = timeout_seconds

    async def generate(
        self,
        messages: List[ChatMessage],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 256,
        api_key_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send chat messages to Groq LLM API and return the generated text and safe metadata.
        
        Args:
            messages: List of conversational ChatMessage objects.
            system_prompt: Optional custom system prompt (defaults to VOICE_SYSTEM_PROMPT).
            model: Optional model override (defaults to configured groq_model).
            temperature: Sampling temperature (0.0 - 2.0).
            max_tokens: Maximum tokens in completion.
            api_key_override: Optional API key override (for testing/mocking).
            
        Returns:
            Dict containing text, provider, model, prompt_tokens, completion_tokens, latency_ms.
            
        Raises:
            GroqLLMServiceError: If API key is missing, network fails, or response is invalid.
        """
        api_key = api_key_override or self.settings.groq_api_key
        if not api_key or not api_key.strip():
            raise GroqLLMServiceError(
                "Groq API key is not configured. Set GROQ_API_KEY in environment or backend/.env."
            )

        if not messages:
            raise GroqLLMServiceError("Cannot generate response: message list is empty.")

        target_model = model or self.settings.groq_model
        sys_prompt = system_prompt if system_prompt is not None else VOICE_SYSTEM_PROMPT

        # Build payload
        payload_messages: List[Dict[str, str]] = []
        if sys_prompt and sys_prompt.strip():
            payload_messages.append({"role": "system", "content": sys_prompt.strip()})

        for msg in messages:
            role = msg["role"] if isinstance(msg, dict) else getattr(msg, "role", "user")
            content = msg["content"] if isinstance(msg, dict) else getattr(msg, "content", "")
            if not content or not content.strip():
                continue
            if role == "system" and sys_prompt and sys_prompt.strip() and payload_messages and payload_messages[0]["role"] == "system":
                continue
            payload_messages.append({"role": role, "content": content.strip()})

        if not payload_messages or (len(payload_messages) == 1 and payload_messages[0]["role"] == "system"):
            raise GroqLLMServiceError("Cannot generate response: no valid user/assistant message content provided.")

        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        }

        body = {
            "model": target_model,
            "messages": payload_messages,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
        }

        start_time = time.perf_counter()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.settings.groq_llm_url,
                    headers=headers,
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise GroqLLMServiceError(
                f"Groq LLM request timed out after {self.timeout}s."
            ) from exc
        except httpx.RequestError as exc:
            raise GroqLLMServiceError(
                f"Network error connecting to Groq LLM service: {exc.__class__.__name__}"
            ) from exc

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if response.status_code == 401:
            raise GroqLLMServiceError("Groq authentication failed: invalid or unauthorized API key.")
        elif response.status_code == 429:
            raise GroqLLMServiceError("Groq rate limit or quota exceeded.")
        elif response.status_code != 200:
            err_msg = f"Groq LLM API returned HTTP {response.status_code}"
            try:
                err_json = response.json()
                if "error" in err_json:
                    msg = err_json["error"].get("message") if isinstance(err_json["error"], dict) else str(err_json["error"])
                    err_msg += f": {msg}"
            except Exception:
                pass
            raise GroqLLMServiceError(err_msg)

        try:
            data = response.json()
        except Exception as exc:
            raise GroqLLMServiceError("Failed to parse JSON response from Groq LLM API.") from exc

        choices = data.get("choices")
        if not choices or not isinstance(choices, list) or len(choices) == 0:
            raise GroqLLMServiceError("Groq LLM API returned empty choices in response.")

        choice = choices[0]
        message = choice.get("message", {})
        text = message.get("content") or message.get("reasoning_content") or message.get("reasoning") or ""

        # Clean out any thinking block tokens if returned
        if "<think>" in text:
            if "</think>" in text:
                text = text.split("</think>")[-1].strip()
            else:
                text = text.replace("<think>", "").strip()

        if not text:
            raise GroqLLMServiceError("Groq LLM API returned empty content in message choice.")

        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")

        return {
            "text": text.strip(),
            "provider": "groq",
            "model": target_model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": round(latency_ms, 2),
            "status": "SUCCESS",
        }


# Default singleton instance
default_llm_service = GroqLLMService()

