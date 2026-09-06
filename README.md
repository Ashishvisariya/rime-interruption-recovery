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
- [ ] **Phase 2: Core Interruption & Cancellation Architecture** *(Planned)*
- [ ] **Phase 3: Rime TTS Streaming & Synthesis Integration** *(Planned)*
- [ ] **Phase 4: Full Voice Pipeline (STT -> LLM -> Rime TTS)** *(Planned)*
- [ ] **Phase 5: Automated Interruption & Recovery Benchmarking** *(Planned)*

---

## 8. Planned Evaluation Approach
The system's core claim will be validated using rigorous automated and live acceptance tests:
- **Interruption Latency:** Measuring time delta between user barge-in speech detection and Rime audio stream cutoff.
- **Stale Response Zero-Tolerance:** Quantifying turn bleed rate across multi-turn rapid-interruption sequences (target: 0 stale audio frames played).
- **Turn Recovery Accuracy:** Verifying that final spoken audio answers the revised query rather than superseded instructions.

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
