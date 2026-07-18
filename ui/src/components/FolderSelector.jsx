"use client"

import React, { useRef } from 'react';
import { Plus, X, Trash2, FolderOpen } from 'lucide-react';

export default function FolderSelector({ 
  selectedFolders, 
  onAddFolders, 
  onRemoveFolder, 
  onClearAll,
  onAnalyze,
  isAnalyzing 
}) {
  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    onAddFolders(e);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const validCount = selectedFolders.filter(f => f.hasValidMetadata).length;

  return (
    <div className="bg-white rounded-xl shadow-lg p-6 mb-8">
      <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
        <FolderOpen className="w-5 h-5" />
        Folder Selection
      </h2>

      <div className="space-y-4">
        {/* Add Folders Button */}
        <div className="flex gap-3">
          <label className="flex-1 cursor-pointer">
            <input
              ref={fileInputRef}
              type="file"
              webkitdirectory=""
              multiple
              onChange={handleFileChange}
              className="hidden"
            />
            <div className="flex items-center justify-center gap-2 px-4 py-3 bg-blue-50 text-blue-700 rounded-lg border-2 border-blue-200 hover:bg-blue-100 font-medium transition-colors">
              <Plus className="w-5 h-5" />
              Select Folders to Upload
            </div>
          </label>
          
          {selectedFolders.length > 0 && (
            <button
              onClick={onClearAll}
              className="px-4 py-3 bg-red-50 text-red-700 rounded-lg border-2 border-red-200 hover:bg-red-100 font-medium flex items-center gap-2 transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              Clear All
            </button>
          )}
        </div>

        {/* Selected Folders List */}
        {selectedFolders.length > 0 && (
          <div className="border rounded-lg overflow-hidden">
            <div className="bg-gray-50 px-4 py-2 border-b flex items-center justify-between">
              <span className="font-medium text-gray-700">
                Selected Folders ({selectedFolders.length})
              </span>
              <span className="text-sm text-gray-500">
                {validCount} valid
              </span>
            </div>
            <div className="max-h-96 overflow-y-auto">
              {selectedFolders.map((folder) => (
                <div
                  key={folder.id}
                  className="flex items-center justify-between px-4 py-3 border-b hover:bg-gray-50 transition-colors"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">
                        {folder.hasValidMetadata ? '✅' : '❌'}
                      </span>
                      <div>
                        <p className="font-medium text-gray-900">{folder.title}</p>
                        <p className="text-xs text-gray-500">
                          {folder.name} • {folder.fileCount} files
                        </p>
                      </div>
                    </div>
                    {!folder.hasValidMetadata && (
                      <p className="text-xs text-red-600 mt-1 ml-7">
                        Missing or invalid metadata.json
                      </p>
                    )}
                  </div>
                  <button
                    onClick={() => onRemoveFolder(folder.id)}
                    className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Analyze Button */}
        {selectedFolders.length > 0 && (
          <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
            <div className="flex items-start gap-3 mb-3">
              <span className="text-2xl">💡</span>
              <div className="flex-1">
                <p className="text-sm font-semibold text-purple-900 mb-1">
                  Smart Batch Processing
                </p>
                <p className="text-xs text-purple-800">
                  All {validCount} folders will be analyzed in <strong>1 single API call</strong> to save costs and time.
                </p>
              </div>
            </div>
            <button
              onClick={onAnalyze}
              disabled={isAnalyzing || validCount === 0}
              className="w-full bg-purple-600 text-white py-3 rounded-lg hover:bg-purple-700 font-medium disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
            >
              {isAnalyzing ? '🤖 AI Analyzing...' : `🤖 Analyze ${validCount} Folders (1 API Call)`}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}