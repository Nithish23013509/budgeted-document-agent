"""
llm.py -- LLM abstraction layer.

The agent depends on the LLMClient interface, NOT on a specific provider.
Provider-specific code is isolated here.

Supported providers (set via LLM_PROVIDER env var):
    - gemini  -- requires GEMINI_API_KEY
    - groq    -- requires GROQ_API_KEY

API keys are loaded from a .env file or environment variables.
NEVER hard-code API keys.
"""

import os
from dotenv import load_dotenv


# -- Exceptions -------------------------------------------------------

class LLMError(Exception):
    """Raised when the LLM call fails for any reason."""
    pass


# -- Abstract interface ------------------------------------------------

class LLMClient:
    """
    Abstract LLM interface.

    All agent code depends on this class, never on a specific provider.
    The system_prompt is baked in at construction time.
    Each generate() call sends a user prompt and returns the model's text.
    """

    def generate(self, prompt: str, require_json: bool = True) -> str:
        """Send a prompt to the LLM and return the response text."""
        raise NotImplementedError


# -- Gemini implementation ---------------------------------------------

class GeminiClient(LLMClient):
    """Google Gemini implementation of LLMClient."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash",
        system_prompt: str = "",
    ) -> None:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._genai = genai
        self._model_name = model_name

        model_kwargs: dict = {"model_name": model_name}
        if system_prompt:
            model_kwargs["system_instruction"] = system_prompt

        self._model = genai.GenerativeModel(**model_kwargs)
        self._temperature = 0.0

    def generate(self, prompt: str, require_json: bool = True) -> str:
        """Call Gemini and return the response text."""
        try:
            config = {"temperature": self._temperature}
            if require_json:
                config["response_mime_type"] = "application/json"
                
            response = self._model.generate_content(
                prompt,
                generation_config=config,
            )
            if not response.candidates:
                raise LLMError(
                    "No response generated (possibly filtered by safety settings)."
                )
            return response.text
        except LLMError:
            raise
        except ValueError as exc:
            raise LLMError(f"No valid response text: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"Gemini API call failed: {exc}") from exc


# -- Groq implementation -----------------------------------------------

class GroqClient(LLMClient):
    """Groq implementation of LLMClient (OpenAI-compatible API)."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "llama-3.3-70b-versatile",
        system_prompt: str = "",
    ) -> None:
        from groq import Groq

        self._client = Groq(api_key=api_key)
        self._model_name = model_name
        self._system_prompt = system_prompt

    def generate(self, prompt: str, require_json: bool = True) -> str:
        """Call Groq and return the response text."""
        try:
            messages = []

            if self._system_prompt:
                messages.append({
                    "role": "system",
                    "content": self._system_prompt,
                })

            messages.append({
                "role": "user",
                "content": prompt,
            })
            
            kwargs = {
                "model": self._model_name,
                "messages": messages,
                "temperature": 0.0,
            }
            if require_json:
                kwargs["response_format"] = {"type": "json_object"}

            response = self._client.chat.completions.create(**kwargs)

            if not response.choices:
                raise LLMError("No response generated from Groq.")

            content = response.choices[0].message.content
            if content is None:
                raise LLMError("Groq returned empty content.")

            return content

        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"Groq API call failed: {exc}") from exc


# -- Factory -----------------------------------------------------------

def create_llm_client(system_prompt: str = "") -> LLMClient:
    """
    Create an LLMClient based on environment configuration.

    Reads from .env file or environment variables:
        LLM_PROVIDER   -- "gemini" or "groq" (default: "groq")
        GEMINI_API_KEY  -- required for gemini
        GEMINI_MODEL    -- optional, default "gemini-2.0-flash"
        GROQ_API_KEY    -- required for groq
        GROQ_MODEL      -- optional, default "llama-3.3-70b-versatile"

    Args:
        system_prompt: The system-level instruction baked into the client.

    Returns:
        A configured LLMClient instance.

    Raises:
        ValueError: If provider is unsupported or API key is missing.
    """
    load_dotenv(override=True)

    provider = os.getenv("LLM_PROVIDER", "groq").lower().strip()

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. "
                "Create a .env file with:\n"
                "  GEMINI_API_KEY=your-key-here\n"
                "Get a key at: https://aistudio.google.com/apikey"
            )
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
        return GeminiClient(
            api_key=api_key,
            model_name=model_name,
            system_prompt=system_prompt,
        )

    elif provider == "groq":
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY is not set. "
                "Create a .env file with:\n"
                "  GROQ_API_KEY=your-key-here\n"
                "Get a key at: https://console.groq.com/keys"
            )
        model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
        return GroqClient(
            api_key=api_key,
            model_name=model_name,
            system_prompt=system_prompt,
        )

    else:
        raise ValueError(
            f"Unsupported LLM provider: '{provider}'. "
            f"Supported: gemini, groq"
        )
