# Rime Hackathon Demo Operator Guide & Architecture Verification

> **Project:** Voice AI Assistant with Interruption & Recovery  
> **Core Claim:** *"When a user interrupts an active voice response and changes their request, obsolete Rime speech stops promptly, obsolete work/results are not spoken, and the final response corresponds only to the latest request."*

---

## 1. What the Demo Proves

The demonstration proves full-duplex conversational voice AI with real-time barge-in handling and deterministic state recovery:
1. **Immediate Audio Interruption:** Browser-native VAD detects speech during playback and halts HTML5 Audio immediately (< 1ms).
2. **Obsolete Task Invalidation:** Background Groq LLM inference and pending Rime synthesis tasks for superseded turns are actively cancelled.
3. **Stale Audio Rejection:** Any asynchronous synthesis packets arriving from superseded turns are rejected and prevented from queuing or playing.
4. **Authoritative Turn Recovery:** Only the user's latest turn ($T_{latest}$) is processed, synthesized via Rime TTS, and spoken to the user.

---

## 2. Required Environment Variables

Configure your `.env` file in the `backend/` directory:

```bash
# Required API Keys
RIME_API_KEY="your_rime_api_key_here"
GROQ_API_KEY="your_groq_api_key_here"

# Runtime Configuration
RIME_SPEAKER="celeste"
RIME_MODEL_ID="coda"
RIME_AUDIO_FORMAT="mp3"
RIME_SAMPLE_RATE="22050"
GROQ_MODEL="llama-3.3-70b-versatile"
GROQ_STT_MODEL="whisper-large-v3"
PORT="8000"
```

> **Security Note:** Keys are strictly read server-side. No API keys, tokens, or authorization headers are ever transmitted to the frontend or exposed in logs.

---

## 3. How to Start Backend

From the repository root:

```bash
# Activate virtual environment if configured
# pip install -r backend/requirements.txt (if first run)

# Run FastAPI WebSocket backend
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend will start at: `https://rime-interruption-recovery-1-tiw6.onrender.com` with WebSocket endpoint at `ws://localhost:8000/ws/session`.

---

## 4. How to Start Frontend

In a separate terminal:

```bash
cd frontend

# Install dependencies (if first run)
npm install

# Start Vite development server
npm run dev
```

Open browser at: `https://rime-interruption-recovery-s5f7.onrender.com/`

---

## 5. Exact Normal Demo Sequence (4–5 Minutes)

### Scenario: *Weather Inquiry Interruption*

1. **Initialize Session:**
   - Open the web interface. Ensure connection badge shows **`CONNECTED`**.
   - VAD indicator will show **`VAD Active (Listening)`** with microphone energy bar.
2. **Turn 1 (T1 Prompt):**
   - Click the **`Preset 1: Normal (Delhi -> Mumbai)`** button or speak:
     > *"What is the weather like in Delhi?"*
   - Assistant transitions to `THINKING` $\rightarrow$ `SPEAKING`.
   - Rime audio begins playing aloud via speaker `celeste`.
3. **Trigger Barge-In (Interruption):**
   - While the assistant is actively speaking, speak into the mic or click **`⚡ Trigger Barge-In (User Interruption)`**:
     > *"Actually, tell me about Mumbai instead."*
4. **Observe Execution:**
   - Turn 1 audio stops immediately.
   - Status badge transitions to **`INTERRUPTING`** $\rightarrow$ **`T#2 (AUTHORITATIVE)`**.
   - T1 marked as **`INTERRUPTED / CANCELLED`**.
   - Assistant processes T2 and speaks weather information for Mumbai.

---

## 6. Exact Stress Demo Sequence

### Scenario: *Search Query Interruption & Stale Discard*

1. Click **`Preset 2: Stress (Flight NYC -> London)`** or speak:
   > *"Search for a flight from New York to Tokyo."*
2. Assistant starts processing Turn 1.
3. Immediately interrupt with:
   > *"Actually, make that London."*
4. Observe that any delayed T1 results/audio are rejected with `STALE RESULT REJECTED` in the audit log, and only the London flight response (T2) is synthesized and played.

---

## 7. What the Judge Should Observe

| Visual Indicator | Expected Behavior During Interruption |
| :--- | :--- |
| **Playback Audio** | Cuts off cleanly and instantly; no lingering words or trailing audio. |
| **Interruption Banner** | High-visibility amber banner appears showing stop latency ($\approx 0.12\text{ ms}$). |
| **Audit Stream** | Logs `USER INTERRUPTED`, `AUDIO STOPPED (IMMEDIATE)`, and `STALE RESULT REJECTED`. |
| **Active Turn Tag** | Monotonically increments from `T#1` to `T#2` tagged **`AUTHORITATIVE`**. |
| **Response Card** | Displays only Turn 2's transcript and assistant response. |

---

## 8. Verified Phase 15 Benchmark Results

Empirical results from the 20-trial automated acceptance benchmark (`demo/benchmark_results_phase15.json`):

```
============================================================
           EMPIRICAL BENCHMARK SUMMARY (20 TRIALS)
============================================================
Total Benchmark Trials:                     20 / 20
Trials Passed:                              20 / 20 (100.0%)
Trials Failed:                               0 / 20 (0.0%)
------------------------------------------------------------
Stale Responses Spoken:                      0
Stale Audio Leaks:                           0
Recovery Rate:                             100.0%
Latest-Turn Correctness:                   100.0%
------------------------------------------------------------
Application-level Interruption-to-Playback-Stop Latency:
  Mean:                                     0.116 ms
  P50:                                      0.113 ms
  P95:                                      0.129 ms
  P99:                                      0.138 ms
  Min:                                      0.104 ms
  Max:                                      0.141 ms
============================================================
```

> **Latency Definition:** Measured strictly as *Application-level interruption-to-playback-stop latency* (memory and audio buffer cancellation time within the runtime).

---

## 9. Rime Runtime Configuration

- **Provider:** Rime Labs (Fast, Expressive Neural TTS)
- **Model:** `coda`
- **Speaker:** `celeste`
- **Audio Format:** `mp3` (22050 Hz)
- **Architecture Principle:** *"Cancellation is best-effort; stale-result rejection is the correctness guarantee."*

---

## 10. Known Limitations & Operating Boundaries

1. **Acoustic Echo Cancellation (AEC):** For best results during microphone-driven voice demo, use headphones or ensure system AEC is enabled so speaker playback does not re-trigger the browser microphone.
2. **Provider-side Cancellation:** External upstream HTTP calls to cloud TTS endpoints may run to completion on the provider's servers; our architecture guarantees zero audio from superseded turns is ever played or retained.
3. **In-Memory Session Storage:** Active sessions and turn history are maintained in server memory for the duration of the WebSocket connection.
