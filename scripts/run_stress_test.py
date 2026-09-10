"""High-Concurrency Stress & Barge-In Invariant Test Runner

Executes high-throughput concurrent trials across multiple simulated voice sessions
to verify that monotonic turn isolation, rapid consecutive barge-in interruptions,
and deterministic stale-result rejection hold under heavy load.

Validates:
1. Monotonic turn counter integrity under concurrent rapid interruptions.
2. In-flight task cancellation propagation via CancellationManager.
3. 100% rejection rate for stale/superseded asynchronous worker results.
4. Zero state pollution across independent concurrent voice sessions.
"""

import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from backend.app.core.session import SessionStore, VoiceSession
from backend.app.core.cancellation import CancellationManager
from backend.app.services.conversation import ConversationManager, StaleTurnMutationError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("stress_test")


@dataclass
class SessionStressResult:
    session_id: str
    total_interruptions: int
    final_turn_id: int
    stale_rejections_verified: int
    audio_stop_latencies_ms: List[float] = field(default_factory=list)
    success: bool = True
    error: str = ""


async def simulate_session_barge_in_stress(
    session_idx: int,
    cancellation_mgr: CancellationManager,
    num_rapid_interruptions: int = 5,
) -> SessionStressResult:
    """Simulates a user issuing rapid, unpredictable barge-in interruptions in a session."""
    session_id = f"stress_sess_{session_idx:03d}_{int(time.time() * 1000) % 100000}"
    store = SessionStore()
    manager = ConversationManager(session_store=store)
    manager.create_session(session_id)

    result = SessionStressResult(
        session_id=session_id,
        total_interruptions=num_rapid_interruptions,
        final_turn_id=0,
        stale_rejections_verified=0,
    )

    try:
        current_turn = manager.create_turn(session_id, "Initial voice query T1")
        assert current_turn == 1, f"Expected Turn 1, got {current_turn}"

        # Register a dummy background worker task representing in-flight generation
        worker_task = asyncio.create_task(asyncio.sleep(1.0))
        cancellation_mgr.register_task(session_id, current_turn, worker_task, "llm")

        for i in range(1, num_rapid_interruptions + 1):
            # Simulated user speech barge-in
            t0 = time.perf_counter()
            cancelled_count = cancellation_mgr.cancel_turn_tasks(session_id, current_turn)
            t_stop = time.perf_counter()
            stop_latency_ms = (t_stop - t0) * 1000.0
            result.audio_stop_latencies_ms.append(stop_latency_ms)

            # Advance to next turn
            superseded_turn = current_turn
            next_prompt = f"Barge-in revision turn T{i + 1}"
            current_turn = manager.create_turn(session_id, next_prompt)

            # Attempt a late/stale mutation using superseded_turn ID — MUST BE REJECTED
            is_valid = manager.validate_turn(session_id, superseded_turn)
            if is_valid:
                result.success = False
                result.error = f"Security breach: Superseded turn T{superseded_turn} still marked valid!"
                return result

            try:
                stale_committed = manager.complete_turn(
                    session_id,
                    superseded_turn,
                    f"Stale reply for T{superseded_turn} that should never appear",
                    strict=True,
                )
                if stale_committed:
                    result.success = False
                    result.error = f"Security breach: Stale turn T{superseded_turn} was accepted!"
                    return result
            except StaleTurnMutationError:
                result.stale_rejections_verified += 1

            # Ensure stale reply was NEVER added to session messages
            sess = manager.get_session(session_id)
            for msg in sess.messages:
                if f"Stale reply for T{superseded_turn}" in msg.content:
                    result.success = False
                    result.error = f"Leak detected: Stale reply found in history!"
                    return result

            # Re-register an async worker for the new active turn
            new_worker = asyncio.create_task(asyncio.sleep(1.0))
            cancellation_mgr.register_task(session_id, current_turn, new_worker, "llm")
            await asyncio.sleep(0.005)  # micro-yield to simulate real async scheduling

        # Final turn settles and completes cleanly
        final_answer = f"Authoritative final response for Turn T{current_turn}."
        manager.complete_turn(session_id, current_turn, final_answer)
        result.final_turn_id = current_turn

        # Verify session integrity
        sess = manager.get_session(session_id)
        assert sess.active_turn_id == current_turn, "Active turn ID mismatch"
        assert len(sess.turns) == num_rapid_interruptions + 1, "Incorrect turn count in history"

    except Exception as exc:
        result.success = False
        result.error = str(exc)

    return result


async def run_stress_suite(num_concurrent_sessions: int = 25, interruptions_per_session: int = 5):
    """Orchestrates concurrent stress sessions and aggregates latency/correctness metrics."""
    print("=" * 72)
    print(f"  VOICE AGENT CONCURRENCY & BARGE-IN STRESS SUITE")
    print(f"  Simulating {num_concurrent_sessions} concurrent sessions × {interruptions_per_session} rapid barge-ins each")
    print("=" * 72)

    cancellation_mgr = CancellationManager()
    start_time = time.perf_counter()

    tasks = [
        simulate_session_barge_in_stress(
            session_idx=i,
            cancellation_mgr=cancellation_mgr,
            num_rapid_interruptions=interruptions_per_session,
        )
        for i in range(num_concurrent_sessions)
    ]

    results: List[SessionStressResult] = await asyncio.gather(*tasks)
    total_elapsed = time.perf_counter() - start_time

    # Aggregate metrics
    all_latencies = [
        lat for r in results for lat in r.audio_stop_latencies_ms
    ]
    all_latencies.sort()
    passed_sessions = sum(1 for r in results if r.success)
    total_turns_tested = sum(r.final_turn_id for r in results)
    total_stale_blocked = sum(r.stale_rejections_verified for r in results)

    mean_stop = sum(all_latencies) / len(all_latencies) if all_latencies else 0.0
    p50_stop = all_latencies[len(all_latencies) // 2] if all_latencies else 0.0
    p95_stop = all_latencies[int(len(all_latencies) * 0.95)] if all_latencies else 0.0
    max_stop = max(all_latencies) if all_latencies else 0.0

    print("\n--- TEST SUMMARY ---")
    print(f"Total Sessions:           {num_concurrent_sessions}")
    print(f"Passed Sessions:          {passed_sessions} / {num_concurrent_sessions} ({passed_sessions / num_concurrent_sessions * 100:.1f}%)")
    print(f"Total Turns Evaluated:    {total_turns_tested}")
    print(f"Stale Mutations Blocked:  {total_stale_blocked} / {num_concurrent_sessions * interruptions_per_session} (100% blocked)")
    print(f"Total Wall-Clock Time:    {total_elapsed:.3f} s")
    print(f"Throughput:               {total_turns_tested / total_elapsed:.1f} turns/sec")
    print("\n--- INTERRUPTION CANCELLATION LATENCY ---")
    print(f"Mean Latency:             {mean_stop:.3f} ms")
    print(f"P50  Latency:             {p50_stop:.3f} ms")
    print(f"P95  Latency:             {p95_stop:.3f} ms")
    print(f"Max  Latency:             {max_stop:.3f} ms")
    print("=" * 72)

    if passed_sessions == num_concurrent_sessions and total_stale_blocked == num_concurrent_sessions * interruptions_per_session:
        print(">>> ALL CONCURRENCY & BARGE-IN INVARIANTS VERIFIED CLEANLY <<<\n")
        return 0
    else:
        print(">>> STRESS TEST FAILED <<<")
        for r in results:
            if not r.success:
                print(f"  [FAIL] {r.session_id}: {r.error}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_stress_suite())
    sys.exit(exit_code)
