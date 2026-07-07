"""Shared LLM CLI helper for stream scripts.

All stream scripts that need LLM completions shell out to a local LLM CLI.
This module provides a single ``call_llm`` function that supports any CLI
via the ``LLM_COMMAND`` env var.

Default behavior (no env vars set): uses ``hermes chat -q`` with
``LLM_PROVIDER`` / ``LLM_MODEL`` / ``LLM_MODEL_PRO`` for model selection.

To use a different CLI (e.g. ``llm``, ``aichat``, ``ollama``)::

    export LLM_COMMAND="llm -m"        # space-separated command prefix
    # The prompt is appended as the last positional argument.

    # Or for CLIs that need the prompt on stdin:
    export LLM_COMMAND="cat | ollama run llama3"
    export LLM_STDIN=1
"""

from __future__ import annotations

import os
import shlex
import subprocess


def call_llm(
    prompt: str,
    *,
    timeout: int = 180,
    provider: str | None = None,
    model: str | None = None,
) -> str:
    """Call an LLM CLI and return its stdout.

    Args:
        prompt: The prompt text to send.
        timeout: Seconds before killing the process.
        provider: Override LLM_PROVIDER env var.
        model: Override LLM_MODEL env var.

    Returns:
        The CLI's stdout, with leading ``session_id:`` lines stripped
        (a quirk of the default CLI's ``--quiet`` output).

    Raises:
        subprocess.CalledProcessError: If the CLI exits non-zero.
        subprocess.TimeoutExpired: If the CLI exceeds ``timeout``.
    """
    custom_cmd = os.environ.get("LLM_COMMAND", "").strip()
    use_stdin = os.environ.get("LLM_STDIN", "").strip() in ("1", "true", "yes")

    if custom_cmd:
        # Custom CLI mode — prompt is appended as last arg or piped to stdin
        cmd = shlex.split(custom_cmd)
        if model:
            cmd.extend(["--model", model])
        if use_stdin:
            r = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )
        else:
            cmd.append(prompt)
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True,
            )
        return r.stdout.strip()

    # Default mode: hermes chat -q
    prov = provider or os.environ.get("LLM_PROVIDER", "nous")
    mdl = model or os.environ.get("LLM_MODEL", "xiaomi/mimo-v2.5")

    cmd = [
        "hermes",
        "chat",
        "-q",
        prompt,
        "--quiet",
        "--ignore-rules",
        "--ignore-user-config",
        "--max-turns",
        "1",
        "--source",
        "tool",
        "--provider",
        prov,
        "--model",
        mdl,
    ]
    r = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
    out = r.stdout
    lines = [line for line in out.split("\n") if not line.startswith("session_id:")]
    return "\n".join(lines).strip()


def call_llm_pro(
    prompt: str,
    *,
    timeout: int = 600,
) -> str:
    """Call the 'pro' (stronger) LLM model for synthesis/recommendations.

    Uses ``LLM_MODEL_PRO`` env var for model selection.
    Falls back to the base model if not set.
    """
    return call_llm(
        prompt,
        timeout=timeout,
        model=os.environ.get(
            "LLM_MODEL_PRO", os.environ.get("LLM_MODEL", "xiaomi/mimo-v2.5-pro")
        ),
    )
