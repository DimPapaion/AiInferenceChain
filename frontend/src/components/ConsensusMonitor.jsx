/**
 * ConsensusMonitor Component
 * 
 * Real-time consensus round monitoring via WebSocket
 */

import React, { useState, useEffect, useRef } from 'react';
import './ConsensusMonitor.css';

function ConsensusMonitor({ streamUrl }) {
  const [isConnected, setIsConnected] = useState(false);
  const [events, setEvents] = useState([]);
  const [currentRound, setCurrentRound] = useState(null);
  const [phase, setPhase] = useState(null);
  const [participants, setParticipants] = useState(0);
  const wsRef = useRef(null);
  const eventsRef = useRef([]);

  useEffect(() => {
    // Replace http with ws in URL
    const wsStreamUrl = streamUrl.replace('http://', 'ws://').replace('https://', 'wss://');
    
    const connect = () => {
      try {
        wsRef.current = new WebSocket(wsStreamUrl);

        wsRef.current.onopen = () => {
          console.log('WebSocket connected');
          setIsConnected(true);
        };

        wsRef.current.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            
            // Update current state
            if (message.type === 'consensus_round') {
              setCurrentRound(message.round);
              setPhase(message.phase);
              setParticipants(message.participants);
            }

            // Add to event log (max 50 events)
            const newEvent = {
              id: Date.now(),
              timestamp: new Date(message.timestamp),
              ...message,
            };

            setEvents(prev => [newEvent, ...prev].slice(0, 50));
          } catch (err) {
            console.error('Failed to parse WebSocket message:', err);
          }
        };

        wsRef.current.onerror = (error) => {
          console.error('WebSocket error:', error);
          setIsConnected(false);
        };

        wsRef.current.onclose = () => {
          console.log('WebSocket disconnected');
          setIsConnected(false);
          // Attempt to reconnect after 3 seconds
          setTimeout(connect, 3000);
        };
      } catch (err) {
        console.error('Failed to connect WebSocket:', err);
        setTimeout(connect, 3000);
      }
    };

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [streamUrl]);

  const getPhaseColor = (phase) => {
    const colors = {
      preprepare: '#3498db',
      prepare: '#f39c12',
      commit: '#27ae60',
    };
    return colors[phase] || '#95a5a6';
  };

  const formatTimestamp = (date) => {
    return date.toLocaleTimeString();
  };

  return (
    <div className="consensus-monitor">
      {/* Connection Status */}
      <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
        <div className="status-indicator" />
        <span>{isConnected ? 'Connected to Consensus Stream' : 'Disconnected - Reconnecting...'}</span>
      </div>

      {/* Current Round Status */}
      {currentRound !== null && (
        <div className="current-round-card">
          <div className="round-display">
            <div className="round-number">
              <span className="label">Current Round</span>
              <h2>#{currentRound}</h2>
            </div>

            <div className="round-details">
              <div className="detail">
                <span className="label">Phase</span>
                <span
                  className="value"
                  style={{ color: getPhaseColor(phase) }}
                >
                  {phase || '—'}
                </span>
              </div>

              <div className="detail">
                <span className="label">Participants</span>
                <span className="value">👥 {participants}</span>
              </div>

              <div className="detail">
                <span className="label">Status</span>
                <span className="value">
                  {phase === 'preprepare' && '📝 Proposing'}
                  {phase === 'prepare' && '🔄 Preparing'}
                  {phase === 'commit' && '✓ Committing'}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Real-time Event Log */}
      <div className="event-log">
        <h3>📋 Event Log</h3>

        <div className="events-container">
          {events.length === 0 ? (
            <div className="empty-log">
              <p>Waiting for consensus events...</p>
            </div>
          ) : (
            events.map(event => (
              <div key={event.id} className="event-item">
                <div className="event-time">
                  {formatTimestamp(event.timestamp)}
                </div>

                <div className="event-content">
                  {event.type === 'consensus_round' && (
                    <div className="event-message">
                      <span className="event-type">🔄 ROUND</span>
                      <span className="event-text">
                        Round #{event.round} entered {event.phase} phase ({event.participants} validators)
                      </span>
                      <span className="event-status">
                        {event.status === 'committed' ? '✓' : '−'}
                      </span>
                    </div>
                  )}

                  {event.type === 'validator_activity' && (
                    <div className="event-message">
                      <span className="event-type">👤 VALIDATOR</span>
                      <span className="event-text">
                        {event.validator_id.substring(0, 8)}... {event.action}
                      </span>
                      <span className="event-status">→</span>
                    </div>
                  )}

                  {event.type === 'model_validation' && (
                    <div className="event-message">
                      <span className="event-type">📚 MODEL</span>
                      <span className="event-text">
                        {event.model_id.substring(0, 8)}... {event.status}
                        {event.progress > 0 && ` (${event.progress}%)`}
                      </span>
                      <span className="event-status">
                        {event.status === 'passed' && '✓'}
                        {event.status === 'failed' && '✗'}
                        {event.status === 'validating' && '⏳'}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Statistics */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Total Events</div>
          <div className="stat-value">{events.length}</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Round Events</div>
          <div className="stat-value">
            {events.filter(e => e.type === 'consensus_round').length}
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Validator Events</div>
          <div className="stat-value">
            {events.filter(e => e.type === 'validator_activity').length}
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Model Events</div>
          <div className="stat-value">
            {events.filter(e => e.type === 'model_validation').length}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ConsensusMonitor;
