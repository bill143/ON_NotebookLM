"""
Integration Tests — Notebooks API
Tests full request→response cycle through FastAPI.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import make_notebook_data


@pytest.mark.asyncio
class TestNotebooksAPI:
    """Test notebook CRUD operations."""

    async def test_create_notebook(self, client: AsyncClient, user_headers: dict):
        """POST /api/v1/notebooks — creates a new notebook."""
        data = make_notebook_data(name="My Research Notebook")

        response = await client.post(
            "/api/v1/notebooks",
            json=data,
            headers=user_headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "My Research Notebook"
        assert body["icon"] == "📓"
        assert "id" in body
        assert body["source_count"] == 0

    async def test_create_notebook_no_auth(self, client: AsyncClient):
        """POST /api/v1/notebooks — rejects unauthenticated requests."""
        data = make_notebook_data()

        response = await client.post("/api/v1/notebooks", json=data)

        assert response.status_code in (401, 422)

    async def test_create_notebook_validation(self, client: AsyncClient, user_headers: dict):
        """POST /api/v1/notebooks — validates required fields."""
        response = await client.post(
            "/api/v1/notebooks",
            json={"name": ""},
            headers=user_headers,
        )

        assert response.status_code == 422

    async def test_list_notebooks(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/notebooks — lists user notebooks."""
        response = await client.get(
            "/api/v1/notebooks",
            headers=user_headers,
        )

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_list_notebooks_pagination(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/notebooks — supports pagination params."""
        response = await client.get(
            "/api/v1/notebooks?limit=5&offset=0",
            headers=user_headers,
        )

        assert response.status_code == 200

    async def test_get_notebook_not_found(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/notebooks/:id — returns 404 for unknown notebook."""
        missing = str(uuid.uuid4())
        response = await client.get(
            f"/api/v1/notebooks/{missing}",
            headers=user_headers,
        )

        assert response.status_code == 404

    async def test_update_notebook(self, client: AsyncClient, user_headers: dict):
        """PATCH /api/v1/notebooks/:id — updates notebook fields."""
        # Create first
        create_resp = await client.post(
            "/api/v1/notebooks",
            json=make_notebook_data(name="Original Name"),
            headers=user_headers,
        )
        notebook_id = create_resp.json()["id"]

        # Update
        response = await client.patch(
            f"/api/v1/notebooks/{notebook_id}",
            json={"name": "Updated Name", "pinned": True},
            headers=user_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Updated Name"

    async def test_delete_notebook(self, client: AsyncClient, user_headers: dict):
        """DELETE /api/v1/notebooks/:id — soft-deletes a notebook."""
        create_resp = await client.post(
            "/api/v1/notebooks",
            json=make_notebook_data(name="To Delete"),
            headers=user_headers,
        )
        notebook_id = create_resp.json()["id"]

        response = await client.delete(
            f"/api/v1/notebooks/{notebook_id}",
            headers=user_headers,
        )

        assert response.status_code == 204

    async def test_delete_preview(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/notebooks/:id/delete-preview — shows cascade counts."""
        create_resp = await client.post(
            "/api/v1/notebooks",
            json=make_notebook_data(name="Preview Test"),
            headers=user_headers,
        )
        notebook_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/v1/notebooks/{notebook_id}/delete-preview",
            headers=user_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert "affected" in body
