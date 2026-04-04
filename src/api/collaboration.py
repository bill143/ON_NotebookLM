"""
Nexus Collaboration Engine — Real-Time Multi-User Workspace
Codename: ESPERANTO — Feature 6C: Collaborative Notebooks

Provides:
- Real-time presence awareness (who's viewing what)
- Live cursor and selection tracking
- Collaborative note editing with CRDT-style conflict resolution
- Notebook lock/unlock for exclusive editing
- Activity feed broadcasting
- Typing indicators and user status
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from loguru import logger

from src.exceptions import AuthError

router = APIRouter(tags=["Collaboration"])


# ── Types ────────────────────────────────────────────────────

class UserStatus(str, Enum):
    ACTIVE = "active"
    IDLE = "idle"
    AWAY = "away"


class ActivityType(str, Enum):
    JOIN = "join"
    LEAVE = "leave"
    CURSOR_MOVE = "cursor_move"
    CONTENT_EDIT = "content_edit"
    NOTE_ADD = "note_add"
    SOURCE_ADD = "source_add"
    ARTIFACT_CREATE = "artifact_create"
    TYPING_START = "typing_start"
    TYPING_STOP = "typing_stop"
    LOCK_ACQUIRE = "lock_acquire"
    LOCK_RELEASE = "lock_release"


@dataclass
class PresenceUser:
    """A user present in a collaborative workspace."""
    user_id: str
    tenant_id: str
    display_name: str
    avatar_color: str
    connection_id: str
    websocket: WebSocket
    notebook_id: str = ""
    status: UserStatus = UserStatus.ACTIVE
    cursor_position: Optional[dict] = None     # {section, offset}
    selection: Optional[dict] = None           # {start, end}
    last_activity: float = field(default_factory=time.time)
    joined_at: float = field(default_factory=time.time)

    def to_presence_dict(self) -> dict[str, Any]:
        """Serialize for broadcasting (excludes websocket)."""
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "avatar_color": self.avatar_color,
            "connection_id": self.connection_id,
            "notebook_id": self.notebook_id,
            "status": self.status.value,
            "cursor_position": self.cursor_position,
            "selection": self.selection,
            "joined_at": self.joined_at,
            "last_activity": self.last_activity,
        }


@dataclass
class NotebookLock:
    """Lock for exclusive editing of notebook content."""
    notebook_id: str
    section_id: str
    locked_by: str          # user_id
    locked_at: float
    expires_at: float       # Auto-expire after timeout

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


@dataclass
class CollaborationEvent:
    """An event in the collaboration activity stream."""
    event_id: str
    event_type: ActivityType
    user_id: str
    display_name: str
    notebook_id: str
    timestamp: float
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "user_id": self.user_id,
            "display_name": self.display_name,
            "notebook_id": self.notebook_id,
            "timestamp": self.timestamp,
            "data": self.data,
        }


# ── Collaboration Hub ────────────────────────────────────────

class CollaborationHub:
    """
    Central hub for real-time collaboration.
    Manages presence, events, locks, and broadcasting.
    """

    def __init__(self) -> None:
        # user_id → PresenceUser
        self._users: dict[str, PresenceUser] = {}
        # connection_id → user_id
        self._connections: dict[str, str] = {}
        # notebook_id → set of connection_ids
        self._notebook_users: dict[str, set[str]] = {}
        # "notebook:section" → NotebookLock
        self._locks: dict[str, NotebookLock] = {}
        # notebook_id → list of recent events
        self._activity_feed: dict[str, list[CollaborationEvent]] = {}
        # Idle detection interval
        self._idle_timeout = 300  # 5 minutes

    # ── Connection Lifecycle ─────────────────────────

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        tenant_id: str,
        display_name: str,
        notebook_id: str = "",
    ) -> str:
        """Register a new collaborative connection."""
        await websocket.accept()
        conn_id = str(uuid.uuid4())[:12]

        # Generate consistent avatar color from user_id
        colors = [
            "#ef4444", "#f97316", "#eab308", "#22c55e",
            "#06b6d4", "#3b82f6", "#8b5cf6", "#ec4899",
        ]
        color = colors[hash(user_id) % len(colors)]

        user = PresenceUser(
            user_id=user_id,
            tenant_id=tenant_id,
            display_name=display_name,
            avatar_color=color,
            connection_id=conn_id,
            websocket=websocket,
            notebook_id=notebook_id,
        )

        self._users[conn_id] = user
        self._connections[conn_id] = user_id

        if notebook_id:
            if notebook_id not in self._notebook_users:
                self._notebook_users[notebook_id] = set()
            self._notebook_users[notebook_id].add(conn_id)

        # Broadcast join event
        await self._broadcast_to_notebook(notebook_id, {
            "type": "presence_join",
            "user": user.to_presence_dict(),
            "active_users": self._get_notebook_presence(notebook_id),
        }, exclude=conn_id)

        # Record activity
        self._add_activity(CollaborationEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type=ActivityType.JOIN,
            user_id=user_id,
            display_name=display_name,
            notebook_id=notebook_id,
            timestamp=time.time(),
        ))

        logger.info(
            f"Collab connected: {display_name} ({conn_id}) → notebook:{notebook_id}"
        )

        return conn_id

    async def disconnect(self, conn_id: str) -> None:
        """Remove a connection and clean up."""
        user = self._users.pop(conn_id, None)
        self._connections.pop(conn_id, None)

        if user:
            # Remove from notebook tracking
            notebook_id = user.notebook_id
            if notebook_id in self._notebook_users:
                self._notebook_users[notebook_id].discard(conn_id)
                if not self._notebook_users[notebook_id]:
                    del self._notebook_users[notebook_id]

            # Release any locks held by this user
            expired_locks = [
                key for key, lock in self._locks.items()
                if lock.locked_by == user.user_id
            ]
            for key in expired_locks:
                del self._locks[key]

            # Broadcast leave
            await self._broadcast_to_notebook(notebook_id, {
                "type": "presence_leave",
                "user_id": user.user_id,
                "display_name": user.display_name,
                "active_users": self._get_notebook_presence(notebook_id),
            })

            self._add_activity(CollaborationEvent(
                event_id=str(uuid.uuid4())[:8],
                event_type=ActivityType.LEAVE,
                user_id=user.user_id,
                display_name=user.display_name,
                notebook_id=notebook_id,
                timestamp=time.time(),
            ))

            logger.info(f"Collab disconnected: {user.display_name} ({conn_id})")

    # ── Event Handling ───────────────────────────────

    async def handle_event(
        self,
        conn_id: str,
        event: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Process an incoming collaboration event."""
        user = self._users.get(conn_id)
        if not user:
            return {"type": "error", "message": "Connection not found"}

        user.last_activity = time.time()
        user.status = UserStatus.ACTIVE

        event_type = event.get("type", "")

        if event_type == "cursor_move":
            return await self._handle_cursor(user, event)

        elif event_type == "selection_change":
            return await self._handle_selection(user, event)

        elif event_type == "content_edit":
            return await self._handle_content_edit(user, event)

        elif event_type == "typing_start":
            return await self._handle_typing(user, True)

        elif event_type == "typing_stop":
            return await self._handle_typing(user, False)

        elif event_type == "lock_request":
            return await self._handle_lock_request(user, event)

        elif event_type == "lock_release":
            return await self._handle_lock_release(user, event)

        elif event_type == "get_presence":
            return {
                "type": "presence_list",
                "users": self._get_notebook_presence(user.notebook_id),
            }

        elif event_type == "get_activity":
            return {
                "type": "activity_feed",
                "events": self._get_activity_feed(user.notebook_id),
            }

        elif event_type == "ping":
            return {"type": "pong", "timestamp": time.time()}

        return None

    async def _handle_cursor(
        self,
        user: PresenceUser,
        event: dict[str, Any],
    ) -> None:
        """Broadcast cursor position to other users."""
        user.cursor_position = event.get("position")

        await self._broadcast_to_notebook(user.notebook_id, {
            "type": "cursor_update",
            "user_id": user.user_id,
            "display_name": user.display_name,
            "avatar_color": user.avatar_color,
            "position": user.cursor_position,
        }, exclude=user.connection_id)
        return None

    async def _handle_selection(
        self,
        user: PresenceUser,
        event: dict[str, Any],
    ) -> None:
        """Broadcast selection range to other users."""
        user.selection = event.get("selection")

        await self._broadcast_to_notebook(user.notebook_id, {
            "type": "selection_update",
            "user_id": user.user_id,
            "display_name": user.display_name,
            "avatar_color": user.avatar_color,
            "selection": user.selection,
        }, exclude=user.connection_id)
        return None

    async def _handle_content_edit(
        self,
        user: PresenceUser,
        event: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Handle content edits with optimistic locking."""
        section_id = event.get("section_id", "")
        lock_key = f"{user.notebook_id}:{section_id}"

        # Check lock
        lock = self._locks.get(lock_key)
        if lock and not lock.is_expired and lock.locked_by != user.user_id:
            return {
                "type": "edit_rejected",
                "reason": "Section is locked",
                "locked_by": lock.locked_by,
            }

        # Broadcast edit to others
        await self._broadcast_to_notebook(user.notebook_id, {
            "type": "content_edit",
            "user_id": user.user_id,
            "display_name": user.display_name,
            "section_id": section_id,
            "operation": event.get("operation"),  # "insert", "delete", "replace"
            "content": event.get("content", ""),
            "position": event.get("position"),
            "version": event.get("version", 0),
        }, exclude=user.connection_id)

        self._add_activity(CollaborationEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type=ActivityType.CONTENT_EDIT,
            user_id=user.user_id,
            display_name=user.display_name,
            notebook_id=user.notebook_id,
            timestamp=time.time(),
            data={"section_id": section_id},
        ))

        return {"type": "edit_ack", "version": event.get("version", 0) + 1}

    async def _handle_typing(
        self,
        user: PresenceUser,
        is_typing: bool,
    ) -> None:
        """Broadcast typing indicator."""
        await self._broadcast_to_notebook(user.notebook_id, {
            "type": "typing_indicator",
            "user_id": user.user_id,
            "display_name": user.display_name,
            "is_typing": is_typing,
        }, exclude=user.connection_id)
        return None

    async def _handle_lock_request(
        self,
        user: PresenceUser,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle section lock request."""
        section_id = event.get("section_id", "")
        lock_key = f"{user.notebook_id}:{section_id}"
        lock_duration = min(event.get("duration", 300), 600)  # Max 10 min

        # Check existing lock
        existing = self._locks.get(lock_key)
        if existing and not existing.is_expired and existing.locked_by != user.user_id:
            return {
                "type": "lock_denied",
                "section_id": section_id,
                "locked_by": existing.locked_by,
                "expires_at": existing.expires_at,
            }

        # Grant lock
        lock = NotebookLock(
            notebook_id=user.notebook_id,
            section_id=section_id,
            locked_by=user.user_id,
            locked_at=time.time(),
            expires_at=time.time() + lock_duration,
        )
        self._locks[lock_key] = lock

        await self._broadcast_to_notebook(user.notebook_id, {
            "type": "section_locked",
            "section_id": section_id,
            "locked_by": user.user_id,
            "display_name": user.display_name,
            "expires_at": lock.expires_at,
        }, exclude=user.connection_id)

        return {
            "type": "lock_granted",
            "section_id": section_id,
            "expires_at": lock.expires_at,
        }

    async def _handle_lock_release(
        self,
        user: PresenceUser,
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """Release a section lock."""
        section_id = event.get("section_id", "")
        lock_key = f"{user.notebook_id}:{section_id}"

        lock = self._locks.pop(lock_key, None)
        if lock and lock.locked_by != user.user_id:
            # Can't release someone else's lock
            self._locks[lock_key] = lock
            return {"type": "lock_release_denied"}

        await self._broadcast_to_notebook(user.notebook_id, {
            "type": "section_unlocked",
            "section_id": section_id,
            "released_by": user.user_id,
        }, exclude=user.connection_id)

        return {"type": "lock_released", "section_id": section_id}

    # ── Broadcasting ─────────────────────────────────

    async def _broadcast_to_notebook(
        self,
        notebook_id: str,
        data: dict[str, Any],
        exclude: str = "",
    ) -> None:
        """Send data to all users in a notebook."""
        conn_ids = self._notebook_users.get(notebook_id, set())
        dead: list[str] = []

        for conn_id in conn_ids:
            if conn_id == exclude:
                continue
            user = self._users.get(conn_id)
            if user:
                try:
                    await user.websocket.send_json(data)
                except Exception:
                    dead.append(conn_id)

        # Clean up dead connections
        for conn_id in dead:
            await self.disconnect(conn_id)

    def _get_notebook_presence(self, notebook_id: str) -> list[dict[str, Any]]:
        """Get presence list for a notebook."""
        conn_ids = self._notebook_users.get(notebook_id, set())
        return [
            self._users[cid].to_presence_dict()
            for cid in conn_ids
            if cid in self._users
        ]

    # ── Activity Feed ────────────────────────────────

    def _add_activity(self, event: CollaborationEvent) -> None:
        """Add event to activity feed (keep last 50)."""
        nb_id = event.notebook_id
        if nb_id not in self._activity_feed:
            self._activity_feed[nb_id] = []
        self._activity_feed[nb_id].append(event)
        self._activity_feed[nb_id] = self._activity_feed[nb_id][-50:]

    def _get_activity_feed(
        self,
        notebook_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get recent activity for a notebook."""
        events = self._activity_feed.get(notebook_id, [])
        return [e.to_dict() for e in events[-limit:]]

    # ── Idle Detection ───────────────────────────────

    async def check_idle_users(self) -> None:
        """Check for idle users and update status."""
        now = time.time()
        for conn_id, user in list(self._users.items()):
            if user.status == UserStatus.ACTIVE:
                if now - user.last_activity > self._idle_timeout:
                    user.status = UserStatus.IDLE
                    await self._broadcast_to_notebook(user.notebook_id, {
                        "type": "presence_status",
                        "user_id": user.user_id,
                        "status": UserStatus.IDLE.value,
                    })

    # ── Stats ────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "total_connections": len(self._users),
            "active_notebooks": len(self._notebook_users),
            "active_locks": len(
                [lock for lock in self._locks.values() if not lock.is_expired]
            ),
        }


# Global singleton
collab_hub = CollaborationHub()


# ── WebSocket Endpoints ──────────────────────────────────────

def _authenticate(token: str) -> tuple[str, str, str]:
    """Authenticate and return (user_id, tenant_id, display_name)."""
    from src.infra.nexus_vault_keys import verify_token
    payload = verify_token(token)
    return payload["sub"], payload["tid"], payload.get("name", payload["sub"][:8])


@router.websocket("/ws/collab")
async def websocket_collab(
    websocket: WebSocket,
    token: str = Query(...),
    notebook_id: str = Query(...),
):
    """
    WebSocket endpoint for real-time collaboration.

    Protocol:
    Client → Server: {"type": "cursor_move", "position": {...}}
    Client → Server: {"type": "content_edit", "section_id": "...", "operation": "insert", "content": "..."}
    Client → Server: {"type": "typing_start"}
    Client → Server: {"type": "lock_request", "section_id": "...", "duration": 300}
    Client → Server: {"type": "get_presence"}

    Server → Client: {"type": "presence_join", "user": {...}, "active_users": [...]}
    Server → Client: {"type": "cursor_update", "user_id": "...", "position": {...}}
    Server → Client: {"type": "content_edit", "user_id": "...", "content": "...", ...}
    Server → Client: {"type": "typing_indicator", "user_id": "...", "is_typing": true}
    """
    try:
        user_id, tenant_id, display_name = _authenticate(token)
    except Exception:
        await websocket.close(code=4001, reason="Authentication failed")
        return

    conn_id = await collab_hub.connect(
        websocket, user_id, tenant_id, display_name, notebook_id
    )

    try:
        # Send initial state
        await websocket.send_json({
            "type": "connected",
            "connection_id": conn_id,
            "active_users": collab_hub._get_notebook_presence(notebook_id),
            "recent_activity": collab_hub._get_activity_feed(notebook_id),
        })

        while True:
            raw = await websocket.receive_text()
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            response = await collab_hub.handle_event(conn_id, event)
            if response:
                await websocket.send_json(response)

    except WebSocketDisconnect:
        await collab_hub.disconnect(conn_id)
    except Exception as e:
        logger.error(f"Collab WebSocket error: {e}")
        await collab_hub.disconnect(conn_id)
        try:
            await websocket.close(code=1011, reason="Internal error")
        except Exception:
            pass


@router.get("/ws/collab/status")
async def collab_status():
    """Get collaboration hub statistics."""
    return collab_hub.stats
