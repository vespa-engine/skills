"""
Provider abstraction for running coding agents in eval mode.

Supports Claude Code CLI and OpenAI Codex CLI. The Provider base class
can be extended with additional providers in the future.

Usage:
    provider = get_provider()                        # default: claude
    provider = get_provider(provider_name="codex")   # OpenAI Codex
    result = provider.run_prompt("Create a schema...", work_dir=Path("/tmp/test"))

Configuration via environment variables:
    EVAL_PROVIDER  - Provider to use: "claude" (default) or "codex"
    EVAL_MODEL     - Model to use (e.g. "claude-sonnet-4-20250514", "gpt-5-codex")
    EVAL_TIMEOUT   - Timeout in seconds (default: 180)
    EVAL_MAX_TURNS - Max agent turns for Claude (default: 20)
    CLAUDE_CLI     - Path to claude binary (default: "claude")
    CODEX_CLI      - Path to codex binary (default: "codex")
"""

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunResult:
    """Result from a provider run."""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    output_files: list[str]


class Provider:
    """Base class for coding agent providers. Extend this to add new providers."""

    name: str = "base"

    def __init__(self, model: str = "", timeout: int = 180):
        self.model = model
        self.timeout = timeout

    def run_prompt(
        self,
        prompt: str,
        work_dir: Path,
        skill_content: str | None = None,
        timeout: int | None = None,
    ) -> RunResult:
        """
        Run a prompt through the coding agent.

        Args:
            prompt: The task prompt
            work_dir: Working directory for the agent
            skill_content: Optional skill SKILL.md content to inject into the prompt
            timeout: Override default timeout (seconds)
        """
        effective_timeout = timeout or self.timeout

        if skill_content:
            prompt = (
                f"You have access to the following skill for reference:\n\n"
                f"<skill>\n{skill_content}\n</skill>\n\n"
                f"Use the skill above to help with this task:\n\n{prompt}"
            )

        return self._run(prompt, work_dir, effective_timeout)

    def _run(self, prompt: str, work_dir: Path, timeout: int) -> RunResult:
        raise NotImplementedError

    def extract_usage(self, stdout: str) -> dict:
        """Extract token usage / cost info from provider output."""
        return {}

    def _collect_output_files(self, work_dir: Path) -> list[str]:
        """Collect files created in work_dir."""
        files = []
        for f in work_dir.rglob("*"):
            if f.is_file() and not f.is_symlink() and f.name not in (".DS_Store",):
                files.append(str(f.relative_to(work_dir)))
        return files


class ClaudeProvider(Provider):
    """Claude Code CLI provider."""

    name = "claude"

    def __init__(self, model: str = "", timeout: int = 180, max_turns: int = 20):
        super().__init__(model, timeout)
        self.cli = os.environ.get("CLAUDE_CLI", "claude")
        self.max_turns = max_turns

    def _run(self, prompt: str, work_dir: Path, timeout: int) -> RunResult:
        cmd = [
            self.cli,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--max-turns",
            str(self.max_turns),
            "--dangerously-skip-permissions",
        ]
        if self.model:
            cmd.extend(["--model", self.model])

        env = os.environ.copy()
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"

        start = time.time()
        try:
            result = subprocess.run(
                cmd,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=timeout + 30,
                env=env,
            )
            duration_ms = int((time.time() - start) * 1000)
            return RunResult(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_ms=duration_ms,
                output_files=self._collect_output_files(work_dir),
            )
        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start) * 1000)
            return RunResult(
                exit_code=124,
                stdout="",
                stderr=f"Timeout after {timeout}s",
                duration_ms=duration_ms,
                output_files=[],
            )

    def extract_usage(self, stdout: str) -> dict:
        try:
            data = json.loads(stdout)
            usage = {}
            if isinstance(data, dict):
                if "usage" in data:
                    usage = dict(data["usage"])
                if "total_cost_usd" in data:
                    usage["cost_usd"] = data["total_cost_usd"]
                if "num_turns" in data:
                    usage["num_turns"] = data["num_turns"]
                # Total input = fresh + cache-write + cache-read. Individual fields
                # are billed at different rates; total_input_tokens is a volume metric.
                input_parts = [
                    usage.get("input_tokens", 0) or 0,
                    usage.get("cache_creation_input_tokens", 0) or 0,
                    usage.get("cache_read_input_tokens", 0) or 0,
                ]
                if any(input_parts):
                    usage["total_input_tokens"] = sum(input_parts)
            return usage
        except (json.JSONDecodeError, TypeError):
            return {}


class CodexProvider(Provider):
    """OpenAI Codex CLI provider.

    Shells out to `codex exec --json` and parses the JSONL event stream
    for token usage. The agent runs with sandboxing/approvals bypassed
    inside the per-eval `work_dir`, mirroring the Claude provider's
    `--dangerously-skip-permissions` behaviour.
    """

    name = "codex"

    def __init__(self, model: str = "", timeout: int = 180):
        super().__init__(model, timeout)
        self.cli = os.environ.get("CODEX_CLI", "codex")

    def _run(self, prompt: str, work_dir: Path, timeout: int) -> RunResult:
        # `codex exec` is the non-interactive subcommand — it does not prompt
        # for approvals, so --sandbox workspace-write is sufficient without
        # the broader --dangerously-bypass-approvals-and-sandbox.
        cmd = [
            self.cli,
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "-C",
            str(work_dir),
        ]
        if self.model:
            cmd.extend(["-m", self.model])
        cmd.append(prompt)

        env = os.environ.copy()

        start = time.time()
        try:
            result = subprocess.run(
                cmd,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                # stdin piped to /dev/null: otherwise codex treats an attached
                # stdin as additional prompt input and appends a <stdin> block.
                stdin=subprocess.DEVNULL,
                timeout=timeout + 30,
                env=env,
            )
            duration_ms = int((time.time() - start) * 1000)
            return RunResult(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_ms=duration_ms,
                output_files=self._collect_output_files(work_dir),
            )
        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start) * 1000)
            return RunResult(
                exit_code=124,
                stdout="",
                stderr=f"Timeout after {timeout}s",
                duration_ms=duration_ms,
                output_files=[],
            )

    def extract_usage(self, stdout: str) -> dict:
        """Parse codex `--json` stdout for token usage.

        Codex emits flat JSONL events. The final event of each turn is
        `turn.completed`, which carries a `usage` sub-object:
            {"type":"turn.completed","usage":{"input_tokens":N,
             "cached_input_tokens":N,"output_tokens":N,
             "reasoning_output_tokens":N}}
        `total_tokens` is not currently emitted on stdout (see
        openai/codex#5276) — we derive it as input + output.
        """
        usage: dict = {}
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(evt, dict) or evt.get("type") != "turn.completed":
                continue
            turn_usage = evt.get("usage")
            if not isinstance(turn_usage, dict):
                continue
            for key in (
                "input_tokens",
                "cached_input_tokens",
                "output_tokens",
                "reasoning_output_tokens",
            ):
                if key in turn_usage:
                    usage[key] = turn_usage[key]

        # Normalize to the field names ClaudeProvider exposes so aggregate.py
        # can treat both providers uniformly.
        if "cached_input_tokens" in usage:
            usage["cache_read_input_tokens"] = usage["cached_input_tokens"]
        if "input_tokens" in usage:
            usage["total_input_tokens"] = usage["input_tokens"]
            usage["total_tokens"] = usage["input_tokens"] + usage.get("output_tokens", 0)
        return usage


def get_provider(
    model: str | None = None,
    timeout: int | None = None,
    provider_name: str | None = None,
) -> Provider:
    """
    Create a coding-agent provider instance.

    Args:
        model: Model override. Default: EVAL_MODEL env var.
        timeout: Timeout in seconds. Default: EVAL_TIMEOUT env var or 180.
        provider_name: "claude" or "codex". Default: EVAL_PROVIDER env var or "claude".
    """
    name = (provider_name or os.environ.get("EVAL_PROVIDER") or "claude").lower()
    eff_model = model or os.environ.get("EVAL_MODEL", "")
    eff_timeout = timeout or int(os.environ.get("EVAL_TIMEOUT", "180"))

    if name == "codex":
        return CodexProvider(model=eff_model, timeout=eff_timeout)
    if name == "claude":
        return ClaudeProvider(
            model=eff_model,
            timeout=eff_timeout,
            max_turns=int(os.environ.get("EVAL_MAX_TURNS", "20")),
        )
    raise ValueError(f"Unknown provider: {name!r} (expected 'claude' or 'codex')")
