# Rime Voice Evidence & Acceptance Test Specification

## 1. Hard Voice Problem
**Interruption and Recovery in Conversational Voice AI**

In natural spoken conversations, humans frequently interrupt speakers mid-utterance to amend instructions, provide missing constraints, or correct misunderstandings. In voice AI systems, handling this gracefully requires immediate audio cessation, asynchronous task cancellation, stale result invalidation, and seamless continuation from the user's latest intent.

---

## 2. Formal Acceptance Test Scenario

The core technical claim will be evaluated against the following strict 8-step end-to-end test sequence:

```
[1. Rime Speaking] ──▶ [2. User Interrupts] ──▶ [3. User Revises Request]
                                                        │
                                                        ▼
[6. Block Stale Results] ◀── [5. Invalidate Turn] ◀── [4. Stop Rime Audio Promptly]
         │
         ▼
[7. Process Latest Request] ──▶ [8. Speak Final Correct Response via Rime]
```

### Detailed Sequence:
1. **Initial Spoken Output:** The assistant begins streaming a conversational response through Rime TTS in response to turn $T_1$.
2. **User Barge-in:** The user speaks while the assistant audio response is actively playing OR while an asynchronous tool/LLM operation is pending.
3. **Request Revision:** The user amends or replaces their previous instruction with new parameters (turn $T_2$).
4. **Immediate Audio Cutoff:** All in-flight Rime audio playback and streaming buffers for turn $T_1$ must stop promptly on the client.
5. **Asynchronous Cancellation:** Any in-flight background generation or synthesis for turn $T_1$ must be cancelled or marked invalidated.
6. **Stale Result Prevention:** Any residual chunks or completed responses from turn $T_1$ must NOT be spoken by Rime.
7. **Latest Turn Processing:** The assistant processes turn $T_2$ without contamination from $T_1$.
8. **Correct Spoken Resolution:** The final audio streamed through Rime must correspond strictly to the latest request ($T_2$).

---

## 3. Planned Measurable Metrics

| Metric | Description | Target Specification | Measured Result | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Interruption-to-Audio-Stop Latency** | Time between user speech detection and cessation of Rime audio playback | $< 250$ ms | *NOT YET MEASURED* | Planned for Phase 5 |
| **Stale Response Leak Count** | Number of obsolete / invalidated response phrases played out loud | $0$ leaks | *NOT YET MEASURED* | Planned for Phase 5 |
| **Turn Cancellation Efficacy** | Percentage of obsolete background LLM/TTS tasks successfully aborted | $100\%$ | *NOT YET MEASURED* | Planned for Phase 5 |
| **Recovery Accuracy Rate** | Rate at which the final spoken response satisfies the amended intent | $> 95\%$ | *NOT YET MEASURED* | Planned for Phase 5 |
| **Rime TTS Time-to-First-Audio (TTFA)** | Latency from text token availability to initial Rime audio chunk | $< 200$ ms | *NOT YET MEASURED* | Planned for Phase 3 |

---

## 4. Empirical Evidence Log

> **Note:** Real benchmark runs, recorded audio session traces, and latency logs will be documented in this section as implementation progresses through subsequent phases. No placeholder metrics or simulated data are permitted.

- **Phase 1 Verification:**
  - Acceptance criteria formalized: `PASSED`
  - Secret isolation & backend foundation: `PASSED`
  - Real voice benchmarks: *NOT YET MEASURED*
