"use client"

import React from 'react';

export default function UploadStatus({ uploadStatus }) {
  if (uploadStatus.length === 0) return null;

  // ✨ Calculate stats
  const successCount = uploadStatus.filter(s => s.success === true).length;
  const failedCount = uploadStatus.filter(s => s.success === false).length;
  const pendingCount = uploadStatus.filter(s => s.success === null).length;

  return (
    <div className="bg-white rounded-xl shadow-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold">📈 Upload Status</h2>
        
        {/* ✨ Status Summary */}
        <div className="flex items-center gap-4 text-sm">
          {successCount > 0 && (
            <span className="flex items-center gap-1 text-green-600 font-medium">
              <span className="w-2 h-2 bg-green-600 rounded-full"></span>
              {successCount} Success
            </span>
          )}
          {failedCount > 0 && (
            <span className="flex items-center gap-1 text-red-600 font-medium">
              <span className="w-2 h-2 bg-red-600 rounded-full"></span>
              {failedCount} Failed
            </span>
          )}
          {pendingCount > 0 && (
            <span className="flex items-center gap-1 text-blue-600 font-medium">
              <span className="w-2 h-2 bg-blue-600 rounded-full animate-pulse"></span>
              {pendingCount} In Progress
            </span>
          )}
        </div>
      </div>

      {/* ✨ Progress Bar */}
      {uploadStatus.length > 0 && (
        <div className="mb-4">
          <div className="flex items-center gap-2 text-sm text-gray-600 mb-2">
            <span>Overall Progress:</span>
            <span className="font-semibold">
              {successCount + failedCount} / {uploadStatus.length}
            </span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
            <div className="h-full flex">
              {/* Success part */}
              {successCount > 0 && (
                <div 
                  className="bg-green-500 transition-all duration-500"
                  style={{ width: `${(successCount / uploadStatus.length) * 100}%` }}
                />
              )}
              {/* Failed part */}
              {failedCount > 0 && (
                <div 
                  className="bg-red-500 transition-all duration-500"
                  style={{ width: `${(failedCount / uploadStatus.length) * 100}%` }}
                />
              )}
              {/* Pending part */}
              {pendingCount > 0 && (
                <div 
                  className="bg-blue-400 transition-all duration-500 animate-pulse"
                  style={{ width: `${(pendingCount / uploadStatus.length) * 100}%` }}
                />
              )}
            </div>
          </div>
        </div>
      )}

      {/* ✨ Status List */}
      <div className="space-y-2 max-h-96 overflow-y-auto">
        {uploadStatus.map((status, idx) => (
          <div
            key={idx}
            className={`p-4 rounded-lg transition-all duration-200 ${
              status.success === null 
                ? 'bg-blue-50 border-2 border-blue-200 shadow-sm' 
                : status.success 
                  ? 'bg-green-50 border border-green-200' 
                  : 'bg-red-50 border border-red-200'
            }`}
          >
            <div className="flex items-start gap-3">
              {/* Status Icon */}
              <div className="shrink-0 mt-0.5">
                {status.success === null ? (
                  <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                ) : status.success ? (
                  <span className="text-xl">✅</span>
                ) : (
                  <span className="text-xl">❌</span>
                )}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                {/* Folder Name */}
                <div className="flex items-start justify-between gap-2">
                  <p className="font-semibold text-gray-900 truncate">
                    {status.folderName}
                  </p>
                  
                  {/* Time estimate for pending */}
                  {status.success === null && (
                    <span className="text-xs text-blue-600 font-medium whitespace-nowrap">
                      ~30s
                    </span>
                  )}
                </div>

                {/* ✨ Community Context Badge */}
                {status.communityContext && (
                  <div className="mt-1 flex items-center gap-1 text-xs text-gray-600">
                    <span>📁</span>
                    <span className="font-medium truncate">{status.communityContext}</span>
                  </div>
                )}

                {/* Status Message */}
                <p 
                  className={`mt-2 text-sm ${
                    status.success === null 
                      ? 'text-blue-700' 
                      : status.success 
                        ? 'text-green-700' 
                        : 'text-red-700'
                  }`}
                >
                  {status.status}
                </p>

                {/* ✨ Additional Info for Success */}
                {status.success === true && status.status.includes('Handle:') && (
                  <div className="mt-2 p-2 bg-white rounded border border-green-200">
                    <p className="text-xs text-gray-600">
                      Item created and uploaded successfully. 
                      <span className="block mt-1 text-green-600 font-medium">
                        You can now access it in DSpace repository
                      </span>
                    </p>
                  </div>
                )}

                {/* ✨ Additional Info for Failed */}
                {status.success === false && (
                  <div className="mt-2 p-2 bg-white rounded border border-red-200">
                    <p className="text-xs text-gray-600">
                      <span className="font-medium text-red-600">Troubleshooting:</span>
                    </p>
                    <ul className="text-xs text-gray-600 mt-1 space-y-1 list-disc list-inside">
                      <li>Check DSpace session is still valid</li>
                      <li>Verify collection permissions</li>
                      <li>Check OCR job output is complete</li>
                    </ul>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* ✨ Action Buttons */}
      {(successCount > 0 || failedCount > 0) && pendingCount === 0 && (
        <div className="mt-4 pt-4 border-t border-gray-200 flex items-center justify-between">
          <div className="text-sm text-gray-600">
            {successCount > 0 && failedCount === 0 ? (
              <span className="flex items-center gap-2 text-green-600 font-medium">
                <span className="text-xl">🎉</span>
                All uploads completed successfully!
              </span>
            ) : failedCount > 0 ? (
              <span className="flex items-center gap-2 text-orange-600 font-medium">
                <span className="text-xl">⚠️</span>
                {failedCount} upload{failedCount > 1 ? 's' : ''} failed
              </span>
            ) : null}
          </div>

          {/* Copy Summary Button */}
          <button
            onClick={() => {
              const summary = uploadStatus.map(s => 
                `${s.folderName} → ${s.communityContext || 'N/A'}: ${s.status}`
              ).join('\n');
              navigator.clipboard.writeText(summary);
              alert('Upload summary copied to clipboard!');
            }}
            className="px-4 py-2 text-sm bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors font-medium"
          >
            📋 Copy Summary
          </button>
        </div>
      )}
    </div>
  );
}