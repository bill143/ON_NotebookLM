"""
Integration Tests — Sources API
Tests file upload, URL/text ingestion, and search endpoints.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import (
    make_source_text_data,
    make_source_url_data,
)


@pytest.mark.asyncio
class TestSourcesAPI:
    """Test source ingestion and search operations."""

    async def test_create_from_text(self, client: AsyncClient, user_headers: dict):
        """POST /api/v1/sources/from-text — creates text source."""
        data = make_source_text_data(
            content="Machine learning is a subset of artificial intelligence.",
            title="ML Overview",
        )

        response = await client.post(
            "/api/v1/sources/from-text",
            json=data,
            headers=user_headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["source_type"] == "pasted_text"
        assert body["status"] == "ready"

    async def test_create_from_text_empty(self, client: AsyncClient, user_headers: dict):
        """POST /api/v1/sources/from-text — rejects empty content."""
        response = await client.post(
            "/api/v1/sources/from-text",
            json={"content": "", "title": "Empty"},
            headers=user_headers,
        )

        assert response.status_code == 422

    async def test_create_from_url(self, client: AsyncClient, user_headers: dict):
        """POST /api/v1/sources/from-url — creates URL source."""
        data = make_source_url_data(url="https://example.com/article")

        response = await client.post(
            "/api/v1/sources/from-url",
            json=data,
            headers=user_headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["source_type"] == "url"
        assert body["status"] == "pending"

    async def test_list_sources(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/sources — lists tenant sources."""
        response = await client.get(
            "/api/v1/sources",
            headers=user_headers,
        )

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_list_sources_filter_type(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/sources?source_type=text — filters by type."""
        response = await client.get(
            "/api/v1/sources?source_type=pasted_text",
            headers=user_headers,
        )

        assert response.status_code == 200

    async def test_get_source(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/sources/:id — gets a source by ID."""
        # Create first
        create_resp = await client.post(
            "/api/v1/sources/from-text",
            json=make_source_text_data(content="Test content for retrieval"),
            headers=user_headers,
        )
        source_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/sources/{source_id}",
            headers=user_headers,
        )

        assert response.status_code == 200
        assert response.json()["id"] == source_id

    async def test_get_source_not_found(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/sources/:id — returns 404."""
        missing = str(uuid.uuid4())
        response = await client.get(
            f"/api/v1/sources/{missing}",
            headers=user_headers,
        )

        assert response.status_code == 404

    async def test_delete_source(self, client: AsyncClient, user_headers: dict):
        """DELETE /api/v1/sources/:id — soft-deletes a source."""
        create_resp = await client.post(
            "/api/v1/sources/from-text",
            json=make_source_text_data(content="Content to delete"),
            headers=user_headers,
        )
        source_id = create_resp.json()["id"]

        response = await client.delete(
            f"/api/v1/sources/{source_id}",
            headers=user_headers,
        )

        assert response.status_code == 204

    async def test_search_sources(self, client: AsyncClient, user_headers: dict):
        """POST /api/v1/sources/search — performs text search."""
        response = await client.post(
            "/api/v1/sources/search",
            json={"query": "machine learning", "search_type": "text", "limit": 5},
            headers=user_headers,
        )

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_search_sources_accepts_retrieval_profile(
        self, client: AsyncClient, user_headers: dict
    ):
        """POST /api/v1/sources/search — accepts advanced retrieval controls."""
        response = await client.post(
            "/api/v1/sources/search",
            json={
                "query": "learning",
                "search_type": "text",
                "limit": 5,
                "search_profile": "deep",
                "fusion_k": 75,
            },
            headers=user_headers,
        )

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_search_empty_query(self, client: AsyncClient, user_headers: dict):
        """POST /api/v1/sources/search — rejects empty query."""
        response = await client.post(
            "/api/v1/sources/search",
            json={"query": "", "search_type": "text"},
            headers=user_headers,
        )

        assert response.status_code == 422
