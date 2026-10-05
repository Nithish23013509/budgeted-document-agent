import React from 'react';
import TracePanel from './TracePanel';

export default function Message({ role, text, status, sources, callsUsed, trace }) {
  const isUser = role === 'user';
  
  return (
    <div className={`message-wrapper ${isUser ? 'user-message' : 'agent-message'}`}>
      <div className="message-header">
        {isUser ? 'User' : 'Agent'}
      </div>
      
      <div className="message-content">
        {status === 'INSUFFICIENT_INFORMATION' && (
          <div className="insufficient-header">INSUFFICIENT INFORMATION</div>
        )}
        
        <div className="message-text">
          {text}
        </div>
        
        {!isUser && sources && sources.length > 0 && (
          <div className="message-sources">
            <strong>Sources:</strong> 
            <span className="source-link"> [{sources}]</span>
          </div>
        )}
        
        {!isUser && callsUsed !== undefined && (
          <div className="message-calls">
            <strong>Tool calls:</strong> {callsUsed} / 6
          </div>
        )}
      </div>

      {!isUser && trace && (
        <TracePanel trace={trace} callsUsed={callsUsed} />
      )}
    </div>
  );
}
