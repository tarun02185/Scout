"""Shared LLM helper — tries Groq first, falls back to Gemini on rate limit or failure."""

from collections.abc import Generator
from src.config import GROQ_API_KEY, GROQ_MODEL, GOOGLE_API_KEY, GEMINI_MODEL


def call_llm(messages: list[dict], temperature: float = 0.3, max_tokens: int = 1500) -> str:
    """Call LLM and return full response. Groq first, Gemini fallback."""
    # Try Groq
    if GROQ_API_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)
            resp = client.chat.completions.create(
                model=GROQ_MODEL, messages=messages,
                temperature=temperature, max_tokens=max_tokens,
            )
            return resp.choices[0].message.content.strip()
        except Exception as groq_err:
            err_str = str(groq_err)
            if "rate_limit" not in err_str and "429" not in err_str:
                # Non-rate-limit error with no fallback — raise
                if not GOOGLE_API_KEY:
                    raise
            # Fall through to Gemini

    # Fallback to Gemini
    if GOOGLE_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GOOGLE_API_KEY)
            model = genai.GenerativeModel(GEMINI_MODEL)

            # Convert messages to Gemini format
            prompt_parts = []
            for m in messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                if role == "system":
                    prompt_parts.append(f"Instructions: {content}")
                else:
                    prompt_parts.append(f"{role}: {content}")

            resp = model.generate_content("\n\n".join(prompt_parts))
            return resp.text.strip()
        except Exception as gem_err:
            raise RuntimeError(f"Both Groq and Gemini failed. Gemini: {gem_err}")

    raise RuntimeError("No LLM API key configured (GROQ_API_KEY or GOOGLE_API_KEY)")


def stream_llm(messages: list[dict], temperature: float = 0.3, max_tokens: int = 1500) -> Generator[str, None, None]:
    """Stream LLM response token by token. Groq first, Gemini fallback."""
    # Try Groq streaming
    if GROQ_API_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)
            stream = client.chat.completions.create(
                model=GROQ_MODEL, messages=messages,
                temperature=temperature, max_tokens=max_tokens, stream=True,
            )
            yielded = False
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yielded = True
                    yield delta.content
            if yielded:
                return
        except Exception as e:
            err_str = str(e)
            if "rate_limit" not in err_str and "429" not in err_str:
                if not GOOGLE_API_KEY:
                    yield f"Error: {e}"
                    return

    # Fallback to Gemini (non-streaming, yield in chunks)
    if GOOGLE_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GOOGLE_API_KEY)
            model = genai.GenerativeModel(GEMINI_MODEL)

            prompt_parts = []
            for m in messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                if role == "system":
                    prompt_parts.append(f"Instructions: {content}")
                else:
                    prompt_parts.append(f"{role}: {content}")

            resp = model.generate_content("\n\n".join(prompt_parts), stream=True)
            for chunk in resp:
                if chunk.text:
                    yield chunk.text
            return
        except Exception as e:
            yield f"Error: {e}"
            return

    yield "No LLM API key configured."
