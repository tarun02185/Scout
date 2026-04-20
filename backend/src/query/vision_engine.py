"""Vision engine — uses Groq Vision (fast) with Gemini fallback for image queries.

If both providers fail (model decommissioned, API key out of quota, network
error), the public `query_image` / `query_multiple_images` functions return
`None`. Callers must treat `None` as "image analysis unavailable" and show a
clean user-facing message instead of letting the raw error flow into the
response LLM — otherwise the LLM treats the error as data and produces a
confusing explanation of the 429.
"""

import base64
import io

from PIL import Image

from src.config import GROQ_API_KEY, GOOGLE_API_KEY, GEMINI_MODEL, GROQ_VISION_MODEL


def _image_to_base64(image_bytes: bytes) -> str:
    """Convert image bytes to base64 data URL."""
    img = Image.open(io.BytesIO(image_bytes))
    # Convert to RGB if needed (handles PNG transparency)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    # Resize if too large (saves tokens and speeds up)
    max_dim = 1024
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        img = img.resize((int(img.width * ratio), int(img.height * ratio)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _query_with_groq(user_query: str, image_bytes: bytes, context: str = "") -> str | None:
    """Query image using Groq Vision — fast (~1-2s)."""
    if not GROQ_API_KEY:
        return None

    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)
        b64 = _image_to_base64(image_bytes)

        prompt = f"""Analyze this image and answer the user's question in simple, non-technical language.

User question: {user_query}

RULES:
1. Start with the direct answer
2. If it's a chart/graph, extract actual data points and trends
3. If it's a diagram, explain the flow and relationships
4. If it's a table or screenshot, extract the text/data
5. Be specific — mention exact numbers, labels, and text visible
6. Keep it concise — 3-5 sentences max for simple questions
"""
        if context:
            prompt += f"\nContext: {context}"

        response = client.chat.completions.create(
            model=GROQ_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                }
            ],
            temperature=0.3,
            max_tokens=1000,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        # Return None to trigger fallback
        return None


def _query_with_gemini(user_query: str, image_bytes: bytes, context: str = "") -> str | None:
    """Fallback: Query image using Gemini Vision. Returns None on any failure."""
    if not GOOGLE_API_KEY:
        return None

    try:
        import google.generativeai as genai
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)

        img = Image.open(io.BytesIO(image_bytes))
        prompt = f"Analyze this image and answer: {user_query}"
        if context:
            prompt += f"\nContext: {context}"

        response = model.generate_content([prompt, img])
        text = (response.text or "").strip()
        return text or None
    except Exception:
        # Intentionally swallowed — caller treats None as "unavailable".
        return None


class VisionUnavailable(Exception):
    """Raised internally to mark no-provider-succeeded."""


def query_image(
    user_query: str,
    image_bytes: bytes,
    image_source: str = "",
    conversation_context: str = "",
) -> str | None:
    """Ask a question about an image. Returns None if all providers fail."""
    context = ""
    if image_source:
        context += f"Image from: {image_source}. "
    if conversation_context:
        context += conversation_context

    result = _query_with_groq(user_query, image_bytes, context)
    if result:
        return result

    result = _query_with_gemini(user_query, image_bytes, context)
    if result:
        return result

    return None


def query_multiple_images(
    user_query: str,
    images: list[dict],
    conversation_context: str = "",
) -> str | None:
    """Query across multiple images. Returns None if every image fails."""
    if not images:
        return None

    if not GROQ_API_KEY and not GOOGLE_API_KEY:
        return None

    results = []
    for img_info in images[:3]:
        image_bytes = img_info.get("image_bytes")
        source = img_info.get("source_file") or img_info.get("source_name", "unknown")
        page = img_info.get("page", "")

        if not image_bytes:
            continue

        result = query_image(
            user_query, image_bytes,
            image_source=f"{source} (page {page})" if page else source,
            conversation_context=conversation_context,
        )
        if not result:
            continue
        label = f"**{source}**" + (f" page {page}" if page else "")
        results.append(f"{label}:\n{result}")

    return "\n\n".join(results) if results else None


def vision_providers_configured() -> bool:
    """Whether at least one vision provider has an API key set."""
    return bool(GROQ_API_KEY or GOOGLE_API_KEY)
