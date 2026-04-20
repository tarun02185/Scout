"""Load images — stores immediately, analyzes lazily only when queried."""

import io
import os

import google.generativeai as genai
from PIL import Image

from src.config import GOOGLE_API_KEY, GEMINI_MODEL


def _describe_image_with_vision(image_path: str) -> str:
    """Use Gemini Vision to generate a text description of an image."""
    if not GOOGLE_API_KEY:
        return "Image uploaded but no vision API key configured."

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)

        img = Image.open(image_path)
        response = model.generate_content(
            [
                "Describe this image in detail. If it contains a chart, diagram, or architecture, "
                "extract all text, labels, relationships, and data points visible. "
                "If it contains a table, extract the data. Be thorough and specific.",
                img,
            ]
        )
        return response.text
    except Exception as e:
        return f"Could not analyze image: {str(e)}"


def describe_image_bytes(image_bytes: bytes, context: str = "") -> str:
    """Describe an image from bytes (used for PDF-embedded images)."""
    if not GOOGLE_API_KEY:
        return "No vision API key configured."

    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)

        img = Image.open(io.BytesIO(image_bytes))

        prompt = (
            "Describe this image in detail. Extract all text, labels, data points, "
            "and relationships visible. "
        )
        if context:
            prompt += f"This image is from a document about: {context}. "

        response = model.generate_content([prompt, img])
        return response.text
    except Exception as e:
        return f"Could not analyze image: {str(e)}"


def analyze_image_if_needed(source: dict, chroma_collection) -> str:
    """Analyze an image on-demand (called when user asks about it, not during upload).

    Updates the source dict in-place with the description.
    """
    # Already analyzed
    if source.get("description") and source["description"] != "Pending analysis":
        return source["description"]

    image_bytes = source.get("image_bytes")
    image_path = source.get("image_path")

    # Read bytes from file if not in memory
    if not image_bytes and image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            image_bytes = f.read()
            source["image_bytes"] = image_bytes

    if not image_bytes:
        return "Image file not available for analysis."

    # Use the fast vision engine (Groq first, Gemini fallback)
    from src.query.vision_engine import query_image
    description = query_image("Describe this image in detail. Extract all text, data, and labels.", image_bytes)

    # Cache the result
    source["description"] = description

    # Store in ChromaDB for future RAG queries
    if chroma_collection is not None:
        file_name = source.get("source_name", "image")
        doc_id = f"image_{file_name}"
        try:
            chroma_collection.add(
                ids=[doc_id],
                documents=[description],
                metadatas=[{"source": file_name, "type": "image_description"}],
            )
        except Exception:
            pass

    return description


def load_image(file_path: str, file_name: str, chroma_collection) -> dict:
    """Load an image file — stores instantly, NO vision API call during upload."""
    try:
        # Just read the bytes and get basic info — no API call
        with open(file_path, "rb") as f:
            image_bytes = f.read()

        # Get dimensions for metadata
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size

        return {
            "source_name": file_name,
            "source_type": "image",
            "description": "Pending analysis",  # Will be filled on first query
            "image_bytes": image_bytes,
            "image_path": file_path,
            "width": width,
            "height": height,
            "analyzed": False,
        }

    except Exception as e:
        return {"source_name": file_name, "source_type": "image", "error": str(e)}
