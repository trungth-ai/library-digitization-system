"use client"

import React, { useMemo, useState, useRef } from 'react';
import { Upload, FileText, X } from 'lucide-react';
import DocumentTypeSelect, {
  AUTO,
  SuggestionHint,
  useDocumentTypes,
  useFilenameSuggestions,
} from '@/components/DocumentTypeSelect';

export default function OCRUploader({ onUploadSuccess, showToast }) {
  const [uploading, setUploading]     = useState(false);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [progress, setProgress]       = useState({}); // { filename: 'pending'|'uploading'|'done'|'error' }
  // Loại tài liệu mặc định cho cả mẻ. 'auto' = để hệ thống đoán từ nội dung sau khi OCR.
  const [docType, setDocType]         = useState(AUTO);
  // Ghi đè RIÊNG cho từng tệp: { filename: 'sach' }. Chỉ chứa tệp cán bộ đã sửa tay.
  const [perFileType, setPerFileType] = useState({});
  const inputRef = useRef(null);

  const documentTypes = useDocumentTypes();
  const filenames = useMemo(() => selectedFiles.map(f => f.name), [selectedFiles]);
  const suggestions = useFilenameSuggestions(filenames);

  // Loại thực sự gửi lên cho một tệp: cán bộ sửa riêng > chọn chung cho cả mẻ.
  // KHÔNG tự áp gợi ý từ tên tệp: gợi ý dựa vào tên tệp yếu hơn hẳn gợi ý dựa vào nội dung mà worker
  // làm sau khi OCR. Để 'auto' đi tiếp thì tài liệu được đoán bằng nội dung — chính xác hơn.
  const typeFor = (name) => perFileType[name] || docType;

  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files).filter(f => f.name.endsWith('.pdf'));
    setSelectedFiles(files);
    setProgress({});
    setPerFileType({});
  };

  const handleDrop = (e) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith('.pdf'));
    if (files.length) {
      setSelectedFiles(files);
      setProgress({});
      setPerFileType({});
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
      formData.append('doc_type', typeFor(file.name));

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
      showToast('Hãy chọn tệp PDF trước', 'warning');
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
      showToast(`✅ Đã đưa ${successCount} tệp vào hàng đợi OCR`, 'success');
      onUploadSuccess();
      // Reset sau 1.5s de user thay trang thai done
      setTimeout(() => {
        setSelectedFiles([]);
        setProgress({});
        setPerFileType({});
        if (inputRef.current) inputRef.current.value = '';
      }, 1500);
    }
    if (failCount > 0) {
      showToast(`❌ ${failCount} tệp tải lên thất bại`, 'error');
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
        Tải PDF lên để OCR
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
            <span className="font-medium text-indigo-600">Bấm để chọn</span> hoặc kéo thả tệp PDF vào đây
          </p>
          <p className="text-xs text-gray-400 mt-1">Chọn được nhiều tệp cùng lúc</p>
        </div>
      </label>

      {/* Loại tài liệu cho cả mẻ */}
      <div className="mt-4">
        <DocumentTypeSelect
          value={docType}
          onChange={setDocType}
          types={documentTypes}
          disabled={uploading}
          label="Loại tài liệu (áp dụng cho tất cả tệp)"
        />
        <p className="text-xs text-gray-500 mt-1">
          Để «Tự động» thì hệ thống đọc nội dung sau khi OCR rồi tự chọn lược đồ biên mục.
          Cán bộ vẫn xem lại và sửa được ở màn hình duyệt.
        </p>
      </div>

      {/* File list */}
      {selectedFiles.length > 0 && (
        <div className="mt-3 space-y-2">
          {selectedFiles.map((file, idx) => {
            const suggestion = suggestions[file.name];
            return (
              <div key={idx} className="px-3 py-2 bg-gray-50 rounded-lg">
                <div className="flex items-center gap-2.5">
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
                      aria-label={`Bỏ tệp ${file.name}`}
                    >
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </div>

                {/* Gợi ý theo TÊN TỆP + ghi đè riêng cho tệp này */}
                {!uploading && (
                  <div className="mt-1.5 flex items-center gap-2">
                    <select
                      value={typeFor(file.name)}
                      onChange={(e) =>
                        setPerFileType(prev => ({ ...prev, [file.name]: e.target.value }))
                      }
                      aria-label={`Loại tài liệu của ${file.name}`}
                      className="text-xs rounded border border-gray-300 bg-white px-2 py-1 max-w-[16rem]"
                    >
                      <option value={AUTO}>Tự động nhận dạng</option>
                      {documentTypes.map(t => (
                        <option key={t.code} value={t.code}>{t.label}</option>
                      ))}
                    </select>
                    {suggestion && suggestion.confidence > 0 && (
                      <div className="flex-1 min-w-0">
                        <SuggestionHint
                          suggestion={suggestion}
                          onApply={
                            suggestion.document_type !== typeFor(file.name)
                              ? () =>
                                  setPerFileType(prev => ({
                                    ...prev,
                                    [file.name]: suggestion.document_type,
                                  }))
                              : null
                          }
                        />
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
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
              Đang tải {selectedFiles.length} tệp song song…
            </>
          ) : (
            <>
              <Upload className="w-3.5 h-3.5" />
              Tải lên {selectedFiles.length} tệp
            </>
          )}
        </button>
      )}
    </div>
  );
}
