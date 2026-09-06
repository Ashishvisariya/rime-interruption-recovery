# Rime Voice Evidence & Acceptance Test Specification

**Project:** Voice AI Assistant with Interruption & Recovery  
**Hackathon:** DataForge 2026 Rime Hackathon  
**Primary TTS Provider:** Rime Labs (Conversational Ultra-Low Latency Speech)  
**Detailed Specification:** See [docs/acceptance-test.md](file:///c:/INTERNSHIP/rime-interruption-recovery/docs/acceptance-test.md)  
**System Architecture:** See [docs/architecture.md](file:///c:/INTERNSHIP/rime-interruption-recovery/docs/architecture.md)

---

## 1. Hard Voice Problem
**Interruption & Recovery in Conversational Voice AI**

When a user interrupts an ongoing AI voice response and changes their request, conversational voice assistants often suffer from audio lag, obsolete speech bleed, stale background execution races, and context corruption. Solving this requires strict turn invalidation, immediate Rime audio cutoff, and rapid recovery to the user's latest intent.

---

## 2. Core Technical Claim
> **"When a user interrupts an ongoing voice response and changes their request, the system promptly stops obsolete Rime speech, invalidates/cancels obsolete work, prevents stale results from being spoken, and responds only to the latest request."**

---

## 3. How the Architecture Satisfies Acceptance Criteria

| Acceptance Criterion | Architectural Enforcement Mechanism | Relevant Component in `docs/architecture.md` |
| :--- | :--- | :--- |
| **Prompt Audio Stopping** | Client-side immediate `AudioContext` buffer flush triggered on VAD barge-in, accompanied by server WebSocket `AUDIO_STOP_REQUESTED` event. | Playback Manager & Audio Input |
| **Obsolete Work Cancellation** | `CancellationManager` signals `asyncio.Task.cancel()` across in-flight LLM streams, async tool executions, and pending Rime TTS requests. | Cancellation Manager |
| **Stale Result Protection** | Every async payload carries `(session_id, turn_id)`. The `StaleResultGuard` strictly drops any payload where `turn_id != active_turn_id`. | Stale Result Guard |
| **Latest-Turn Correctness** | Monotonic `active_turn_id` guarantees that only the newest user intent drives LLM context and Rime speech synthesis. | Turn Manager & Session State |
| **Post-Interruption Usability** | Fault-isolated error boundaries intercept and discard superseded turn exceptions without crashing the active WebSocket session. | Session Manager & Error Boundary |

---

## 4. Formal 10-Step Acceptance Test Scenario

```
[1. User Turn T1] ──▶ [2. Assistant Speaks via Rime] ──▶ [3. User Barge-in Interruption]
                                                                    │
                                                                    ▼
[6. Block Stale Output] ◀── [5. Invalidate Obsolete Work] ◀── [4. Stop Rime Audio Immediately]
         │
         ▼
[7. Transition to Turn T2] ──▶ [8. Ingest Revised Request] ──▶ [9. Process Turn T2]
                                                                    │
                                                                    ▼
                                               [10. Speak Correct T2 Response via Rime]
```

### End-to-End Sequence:
1. User sends an initial voice request ($T_1$).
2. Assistant begins processing and streaming the response through Rime TTS.
3. User interrupts before the response completes.
4. User changes or corrects part of the request ($T_2$).
5. System recognizes $T_2$ as the active request.
6. Obsolete Rime speech stops promptly on the client ($<250$ms).
7. Obsolete background work for $T_1$ is cancelled or invalidated.
8. Late results from $T_1$ are never spoken as the current response.
9. Latest request ($T_2$) is processed cleanly.
10. Final spoken response corresponds strictly to $T_2$.

---

## 5. Pass / Fail Evaluation Criteria

### Strict PASS Requirements:
- **Condition A:** User interruption accepted during active speech or wait states.
- **Condition B:** Obsolete Rime audio halts immediately upon barge-in.
- **Condition C:** Previous turn ($T_1$) cannot overwrite or race with $T_2$.
- **Condition D:** Stale LLM/tool results from $T_1$ are blocked from Rime synthesis.
- **Condition E:** Revised request reaches active conversation state.
- **Condition F:** Final spoken response corresponds strictly to $T_2$.
- **Condition G:** Session remains healthy and interactive for subsequent turns.

---

## 6. Measurable Metrics Specification

| Metric | Target Specification | Current Status |
| :--- | :--- | :--- |
| **Interruption-to-Audio-Stop Latency** | $< 250$ ms | **NOT YET MEASURED** (Specification Defined) |
| **Stale-Response Count** | $0$ leaks | **NOT YET MEASURED** (Specification Defined) |
| **Recovery Success Rate** | $\ge 95\%$ | **NOT YET MEASURED** (Specification Defined) |
| **Latest-Turn Correctness** | $100\%$ | **NOT YET MEASURED** (Specification Defined) |
| **Post-Interruption Usability** | $100\%$ | **NOT YET MEASURED** (Specification Defined) |

---

## 7. Empirical Evidence Status
- **Phase 1 Foundation:** `PASSED`
- **Phase 2 Evaluation Specification:** `PASSED`
- **Phase 3 Architecture & Concurrency Design:** `PASSED`
- **Phase 4+ Real Voice Benchmarks:** *NOT YET MEASURED (Pending Implementation)*
