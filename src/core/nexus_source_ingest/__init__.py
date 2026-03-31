"""
Nexus Source Ingest — Feature 4: Multi-Format Content Ingestion Pipeline
Source: Repo #7 (content-core multi-engine), Repo #5 (source types), Repo #1 (VLM)

Handles: PDF, web, YouTube, audio, image, text extraction and transformation.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from loguru import logger

from src.infra.nexus_obs_tracing import traced
from src.exceptions import (
    SourceProcessingError,
    EmptyContentError,
    UnsupportedFormatError,
    FileTooLargeError,
)


# ── Content Extractors ───────────────────────────────────────

class ContentExtractor:
    """
    Multi-engine content extraction.
    Source: Repo #7 uses auto/readability/jina/firecrawl engines.
    """

    @traced("source.extract.pdf")
    async def extract_pdf(self, file_path: str) -> str:
        """Extract text from PDF."""
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            content = "\n\n".join(text_parts)
            if not content.strip():
                raise EmptyContentError("PDF contains no extractable text (may need OCR)")
            return content
        except EmptyContentError:
            raise
        except Exception as e:
            raise SourceProcessingError(f"PDF extraction failed: {e}", original_error=e)

    @traced("source.extract.url")
    async def extract_url(self, url: str) -> str:
        """Extract text from a web URL."""
        import httpx
        from bs4 import BeautifulSoup

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; NexusBot/1.0)"
                })
                response.raise_for_status()

            # Check content size
            if len(response.content) > 50 * 1024 * 1024:  # 50MB limit
                raise FileTooLargeError("Web page content too large")

            soup = BeautifulSoup(response.text, "html.parser")

            # Remove script and style elements
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()

            text = soup.get_text(separator="\n", strip=True)

            if not text.strip():
                raise EmptyContentError("Web page contains no extractable text")

            return text

        except (EmptyContentError, FileTooLargeError):
            raise
        except Exception as e:
            raise SourceProcessingError(f"URL extraction failed: {e}", original_error=e)

    @traced("source.extract.text")
    async def extract_text(self, content: str) -> str:
        """Pass-through for pasted text."""
        if not content.strip():
            raise EmptyContentError("Empty text content provided")
        return content

    @traced("source.extract.youtube")
    async def extract_youtube(self, url: str) -> str:
        """Extract transcript from YouTube video."""
        try:
            # Try youtube-transcript-api
            from youtube_transcript_api import YouTubeTranscriptApi

            # Extract video ID from URL
            parsed = urlparse(url)
            video_id = ""
            if "youtube.com" in parsed.hostname or "":
                from urllib.parse import parse_qs
                video_id = parse_qs(parsed.query).get("v", [""])[0]
            elif "youtu.be" in (parsed.hostname or ""):
                video_id = parsed.path.strip("/")

            if not video_id:
                raise SourceProcessingError("Could not extract YouTube video ID")

            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            transcript = " ".join(entry["text"] for entry in transcript_list)
            return transcript

        except Exception as e:
            raise SourceProcessingError(f"YouTube extraction failed: {e}", original_error=e)

    async def extract(self, source_type: str, **kwargs: Any) -> str:
        """Route to the appropriate extractor."""
        extractors = {
            "pdf": lambda: self.extract_pdf(kwargs.get("file_path", "")),
            "url": lambda: self.extract_url(kwargs.get("url", "")),
            "youtube": lambda: self.extract_youtube(kwargs.get("url", "")),
            "text": lambda: self.extract_text(kwargs.get("content", "")),
            "pasted_text": lambda: self.extract_text(kwargs.get("content", "")),
            "markdown": lambda: self.extract_text(kwargs.get("content", "")),
        }

        extractor = extractors.get(source_type)
        if not extractor:
            raise UnsupportedFormatError(f"Unsupported source type: {source_type}")

        return await extractor()


# ── Source Processing Pipeline ───────────────────────────────

class SourceProcessor:
    """
    Orchestrates the full source ingestion pipeline.
    Source: Repo #7, graphs/source.py — StateGraph pipeline
    """

    def __init__(self) -> None:
        self.extractor = ContentExtractor()

    @traced("source.process")
    async def process_source(
        self,
        source_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        """
        Full source processing pipeline:
        1. Extract content from source
        2. Update source record with content
        3. Generate embeddings (async)
        4. Generate insights (async)
        """
        from src.infra.nexus_data_persist import sources_repo, get_session
        from sqlalchemy import text
        from datetime import datetime, timezone

        # 1. Get source record
        source = await sources_repo.get_by_id(source_id, tenant_id)
        if not source:
            raise SourceProcessingError(f"Source {source_id} not found")

        # Update status
        await sources_repo.update(source_id, {
            "status": "processing",
            "processing_started_at": datetime.now(timezone.utc),
        }, tenant_id)

        try:
            # 2. Extract content
            content = await self.extractor.extract(
                source["source_type"],
                file_path=source.get("asset_file_path", ""),
                url=source.get("asset_url", ""),
                content=source.get("full_text", ""),
            )

            # 3. Calculate metadata
            word_count = len(content.split())
            topics = await self._extract_topics(content, tenant_id)

            # 4. Update source with extracted content
            await sources_repo.update(source_id, {
                "status": "ready",
                "full_text": content,
                "word_count": word_count,
                "topics": topics,
                "processing_completed_at": datetime.now(timezone.utc),
            }, tenant_id)

            logger.info(
                f"Source processed successfully",
                source_id=source_id,
                word_count=word_count,
                topics=len(topics),
            )

            return {
                "source_id": source_id,
                "status": "ready",
                "word_count": word_count,
                "topics": topics,
            }

        except Exception as e:
            await sources_repo.update(source_id, {
                "status": "error",
                "processing_error": str(e)[:500],
            }, tenant_id)
            raise

    async def _extract_topics(self, content: str, tenant_id: str) -> list[str]:
        """Extract topics from content using LLM."""
        try:
            from src.agents.nexus_model_layer import model_manager
            import json

            llm = await model_manager.provision_llm(task_type="transformation", tenant_id=tenant_id)
            response = await llm.generate(
                [{"role": "system", "content": f"Extract 3-7 key topics from this text. Return as JSON array of strings.\n\nText:\n{content[:5000]}"}],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.content)
            return result.get("topics", result) if isinstance(result, dict) else result
        except Exception:
            return []


# Global singleton
source_processor = SourceProcessor()
