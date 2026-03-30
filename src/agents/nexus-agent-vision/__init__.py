"""
Nexus Vision Agent — Image & Diagram Analysis with Vision LLMs
Codename: ESPERANTO — Feature 4C: Visual Understanding

Provides:
- Image analysis and description via vision-capable LLMs
- PDF image extraction with page-level visual analysis
- Diagram/chart interpretation with structured data extraction
- OCR fallback for scanned documents
- Batch image processing for multi-page documents
"""

from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from src.infra.nexus_obs_tracing import traced
from src.infra.nexus_cost_tracker import cost_tracker, UsageRecord
from src.exceptions import AIProviderError, ValidationError


# ── Types ────────────────────────────────────────────────────

@dataclass
class ImageInput:
    """An image to be analyzed."""
    source: str                     # "file", "url", "base64", "pdf_page"
    data: str | bytes               # File path, URL, base64 string, or raw bytes
    mime_type: str = "image/png"
    page_number: Optional[int] = None
    description_hint: str = ""      # Optional hint for analysis focus


@dataclass
class VisionResult:
    """Result from analyzing a single image."""
    description: str
    diagram_type: Optional[str] = None     # "flowchart", "table", "chart", "photo", etc.
    extracted_text: str = ""                # OCR / text from image
    structured_data: dict[str, Any] = field(default_factory=dict)
    key_entities: list[str] = field(default_factory=list)
    confidence: float = 0.0
    model_used: str = ""
    tokens_used: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "diagram_type": self.diagram_type,
            "extracted_text": self.extracted_text,
            "structured_data": self.structured_data,
            "key_entities": self.key_entities,
            "confidence": self.confidence,
            "model_used": self.model_used,
        }


@dataclass
class DocumentVisionResult:
    """Result from analyzing an entire document's visuals."""
    pages: list[VisionResult] = field(default_factory=list)
    summary: str = ""
    total_images: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0


# ── Image Preparation ───────────────────────────────────────

class ImageEncoder:
    """Converts image inputs to base64 for API consumption."""

    SUPPORTED_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
    MAX_IMAGE_SIZE_MB = 20

    @staticmethod
    def to_base64_url(image: ImageInput) -> str:
        """Convert ImageInput to a base64 data URL for vision API."""

        if image.source == "base64":
            data = image.data if isinstance(image.data, str) else image.data.decode()
            return f"data:{image.mime_type};base64,{data}"

        elif image.source == "url":
            return str(image.data)

        elif image.source == "file":
            path = Path(str(image.data))
            if not path.exists():
                raise ValidationError(f"Image file not found: {path}")

            size_mb = path.stat().st_size / (1024 * 1024)
            if size_mb > ImageEncoder.MAX_IMAGE_SIZE_MB:
                raise ValidationError(
                    f"Image too large: {size_mb:.1f}MB (max {ImageEncoder.MAX_IMAGE_SIZE_MB}MB)"
                )

            data_bytes = path.read_bytes()
            b64 = base64.b64encode(data_bytes).decode("utf-8")

            # Detect mime type from extension
            suffix = path.suffix.lower()
            mime_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            mime = mime_map.get(suffix, image.mime_type)
            return f"data:{mime};base64,{b64}"

        elif image.source == "pdf_page":
            # Raw bytes from PDF extraction
            data_bytes = image.data if isinstance(image.data, bytes) else base64.b64decode(image.data)
            b64 = base64.b64encode(data_bytes).decode("utf-8")
            return f"data:{image.mime_type};base64,{b64}"

        else:
            raise ValidationError(f"Unsupported image source: {image.source}")

    @staticmethod
    def extract_pdf_images(pdf_path: str, max_pages: int = 20) -> list[ImageInput]:
        """Extract images from a PDF as individual ImageInputs."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            logger.warning("PyMuPDF not installed — can't extract PDF images")
            return []

        images: list[ImageInput] = []
        doc = fitz.open(pdf_path)

        for page_idx in range(min(len(doc), max_pages)):
            page = doc[page_idx]

            # Get page images
            image_list = page.get_images(full=True)

            for img_idx, img_info in enumerate(image_list):
                xref = img_info[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n > 4:  # CMYK → RGB
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    img_bytes = pix.tobytes("png")

                    images.append(ImageInput(
                        source="pdf_page",
                        data=img_bytes,
                        mime_type="image/png",
                        page_number=page_idx + 1,
                        description_hint=f"Image from page {page_idx + 1}",
                    ))
                except Exception as e:
                    logger.debug(f"Skipping PDF image (page {page_idx + 1}): {e}")

            # If no embedded images, render the page itself
            if not image_list:
                try:
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x resolution
                    img_bytes = pix.tobytes("png")
                    images.append(ImageInput(
                        source="pdf_page",
                        data=img_bytes,
                        mime_type="image/png",
                        page_number=page_idx + 1,
                        description_hint=f"Page {page_idx + 1} render",
                    ))
                except Exception as e:
                    logger.debug(f"Skipping page render {page_idx + 1}: {e}")

        doc.close()
        return images


# ── Vision Analysis Engine ───────────────────────────────────

class VisionAgent:
    """
    Analyzes images using vision-capable LLMs.
    Supports single image, batch, and full document analysis.
    """

    ANALYSIS_PROMPT = """Analyze this image thoroughly. Provide:

1. **Description**: A detailed description of what the image shows.
2. **Diagram Type**: If it's a diagram, classify it (flowchart, table, chart, graph, architecture, screenshot, photo, text_document, other).
3. **Extracted Text**: Any text visible in the image (OCR).
4. **Structured Data**: If the image contains structured information (table, chart data), extract it.
5. **Key Entities**: Names, labels, or key terms found in the image.
6. **Confidence**: Your confidence in the analysis (0.0-1.0).

{focus_hint}

Respond as JSON with keys: description, diagram_type, extracted_text, structured_data, key_entities, confidence"""

    TABLE_PROMPT = """Extract the table data from this image.
Return as JSON with:
- headers: array of column headers
- rows: array of arrays representing each row
- notes: any footnotes or annotations"""

    CHART_PROMPT = """Extract data from this chart/graph.
Return as JSON with:
- chart_type: "bar", "line", "pie", "scatter", etc.
- title: chart title if visible
- x_axis: x-axis label
- y_axis: y-axis label
- data_points: array of {label, value} objects
- trends: notable trends or observations"""

    @traced("vision.analyze_image")
    async def analyze_image(
        self,
        image: ImageInput,
        *,
        tenant_id: str = "",
        user_id: str = "",
        analysis_type: str = "general",
    ) -> VisionResult:
        """Analyze a single image using a vision LLM."""
        from src.agents.nexus_model_layer import model_manager

        # Prepare the image URL
        encoder = ImageEncoder()
        image_url = encoder.to_base64_url(image)

        # Choose prompt based on analysis type
        if analysis_type == "table":
            prompt_text = self.TABLE_PROMPT
        elif analysis_type == "chart":
            prompt_text = self.CHART_PROMPT
        else:
            focus = f"Focus: {image.description_hint}" if image.description_hint else ""
            prompt_text = self.ANALYSIS_PROMPT.format(focus_hint=focus)

        # Build vision message (OpenAI-compatible format)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url,
                            "detail": "high",
                        },
                    },
                ],
            }
        ]

        # Get vision model
        llm = await model_manager.provision_llm(
            task_type="vision",
            tenant_id=tenant_id,
        )

        try:
            response = await llm.generate(
                messages,
                temperature=0.2,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )

            result_data = json.loads(response.content)

            # Record usage
            await cost_tracker.record_usage(UsageRecord(
                tenant_id=tenant_id,
                user_id=user_id,
                model_name=response.model,
                provider="",
                feature_id="4C",
                agent_id="vision_agent",
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_usd=response.cost_usd,
            ))

            return VisionResult(
                description=result_data.get("description", ""),
                diagram_type=result_data.get("diagram_type"),
                extracted_text=result_data.get("extracted_text", ""),
                structured_data=result_data.get("structured_data", {}),
                key_entities=result_data.get("key_entities", []),
                confidence=float(result_data.get("confidence", 0.5)),
                model_used=response.model,
                tokens_used=response.output_tokens,
            )

        except json.JSONDecodeError:
            # Fallback: use raw response as description
            return VisionResult(
                description=response.content,
                model_used=response.model,
                tokens_used=response.output_tokens,
                confidence=0.3,
            )
        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            raise AIProviderError(f"Vision analysis failed: {e}")

    @traced("vision.analyze_batch")
    async def analyze_batch(
        self,
        images: list[ImageInput],
        *,
        tenant_id: str = "",
        user_id: str = "",
        concurrency: int = 3,
    ) -> list[VisionResult]:
        """Analyze multiple images with concurrency control."""
        import asyncio

        semaphore = asyncio.Semaphore(concurrency)
        results: list[VisionResult] = []

        async def process_one(img: ImageInput) -> VisionResult:
            async with semaphore:
                return await self.analyze_image(
                    img, tenant_id=tenant_id, user_id=user_id
                )

        tasks = [process_one(img) for img in images]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final: list[VisionResult] = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning(f"Batch vision item failed: {r}")
                final.append(VisionResult(
                    description=f"Analysis failed: {str(r)[:100]}",
                    confidence=0.0,
                ))
            else:
                final.append(r)

        return final

    @traced("vision.analyze_document")
    async def analyze_document(
        self,
        pdf_path: str,
        *,
        tenant_id: str = "",
        user_id: str = "",
        max_pages: int = 20,
    ) -> DocumentVisionResult:
        """
        Analyze an entire document's visual content.
        Extracts images from PDF and analyzes each.
        """
        encoder = ImageEncoder()
        images = encoder.extract_pdf_images(pdf_path, max_pages=max_pages)

        if not images:
            return DocumentVisionResult(summary="No images found in document")

        logger.info(f"Analyzing {len(images)} images from {pdf_path}")
        page_results = await self.analyze_batch(
            images, tenant_id=tenant_id, user_id=user_id
        )

        # Generate document-level summary
        total_tokens = sum(r.tokens_used for r in page_results)
        descriptions = [
            f"Page {images[i].page_number}: {r.description[:200]}"
            for i, r in enumerate(page_results)
            if r.confidence > 0.2
        ]

        from src.agents.nexus_model_layer import model_manager
        llm = await model_manager.provision_llm(
            task_type="transformation",
            tenant_id=tenant_id,
        )

        summary_response = await llm.generate(
            [
                {
                    "role": "system",
                    "content": "Summarize the visual content of this document based on individual page analyses.",
                },
                {
                    "role": "user",
                    "content": "\n\n".join(descriptions),
                },
            ],
            temperature=0.3,
            max_tokens=500,
        )

        return DocumentVisionResult(
            pages=page_results,
            summary=summary_response.content,
            total_images=len(images),
            total_tokens=total_tokens + summary_response.output_tokens,
        )

    @traced("vision.extract_table")
    async def extract_table(
        self,
        image: ImageInput,
        *,
        tenant_id: str = "",
        user_id: str = "",
    ) -> dict[str, Any]:
        """Specialized table extraction from an image."""
        result = await self.analyze_image(
            image, tenant_id=tenant_id, user_id=user_id, analysis_type="table"
        )
        return result.structured_data

    @traced("vision.extract_chart")
    async def extract_chart(
        self,
        image: ImageInput,
        *,
        tenant_id: str = "",
        user_id: str = "",
    ) -> dict[str, Any]:
        """Specialized chart data extraction from an image."""
        result = await self.analyze_image(
            image, tenant_id=tenant_id, user_id=user_id, analysis_type="chart"
        )
        return result.structured_data


# Global singleton
vision_agent = VisionAgent()
