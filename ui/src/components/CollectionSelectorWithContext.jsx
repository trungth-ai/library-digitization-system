// File: src/components/CollectionSelectorWithContext.jsx
'use client';

import { useState, useEffect } from 'react';
import { useDSpaceCollections } from '@/hooks/useDSpaceCollections';

/**
 * Collection selector with community hierarchy
 * Solves duplicate collection name problem
 */
export default function CollectionSelectorWithContext({ 
  dspaceUrl, 
  value, 
  onChange,
  aiSuggestedId = null,
  aiMetadata = null,
}) {
  const { 
    collections, 
    loading, 
    error, 
    fetchCollections, 
    findBestMatch,
    getCollectionsByComm 
  } = useDSpaceCollections();

  const [viewMode, setViewMode] = useState('flat'); // 'flat' | 'grouped'
  const [searchTerm, setSearchTerm] = useState('');
  const [showAISuggestion, setShowAISuggestion] = useState(true);

  // Load collections on mount
  useEffect(() => {
    if (dspaceUrl) {
      fetchCollections(dspaceUrl);
    }
  }, [dspaceUrl, fetchCollections]);

  // Auto-suggest based on AI metadata
  useEffect(() => {
    if (aiMetadata && collections.length > 0 && !value) {
      const suggested = findBestMatch(aiMetadata);
      if (suggested) {
        console.log('AI suggested collection:', suggested.displayName);
        // Auto-select if confidence is very high
        if (suggested.score > 100) {
          onChange?.(suggested.id);
        }
      }
    }
  }, [aiMetadata, collections, value, findBestMatch, onChange]);

  // Filter collections
  const filteredCollections = collections.filter(col => {
    if (!searchTerm) return true;
    const search = searchTerm.toLowerCase();
    return (
      col.name.toLowerCase().includes(search) ||
      col.communityName.toLowerCase().includes(search) ||
      col.fullContext.toLowerCase().includes(search)
    );
  });

  // Get AI suggestion
  const aiSuggestion = aiMetadata ? findBestMatch(aiMetadata) : null;

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-gray-600">
        <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
        <span>Loading collections...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
        <p className="font-semibold">Error loading collections</p>
        <p className="text-sm">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* AI Suggestion Banner */}
      {aiSuggestion && showAISuggestion && (
        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                <span className="font-semibold text-blue-900">AI Suggestion</span>
                <span className="text-xs bg-blue-100 px-2 py-0.5 rounded-full text-blue-700">
                  {aiSuggestion.score}% confidence
                </span>
              </div>
              
              <p className="text-sm text-blue-800 mb-2">
                Based on the document content, we suggest:
              </p>
              
              <div className="bg-white p-3 rounded border border-blue-200">
                <p className="font-semibold text-gray-900">{aiSuggestion.name}</p>
                <p className="text-sm text-gray-600 mt-1">
                  📁 {aiSuggestion.communityName}
                </p>
                {aiSuggestion.archivedItemsCount > 0 && (
                  <p className="text-xs text-gray-500 mt-1">
                    {aiSuggestion.archivedItemsCount} items
                  </p>
                )}
              </div>
              
              <div className="mt-2 flex gap-2">
                <button
                  onClick={() => {
                    onChange?.(aiSuggestion.id);
                    setShowAISuggestion(false);
                  }}
                  className="text-sm px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700"
                >
                  Use this suggestion
                </button>
                <button
                  onClick={() => setShowAISuggestion(false)}
                  className="text-sm px-3 py-1 border border-blue-300 text-blue-700 rounded hover:bg-blue-50"
                >
                  Choose manually
                </button>
              </div>
            </div>
            
            <button
              onClick={() => setShowAISuggestion(false)}
              className="text-blue-400 hover:text-blue-600"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Search and View Mode */}
      <div className="flex gap-3">
        <div className="flex-1 relative">
          <input
            type="text"
            placeholder="Search collections or communities..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full px-4 py-2 pl-10 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <svg 
            className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400"
            fill="none" 
            stroke="currentColor" 
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>

        <div className="flex border border-gray-300 rounded-lg overflow-hidden">
          <button
            onClick={() => setViewMode('flat')}
            className={`px-4 py-2 text-sm font-medium ${
              viewMode === 'flat'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-50'
            }`}
          >
            Flat List
          </button>
          <button
            onClick={() => setViewMode('grouped')}
            className={`px-4 py-2 text-sm font-medium ${
              viewMode === 'grouped'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 hover:bg-gray-50'
            }`}
          >
            By Community
          </button>
        </div>
      </div>

      {/* Collections Display */}
      <div className="border border-gray-300 rounded-lg max-h-96 overflow-y-auto">
        {viewMode === 'flat' ? (
          // Flat list with full context
          <div className="divide-y divide-gray-200">
            {filteredCollections.length === 0 ? (
              <div className="p-8 text-center text-gray-500">
                No collections found
              </div>
            ) : (
              filteredCollections.map((col) => (
                <label
                  key={col.id}
                  className={`flex items-start gap-3 p-4 cursor-pointer hover:bg-gray-50 ${
                    value === col.id ? 'bg-blue-50' : ''
                  }`}
                >
                  <input
                    type="radio"
                    name="collection"
                    value={col.id}
                    checked={value === col.id}
                    onChange={() => onChange?.(col.id)}
                    className="mt-1 w-4 h-4 text-blue-600"
                  />
                  <div className="flex-1">
                    <div className="font-medium text-gray-900">{col.name}</div>
                    <div className="text-sm text-gray-600 mt-1">
                      📁 {col.communityName}
                    </div>
                    {col.archivedItemsCount > 0 && (
                      <div className="text-xs text-gray-500 mt-1">
                        {col.archivedItemsCount} items
                      </div>
                    )}
                  </div>
                  {aiSuggestion?.id === col.id && (
                    <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full">
                      AI Suggested
                    </span>
                  )}
                </label>
              ))
            )}
          </div>
        ) : (
          // Grouped by community
          <div>
            {Object.entries(getCollectionsByComm()).map(([commName, cols]) => {
              const filtered = cols.filter(col => 
                filteredCollections.some(fc => fc.id === col.id)
              );
              
              if (filtered.length === 0) return null;
              
              return (
                <div key={commName} className="border-b border-gray-200 last:border-b-0">
                  <div className="bg-gray-100 px-4 py-2 font-semibold text-gray-700">
                    📁 {commName} ({filtered.length})
                  </div>
                  <div className="divide-y divide-gray-200">
                    {filtered.map((col) => (
                      <label
                        key={col.id}
                        className={`flex items-start gap-3 p-4 pl-8 cursor-pointer hover:bg-gray-50 ${
                          value === col.id ? 'bg-blue-50' : ''
                        }`}
                      >
                        <input
                          type="radio"
                          name="collection"
                          value={col.id}
                          checked={value === col.id}
                          onChange={() => onChange?.(col.id)}
                          className="mt-1 w-4 h-4 text-blue-600"
                        />
                        <div className="flex-1">
                          <div className="font-medium text-gray-900">{col.name}</div>
                          {col.archivedItemsCount > 0 && (
                            <div className="text-xs text-gray-500 mt-1">
                              {col.archivedItemsCount} items
                            </div>
                          )}
                        </div>
                        {aiSuggestion?.id === col.id && (
                          <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full">
                            AI Suggested
                          </span>
                        )}
                      </label>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Stats */}
      <div className="text-sm text-gray-600">
        Showing {filteredCollections.length} of {collections.length} collections
      </div>
    </div>
  );
}