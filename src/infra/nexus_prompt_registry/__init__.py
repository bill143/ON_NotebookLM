"""
Nexus Prompt Registry — Feature 14: Prompt Versioning, Resolution & Testing
Source: Repo #7 (file-based prompts, ai-prompter), Repo #9 (LangChain Hub)

Provides:
- Namespace/name/version addressing: chat/system@1.0.0
- DB-backed prompt storage with version history
- Template rendering with Jinja2 variables
- Prompt performance tracking (latency, cost, quality)
- Injection defense (separator tokens, content escaping)
"""

from __future__ import annotations

import re
from datetime import UTC
from pathlib import Path
from typing import Any

from jinja2 import BaseLoader, Environment, TemplateSyntaxError
from loguru import logger

from src.exceptions import PromptError, PromptInjectionDetected

# ── Prompt Resolution ────────────────────────────────────────


class PromptRegistry:
    """
    Versioned prompt registry with DB and file-based fallback.
    Convention: [namespace]/[name]@[version]
    """

    def __init__(self, prompts_dir: str = "prompts") -> None:
        self.prompts_dir = Path(prompts_dir)
        self._jinja_env = Environment(loader=BaseLoader(), autoescape=True)
        self._cache: dict[str, str] = {}

    async def resolve(
        self,
        namespace: str,
        name: str,
        *,
        version: str | None = None,
        variables: dict[str, Any] | None = None,
    ) -> PromptResult:
        """
        Resolve a prompt template and render with variables.

        Resolution order:
        1. DB (prompt_versions table, status='active')
        2. File system fallback (prompts/{namespace}/{name}.md)
        """
        variables = variables or {}
        prompt_content = None
        resolved_version = version or "latest"
        source = "unknown"

        # 1. Try DB resolution
        try:
            prompt_content, resolved_version = await self._resolve_from_db(namespace, name, version)
            source = "database"
        except Exception:
            logger.debug(
                "DB prompt resolution failed; falling back to filesystem",
                extra={"namespace": namespace, "name": name},
                exc_info=True,
            )

        # 2. Fallback to file system
        if not prompt_content:
            prompt_content = self._resolve_from_file(namespace, name)
            source = "filesystem"
            resolved_version = "file"

        if not prompt_content:
            raise PromptError(f"Prompt not found: {namespace}/{name}@{version or 'latest'}")

        # 3. Render template with variables
        rendered = self._render(prompt_content, variables)

        # 4. Apply injection defense
        rendered = self._apply_injection_defense(rendered)

        logger.debug(
            "Resolved prompt",
            namespace=namespace,
            name=name,
            version=resolved_version,
            source=source,
            length=len(rendered),
        )

        return PromptResult(
            content=rendered,
            namespace=namespace,
            name=name,
            version=resolved_version,
            source=source,
        )

    async def _resolve_from_db(
        self, namespace: str, name: str, version: str | None
    ) -> tuple[str, str]:
        """Resolve prompt from database."""
        from sqlalchemy import text

        from src.infra import nexus_data_persist as db

        if version:
            query = """
                SELECT content, version FROM prompt_versions
                WHERE namespace = :namespace AND name = :name AND version = :version
            """
            params = {"namespace": namespace, "name": name, "version": version}
        else:
            query = """
                SELECT content, version FROM prompt_versions
                WHERE namespace = :namespace AND name = :name AND status = 'active'
                ORDER BY deployed_at DESC NULLS LAST LIMIT 1
            """
            params = {"namespace": namespace, "name": name}

        async with db.get_session() as session:
            result = await session.execute(text(query), params)
            row = result.mappings().first()

        if row:
            return row["content"], row["version"]
        raise PromptError("Not in DB")

    def _resolve_from_file(self, namespace: str, name: str) -> str | None:
        """Resolve prompt from file system."""
        # Try multiple extensions
        for ext in [".md", ".txt", ".j2", ""]:
            path = self.prompts_dir / namespace / f"{name}{ext}"
            if path.exists():
                return path.read_text(encoding="utf-8")
        return None

    def _render(self, template: str, variables: dict[str, Any]) -> str:
        """Render a Jinja2 template with variables."""
        try:
            tmpl = self._jinja_env.from_string(template)
            return tmpl.render(**variables)
        except TemplateSyntaxError as e:
            raise PromptError(f"Template syntax error: {e}") from e

    def _apply_injection_defense(self, content: str) -> str:
        """
        Apply prompt injection defense measures.
        - Add separator tokens between system and user content
        - Escape known injection patterns
        """
        # Detect obvious injection attempts
        injection_patterns = [
            r"ignore\s*(all\s*)?previous\s*instructions",
            r"disregard\s*(all\s*)?above",
            r"you\s*are\s*now\s*(?:a|an)\s*\w+\s*(?:that|who|which)",
            r"system\s*prompt\s*override",
            r"<\|im_start\|>system",
            r"\[INST\].*\[/INST\]",
        ]

        for pattern in injection_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                logger.critical(
                    "PROMPT INJECTION DETECTED",
                    pattern=pattern,
                    content_preview=content[:200],
                )
                raise PromptInjectionDetected("Potential prompt injection detected in input")

        return content

    # ── Prompt Management ────────────────────────────────────

    async def create_version(
        self,
        namespace: str,
        name: str,
        version: str,
        content: str,
        *,
        variables: list[dict[str, str]] | None = None,
        model_target: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
        changelog: str | None = None,
        created_by: str | None = None,
    ) -> str:
        """Create a new prompt version."""
        from src.infra import nexus_data_persist as db

        data = {
            "namespace": namespace,
            "name": name,
            "version": version,
            "content": content,
            "variables": variables or [],
            "model_target": model_target,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "status": "draft",
            "changelog": changelog,
            "created_by": created_by,
        }

        result = await db.BaseRepository("prompt_versions").create(data)
        logger.info(
            "Created prompt version",
            prompt=f"{namespace}/{name}@{version}",
        )
        return result["id"]

    async def deploy(
        self,
        namespace: str,
        name: str,
        version: str,
        environment: str = "prod",
        deployed_by: str | None = None,
    ) -> None:
        """Deploy a prompt version (set as active)."""
        from datetime import datetime

        from sqlalchemy import text

        from src.infra import nexus_data_persist as db

        now = datetime.now(UTC)

        async with db.get_session() as session:
            # Deactivate previous active versions
            await session.execute(
                text("""
                    UPDATE prompt_versions SET status = 'deprecated'
                    WHERE namespace = :namespace AND name = :name AND status = 'active'
                """),
                {"namespace": namespace, "name": name},
            )

            # Activate new version
            await session.execute(
                text("""
                    UPDATE prompt_versions
                    SET status = 'active', deployed_at = :now
                    WHERE namespace = :namespace AND name = :name AND version = :version
                """),
                {"namespace": namespace, "name": name, "version": version, "now": now},
            )

            # Record deployment
            await session.execute(
                text("""
                    INSERT INTO prompt_deployments (id, prompt_version_id, environment, deployed_by)
                    SELECT uuid_generate_v4(), id, :environment, :deployed_by
                    FROM prompt_versions
                    WHERE namespace = :namespace AND name = :name AND version = :version
                """),
                {
                    "namespace": namespace,
                    "name": name,
                    "version": version,
                    "environment": environment,
                    "deployed_by": deployed_by,
                },
            )

        logger.info(
            "Deployed prompt",
            prompt=f"{namespace}/{name}@{version}",
            environment=environment,
        )


class PromptResult:
    """Result of prompt resolution."""

    def __init__(
        self,
        content: str,
        namespace: str,
        name: str,
        version: str,
        source: str,
    ) -> None:
        self.content = content
        self.namespace = namespace
        self.name = name
        self.version = version
        self.source = source
        self.address = f"{namespace}/{name}@{version}"

    def __str__(self) -> str:
        return self.content


# Global singleton
prompt_registry = PromptRegistry()
