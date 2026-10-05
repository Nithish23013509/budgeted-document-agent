import React, { useState } from 'react';
import { uploadPdf } from '../api';

export default function UploadPanel({ onUploadSuccess }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [docMeta, setDocMeta] = useState(null);

  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setError("Please select a valid PDF file.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const meta = await uploadPdf(file);
      setDocMeta(meta);
      onUploadSuccess(meta);
    } catch (err) {
      setError(err.message || "Unable to read this PDF. Please try another PDF.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card">
      <h2 className="section-title">DOCUMENT</h2>
      <div className="upload-box">
        {!docMeta ? (
          <>
            <label className="upload-label">
              <input 
                type="file" 
                accept="application/pdf" 
                onChange={handleFileChange} 
                disabled={loading} 
                style={{ display: 'none' }} 
              />
              <span className="upload-btn">
                {loading ? "Uploading..." : "Drop PDF here / Select PDF"}
              </span>
            </label>
            {error && <div className="error-text">{error}</div>}
          </>
        ) : (
          <div className="upload-success">
            <div className="doc-icon">📄</div>
            <div className="doc-info">
              <div className="doc-name">✓ {docMeta.title}</div>
              <div className="doc-pages">{docMeta.pages} pages</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
