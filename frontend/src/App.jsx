import React, { useState, useEffect } from 'react';
import { defaultPlaybackManager, PlaybackState, AudioEventType } from './services/audio.js';
import { defaultApiClient } from './services/api.js';
import SpeakingIndicator from './components/SpeakingIndicator.jsx';
import Status from './components/Status.jsx';
import VoiceButton from './components/VoiceButton.jsx';
import Transcript from './components/Transcript.jsx';

export default function App() {
  const [sessionId, setSessionId] = useState('');
  const [activeTurnId, setActiveTurnId] = useState(0);
  const [playbackState, setPlaybackState] = useState(PlaybackState.IDLE);
  const [currentAudio, setCurrentAudio] = useState(null);
  const [events, setEvents] = useState([]);
  const [ttsText, setTtsText] = useState('Rime voice synthesis with interruption recovery.');
  const [isLoading, setIsLoading] = useState(false);
  const [backendStatus, setBackendStatus] = useState(null);

  // Initialize session and subscribe to Playback Manager events
  useEffect(() => {
    // 1. Subscribe to playback state changes
    const unsubState = defaultPlaybackManager.onStateChange((state, prevState, audio) => {
      setPlaybackState(state);
      setCurrentAudio(audio);
    });

    // 2. Subscribe to structured audio events
    const unsubEvents = defaultPlaybackManager.onEvent((evt) => {
      setEvents((prev) => [evt, ...prev.slice(0, 49)]);
    });

    // 3. Initialize backend session
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
    };
  }, []);

  // Handler: Advance monotonic turn
  const handleAdvanceTurn = async () => {
    if (!sessionId) return;
    try {
      const updatedSess = await defaultApiClient.createTurn(sessionId, ttsText);
      setActiveTurnId(updatedSess.active_turn_id);
      defaultPlaybackManager.setActiveTurn(updatedSess.active_turn_id);
    } catch (err) {
      console.error('Failed to advance turn:', err);
    }
  };

  // Handler: Synthesize genuine Rime audio and play via PlaybackManager
  const handleSynthesizeAndPlay = async () => {
    if (!sessionId) return;

    // Ensure we are at turn >= 1
    let targetTurn = activeTurnId;
    if (targetTurn === 0) {
      const turnRes = await defaultApiClient.createTurn(sessionId, ttsText);
      targetTurn = turnRes.active_turn_id;
      setActiveTurnId(targetTurn);
      defaultPlaybackManager.setActiveTurn(targetTurn);
    }

    setIsLoading(true);
    try {
      const { blob, headers } = await defaultApiClient.synthesizeSpeech({
        sessionId,
        turnId: targetTurn,
        text: ttsText,
      });

      // Play via client playback manager with strict turn check
      await defaultPlaybackManager.playAudio({
        sessionId,
        turnId: targetTurn,
        audioSource: blob,
        metadata: {
          speaker: headers.speaker || 'celeste',
          modelId: headers.modelId || 'coda',
          format: headers.audioFormat || 'mp3',
          bytes: headers.audioBytesLength,
        },
      });
    } catch (err) {
      console.error('TTS playback error:', err);
      alert(`TTS Error: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  // Handler: Stop audio immediately
  const handleStopAudio = () => {
    defaultPlaybackManager.stopCurrentAudio('user_manual_stop');
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="logo-badge">
          <span className="logo-dot"></span>
          <h1>Rime Voice AI Assistant</h1>
        </div>
        <p className="app-tagline">
          Phase 6 — Conversational Audio Delivery & Playback Pipeline with Interruption Protection
        </p>
      </header>

      <main className="app-main">
        <SpeakingIndicator state={playbackState} currentAudio={currentAudio} />

        <Status
          sessionId={sessionId}
          activeTurnId={activeTurnId}
          state={playbackState}
          metadata={currentAudio?.metadata}
          backendStatus={backendStatus}
        />

        <VoiceButton
          state={playbackState}
          onAdvanceTurn={handleAdvanceTurn}
          onSynthesizeAndPlay={handleSynthesizeAndPlay}
          onStop={handleStopAudio}
          isLoading={isLoading}
          activeTurnId={activeTurnId}
        />

        <Transcript events={events} text={ttsText} setText={setTtsText} />
      </main>

      <footer className="app-footer">
        <span>DataForge 2026 Rime Hackathon &bull; Phase 6 Audio Pipeline</span>
      </footer>
    </div>
  );
}
