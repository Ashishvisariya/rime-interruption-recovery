"""Task Cancellation Manager & Abort Hub

Manages asyncio task ownership indexed by (session_id, turn_id), provides
thread-safe task registration and immediate task cancellation upon barge-in / interruption,
and guarantees clean cancellation propagation without blocking the event loop.

Core Invariant:
"Cancellation is best-effort; stale-result rejection is the correctness guarantee."

DataForge 2026 Rime Hackathon - Phase 13
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Union

logger = logging.getLogger(__name__)


@dataclass
class TrackedTask:
    """Encapsulates metadata and reference for an in-flight asynchronous task."""
    task_id: str
    session_id: str
    turn_id: int
    task_type: str  # "llm", "stt", "tts", "tool", "agent_turn"
    task: asyncio.Task
    created_at_ms: int
    is_cancelled: bool = False
    cancelled_at_ms: Optional[int] = None
    cancellation_reason: Optional[str] = None

    @property
    def is_done(self) -> bool:
        return self.task.done()


class CancellationManager:
    """Thread-safe registry and abort hub for turn-bound asynchronous tasks."""

    def __init__(self):
        # Maps (session_id, turn_id) -> Dict[task_id, TrackedTask]
        self._tasks: Dict[str, Dict[int, Dict[str, TrackedTask]]] = {}
        self._lock = threading.RLock()

    def register_task(
        self,
        session_id: str,
        turn_id: int,
        task: asyncio.Task,
        task_type: str = "llm",
        task_id: Optional[str] = None,
    ) -> TrackedTask:
        """Register an active asyncio.Task under (session_id, turn_id) ownership."""
        with self._lock:
            now_ms = int(time.time() * 1000)
            tid = task_id or f"task_{session_id}_{turn_id}_{task_type}_{id(task)}"

            tracked = TrackedTask(
                task_id=tid,
                session_id=session_id,
                turn_id=turn_id,
                task_type=task_type,
                task=task,
                created_at_ms=now_ms,
            )

            if session_id not in self._tasks:
                self._tasks[session_id] = {}
            if turn_id not in self._tasks[session_id]:
                self._tasks[session_id][turn_id] = {}

            self._tasks[session_id][turn_id][tid] = tracked

            # Auto-cleanup callback when task finishes
            def _on_done(t: asyncio.Task):
                self._remove_task(session_id, turn_id, tid)

            try:
                task.add_done_callback(_on_done)
            except Exception:
                pass

            return tracked

    def unregister_task(
        self,
        session_id: str,
        turn_id: int,
        task_or_id: Union[asyncio.Task, str],
    ) -> bool:
        """Explicitly unregister a task."""
        with self._lock:
            if isinstance(task_or_id, str):
                return self._remove_task(session_id, turn_id, task_or_id)
            else:
                # Find by task instance
                session_turns = self._tasks.get(session_id, {})
                turn_tasks = session_turns.get(turn_id, {})
                for tid, tracked in list(turn_tasks.items()):
                    if tracked.task is task_or_id:
                        return self._remove_task(session_id, turn_id, tid)
                return False

    def _remove_task(self, session_id: str, turn_id: int, task_id: str) -> bool:
        """Internal helper to remove task from registry."""
        with self._lock:
            session_turns = self._tasks.get(session_id)
            if not session_turns:
                return False
            turn_tasks = session_turns.get(turn_id)
            if not turn_tasks:
                return False
            if task_id in turn_tasks:
                del turn_tasks[task_id]
                if not turn_tasks:
                    del session_turns[turn_id]
                if not session_turns:
                    del self._tasks[session_id]
                return True
            return False

    def cancel_turn_tasks(
        self,
        session_id: str,
        turn_id: int,
        reason: str = "turn_superseded",
    ) -> int:
        """Cancel all in-flight asynchronous tasks registered for a specific turn.
        
        Returns the number of tasks for which cancellation was requested.
        """
        with self._lock:
            session_turns = self._tasks.get(session_id, {})
            turn_tasks = session_turns.get(turn_id, {})
            if not turn_tasks:
                return 0

            cancelled_count = 0
            now_ms = int(time.time() * 1000)

            for tid, tracked in list(turn_tasks.items()):
                if not tracked.is_done:
                    tracked.is_cancelled = True
                    tracked.cancelled_at_ms = now_ms
                    tracked.cancellation_reason = reason
                    try:
                        tracked.task.cancel()
                        cancelled_count += 1
                    except Exception as e:
                        logger.warning(f"Error requesting cancellation for task {tid}: {e}")

            return cancelled_count

    def cancel_obsolete_tasks(
        self,
        session_id: str,
        active_turn_id: int,
        reason: str = "turn_superseded",
    ) -> int:
        """Cancel all in-flight tasks for turns strictly older than active_turn_id.
        
        Guarantees:
        - Tasks belonging to turn_id < active_turn_id are cancelled.
        - Tasks belonging to active_turn_id remain completely unaffected.
        """
        with self._lock:
            session_turns = self._tasks.get(session_id, {})
            if not session_turns:
                return 0

            total_cancelled = 0
            obsolete_turn_ids = [tid for tid in session_turns.keys() if tid < active_turn_id]

            for tid in obsolete_turn_ids:
                total_cancelled += self.cancel_turn_tasks(session_id, tid, reason=reason)

            return total_cancelled

    def cancel_all_session_tasks(
        self,
        session_id: str,
        reason: str = "session_closed",
    ) -> int:
        """Cancel all in-flight tasks across all turns for a given session."""
        with self._lock:
            session_turns = self._tasks.get(session_id, {})
            if not session_turns:
                return 0

            total_cancelled = 0
            for tid in list(session_turns.keys()):
                total_cancelled += self.cancel_turn_tasks(session_id, tid, reason=reason)

            return total_cancelled

    def get_active_tasks(
        self,
        session_id: Optional[str] = None,
        turn_id: Optional[int] = None,
    ) -> List[TrackedTask]:
        """Retrieve all currently registered non-completed tasks."""
        with self._lock:
            results: List[TrackedTask] = []
            sessions = [session_id] if session_id else list(self._tasks.keys())

            for sid in sessions:
                session_turns = self._tasks.get(sid, {})
                turns = [turn_id] if turn_id is not None else list(session_turns.keys())
                for tid in turns:
                    turn_tasks = session_turns.get(tid, {})
                    for tracked in turn_tasks.values():
                        if not tracked.is_done:
                            results.append(tracked)

            return results

    def clear(self) -> None:
        """Clear all tasks from the registry."""
        with self._lock:
            self._tasks.clear()


# Default global cancellation manager singleton
default_cancellation_manager = CancellationManager()
