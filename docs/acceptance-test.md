# Acceptance Test Specification: Interruption and Recovery

**Project:** Voice AI Assistant with Interruption & Recovery  
**Hackathon:** DataForge 2026 Rime Hackathon  
**Phase:** Phase 2 — Evaluation Specification  
**Status:** SPECIFICATION ONLY (Implementation and measurement pending in subsequent phases)

---

## 1. Objective & Hard Voice Problem
In real-time conversational voice interfaces, humans do not wait passively for a speech synthesizer to finish a turn if they need to revise a constraint, cancel an action, or correct an initial statement. 

**The Hard Voice Problem:** Achieving prompt, race-condition-free interruption and recovery where obsolete Rime audio immediately halts, in-flight background processing (STT, LLM tokens, TTS buffers, tool calls) is invalidated or cancelled, stale results are blocked from being vocalized, and the system resolves cleanly to the user's latest intent.

---

## 2. Primary Acceptance Test Specification

### Test Name:
**"Interruption and Recovery Acceptance Test"**

### End-to-End Sequence:
1. **Initial Spoken Request:** The user submits an initial voice query (Turn $T_1$, e.g., asking for information or initiating an action).
2. **Assistant Output Initiation:** The assistant begins processing and streaming the spoken response via Rime TTS.
3. **User Barge-In:** While the assistant is actively speaking or awaiting an asynchronous operation for $T_1$, the user interrupts mid-stream.
4. **Request Amendment:** The user provides a revised or replacement prompt (Turn $T_2$, e.g., correcting the entity, destination, or parameters).
5. **Active Turn Migration:** The system immediately transitions the active conversational context from $T_1$ to $T_2$.
6. **Prompt Audio Cessation:** All active Rime audio stream chunks and client-side playback buffers for $T_1$ are stopped immediately.
7. **Obsolete Work Invalidation:** In-flight background generation, tool executions, and pending TTS audio synthesis for $T_1$ are aborted or marked as superseded.
8. **Stale Output Blockade:** Any late-arriving results, tokens, or audio chunks from $T_1$ are completely blocked from being spoken.
9. **New Turn Resolution:** The assistant processes Turn $T_2$ without state corruption or bleed from $T_1$.
10. **Targeted Spoken Completion:** The final audio streamed through Rime corresponds strictly and accurately to Turn $T_2$.

---

## 3. Pass / Fail Evaluation Criteria

### Strict PASS Conditions (All 7 Must Be Satisfied):
- **Condition A (Interruption Ingestion):** User barge-in is detected and ingested while the assistant is actively speaking or awaiting backend response.
- **Condition B (Audio Cutoff):** Obsolete Rime audio stream stops delivering playback immediately upon interruption.
- **Condition C (Turn Isolation):** The previous turn ($T_1$) cannot overwrite or race with the state of the newer turn ($T_2$).
- **Condition D (Stale Result Zero-Tolerance):** Outdated LLM completions, tool results, or audio packets from $T_1$ are never spoken as active responses.
- **Condition E (Context Progression):** The revised instruction ($T_2$) accurately updates active session context.
- **Condition F (Response Semantic Alignment):** The final synthesized speech answers the updated request ($T_2$).
- **Condition G (Post-Interruption Usability):** The assistant remains interactive, healthy, and ready for subsequent turns without requiring page refresh or reconnection.

---

### Critical Failures vs. Non-Critical Imperfections

#### Critical Failures (Immediate FAIL):
- **CF-1 (Speech Bleed):** Assistant continues speaking the $T_1$ response after the user has begun and completed $T_2$.
- **CF-2 (Stale Result Echo):** Old $T_1$ result is spoken *after* the user's $T_2$ request has finished.
- **CF-3 (Request Dropping):** The newer request ($T_2$) is ignored or dropped by the system.
- **CF-4 (State Inversion):** Late-arriving $T_1$ computation overwrites or pollutes $T_2$ memory/context.
- **CF-5 (Session Deadlock):** Assistant crashes, hangs, freezes, or fails to respond to subsequent turns after an interruption.
- **CF-6 (Incorrect Output):** The final voice output satisfies $T_1$ instead of $T_2$.

#### Non-Critical Imperfections (Does Not Fail Core Test, Logged as Latency/UX Defects):
- Minor audible click or sub-100ms hardware buffer draining artifact at the exact moment of audio cutoff.
- Log warning regarding aborted HTTP/WebSocket connection during cancellation.
- Slight variance in STT transcription confidence during initial barge-in frame.

---

## 4. Measurable Metrics Specification

| Metric | Definition | Trigger / Measurement Start | Resolution / Measurement End | Data Source | Target / Expected Behavior | Current Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Interruption-to-Audio-Stop Latency** | Time between detection of user interruption and cessation of Rime audio playback | Timestamp of client barge-in signal / VAD trigger | Timestamp of audio hardware buffer silence / pause | Client audio playback event logs & WebSocket trace | $< 250$ ms | **NOT YET MEASURED** |
| **2. Stale-Response Count** | Number of obsolete/superseded turn responses or chunks spoken out loud after a new turn begins | Timestamp of new turn acceptance ($T_2$) | Completion of entire conversation session | Spoken transcript log & audio output frame auditor | $0$ stale responses | **NOT YET MEASURED** |
| **3. Recovery Success Rate** | Percentage of interruption trials where the system halts old audio, prevents stale results, and answers new intent | Start of first trial in benchmark suite | Completion of final trial in benchmark suite | Benchmark harness automated test log | $100\%$ (Target: $\ge 95\%$) | **NOT YET MEASURED** |
| **4. Latest-Turn Correctness** | Verification that final spoken response matches semantic intent of $T_2$ | Delivery of final Rime audio response | Evaluator semantic matching against $T_2$ prompt | LLM evaluator / transcript verification | $100\%$ semantic fidelity | **NOT YET MEASURED** |
| **5. Post-Interruption Usability** | Verification that session state remains operational for subsequent turns ($T_3, T_4$) | End of recovery response $T_2$ | Successful roundtrip completion of $T_3$ | Health probe & interactive roundtrip check | Normal operational readiness | **NOT YET MEASURED** |

---

## 5. Test Scenarios

### Scenario 1: Normal Interruption & Recovery Test Case
- **Status:** `STATUS: SPECIFICATION ONLY`
- **Initial Query ($T_1$):** `"Tell me the weather in Delhi."`
- **Assistant Action:** Assistant begins generating weather details and streaming audio via Rime: *"The current weather in Delhi is sunny with a temperature of..."*
- **User Interruption ($T_2$):** Mid-sentence, the user interrupts: *"Actually, tell me the weather in Mumbai."*
- **Expected Outcome:**
  - Delhi audio playback halts immediately.
  - Delhi generation pipeline is marked obsolete.
  - Mumbai becomes the active turn.
  - Delhi results cannot overwrite Mumbai state.
  - Assistant speaks the Mumbai weather response via Rime: *"In Mumbai, the current weather is..."*

---

### Scenario 2: Deliberate Stress & Race-Condition Test Case
- **Status:** `STATUS: SPECIFICATION ONLY`
- **Setup:** A deliberate artificial processing/tool delay is introduced for $T_1$ (e.g., a slow mock database or heavy retrieval simulation).
- **Initial Query ($T_1$):** `"Search for the full flight itinerary from New York to Tokyo."`
- **Assistant Action:** Assistant enters waiting/processing state or begins playing initial filler audio.
- **User Interruption ($T_2$):** While the heavy $T_1$ task is still in-flight, user interrupts: `"Cancel that, search for flights from New York to London instead."`
- **Race Condition Trigger:** The slow $T_1$ task completes and returns its payload *after* $T_2$ has already been registered as active.
- **Expected Outcome:**
  - In-flight $T_1$ task is cancelled or marked obsolete via Turn ID generation token.
  - When the late $T_1$ result resolves, the Stale Guard Buffer discards it immediately.
  - Tokyo flight details are NEVER dispatched to Rime TTS and NEVER spoken.
  - London flight search executes cleanly and is spoken as the sole final response.
  - Application remains completely responsive and ready for $T_3$.

---

## 6. Repeatability & Evaluation Protocol

### Planned Evaluation Configuration:
- **Trial Count:** Standard evaluation suite of **20 consecutive trials** (10 Normal Interruption Scenarios + 10 Deliberate Stress Race Scenarios).
- **Trial Log Schema:**

```json
{
  "trial_id": 1,
  "scenario_type": "stress_race_condition",
  "turn_1_prompt": "Search flight NY to Tokyo",
  "interruption_timestamp_ms": 1420,
  "turn_2_prompt": "Search flight NY to London",
  "audio_stop_latency_ms": null,
  "stale_speech_detected": false,
  "latest_turn_completed": true,
  "final_response_correct": true,
  "post_usable": true,
  "verdict": "PENDING_EXECUTION"
}
```

---

## 7. Evidence Collection Plan (For Final Submission)

1. **Live Screen & Audio Recording (Normal Flow):** Demonstrating standard voice roundtrip with smooth Rime speech.
2. **Live Screen & Audio Recording (Interruption Flow):** Highlighting clean audio cutoff and fast recovery when interrupted.
3. **Stress Test Video Demonstration:** Visualizing real-time token logs as late-arriving results are blocked and discarded.
4. **Timestamped Server & Client Event Logs:** Showing exact millisecond timings from interruption signal to playback halt.
5. **Empirical Latency & Recovery Matrix:** Documenting the 20-trial evaluation run with computed metrics.
6. **Zero Stale Result Verification:** Direct audit logs confirming zero obsolete audio chunk deliveries.
7. **Complete Configuration Transparency:** Documenting exact TTS models, sample rates, buffer sizes, and network setup.
