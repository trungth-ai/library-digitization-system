"use client"

import React, { useState, useRef } from 'react';
import { Upload, FileText, X } from 'lucide-react';

export default function OCRUploader({ onUploadSuccess, showToast }) {
  const [uploading, setUploading]     = useState(false);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [progress, setProgress]       = useState({}); // { filename: 'pending'|'uploading'|'done'|'error' }
  const inputRef = useRef(null);

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files).filter(f => f.name.endsWith('.pdf'));
    setSelectedFiles(files);
    setProgress({});
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith('.pdf'));
    if (files.length) {
      setSelectedFiles(files);
      setProgress({});
    }
  };

  const removeFile = (idx) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== idx));
  };

  const uploadOne = async (file) => {
    setProgress(p => ({ ...p, [file.name]: 'uploading' }));
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('collection', 'default');
      formData.append('language', 'vie');

      const res = await fetch('/api/ocr/upload', { method: 'POST', body: formData });
      if (!res.ok) throw new Error('Upload failed');
      setProgress(p => ({ ...p, [file.name]: 'done' }));
      return true;
    } catch {
      setProgress(p => ({ ...p, [file.name]: 'error' }));
      return false;
    }
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) {
      showToast('Please select PDF files', 'warning');
      return;
    }

    setUploading(true);
    // Init all as pending
    setProgress(Object.fromEntries(selectedFiles.map(f => [f.name, 'pending'])));

    // Upload song song tat ca cung luc
    const results = await Promise.allSettled(selectedFiles.map(uploadOne));

    const successCount = results.filter(r => r.value === true).length;
    const failCount    = results.filter(r => r.value === false).length;

    setUploading(false);

    if (successCount > 0) {
      showToast(`✅ ${successCount} file(s) queued for OCR`, 'success');
      onUploadSuccess();
      // Reset sau 1.5s de user thay trang thai done
      setTimeout(() => {
        setSelectedFiles([]);
        setProgress({});
        if (inputRef.current) inputRef.current.value = '';
      }, 1500);
    }
    if (failCount > 0) {
      showToast(`❌ ${failCount} file(s) failed to upload`, 'error');
    }
  };

  const statusIcon = (name) => {
    const s = progress[name];
    if (s === 'uploading') return <div className="w-3.5 h-3.5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />;
    if (s === 'done')      return <span className="text-green-500 text-xs">✓</span>;
    if (s === 'error')     return <span className="text-red-500 text-xs">✗</span>;
    return null;
  };

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
      <h2 className="text-sm font-semibold text-gray-700 tracking-wide uppercase mb-4 flex items-center gap-2">
        <Upload className="w-4 h-4" />
        Upload PDFs for OCR
      </h2>

      {/* Drop zone */}
      <label
        onDragOver={e => e.preventDefault()}
        onDrop={handleDrop}
        className="block cursor-pointer"
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf"
          onChange={handleFileSelect}
          className="hidden"
        />
        <div className="border-2 border-dashed border-gray-200 rounded-xl p-6 text-center hover:border-indigo-400 hover:bg-indigo-50/30 transition-colors">
          <FileText className="w-8 h-8 mx-auto mb-2 text-gray-300" />
          <p className="text-sm text-gray-500">
            <span className="font-medium text-indigo-600">Click to select</span> or drag & drop PDFs
          </p>
          <p className="text-xs text-gray-400 mt-1">Multiple files supported</p>
        </div>
      </label>

      {/* File list */}
      {selectedFiles.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {selectedFiles.map((file, idx) => (
            <div key={idx} className="flex items-center gap-2.5 px-3 py-2 bg-gray-50 rounded-lg">
              <FileText className="w-3.5 h-3.5 text-gray-400 shrink-0" />
              <span className="text-xs text-gray-700 flex-1 truncate">{file.name}</span>
              <span className="text-xs text-gray-400 shrink-0">
                {(file.size / 1024 / 1024).toFixed(1)} MB
              </span>
              {statusIcon(file.name)}
              {!uploading && (
                <button
                  onClick={() => removeFile(idx)}
                  className="w-4 h-4 flex items-center justify-center text-gray-400 hover:text-red-500 transition-colors shrink-0"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Upload button */}
      {selectedFiles.length > 0 && (
        <button
          onClick={handleUpload}
          disabled={uploading}
          className="mt-3 w-full py-2.5 rounded-xl text-sm font-semibold bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
        >
          {uploading ? (
            <>
              <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Uploading {selectedFiles.length} file(s) in parallel...
            </>
          ) : (
            <>
              <Upload className="w-3.5 h-3.5" />
              Upload {selectedFiles.length} file(s)
            </>
          )}
        </button>
      )}
    </div>
  );
}