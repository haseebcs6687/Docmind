"""Utility script to verify Gemini API connectivity, list models, and test generation/embedding."""

import argparse
import sys
from pathlib import Path
from typing import List

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_gemini_api_key


def _handle_api_error(err: Exception) -> None:
    """Print user-friendly error messages without exposing sensitive information."""
    err_str = str(err)
    status_code = getattr(err, "code", None) or getattr(err, "status_code", None)

    if isinstance(err, ValueError):
        print(f"[Error] Configuration: {err}")
    elif status_code == 429 or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
        print(
            "[Error] Rate limit reached: Gemini API quota exceeded "
            "(HTTP 429 / RESOURCE_EXHAUSTED). Please wait a moment before retrying."
        )
    elif (
        status_code in (400, 403)
        or "API_KEY_INVALID" in err_str
        or "PERMISSION_DENIED" in err_str
        or "INVALID_ARGUMENT" in err_str
    ):
        print(
            "[Error] Authentication failed: The provided Gemini API key is invalid "
            "or lacks necessary permissions."
        )
    elif (
        "ConnectError" in err_str
        or "NetworkError" in err_str
        or "Timeout" in err_str
        or "ConnectionError" in err_str
    ):
        print(
            "[Error] Network issue: Unable to connect to Gemini API servers. "
            "Please check your internet connection or proxy settings."
        )
    else:
        print(f"[Error] Gemini API operation failed: {err_str}")


def mode_a_list_models(client) -> None:
    """List available Gemini models supporting text generation and embeddings in clean tables."""
    print("Fetching available Gemini models...\n")
    try:
        all_models = list(client.models.list())
    except Exception as e:
        _handle_api_error(e)
        return

    text_models = []
    embed_models = []

    for m in all_models:
        name = getattr(m, "name", "")
        actions: List[str] = getattr(m, "supported_actions", []) or []
        actions_lower = [a.lower() for a in actions]

        if "generatecontent" in actions_lower:
            text_models.append((name, ", ".join(actions)))
        if "embedcontent" in actions_lower:
            embed_models.append((name, ", ".join(actions)))

    def print_table(title: str, rows: List[tuple[str, str]]) -> None:
        print("=" * 80)
        print(f" {title} ({len(rows)} models)")
        print("=" * 80)
        if not rows:
            print(" No matching models found.")
            print("-" * 80)
            return

        name_col_width = max(len(r[0]) for r in rows)
        name_col_width = max(name_col_width, 25)

        header = f"{'Model Name'.ljust(name_col_width)} | Supported Actions"
        print(header)
        print("-" * len(header))
        for name, act in sorted(rows, key=lambda x: x[0]):
            print(f"{name.ljust(name_col_width)} | {act}")
        print("-" * len(header) + "\n")

    print_table("Models Supporting Text Generation", text_models)
    print_table("Models Supporting Embeddings", embed_models)


def mode_b_test_models(client, gen_model: str, embed_model: str) -> None:
    """Perform one minimal text generation call and one minimal embedding call."""
    print(f"Testing text generation with model: '{gen_model}'...")
    try:
        response = client.models.generate_content(
            model=gen_model,
            contents="Say hello in Urdu",
        )
        reply = getattr(response, "text", "")
        print("\n--- Text Generation Response ---")
        print(reply.strip() if reply else "[Empty response received]")
        print("--------------------------------\n")
    except Exception as e:
        print("\nText generation failed:")
        _handle_api_error(e)
        return

    print(f"Testing embeddings with model: '{embed_model}'...")
    try:
        embed_response = client.models.embed_content(
            model=embed_model,
            contents="Say hello in Urdu",
        )
        vector_len = 0
        if hasattr(embed_response, "embeddings") and embed_response.embeddings:
            values = getattr(embed_response.embeddings[0], "values", None)
            if values is not None:
                vector_len = len(values)

        print("\n--- Embedding Result ---")
        print(f"Vector Dimensions: {vector_len}")
        print("------------------------\n")
    except Exception as e:
        print("\nEmbedding generation failed:")
        _handle_api_error(e)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Gemini API models and connectivity.")
    parser.add_argument("--model", type=str, default=None, help="Model name for text generation test.")
    parser.add_argument("--embed-model", type=str, default=None, help="Model name for embedding test.")
    args = parser.parse_args()

    try:
        api_key = get_gemini_api_key()
    except ValueError as e:
        _handle_api_error(e)
        sys.exit(1)

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
    except Exception as e:
        _handle_api_error(e)
        sys.exit(1)

    if args.model or args.embed_model:
        if not (args.model and args.embed_model):
            print("[Error] Mode B requires both --model and --embed-model arguments.")
            sys.exit(1)
        mode_b_test_models(client, args.model, args.embed_model)
    else:
        mode_a_list_models(client)


if __name__ == "__main__":
    main()
