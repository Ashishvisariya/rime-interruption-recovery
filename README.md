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
  - Direct integration with genuine Rime Labs TTS API (`https://users.rime.ai/v1/rime-tts`).
  - Flagship `coda` model and `celeste` speaker voice with MP3/WAV audio output.
  - Safe credential loading from `RIME_API_KEY` with zero client exposure.
  - Two-phase monotonic turn validation (pre-dispatch and post-return) discarding obsolete speech.
  - Dedicated REST endpoint `POST /api/voice/tts` with binary audio response and turn metadata headers.
  - 100% automated test suite pass rate with mocked HTTP boundaries (zero quota drain).
  - Verified with single real live synthesis request.
  - *Status:* **Phase 5 — Real Rime TTS integration implemented; interruption pipeline pending.**
- [ ] **Phase 6: Full Voice Pipeline (STT -> LLM -> Tools -> Rime TTS)** *(Planned)*
- [ ] **Phase 7: Automated Interruption & Recovery Benchmarking** *(Planned)*

---

## 8. Backend Foundation & Getting Started

### Prerequisites
- Python 3.10+
- Valid API keys (`RIME_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`)

### Setup & Run
1. Configure environment template:
   ```bash
   cp backend/.env.example backend/.env
   # Edit backend/.env with your API credentials (kept server-side & git-ignored)
   ```
2. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
3. Run automated test suite (mocked HTTP layer, 0 API quota used):
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
6. Test Rime TTS endpoint:
   ```bash
   # 1. Initialize a session
   curl -X POST http://127.0.0.1:8000/api/voice/session \
     -H "Content-Type: application/json" \
     -d '{"session_id": "test_sess"}'

   # 2. Advance to Turn 1
   curl -X POST http://127.0.0.1:8000/api/voice/session/test_sess/turn \
     -H "Content-Type: application/json" \
     -d '{"prompt": "Hello"}'

   # 3. Synthesize speech for Turn 1 (returns binary audio/mpeg)
   curl -X POST http://127.0.0.1:8000/api/voice/tts \
     -H "Content-Type: application/json" \
     -d '{"session_id": "test_sess", "turn_id": 1, "text": "Hello, this is Rime speech."}' \
     --output speech.mp3
   ```

