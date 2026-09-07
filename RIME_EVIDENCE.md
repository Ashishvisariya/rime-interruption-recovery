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
- **Phase 4 FastAPI Backend Foundation:** `PASSED`
- **Phase 5 Genuine Rime TTS Integration:** `PASSED`
- **Phase 6 Audio Delivery & Playback Pipeline:** `PASSED`
- **Phase 7+ Full Pipeline & Interruption Benchmarks:** *Pending Phase 7+ Implementation*

---

## 8. Phase 5 Real Rime TTS Integration Evidence

### Integration Specification & Configuration
- **TTS Provider:** Rime Labs
- **Official Endpoint:** `https://users.rime.ai/v1/rime-tts`
- **Model ID:** `coda` (Flagship ultra-expressive conversational model)
- **Speaker:** `celeste`
- **Language:** `en` (English)
- **Audio Output Format:** `mp3` (`audio/mpeg`, 51,360 bytes synthesized for short prompt)
- **Authentication:** Bearer token loaded strictly server-side from `RIME_API_KEY` (never exposed in client, logs, or responses).

### Architecture & Turn-Association Workflow
```
Text Payload
   │
   ▼
[Turn Validation Check: session.validate_turn(turn_id)]
   │
   ▼
[RimeTTSService (Async HTTP POST to https://users.rime.ai/v1/rime-tts)]
   │
   ▼
[Genuine Binary Audio Bytes Received]
   │
   ▼
[Post-Synthesis Invariant Check: session.validate_turn(turn_id)]
   ├── If active ──▶ Expose binary audio to caller (HTTP 200)
   └── If stale  ──▶ Discard audio immediately & reject (HTTP 409 Conflict)
```

---

### REAL RIME VERIFICATION (Single Live Request Evidence)

> [!IMPORTANT]
> **Single Real Request Guarantee:** In strict compliance with API quota preservation rules, exactly ONE real Rime TTS generation request was executed for end-to-end verification. No loops or test suite integrations call the live API.

| Field | Verification Value |
| :--- | :--- |
| **Request Attempted** | `YES` |
| **Verification Timestamp** | `2026-09-07T04:22:12Z` (Local: `2026-09-07 09:52:12 IST`) |
| **Target Endpoint** | `https://users.rime.ai/v1/rime-tts` |
| **Input Sentence** | `"Rime TTS integration test."` |
| **HTTP Status Code** | `200 OK` |
| **Provider** | `rime` |
| **Model ID** | `coda` |
| **Speaker Voice** | `celeste` |
| **Audio Format** | `mp3` |
| **Generated Audio Size** | `51,360 bytes` |
| **Measured Roundtrip Latency** | `2,818.45 ms` |
| **Turn Invariant Validated** | `TRUE (session.validate_turn(turn_id) == True)` |
| **Credential Security** | `ZERO secrets logged, exposed, or committed` |

---

### UNIT TESTS (Mocked Boundary Evidence)

Automated tests in `tests/test_rime_tts.py` use mocked HTTP boundaries to verify system logic without consuming live API quota:
- `test_rime_service_successful_synthesis`: Verifies correct HTTP headers, JSON body schema, and `RimeTTSMetadata` assembly.
- `test_rime_service_custom_overrides`: Verifies model, speaker, format, and language override mechanics.
- `test_rime_service_empty_text_raises`: Verifies immediate client-side validation failure on empty text without network calls.
- `test_rime_service_unconfigured_api_key_raises`: Verifies safe failure when `RIME_API_KEY` is missing.
- `test_rime_service_http_error_handling`: Verifies 401/429/500 upstream error sanitization (no secret leakage).
- `test_rime_service_empty_audio_response_raises`: Verifies detection of empty payload.
- `test_rime_service_timeout_handling`: Verifies clean timeout handling.
- `test_api_tts_missing_session`: Verifies HTTP 404 for unknown session.
- `test_api_tts_invalid_or_superseded_turn`: Verifies HTTP 409 when attempting TTS on superseded turn.
- `test_api_tts_success_with_mocked_service`: Verifies HTTP 200 binary audio delivery and `X-Session-ID`, `X-Turn-ID`, `X-Model-ID`, `X-Speaker` response headers.
- `test_api_tts_mid_generation_turn_invalidation`: Verifies that if a barge-in advances the session while TTS is in flight, the generated audio is strictly discarded and HTTP 409 Conflict is returned.

---

## 9. Phase 6 Audio Playback Pipeline Evidence

### Playback Architecture & State Transitions
The browser client implements `AudioPlaybackManager` (`frontend/src/services/audio.js`), orchestrating browser-native playback with strict turn validation:
- **States Supported:** `IDLE`, `LOADING`, `READY`, `PLAYING`, `STOPPING`, `STOPPED`, `COMPLETED`, `DISCARDED`, `ERROR`.
- **Immediate Barge-in Mechanism (`stopCurrentAudio`):** Pauses audio hardware output, detaches media source, flushes queued buffers, and transitions to `STOPPED` then `IDLE`.
- **Turn Isolation Invariant:** Any audio chunk or queue item where `turn_id < active_turn_id` is immediately rejected (`DISCARDED`).
- **Observability:** Emits structured JSON events (`AUDIO_LOAD_STARTED`, `AUDIO_READY`, `AUDIO_PLAY_STARTED`, `AUDIO_PLAY_COMPLETED`, `AUDIO_STOP_REQUESTED`, `AUDIO_STOPPED`, `AUDIO_DISCARDED`, `AUDIO_PLAYBACK_ERROR`).

### Unit Test Verification (Mocked Browser Environment)
Automated test suite (`frontend/tests/playback_manager.test.mjs`):
1. Audio starts in `IDLE` state: `PASSED`
2. Audio transitions to `PLAYING`: `PASSED`
3. Completion transitions correctly to `COMPLETED` then `IDLE`: `PASSED`
4. `stopCurrentAudio` stops active audio immediately: `PASSED`
5. `stopCurrentAudio` clears obsolete queued audio: `PASSED`
6. Stale turn audio is rejected and discarded: `PASSED`
7. Newer turn audio can play cleanly: `PASSED`
8. Playback errors transition safely to `ERROR` and recover to `IDLE`: `PASSED`
9. Stopping twice is safe and idempotent: `PASSED`
10. Obsolete audio cannot resume automatically after stop: `PASSED`

### Production Build Verification
- Vite production bundle compiled cleanly in `2.11s` (`dist/assets/index-DXSd3qzu.js`, `dist/assets/index-BFJGTF_S.css`).

### Security Verification
- Zero `RIME_API_KEY` or credentials present in frontend client or bundle. All synthesis requests proxy through backend FastAPI gateway.


