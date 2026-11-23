"""Latency diagnosis probe comparing primary, fallback, and thinking level controls."""

from pathlib import Path
import statistics
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from typing import Any, Dict, List, Optional
from google.genai import types

from src.config import GEMINI_FALLBACK_MODEL, GEMINI_MODEL, GEN_TEMPERATURE
from src.gemini_client import create_gemini_client
from src.logging_setup import configure_logging
from src.rag import RagJsonOutput
from src.vectorstore import VectorStore

configure_logging()

SYSTEM_INSTRUCTION = (
    "You are DocMind, an assistant for a law firm's staff and clients. "
    "Answer ONLY from the numbered context passages provided below. Never use outside knowledge. "
    "Do not give legal advice beyond what the documents state. If the context does not contain the answer, set found=false. "
    "Answer in clear English only, whatever language the question is written in. "
    "Keep answers concise and include exact figures, dates, and names as written in the documents. "
    "In used_sources, list ONLY passages that directly state a fact used in the answer; prefer the single most authoritative passage; "
    "add another passage only if it states a different fact needed for the answer. Never list passages that are merely related or background."
)


def run_call(
    client: Any,
    model: str,
    prompt: str,
    thinking_level: Optional[Any] = None,
) -> Dict[str, Any]:
    """Execute a single Gemini generate_content call and measure latency and token usage."""
    config_args: Dict[str, Any] = {
        "response_mime_type": "application/json",
        "response_schema": RagJsonOutput,
        "temperature": GEN_TEMPERATURE,
        "system_instruction": SYSTEM_INSTRUCTION,
    }
    if thinking_level is not None:
        config_args["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)

    config = types.GenerateContentConfig(**config_args)

    max_attempts = 4
    for attempt in range(1, max_attempts + 1):
        try:
            start = time.perf_counter()
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
            latency_ms = round((time.perf_counter() - start) * 1000, 2)

            meta = getattr(resp, "usage_metadata", None)
            prompt_tokens = getattr(meta, "prompt_token_count", None) if meta else None
            output_tokens = getattr(meta, "candidates_token_count", None) if meta else None
            thoughts_tokens = getattr(meta, "thoughts_token_count", None) if meta else None

            text = getattr(resp, "text", "") or ""
            return {
                "latency_ms": latency_ms,
                "text": text,
                "prompt_tokens": prompt_tokens,
                "output_tokens": output_tokens,
                "thoughts_tokens": thoughts_tokens,
            }
        except Exception as e:
            is_transient = any(
                code in str(e)
                for code in ("500", "502", "503", "504", "UNAVAILABLE", "DEADLINE_EXCEEDED", "ResourceExhausted")
            )
            if attempt < max_attempts and is_transient:
                print(f"    [Transient error on {model}: {type(e).__name__}, retrying in 4s...]")
                time.sleep(4)
            else:
                raise


def main():
    store = VectorStore()
    query = "What are the hourly rates for each lawyer level?"
    results = store.query(query, k=5)
    context_lines = [f"[{i}] Citation: {r['citation']}\n{r['text']}" for i, r in enumerate(results, start=1)]
    context_str = "\n\n".join(context_lines)
    prompt = f"Context passages:\n{context_str}\n\nUser Question: {query}"

    client = create_gemini_client()
    primary_model = GEMINI_MODEL or "gemini-3.5-flash-lite"
    fallback_model = GEMINI_FALLBACK_MODEL or "gemini-3.1-flash-lite"

    print("=" * 85)
    print("DOCMIND LATENCY PROBE (3 calls per group, 4s spacing)")
    print(f"Primary Model : {primary_model}")
    print(f"Fallback Model: {fallback_model}")
    print("=" * 85)

    groups = [
        ("Group 1: Primary Model (default)", primary_model, None),
        ("Group 2: Fallback Model (default)", fallback_model, None),
        ("Group 3: Primary Model (thinking_level=MINIMAL)", primary_model, types.ThinkingLevel.MINIMAL),
    ]

    all_results: Dict[str, List[Dict[str, Any]]] = {}

    for group_name, model_name, thinking_lvl in groups:
        print(f"\n--- Running {group_name} ---")
        group_records = []
        for call_idx in range(1, 4):
            try:
                res = run_call(client, model_name, prompt, thinking_level=thinking_lvl)
                group_records.append(res)
                print(
                    f"  Call {call_idx}: {res['latency_ms']:.1f} ms | "
                    f"Prompt tokens: {res['prompt_tokens']} | Output tokens: {res['output_tokens']} | "
                    f"Thoughts: {res['thoughts_tokens']}"
                )
            except Exception as exc:
                err_msg = f"{type(exc).__name__}: {str(exc)[:60]}"
                print(f"  Call {call_idx}: FAILED ({err_msg})")
                group_records.append({
                    "latency_ms": None,
                    "error": err_msg,
                    "text": "",
                    "prompt_tokens": None,
                    "output_tokens": None,
                    "thoughts_tokens": None,
                })
            time.sleep(4)

        all_results[group_name] = group_records

    print("\n" + "=" * 85)
    print("PROBE RESULTS SUMMARY")
    print("=" * 85)
    for group_name, records in all_results.items():
        latencies = [r["latency_ms"] for r in records if r.get("latency_ms") is not None]
        if latencies:
            median_lat = statistics.median(latencies)
            mean_lat = statistics.mean(latencies)
            out_toks = [r["output_tokens"] for r in records if r.get("output_tokens") is not None]
            avg_out = statistics.mean(out_toks) if out_toks else "N/A"
            sample_txt = next((r["text"] for r in records if r.get("text")), "N/A")
            print(f"\n{group_name}:")
            print(f"  Latencies   : {[f'{x:.1f}ms' for x in latencies]}")
            print(f"  Median      : {median_lat:.1f} ms")
            print(f"  Mean        : {mean_lat:.1f} ms")
            print(f"  Avg Output  : {avg_out} tokens")
            print(f"  Sample text : {sample_txt[:140]}...")
        else:
            errors = [r.get("error") for r in records if r.get("error")]
            print(f"\n{group_name}:")
            print(f"  Status      : All calls failed due to upstream availability ({errors[0] if errors else 'N/A'})")

    print("\n" + "=" * 85)


if __name__ == "__main__":
    main()
