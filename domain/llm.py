from __future__ import annotations

import os


def call_llm(prompt: str, *, api_key: str, model: str) -> str:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    api_key = (api_key or "").strip()
    if not api_key:
        raise ValueError("api_key is required")

    model = (model or "").strip()
    if not model:
        raise ValueError("model is required")

    from google import genai  # type: ignore[import-not-found]

    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(model=model, contents=prompt)
    text = getattr(resp, "text", None)
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Empty response from GenAI")
    return text


if __name__ == "__main__":
    import argparse
    import sys

    try:
        from dotenv import load_dotenv  # type: ignore[import-not-found]
    except ImportError:
        load_dotenv = None

    parser = argparse.ArgumentParser(description="Quick CLI test for call_llm().")
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Prompt text. If omitted, prompt is read from stdin.",
    )
    args = parser.parse_args()

    if load_dotenv is not None:
        load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY") or ""
    model = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"

    prompt = " ".join(args.prompt).strip()
    if not prompt:
        prompt = sys.stdin.read().strip()

    try:
        out = call_llm(prompt, api_key=api_key, model=model)
    except Exception as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1) from e

    sys.stdout.write(out.rstrip() + "\n")
