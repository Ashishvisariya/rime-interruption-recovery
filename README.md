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
Voice communication is intrinsically bidirectional, continuous, and dynamic. Unlike text chat where turns are atomic and discrete, human conversation relies on real-time feedback cues, fast barge-ins, and conversational repairs. A natural voice assistant must support fluid turn invalidation with millisecond-level responsiveness.

---

## 5. Core Technical Claim
> **"When a user interrupts an ongoing voice response and changes their request, the system promptly stops obsolete Rime speech, invalidates/cancels obsolete work, prevents stale results from being spoken, and responds only to the latest request."**

---

## 6. Architecture & Concurrency Model *(Detailed in [docs/architecture.md](file:///c:/INTERNSHIP/rime-interruption-recovery/docs/architecture.md))*

```
Microphone Stream ──▶ Audio Input / VAD ──▶ STT Service ──▶ Turn Manager (Active Turn ID: N)
                                                                │
                                                                ▼
Client Playback ◀── Rime TTS API ◀── Stale Guard Buffer ◀── LLM & Async Tools
```

### Key Concurrency Principles:
1. **Monotonic Turn Isolation:** Every session maintains a strictly increasing `active_turn_id`. All asynchronous tasks, LLM tokens, tool responses, and Rime TTS chunks carry an immutable `turn_id`.
2. **Four-Tier Cancellation:** 
   - *Tier 1 (Client):* Instant audio hardware buffer flush upon barge-in.
   - *Tier 2 (Generation):* `asyncio.Task` cancellation on LLM streams.
   - *Tier 3 (Tools):* In-flight async tool call abort.
   - *Tier 4 (Logical):* Immediate invalidation of superseded turn state.
3. **Core Architectural Axiom:**
   > **"Cancellation is best-effort; stale-result rejection is the correctness guarantee."**  
   Even if an obsolete worker completes late, the Stale Result Guard rejects any payload where `worker.turn_id != active_turn_id`.
4. **Primary Rime TTS Spoken Output:** Expressive, ultra-low latency voice rendering managed through strict lifecycle states (`GENERATING` $\rightarrow$ `READY` $\rightarrow$ `PLAYING` $\rightarrow$ `COMPLETED` / `CANCELLED` / `STOPPED`).

---

## 7. Current Development Status
- [x] **Phase 1: Problem Definition, Project Audit & Safe Foundation** *(Completed)*
- [x] **Phase 2: Acceptance Test, Success Metrics & Evaluation Specification** *(Completed)*
- [x] **Phase 3: System Architecture & Concurrency Design** *(Completed)*
- [x] **Phase 4: FastAPI Backend Foundation** *(Completed)*
- [x] **Phase 5: Real Rime TTS Integration** *(Completed)*
- [x] **Phase 6: Rime Audio Delivery & Playback Pipeline** *(Completed)*
- [x] **Phase 7: Speech-to-Text Integration** *(Completed)*
  - Server-side `GroqSTTService` integrating Groq Whisper (`whisper-large-v3`) via multipart audio upload.
  - Backend `POST /api/voice/transcribe` endpoint with session and turn invariant enforcement.
  - Client-side `MicrophoneRecorder` service capturing microphone input with `MediaRecorder` / `getUserMedia`.
  - Push-to-Talk (PTT) interactive UI button with real-time state feedback and prompt pre-fill.
  - 100% automated test pass rate across backend (39 tests) and frontend (10 tests).
  - *Status:* **Phase 7 — Speech-to-text implemented; LLM and interruption pipeline pending.**
- [ ] **Phase 8: Full Voice Pipeline (LLM -> Tools -> Full Duplex Recovery)** *(Planned)*
- [ ] **Phase 9: Automated Interruption & Recovery Benchmarking** *(Planned)*

---

## 8. Getting Started & Running Locally

### Prerequisites
- Python 3.10+
- Node.js 18+ and npm
- Valid API keys (`RIME_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`)

### Backend Setup & Run
1. Configure environment template:
   ```bash
   cp backend/.env.example backend/.env
   # Edit backend/.env with your API credentials (kept server-side & git-ignored)
   ```
2. Install Python dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
3. Run automated backend test suite (0 external API calls):
   ```bash
   python -m pytest tests/ -v
   ```
4. Start FastAPI server locally:
   ```bash
   uvicorn backend.app.main:app --reload --port 8000
   ```
5. Check health probe:
   ```bash
   curl http://127.0.0.1:8000/health
   # Returns: {"status": "ok"}
   ```

### Frontend Setup & Run
1. Install dependencies & run frontend tests:
   ```bash
   cd frontend
   npm install
   npm test
   ```
2. Start Vite development server:
   ```bash
   npm run dev
   ```
3. Open browser at `http://localhost:5173`.
4. Interact with the voice assistant:
   - **Record Voice (Mic PTT):** Click the Push-to-Talk button, grant microphone permission, speak your prompt, and click to finish recording. Audio is sent to `/api/voice/transcribe` and the transcript is populated directly into the input field.
   - **Advance Turn:** Atomically advances monotonic turn $N \rightarrow N+1$.
   - **Synthesize & Play Rime Audio:** Fetches genuine Rime audio from `/api/voice/tts` and streams via `AudioPlaybackManager`.
   - **Stop / Interrupt Speech:** Immediately halts active audio output, detaches media stream, and logs the interruption event.


