import React, { useState } from 'react';
import UploadPanel from './components/UploadPanel';
import ChatPanel from './components/ChatPanel';
import './styles.css';

function App() {
  const [docMeta, setDocMeta] = useState(null);

  const handleUploadSuccess = (meta) => {
    setDocMeta(meta);
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>BUDGETED DOCUMENT AGENT</h1>
      </header>
      
      <main className="app-main">
        <UploadPanel onUploadSuccess={handleUploadSuccess} />
        <ChatPanel 
          docId={docMeta?.doc_id} 
          disabled={!docMeta} 
        />
      </main>
    </div>
  );
}

export default App;
