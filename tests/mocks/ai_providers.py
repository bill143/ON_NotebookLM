"""Shared mock factory for all external AI provider SDKs and export libraries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

# ── OpenAI response shapes ───────────────────────────────────


@dataclass
class _Usage:
    prompt_tokens: int = 50
    completion_tokens: int = 120
    total_tokens: int = 170
    cached_tokens: int = 0


@dataclass
class _Message:
    content: str = "This is a mock AI response."
    role: str = "assistant"
    tool_calls: list[Any] = field(default_factory=list)


@dataclass
class _Choice:
    message: _Message = field(default_factory=_Message)
    finish_reason: str = "stop"
    index: int = 0


@dataclass
class _ChatCompletion:
    choices: list[_Choice] = field(default_factory=lambda: [_Choice()])
    usage: _Usage = field(default_factory=_Usage)
    model: str = "gpt-4o"
    id: str = "chatcmpl-mock"


@dataclass
class _EmbeddingItem:
    embedding: list[float] = field(default_factory=lambda: [0.01] * 1536)
    index: int = 0


@dataclass
class _EmbeddingUsage:
    total_tokens: int = 10


@dataclass
class _EmbeddingResponse:
    data: list[_EmbeddingItem] = field(default_factory=lambda: [_EmbeddingItem()])
    usage: _EmbeddingUsage = field(default_factory=_EmbeddingUsage)
    model: str = "text-embedding-3-small"


@dataclass
class _TTSResponse:
    content: bytes = b"\xff\xfb\x90\x00" * 100


@dataclass
class _StreamDelta:
    content: str | None = "chunk"


@dataclass
class _StreamChoice:
    delta: _StreamDelta = field(default_factory=_StreamDelta)
    index: int = 0


@dataclass
class _StreamChunk:
    choices: list[_StreamChoice] = field(default_factory=lambda: [_StreamChoice()])


class MockOpenAIClient:
    """Mocks openai.AsyncOpenAI with chat, embeddings, and audio."""

    def __init__(self) -> None:
        self.chat = MagicMock()
        self.chat.completions = MagicMock()
        self.chat.completions.create = AsyncMock(return_value=_ChatCompletion())
        self.embeddings = MagicMock()
        self.embeddings.create = AsyncMock(return_value=_EmbeddingResponse())
        self.audio = MagicMock()
        self.audio.speech = MagicMock()
        self.audio.speech.create = AsyncMock(return_value=_TTSResponse())

    def enable_streaming(self, chunks: int = 3) -> None:
        """Configure chat.completions.create to return an async iterable."""

        async def _stream(**kwargs: Any) -> Any:
            for _ in range(chunks):
                yield _StreamChunk()

        self.chat.completions.create = AsyncMock(side_effect=_stream)


# ── Anthropic response shapes ────────────────────────────────


@dataclass
class _AnthropicUsage:
    input_tokens: int = 40
    output_tokens: int = 100


@dataclass
class _AnthropicTextBlock:
    text: str = "Mock Anthropic response."
    type: str = "text"


@dataclass
class _AnthropicMessage:
    content: list[_AnthropicTextBlock] = field(default_factory=lambda: [_AnthropicTextBlock()])
    usage: _AnthropicUsage = field(default_factory=_AnthropicUsage)
    stop_reason: str = "end_turn"
    model: str = "claude-3-5-sonnet"
    id: str = "msg-mock"


class MockAnthropicClient:
    """Mocks anthropic.AsyncAnthropic."""

    def __init__(self) -> None:
        self.messages = MagicMock()
        self.messages.create = AsyncMock(return_value=_AnthropicMessage())
        self.messages.stream = MagicMock()


# ── Google GenAI response shapes ─────────────────────────────


@dataclass
class _GeminiUsage:
    prompt_token_count: int = 30
    candidates_token_count: int = 80


@dataclass
class _GeminiResponse:
    text: str = "Mock Gemini response."
    usage_metadata: _GeminiUsage = field(default_factory=_GeminiUsage)


class _MockAsyncModels:
    generate_content = AsyncMock(return_value=_GeminiResponse())
    generate_content_stream = AsyncMock(return_value=iter([]))


class _MockAioModels:
    models = _MockAsyncModels()


class MockGoogleGenAI:
    """Mocks google.genai.Client."""

    def __init__(self) -> None:
        self.aio = _MockAioModels()

    def Client(self, **kwargs: Any) -> MockGoogleGenAI:  # noqa: N802
        return self


# ── ReportLab mock ────────────────────────────────────────────


class MockReportLabCanvas:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.pages: list[str] = []

    def drawString(self, x: float, y: float, text: str) -> None:  # noqa: N802
        self.pages.append(text)

    def showPage(self) -> None:  # noqa: N802
        pass

    def save(self) -> None:
        pass


class MockReportLab:
    Canvas = MockReportLabCanvas


# ── python-docx mock ─────────────────────────────────────────


class MockDocxParagraph:
    def __init__(self, text: str = "") -> None:
        self.text = text


class MockDocxDocument:
    def __init__(self) -> None:
        self.paragraphs: list[MockDocxParagraph] = []
        self.tables: list[Any] = []

    def add_heading(self, text: str, level: int = 1) -> None:
        self.paragraphs.append(MockDocxParagraph(text))

    def add_paragraph(self, text: str = "", style: str | None = None) -> MockDocxParagraph:
        p = MockDocxParagraph(text)
        self.paragraphs.append(p)
        return p

    def save(self, path: Any) -> None:
        pass


class MockDocx:
    Document = MockDocxDocument


# ── ebooklib mock ─────────────────────────────────────────────


class MockEpubBook:
    def __init__(self) -> None:
        self.items: list[Any] = []
        self.metadata: dict[str, Any] = {}

    def set_title(self, title: str) -> None:
        self.metadata["title"] = title

    def set_language(self, lang: str) -> None:
        self.metadata["language"] = lang

    def add_author(self, author: str) -> None:
        self.metadata["author"] = author

    def add_item(self, item: Any) -> None:
        self.items.append(item)

    def set_spine(self, spine: list[Any]) -> None:
        pass

    def set_toc(self, toc: list[Any]) -> None:
        pass


class MockEbooklib:
    EpubBook = MockEpubBook

    @staticmethod
    def write_epub(path: str, book: Any, options: Any = None) -> None:
        pass


# ── Factory ───────────────────────────────────────────────────


def get_mock_clients() -> dict[str, Any]:
    """Returns all mocks as a dict for easy fixture injection."""
    return {
        "openai": MockOpenAIClient(),
        "anthropic": MockAnthropicClient(),
        "google": MockGoogleGenAI(),
        "reportlab": MockReportLab(),
        "docx": MockDocx(),
        "epub": MockEbooklib(),
    }
