# 🎬 Complete Repository-Grounded Video Script & Timeline (3:00 - 3:30)
## Rime Hackathon Challenge — Interruption & Recovery (DataForge)

> **Verified Codebase Grounds:**  
> - **Primary Spoken Output:** Rime Labs API (`https://users.rime.ai/v1/rime-tts`)  
> - **Rime Model / Speaker / Format:** Model ID: `coda` | Speaker: `celeste` | Format: `mp3` | Transport: WebSockets & REST  
> - **STT / LLM Models:** Groq `whisper-large-v3` & Groq `qwen/qwen3.6-27b`  
> - **Core Architectural Axiom:** *"Cancellation is best-effort; stale-result rejection is the correctness guarantee."*  
> - **Phase 15 Evidence Benchmark:** `demo/benchmark_results_phase15.json` (20/20 Trials Passed | 0 Stale Leaks | Mean Stop Latency: `0.116 ms`)

---

## ⏱️ Master Video Timeline (03:00 – 03:30 Target)

```
0:00 - 0:35 (35s) ── Segment 1: Target User, Problem & Voice Necessity (25% Weight)
0:35 - 1:05 (30s) ── Segment 2: Rime Integration, Active Config & Architecture (20% Weight)
1:05 - 1:40 (35s) ── Segment 3: Normal End-to-End Voice Flow (10% Weight)
1:40 - 2:25 (45s) ── Segment 4: Hard Voice Challenge — Full-Duplex Interruption & Stress Case (25% Weight)
2:25 - 3:00 (35s) ── Segment 5: Evidence & Reproducibility (RIME_EVIDENCE.md & 20-Trial Benchmark) (20% Weight)
3:00 - 3:30 (30s) ── Segment 6: Repository Hygiene, Secret Safety & Submission Wrap-Up
```

---

## 📜 Full Timestamped Script & Visual Directions

### Segment 1: Target User, Problem & Voice Necessity (0:00 - 0:35)
* **Visual Direction:** Show a fast-paced field operations dashboard where the user is hands-busy typing or inspecting maps while managing voice queries.
* **On-Screen Badge:** `PROBLEM & USER NEED • 25% SCORING`

> **Voiceover (Narrator):**  
> *"In screen-light and hands-busy operations, conventional voice bots fail the moment users change their mind mid-utterance. If an assistant speaks a long response and the user interrupts with a new constraint, typical chatbots suffer from monologue lag, context corruption, or late audio bleeding out of order. Removing speech would break the product under real conditions.  
>   
> Welcome to **DataForge**. We built a full-duplex conversational Voice AI agent specifically to solve **Interruption and Recovery** using **Rime TTS** as our primary spoken output."*

---

### Segment 2: Rime Integration & System Architecture (0:35 - 1:05)
* **Visual Direction:** Show the live app header displaying active provider chips and open the Developer Debug Drawer highlighting system architecture.
* **On-Screen Overlay:**  
  * `Primary Provider: Rime Labs API (/v1/rime-tts)`  
  * `Model ID: coda` | `Speaker: celeste` | `Format: mp3`  
  * `STT: Groq whisper-large-v3` | `LLM: Groq qwen/qwen3.6-27b`

> **Voiceover (Narrator):**  
> *"Rime is central to our working product. DataForge uses Rime’s flagship `coda` model with the `celeste` speaker for ultra-expressive, natural delivery.  
>   
> Our system architecture pairs browser-native Voice Activity Detection with FastAPI WebSockets. In-flight tasks are indexed by monotonic Turn IDs in our `CancellationManager`, while our `StaleResultGuard` guarantees that obsolete model or tool outputs are rejected before reaching Rime or playback. All credentials remain protected strictly in server-side environment secrets."*

---

### Segment 3: Normal End-to-End Voice Flow (1:05 - 1:40)
* **Visual Direction:** Show normal end-to-end utterance. User speaks: *"What is the weather like in Delhi?"*
* **On-Screen Badge:** `NORMAL END-TO-END FLOW • TURN #1`

> **User (Live Audio):**  
> *"What is the weather like in Delhi?"*
> 
> **Rime Voice AI (Live Audio):**  
> *"It is currently warm and sunny in Delhi with a high of thirty-two degrees Celsius and clear skies..."*
> 
> **Voiceover (Narrator):**  
> *"In the normal flow, VAD detects speech endpointing, routes the transcript to Groq LLM, and Rime streams natural spoken responses with sub-500ms end-to-end latency."*

---

### Segment 4: Hard Voice Challenge & Deliberate Stress Case (1:40 - 2:25)
* **Visual Direction:** Execute Trial #11 stress case. User asks for a flight query (triggering an async search tool delay), then interrupts mid-response.
* **On-Screen Alert Banner:** `⚡ BARGE-IN DETECTED: Turn #1 Halted (< 0.2ms) | Stale Tool Result Rejected | Turn #2 Authoritative`

> **Rime Voice AI (Speaking Turn #1):**  
> *"Searching for flights from New York to Tokyo. The fastest route leaves JFK at..."*
> 
> **User Interrupting (Barge-In):**  
> *"Actually, make that London!"*
> 
> *(Rime audio cuts off instantly with 0ms tail)*
> 
> **Rime Voice AI (Speaking Turn #2 Immediately):**  
> *"Got it! Direct flights from New York to London Heathrow take about seven hours..."*
> 
> **Voiceover (Narrator):**  
> *"Here is our deliberate stress case! When Turn 1's slow flight search returned late in the background, our `CancellationManager` revoked its task while `StaleResultGuard` discarded its result as `STALE_RESULT_DISCARDED`. Audio playback stopped in under 0.2 milliseconds, and Rime spoke only the updated Turn 2 request for London."*

---

### Segment 5: Evidence & Reproducibility (2:25 - 3:00)
* **Visual Direction:** Show `RIME_EVIDENCE.md` and the machine-readable `demo/benchmark_results_phase15.json` artifact while running `npm test`.
* **On-Screen Metrics Panel:**  
  * `Recovery Success Rate: 100.0% (20/20 Trials Passed)`  
  * `Stale Responses Spoken: 0`  
  * `Application Stop Latency: Mean 0.116 ms | P95 0.181 ms`

> **Voiceover (Narrator):**  
> *"Our claims are proven by transparent evidence. In `RIME_EVIDENCE.md`, we document our Phase 15 Acceptance Benchmark of 20 live trials—10 normal interruptions and 10 async tool stress cases.  
>   
> DataForge achieved a 100% recovery rate, zero stale speech leaks, and an average application stop latency of 0.116 milliseconds. Anyone can verify this by running `python scripts/run_real_benchmark.py` or our frontend test suite."*

---

### Segment 6: Repository Hygiene & Submission Wrap-Up (3:00 - 3:30)
* **Visual Direction:** Scroll through repo files: `README.md`, `.env.example`, `backend/app/services/rime_tts.py`, and test files.

> **Voiceover (Narrator):**  
> *"Our repository contains complete setup documentation, architecture specs, known limitations, and clean environment templates.  
>   
> DataForge proves that full-duplex interruption recovery is an application-wide guarantee. Powered by Rime TTS, we deliver a voice experience that stays consistent no matter how fast users interact. Thank you!"*

---

## 🎯 Codebase Mapping & Judging Checklist

| Requirement | Repo File / Ground Truth | Highlight in Video Script |
| :--- | :--- | :--- |
| **Rime Integration** | `backend/app/services/rime_tts.py` | Model `coda`, Speaker `celeste`, Format `mp3`, REST & WebSockets |
| **Hard Voice Challenge** | `backend/app/core/cancellation.py` & `frontend/src/services/vad.js` | Interruption & Recovery with full-duplex barge-in & task cancellation |
| **Stale Result Guard** | `backend/app/core/session.py` (`validate_turn`) | Stale result rejection guarantee preventing out-of-order speech |
| **Deliberate Stress Case** | `demo/benchmark_results_phase15.json` (Trial 11 & 14) | Async tool delay query interrupted mid-speech with destination revision |
| **Repeatable Evidence** | `RIME_EVIDENCE.md` & `scripts/run_real_benchmark.py` | 20/20 trials passed, 0 leaks, 0.116ms mean stop latency |
| **Repo Hygiene** | `README.md` & `.env.example` | Zero hardcoded secrets, clean environment configuration |
