import React, { useState, useEffect } from 'react';
import { defaultPlaybackManager, PlaybackState, AudioEventType } from './services/audio.js';
import { defaultApiClient } from './services/api.js';
import { defaultRecorder, RecorderState } from './services/recorder.js';
import { defaultVAD, VADEventType, VADState } from './services/vad.js';
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
  INTERRUPTING: 'INTERRUPTING',
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
  const [isVADActive, setIsVADActive] = useState(false);

  // Sync VAD callbacks with current React state
  useEffect(() => {
    defaultVAD.getAssistantState = () => agentState;
    defaultVAD.getSessionContext = () => ({ sessionId, activeTurnId });
  }, [agentState, sessionId, activeTurnId]);

  // Initialize session and subscribe to Playback Manager, Recorder, and VAD events
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

    // 4. Subscribe to VAD real-time interruption events
    const unsubVAD = defaultVAD.onEvent(async (evt) => {
      if (evt.eventType === VADEventType.INTERRUPTION_DETECTED) {
        const t_detection = Date.now();

        // 1. IMMEDIATELY stop active Rime audio playback and advance client turn
        defaultPlaybackManager.stopCurrentAudio('interruption_barge_in');
        defaultPlaybackManager.setActiveTurn(evt.newTurnId);

        const t_stop = Date.now();
        const stopLatencyMs = t_stop - t_detection;

        // 2. Transition UI to INTERRUPTING
        setAgentState(AgentState.INTERRUPTING);

        setEvents((prev) => [
          {
            event_type: 'AUDIO_STOP_REQUESTED',
            timestamp_ms: t_detection,
            session_id: evt.sessionId,
            turn_id: evt.previousTurnId,
            state: playbackState,
            details: {
              previous_turn_id: evt.previousTurnId,
              new_turn_id: evt.newTurnId,
              reason: 'vad_barge_in',
              stop_latency_ms: stopLatencyMs,
            },
          },
          {
            event_type: 'INTERRUPTION_DETECTED',
            timestamp_ms: evt.timestamp,
            session_id: evt.sessionId,
            turn_id: evt.previousTurnId,
            state: playbackState,
            details: {
              previous_turn_id: evt.previousTurnId,
              new_turn_id: evt.newTurnId,
              detection_source: evt.detectionSource,
              assistant_state: evt.assistantState,
              energy: evt.energy?.toFixed(4),
              speech_duration_ms: evt.speechDurationMs,
            },
          },
          ...prev.slice(0, 49),
        ]);

        try {
          const intRes = await defaultApiClient.interruptSession({
            sessionId: evt.sessionId,
            turnId: evt.previousTurnId,
            reason: 'barge_in',
            detectionSource: evt.detectionSource,
            advanceTurn: true,
            assistantState: evt.assistantState,
          });

          setActiveTurnId(intRes.new_turn_id);
          defaultPlaybackManager.setActiveTurn(intRes.new_turn_id);

          setEvents((prev) => [
            {
              event_type: 'INTERRUPTION_TURN_TRANSITIONED',
              timestamp_ms: intRes.timestamp_ms,
              session_id: intRes.session_id,
              turn_id: intRes.new_turn_id,
              state: playbackState,
              details: {
                previous_turn_id: intRes.previous_turn_id,
                new_turn_id: intRes.new_turn_id,
                status: intRes.status,
              },
            },
            ...prev.slice(0, 49),
          ]);

          // Seamlessly transition UI to LISTENING for new user utterance
          setAgentState(AgentState.LISTENING);
        } catch (err) {
          console.error('Failed to notify backend of interruption:', err);
          setAgentState(AgentState.IDLE);
        }
      }
    });

    // 5. Initialize backend session
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
      unsubVAD();
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

  // Handler: Manual Barge-In Trigger
  const handleBargeIn = async () => {
    if (!sessionId) return;
    const t_detection = Date.now();
    const prevTurnId = activeTurnId;
    const prevAgentState = agentState;
    const nextTurnId = prevTurnId + 1;

    // Immediately stop active audio and advance client active turn
    defaultPlaybackManager.stopCurrentAudio('manual_barge_in');
    defaultPlaybackManager.setActiveTurn(nextTurnId);

    const t_stop = Date.now();
    const stopLatencyMs = t_stop - t_detection;

    setAgentState(AgentState.INTERRUPTING);

    setEvents((prev) => [
      {
        event_type: 'AUDIO_STOP_REQUESTED',
        timestamp_ms: t_detection,
        session_id: sessionId,
        turn_id: prevTurnId,
        state: playbackState,
        details: {
          previous_turn_id: prevTurnId,
          new_turn_id: nextTurnId,
          reason: 'manual_barge_in',
          stop_latency_ms: stopLatencyMs,
        },
      },
      {
        event_type: 'INTERRUPTION_DETECTED',
        timestamp_ms: t_detection,
        session_id: sessionId,
        turn_id: prevTurnId,
        state: playbackState,
        details: {
          previous_turn_id: prevTurnId,
          new_turn_id: nextTurnId,
          detection_source: 'manual_barge_in',
          assistant_state: prevAgentState,
        },
      },
      ...prev.slice(0, 49),
    ]);

    try {
      const intRes = await defaultApiClient.interruptSession({
        sessionId,
        turnId: prevTurnId,
        reason: 'barge_in',
        detectionSource: 'manual_barge_in',
        advanceTurn: true,
        assistantState: prevAgentState,
      });

      setActiveTurnId(intRes.new_turn_id);
      defaultPlaybackManager.setActiveTurn(intRes.new_turn_id);

      setEvents((prev) => [
        {
          event_type: 'INTERRUPTION_TURN_TRANSITIONED',
          timestamp_ms: intRes.timestamp_ms,
          session_id: intRes.session_id,
          turn_id: intRes.new_turn_id,
          state: playbackState,
          details: {
            previous_turn_id: intRes.previous_turn_id,
            new_turn_id: intRes.new_turn_id,
            status: intRes.status,
          },
        },
        ...prev.slice(0, 49),
      ]);
      setAgentState(AgentState.LISTENING);
    } catch (err) {
      console.error('Failed to trigger manual barge-in:', err);
      setAgentState(AgentState.IDLE);
    }
  };

  // Handler: Toggle Continuous VAD
  const handleToggleVAD = async () => {
    if (isVADActive) {
      defaultVAD.stop();
      setIsVADActive(false);
    } else {
      try {
        await defaultVAD.start();
        setIsVADActive(true);
      } catch (err) {
        console.error('Failed to start VAD:', err);
        alert(`VAD Error: ${err.message}`);
      }
    }
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="logo-badge">
          <span className="logo-dot"></span>
          <h1>Rime Voice AI Assistant</h1>
        </div>
        <p className="app-tagline">
          Phase 11 — Real-Time Interruption & Barge-In Detection (VAD &bull; Monotonic Turn Invalidation)
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
          onBargeIn={handleBargeIn}
          onToggleVAD={handleToggleVAD}
          isRecording={isRecording}
          isProcessing={isProcessing}
          isLoading={isLoading}
          isVADActive={isVADActive}
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
        <span>DataForge 2026 Rime Hackathon &bull; Phase 11 Interruption Detection</span>
      </footer>
    </div>
  );
}

