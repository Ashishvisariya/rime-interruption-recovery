# Voice AI Assistant with Interruption & Recovery
*DataForge 2026 Rime Hackathon Submission*

## 1. Project Overview & Name
**Project Name:** Voice AI Assistant with Interruption & Recovery  
**Primary TTS Provider:** Rime Labs (Ultra-low latency, expressive conversational voice output)

---

## 2. Target User
Users engaging in high-velocity, real-time spoken interactions (e.g., dispatch operators, interactive customer assistance, hands-free field specialists, and voice-first personal productivity workflows) where pauses, corrections, mid-sentence topic shifts, and interruptions are natural and frequent.

---

## 3. The Problem
Conventional voice assistants suffer from high turn rigidity and "barge-in" failure modes:
- **Speech Pipeline Lag:** When a user interrupts an ongoing AI monologue, current systems often continue rendering or streaming stale TTS audio for hundreds of milliseconds.
- **Stale Computation / Race Conditions:** Stale LLM inferences and pending tool calls from invalidated turns continue in the background and pollute subsequent context or trigger outdated responses.
- **Cognitive Friction:** Users are forced to listen to irrelevant answers or explicitly wait for completion before correcting their prompt.

---

## 4. Why Voice is Necessary
Voice communication is intrinsically bidirectional, continuous, and dynamic. Unlike text chat where turns are atomic and strictly discrete, human conversation relies on real-time feedback cues, fast barge-ins, and conversational repairs. A truly natural voice assistant must support fluid turn invalidation with millisecond-level responsiveness.

---

## 5. Core Technical Claim
> **"When a user interrupts an ongoing voice response and changes their request, the system promptly stops obsolete Rime speech, invalidates/cancels obsolete work, prevents stale results from being spoken, and responds only to the latest request."**

---

## 6. High-Level Intended Architecture *(Planned)*

```
                       ┌───────────────────────────────────────────────┐
                       │               Client / Browser                │
                       │   (Microphone Stream & Real-time Playback)    │
                       └───────────────────────┬───────────────────────┘
                                               │ Full-duplex WebSocket (Planned)
                                               ▼
                       ┌───────────────────────────────────────────────┐
                       │          Voice Session Orchestrator           │
                       │      (Interruption & Turn State Engine)       │
                       └───────┬───────────────┬───────────────┬───────┘
                               │               │               │
                 [Cancel Stale]│               │               │[Audio Stream]
                               ▼               ▼               ▼
                 ┌───────────────────┐ ┌───────────────┐ ┌───────────────────┐
                 │    Cancellation   │ │   STT & LLM   │ │   Rime TTS API    │
                 │   Engine / Tasks  │ │   Pipelines   │ │ (Primary Spoken   │
                 │     (Planned)     │ │   (Planned)   │ │  Output Engine)   │
                 └───────────────────┘ └───────────────┘ └───────────────────┘
```

### Architectural Modules:
1. **Voice Session Manager:** Maintains turn IDs, active generation tokens, and lifecycle state. *(Planned)*
2. **Interruption & Cancellation Engine:** Tracks active asynchronous tasks (STT, LLM tokens, TTS audio streams) and immediately issues abort signals upon barge-in detection. *(Planned)*
3. **Stale Guard Buffer:** Validates turn sequence tokens before any synthesized audio chunk is scheduled or dispatched to the client playback buffer. *(Planned)*
4. **Rime TTS Service:** Streams ultra-low latency audio directly to the user. *(Planned / Integration Ready)*

---

## 7. Current Development Status
- [x] **Phase 1: Problem Definition, Project Audit & Safe Foundation** *(Completed)*
  - Problem framing & formal acceptance criteria established.
  - Safe environment configuration and secret isolation verified.
  - Minimal FastAPI application foundation with health checks established.
  - Baseline testing suite implemented.
- [x] **Phase 2: Acceptance Test, Success Metrics & Evaluation Specification** *(Completed)*
  - Detailed 10-step acceptance test defined in [docs/acceptance-test.md](file:///c:/INTERNSHIP/rime-interruption-recovery/docs/acceptance-test.md).
  - Concrete Pass/Fail criteria and 5 quantifiable metrics specified.
  - Normal and stress race-condition test scenarios documented.
  - Repeatability protocol and empirical trial log template established.
  - *Status:* **Phase 2 — Evaluation specification complete; implementation pending.**
- [ ] **Phase 3: Core Interruption & Cancellation Architecture** *(Planned)*
- [ ] **Phase 4: Rime TTS Streaming & Synthesis Integration** *(Planned)*
- [ ] **Phase 5: Full Voice Pipeline (STT -> LLM -> Rime TTS)** *(Planned)*
- [ ] **Phase 6: Automated Interruption & Recovery Benchmarking** *(Planned)*

---

## 8. Evaluation & Acceptance Criteria

### What is Being Tested:
The assistant's ability to gracefully handle mid-turn interruptions: immediately halting obsolete Rime speech, aborting or invalidating stale background tasks, suppressing outdated results, and responding solely to the user's revised request.

### Why Interruption is Difficult in Voice Systems:
Unlike discrete text exchanges, voice involves overlapping asynchronous pipelines (streaming ASR, token-by-token LLM generation, streaming TTS synthesis, and client audio buffer queues). A mid-turn interruption creates race conditions where delayed responses can collide with new requests unless guarded by turn-version isolation.

### Key Evaluation Metrics *(Detailed in [docs/acceptance-test.md](file:///c:/INTERNSHIP/rime-interruption-recovery/docs/acceptance-test.md))*:
- **Interruption-to-Audio-Stop Latency:** Target $< 250$ ms (*Status: NOT YET MEASURED*).
- **Stale Response Count:** Target $0$ leaks (*Status: NOT YET MEASURED*).
- **Recovery Success Rate:** Target $\ge 95\%$ across 20 trials (*Status: NOT YET MEASURED*).
- **Latest-Turn Correctness:** Target $100\%$ (*Status: NOT YET MEASURED*).
- **Post-Interruption Usability:** Target $100\%$ operational uptime (*Status: NOT YET MEASURED*).

---

## 9. Getting Started (Phase 1 Baseline)

### Prerequisites
- Python 3.10+
- Valid API keys (`RIME_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`)

### Setup & Run
1. Configure environment:
   ```bash
   cp .env.example backend/.env
   # Edit backend/.env with your API credentials
   ```
2. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
3. Run test suite:
   ```bash
   pytest tests/test_phase1.py -v
   ```
4. Start backend:
   ```bash
   uvicorn backend.app.main:app --reload --port 8000
   ```
