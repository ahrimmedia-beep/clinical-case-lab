"""One tiny live call per model, to prove it is enabled for this project (infra/check-models.sh).

Env: CHECK_MODELS ("provider/model ..."), OPTIONAL_MODELS ("provider/model ..." subset of
CHECK_MODELS that may WARN instead of FAIL, per spec SS15 Claude Opus 5.5 is optional), GCP_PROJECT,
GEMINI_LOCATION, CLAUDE_REGION, CHECK_RUN_ID.
Prints one line per model: MODEL_CHECK <run id> OK|FAIL|WARN <provider/model> <details>.
Exits 1 if any *required* (non-optional) model failed; a WARN never fails the run.
Talks to Vertex AI only (never the direct-API fallbacks).
"""

from __future__ import annotations

import os
import sys
import time

PROMPT = "Reply with the single word OK."
# Claude calls on Vertex always pass a low-effort output config (amendments.md D): no sampling
# params, cheapest/fastest route for a one-word liveness probe.
CLAUDE_OUTPUT_CONFIG = {"effort": "low"}
HINTS = (
    ("location is not supported", "Google does not serve this network: run without --local (Cloud Run)"),
    ("resource_exhausted", "quota: request a quota increase for this model, or use the API-key fallback"),
    ("429", "quota or rate limit: request a quota increase, or use the API-key fallback"),
    ("permission_denied", "caller lacks roles/aiplatform.user, or the model is not enabled in Model Garden"),
    ("403", "caller lacks roles/aiplatform.user, or the model is not enabled in Model Garden"),
    ("not_found", "model id or region unavailable, or the model is not enabled in Model Garden"),
    ("404", "model id or region unavailable, or the model is not enabled in Model Garden"),
)


def hint(message: str) -> str:
    lowered = message.lower()
    for needle, text in HINTS:
        if needle in lowered:
            return text
    return "see the error text"


def call(provider: str, model: str, project: str) -> str:
    if provider == "gemini":
        from google import genai

        client = genai.Client(
            vertexai=True, project=project, location=os.environ.get("GEMINI_LOCATION", "global")
        )
        response = client.models.generate_content(model=model, contents=PROMPT)
        return (response.text or "").strip()
    if provider == "claude":
        from anthropic import AnthropicVertex

        claude = AnthropicVertex(project_id=project, region=os.environ.get("CLAUDE_REGION", "global"))
        message = claude.messages.create(
            model=model,
            max_tokens=16,
            messages=[{"role": "user", "content": PROMPT}],
            output_config=CLAUDE_OUTPUT_CONFIG,
        )
        return "".join(block.text for block in message.content if block.type == "text").strip()
    raise ValueError(f"unknown provider {provider!r}")


def main() -> int:
    run_id = os.environ.get("CHECK_RUN_ID", "local")
    project = os.environ.get("GCP_PROJECT", "")
    optional = set(os.environ.get("OPTIONAL_MODELS", "").split())
    failed = 0
    for spec in os.environ.get("CHECK_MODELS", "").split():
        provider, _, model = spec.partition("/")
        started = time.monotonic()
        try:
            if not project:
                raise RuntimeError("GCP_PROJECT is not set")
            reply = call(provider, model, project)
            elapsed_ms = int((time.monotonic() - started) * 1000)
            print(f"MODEL_CHECK {run_id} OK {spec} {elapsed_ms}ms reply={reply[:20]!r}", flush=True)
        except Exception as exc:  # report every failure kind, per model
            text = " ".join(str(exc).split())[:300]
            status = "WARN" if spec in optional else "FAIL"
            if status == "FAIL":
                failed += 1
            print(
                f"MODEL_CHECK {run_id} {status} {spec} {type(exc).__name__}: {text} | hint: {hint(text)}",
                flush=True,
            )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
