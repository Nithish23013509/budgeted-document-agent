import React, { useState, useRef, useEffect } from 'react';
import { askQuestion, createSession } from '../api';
import Message from './Message';

export default function ChatPanel({ docId, disabled }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const endRef = useRef(null);

  useEffect(() => {
    // Initialize session once
    createSession().then(res => setSessionId(res.session_id)).catch(console.error);
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || !docId || loading) return;

    // Add user message
    const userMsg = { role: 'user', text };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const result = await askQuestion(docId, text, sessionId);
      const agentMsg = {
        role: 'agent',
        text: result.answer,
        status: result.status,
        sources: result.supporting_pages.length > 0 ? result.supporting_pages.map(p => `Page ${p}`).join(', ') : '',
        callsUsed: result.calls_used,
        trace: result.trace
      };
      setMessages(prev => [...prev, agentMsg]);
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'agent',
        text: `Error: ${err.message || "The agent encountered an error. Please try again."}`
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="card chat-card">
      <h2 className="section-title">CHAT</h2>
      
      <div className="chat-history">
        {messages.length === 0 && (
          <div className="empty-chat">
            Upload a document and ask a question to begin.
          </div>
        )}
        
        {messages.map((m, i) => (
          <Message key={i} {...m} />
        ))}
        
        {loading && (
          <div className="loading-indicator">
            <span className="spinner"></span> Analyzing document...
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="chat-input-area">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? "Please upload a document first..." : "Ask a question..."}
          disabled={disabled || loading}
          className="chat-textarea"
          rows={1}
        />
        <button 
          onClick={handleSend} 
          disabled={!input.trim() || disabled || loading}
          className="send-btn"
        >
          Send
        </button>
      </div>
    </div>
  );
}
