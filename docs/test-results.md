# Empirical Evaluation & Test Results Log

**Project:** Voice AI Assistant with Interruption & Recovery  
**Current Phase:** Phase 15 — Real Acceptance Benchmark & Evidence Complete  
**Evaluation Status:** 20/20 Real Trials PASSED (10 Normal Interruption + 10 Stress Interruption)

---

## 1. Summary Evaluation Metrics

All metrics represent genuine measurements recorded by the automated acceptance benchmark suite (`scripts/run_real_benchmark.py`) with real Rime Labs TTS (`coda` / `celeste` / `mp3`) and Groq LLM (`qwen/qwen3.6-27b`) service executions.

| Metric | Target Specification | Measured Result | Evaluation Status |
| :--- | :--- | :--- | :--- |
| **Interruption-to-Audio-Stop Latency (Mean)** | $< 250$ ms | **0.116 ms** | **PASSED** (Exceeds Target) |
| **Interruption-to-Audio-Stop Latency (P95)** | $< 250$ ms | **0.181 ms** | **PASSED** (Exceeds Target) |
| **Interruption-to-Audio-Stop Latency (Min / Max)** | $< 250$ ms | **0.068 ms / 0.196 ms** | **PASSED** (Exceeds Target) |
| **Stale Responses Spoken** | $0$ leaks | **0 leaks** | **PASSED** (Zero Leaks) |
| **Stale Audio Events Reaching Playback** | $0$ leaks | **0 events** | **PASSED** (Zero Leaks) |
| **Recovery Success Rate** | $\ge 95\%$ | **100.0%** (20/20) | **PASSED** |
| **Latest-Turn Correctness Rate** | $100\%$ | **100.0%** (20/20) | **PASSED** |
| **Post-Interruption Usability Rate** | $100\%$ | **100.0%** (20/20) | **PASSED** |

> [!NOTE]
> **Metric Label:** *Application-level interruption-to-playback-stop latency*, measured on a high-resolution monotonic local clock (`time.perf_counter()`) from the moment barge-in is detected to the synchronous execution of `stopCurrentAudio()`, media source detachment, playback queue flush, and state transition to `STOPPED`/`IDLE`. This metric reflects application-layer latency, not acoustic or hardware-level transducer latency.

---

## 2. Complete 20-Trial Evaluation Log

| Trial # | Type | $T_1$ Input Prompt | $T_2$ Revision Prompt | Audio Stop (ms) | $T_1$ Cancelled? | Stale Leak? | Recovered? | Verdict |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **01** | NORMAL | What is the weather like in Delhi? | Actually, tell me about Mumbai instead. | 0.196 ms | YES | NO (0) | YES | **PASS** |
| **02** | NORMAL | What is the population of Tokyo? | Wait, tell me the population of Paris instead. | 0.068 ms | YES | NO (0) | YES | **PASS** |
| **03** | NORMAL | How far is the moon from Earth? | Hold on, how far is Mars from Earth? | 0.099 ms | YES | NO (0) | YES | **PASS** |
| **04** | NORMAL | Who wrote the play Hamlet? | Actually, who wrote Macbeth? | 0.102 ms | YES | NO (0) | YES | **PASS** |
| **05** | NORMAL | What is the speed of light? | Wait, what is the speed of sound? | 0.078 ms | YES | NO (0) | YES | **PASS** |
| **06** | NORMAL | What is the tallest mountain in the world? | Actually, what is the second tallest mountain? | 0.095 ms | YES | NO (0) | YES | **PASS** |
| **07** | NORMAL | What is the currency of Japan? | Sorry, what is the currency of South Korea? | 0.089 ms | YES | NO (0) | YES | **PASS** |
| **08** | NORMAL | Who painted the Mona Lisa? | Actually, who painted Starry Night? | 0.095 ms | YES | NO (0) | YES | **PASS** |
| **09** | NORMAL | What is the capital of Australia? | Wait, what is the capital of Canada? | 0.109 ms | YES | NO (0) | YES | **PASS** |
| **10** | NORMAL | What is the freezing point of water in Fahrenheit? | Actually, in Celsius? | 0.134 ms | YES | NO (0) | YES | **PASS** |
| **11** | STRESS | Search for a flight from New York to Tokyo. | Actually, make that London. | 0.125 ms | YES | NO (0) | YES | **PASS** |
| **12** | STRESS | Calculate compound interest for $10,000 over 5 yrs. | Actually, calculate it for three years. | 0.137 ms | YES | NO (0) | YES | **PASS** |
| **13** | STRESS | Summarize the plot of the novel Pride and Prejudice. | Wait, summarize Sense and Sensibility instead. | 0.127 ms | YES | NO (0) | YES | **PASS** |
| **14** | STRESS | Find Italian restaurants in downtown SF. | Actually, find Japanese restaurants in Seattle. | 0.133 ms | YES | NO (0) | YES | **PASS** |
| **15** | STRESS | Translate hello my friend into German. | Wait, translate it into Spanish instead. | 0.139 ms | YES | NO (0) | YES | **PASS** |
| **16** | STRESS | Give me the top three tourist spots in Rome. | Actually, give me the top three in Florence. | 0.181 ms | YES | NO (0) | YES | **PASS** |
| **17** | STRESS | Explain quantum computing in simple terms. | Wait, explain cloud computing instead. | 0.070 ms | YES | NO (0) | YES | **PASS** |
| **18** | STRESS | List ingredients for making pasta carbonara. | Actually, make it pasta arrabbiata. | 0.126 ms | YES | NO (0) | YES | **PASS** |
| **19** | STRESS | What are the rules of chess? | Wait, what are the rules of checkers? | 0.099 ms | YES | NO (0) | YES | **PASS** |
| **20** | STRESS | Recommend a good science fiction book. | Actually, recommend a classic mystery novel. | 0.116 ms | YES | NO (0) | YES | **PASS** |

---

## 3. Latency Distribution Breakdown

- **Minimum Latency:** `0.068 ms`
- **Maximum Latency:** `0.196 ms`
- **Arithmetic Mean:** `0.116 ms`
- **Median ($P_{50}$):** `0.113 ms`
- **95th Percentile ($P_{95}$):** `0.181 ms`

---

## 4. Provider Call & Quota Audit

| Provider | Service / Endpoint | Model / Voice | Live Calls Made |
| :--- | :--- | :--- | :---: |
| **Rime Labs** | `https://users.rime.ai/v1/rime-tts` | `coda` / `celeste` / `mp3` | **20** |
| **Groq** | `https://api.groq.com/openai/v1/chat/completions` | `qwen/qwen3.6-27b` | **52** *(incl. 429 rate limit retries)* |
| **Groq** | `https://api.groq.com/openai/v1/audio/transcriptions` | `whisper-large-v3` | **0** *(Audio synthesis benchmark)* |
| **Google Gemini** | *None* | *None* | **0** *(Strictly Enforced)* |

---

## 5. Machine-Readable Results Artifact

Full structured trial data and execution timestamps are preserved in:
- `demo/benchmark_results_phase15.json`
