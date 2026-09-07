import React, { useState, useEffect } from 'react';
import { defaultPlaybackManager, PlaybackState, AudioEventType } from './services/audio.js';
import { defaultApiClient } from './services/api.js';
import { defaultRecorder, RecorderState } from './services/recorder.js';
import SpeakingIndicator from './components/SpeakingIndicator.jsx';
import Status from './components/Status.jsx';
import VoiceButton from './components/VoiceButton.jsx';
import Transcript from './components/Transcript.jsx';

export const AgentState = {
  IDLE: 'IDLE',
  LISTENING: 'LISTENING',
  TRANSCRIBING: 'TRANSCRIBING',
  THINKING: 'THINKING',
  SYNTHESIZING: 'SYNTHESIZING',
  PLAYING: 'PLAYING',
  ERROR: 'ERROR',
};

export default function App() {
  const [sessionId, setSessionId] = useState('');
  const [activeTurnId, setActiveTurnId] = useState(0);
  const [playbackState, setPlaybackState] = useState(PlaybackState.IDLE);
  const [agentState, setAgentState] = useState(AgentState.IDLE);
  const [currentAudio, setCurrentAudio] = useState(null);
  const [events, setEvents] = useState([]);
  const [ttsText, setTtsText] = useState('What is the weather like today?');
  const [conversationTurns, setConversationTurns] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [backendStatus, setBackendStatus] = useState(null);

  // Initialize session and subscribe to Playback Manager & Recorder events
  useEffect(() => {
    // 1. Subscribe to playback state changes
    const unsubState = defaultPlaybackManager.onStateChange((state, prevState, audio) => {
      setPlaybackState(state);
      setCurrentAudio(audio);
      if (state === PlaybackState.PLAYING) {
        setAgentState(AgentState.PLAYING);
      } else if (state === PlaybackState.IDLE && !isRecording && !isProcessing) {
        setAgentState(AgentState.IDLE);
      }
    });

    // 2. Subscribe to structured audio events
    const unsubEvents = defaultPlaybackManager.onEvent((evt) => {
      setEvents((prev) => [evt, ...prev.slice(0, 49)]);
    });

    // 3. Subscribe to microphone recorder state changes
    const unsubRecorder = defaultRecorder.onStateChange((state) => {
      const rec = state === RecorderState.RECORDING;
      setIsRecording(rec);
      if (rec) {
        setAgentState(AgentState.LISTENING);
      } else if (state === RecorderState.ERROR) {
        setIsRecording(false);
        setIsProcessing(false);
        setAgentState(AgentState.ERROR);
      }
    });

    // 4. Initialize backend session
    async function init() {
      try {
        const rootRes = await fetch('http://127.0.0.1:8000/').then((r) => r.json());
        setBackendStatus(rootRes);

        const sess = await defaultApiClient.createSession();
        setSessionId(sess.session_id);
        setActiveTurnId(sess.active_turn_id);
        defaultPlaybackManager.setSession(sess.session_id, sess.active_turn_id);
      } catch (err) {
        console.error('Session initialization error:', err);
      }
    }
    init();

    return () => {
      unsubState();
      unsubEvents();
      unsubRecorder();
    };
  }, []);

  // Handler: Advance monotonic turn manually
  const handleAdvanceTurn = async () => {
    if (!sessionId) return;
    try {
      const updatedSess = await defaultApiClient.createTurn(sessionId, ttsText);
      setActiveTurnId(updatedSess.active_turn_id);
      defaultPlaybackManager.setActiveTurn(updatedSess.active_turn_id);
      setEvents((prev) => [
        {
          event_type: 'MANUAL_TURN_ADVANCED',
          timestamp_ms: Date.now(),
          session_id: sessionId,
          turn_id: updatedSess.active_turn_id,
          state: playbackState,
          details: { new_turn_id: updatedSess.active_turn_id },
        },
        ...prev.slice(0, 49),
      ]);
    } catch (err) {
      console.error('Failed to advance turn:', err);
    }
  };

  // Handler: Push-to-Talk Full Pipeline (Microphone -> STT -> LLM -> Rime TTS -> Playback)
  const handleToggleRecord = async () => {
    if (isRecording) {
      // 1. Finish microphone recording
      try {
        const recResult = await defaultRecorder.stopRecording();
        if (!recResult || !recResult.blob) return;

        setIsProcessing(true);
        setAgentState(AgentState.TRANSCRIBING);

        setEvents((prev) => [
          {
            event_type: 'MIC_RECORDING_COMPLETED',
            timestamp_ms: Date.now(),
            session_id: sessionId,
            turn_id: activeTurnId,
            state: playbackState,
            details: { durationMs: recResult.durationMs, bytes: recResult.blob.size },
          },
          ...prev.slice(0, 49),
        ]);

        // 2. Call End-to-End Voice Agent Orchestrator
        setAgentState(AgentState.THINKING);
        const { blob, headers } = await defaultApiClient.processAgentAudio({
          audioBlob: recResult.blob,
          sessionId,
        });

        // 3. Update active turn from response headers
        const turnId = headers.turnId;
        setActiveTurnId(turnId);
        defaultPlaybackManager.setActiveTurn(turnId);

        // Record turn conversation history
        const turnData = {
          turnId,
          userPrompt: headers.userTranscript,
          assistantResponse: headers.assistantResponse,
          speaker: headers.speaker || 'celeste',
          modelId: headers.modelId || 'coda',
          latencyMs: headers.latencyMs,
        };
        setConversationTurns((prev) => [...prev, turnData]);
        setTtsText(headers.assistantResponse);

        setEvents((prev) => [
          {
            event_type: 'AGENT_ORCHESTRATION_SUCCESS',
            timestamp_ms: Date.now(),
            session_id: headers.sessionId,
            turn_id: turnId,
            state: playbackState,
            details: {
              transcript: headers.userTranscript,
              response: headers.assistantResponse,
              llm_model: headers.llmModel,
              speaker: headers.speaker,
              audio_bytes: headers.audioBytesLength,
              latency_ms: headers.latencyMs,
            },
          },
          ...prev.slice(0, 49),
        ]);

        // 4. Play synthesized Rime speech via PlaybackManager
        setAgentState(AgentState.PLAYING);
        await defaultPlaybackManager.playAudio({
          sessionId: headers.sessionId,
          turnId: turnId,
          audioSource: blob,
          metadata: {
            speaker: headers.speaker || 'celeste',
            modelId: headers.modelId || 'coda',
            format: headers.audioFormat || 'mp3',
            bytes: headers.audioBytesLength,
          },
        });
      } catch (err) {
        console.error('Voice Agent orchestration error:', err);
        setAgentState(AgentState.ERROR);
        alert(`Voice Agent Error: ${err.message}`);
      } finally {
        setIsProcessing(false);
      }
    } else {
      // Start recording
      try {
        await defaultRecorder.startRecording();
      } catch (err) {
        console.error('Microphone access error:', err);
        setAgentState(AgentState.ERROR);
        alert(`Microphone Error: ${err.message}`);
      }
    }
  };

  // Handler: Text-based Voice Agent Pipeline (Text -> LLM -> Rime TTS -> Playback)
  const handleProcessText = async () => {
    if (!sessionId || !ttsText.trim()) return;

    setIsLoading(true);
    setIsProcessing(true);
    setAgentState(AgentState.THINKING);

    try {
      const { blob, headers } = await defaultApiClient.processAgentText({
        text: ttsText,
        sessionId,
      });

      const turnId = headers.turnId;
      setActiveTurnId(turnId);
      defaultPlaybackManager.setActiveTurn(turnId);

      // Record conversation turn
      const turnData = {
        turnId,
        userPrompt: ttsText,
        assistantResponse: headers.assistantResponse,
        speaker: headers.speaker || 'celeste',
        modelId: headers.modelId || 'coda',
        latencyMs: headers.latencyMs,
      };
      setConversationTurns((prev) => [...prev, turnData]);

      setEvents((prev) => [
        {
          event_type: 'AGENT_TEXT_ORCHESTRATION_SUCCESS',
          timestamp_ms: Date.now(),
          session_id: headers.sessionId,
          turn_id: turnId,
          state: playbackState,
          details: {
            prompt: ttsText,
            response: headers.assistantResponse,
            llm_model: headers.llmModel,
            speaker: headers.speaker,
            audio_bytes: headers.audioBytesLength,
            latency_ms: headers.latencyMs,
          },
        },
        ...prev.slice(0, 49),
      ]);

      // Play synthesized Rime audio
      setAgentState(AgentState.PLAYING);
      await defaultPlaybackManager.playAudio({
        sessionId: headers.sessionId,
        turnId: turnId,
        audioSource: blob,
        metadata: {
          speaker: headers.speaker || 'celeste',
          modelId: headers.modelId || 'coda',
          format: headers.audioFormat || 'mp3',
          bytes: headers.audioBytesLength,
        },
      });
    } catch (err) {
      console.error('Agent text processing error:', err);
      setAgentState(AgentState.ERROR);
      alert(`Voice Agent Error: ${err.message}`);
    } finally {
      setIsLoading(false);
      setIsProcessing(false);
    }
  };

  // Handler: Stop audio immediately
  const handleStopAudio = () => {
    defaultPlaybackManager.stopCurrentAudio('user_manual_stop');
    setAgentState(AgentState.IDLE);
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="logo-badge">
          <span className="logo-dot"></span>
          <h1>Rime Voice AI Assistant</h1>
        </div>
        <p className="app-tagline">
          Phase 10 — End-to-End Voice Agent Orchestration (Groq Whisper STT &bull; Groq LLM &bull; Rime TTS)
        </p>
      </header>

      <main className="app-main">
        <SpeakingIndicator
          state={playbackState}
          agentState={agentState}
          currentAudio={currentAudio}
        />

        <Status
          sessionId={sessionId}
          activeTurnId={activeTurnId}
          state={playbackState}
          agentState={agentState}
          metadata={currentAudio?.metadata}
          backendStatus={backendStatus}
        />

        <VoiceButton
          state={playbackState}
          agentState={agentState}
          onAdvanceTurn={handleAdvanceTurn}
          onProcessText={handleProcessText}
          onStop={handleStopAudio}
          onToggleRecord={handleToggleRecord}
          isRecording={isRecording}
          isProcessing={isProcessing}
          isLoading={isLoading}
          activeTurnId={activeTurnId}
        />

        <Transcript
          events={events}
          text={ttsText}
          setText={setTtsText}
          conversationTurns={conversationTurns}
        />
      </main>

      <footer className="app-footer">
        <span>DataForge 2026 Rime Hackathon &bull; Phase 10 Voice Orchestration</span>
      </footer>
    </div>
  );
}
