import React, { useState } from 'react';

export default function TracePanel({ trace, callsUsed }) {
  const [expanded, setExpanded] = useState(false);

  if (!trace || trace.length === 0) return null;

  return (
    <div className="trace-panel">
      <button 
        className="trace-toggle" 
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? "▼" : "▶"} Agent Trace
      </button>

      {expanded && (
        <div className="trace-content">
          {trace.map((entry, idx) => (
            <div key={idx} className="trace-entry">
              {entry.type ? (
                // Meta event
                <div className="trace-meta">
                  <div className="meta-title">{entry.type.replace(/_/g, " ")}</div>
                  {entry.answer && <div className="meta-detail">{entry.answer}</div>}
                  {entry.result && (
                    <pre className="meta-json">
                      {JSON.stringify(entry.result, null, 2)}
                    </pre>
                  )}
                </div>
              ) : (
                // Tool call
                <div className="trace-call">
                  <div className="call-header">
                    CALL {entry.call_number} / 6
                  </div>
                  <div className="call-body">
                    <strong>Tool:</strong> <span>{entry.tool}</span>
                    <br />
                    <strong>Arguments:</strong>
                    <pre className="call-args">
                      {JSON.stringify(entry.arguments, null, 2)}
                    </pre>
                    <strong>Result:</strong>
                    <pre className="call-result">
                      {typeof entry.result === 'object' 
                        ? JSON.stringify(entry.result, null, 2) 
                        : String(entry.result)}
                    </pre>
                    {entry.error && (
                      <div className="call-error">Error: {entry.error}</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
