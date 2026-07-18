"use client"

import React, { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

// Component Tooltip cho title
function TooltipTitle({ title, folderName }) {
  const [show, setShow] = React.useState(false);
  const [position, setPosition] = React.useState({ x: 0, y: 0 });
  const ref = React.useRef(null);

  const handleMouseEnter = () => {
    if (ref.current) {
      const rect = ref.current.getBoundingClientRect();
      setPosition({ x: rect.left, y: rect.top });
      setShow(true);
    }
  };

  return (
    <div className="relative">
      <h3 
        ref={ref}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={() => setShow(false)}
        className="font-semibold text-gray-900 truncate cursor-help"
      >
        {title}
      </h3>
      
      {show && (
        <div 
          className="fixed z-9999 pointer-events-none w-96"
          style={{ 
            left: `${position.x}px`, 
            top: `${position.y - 70}px` 
          }}
        >
          <div className="bg-gray-900 text-white text-xs rounded-lg py-2 px-3 shadow-2xl border border-gray-700">
            <div className="font-semibold mb-1">{title}</div>
            <div className="text-gray-300">{folderName}</div>
            <div className="absolute top-full left-4 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900"></div>
          </div>
        </div>
      )}
      
      <p className="text-xs text-gray-500 mt-1 truncate">
        {folderName}
      </p>
    </div>
  );
}

// Component Tooltip cho reasoning
function TooltipReasoning({ reasoning }) {
  const [show, setShow] = React.useState(false);
  const [position, setPosition] = React.useState({ x: 0, y: 0 });
  const ref = React.useRef(null);

  const handleMouseEnter = () => {
    if (ref.current) {
      const rect = ref.current.getBoundingClientRect();
      setPosition({ x: rect.left, y: rect.top });
      setShow(true);
    }
  };

  if (reasoning.length <= 80) {
    return <div className="line-clamp-2">{reasoning}</div>;
  }

  return (
    <div className="relative">
      <div 
        ref={ref}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={() => setShow(false)}
        className="line-clamp-2 cursor-help"
      >
        {reasoning}
      </div>
      
      {show && (
        <div 
          className="fixed z-9999 pointer-events-none w-96"
          style={{ 
            left: `${position.x}px`, 
            top: `${position.y - 70}px` 
          }}
        >
          <div className="bg-gray-900 text-white text-xs rounded-lg py-2 px-3 shadow-2xl border border-gray-700">
            {reasoning}
            <div className="absolute top-full left-4 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900"></div>
          </div>
        </div>
      )}
    </div>
  );
}

function CommunityBadge({ communityName }) {
  if (!communityName) return null;
  
  return (
    <div className="flex items-center gap-1 mt-1 text-xs text-gray-600 bg-gray-50 px-2 py-1 rounded">
      <span>📁</span>
      <span className="font-medium">{communityName}</span>
    </div>
  );
}

function getPageNumbers(currentPage, totalPages) {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }
  
  if (currentPage <= 3) {
    return [1, 2, 3, 4, '...', totalPages];
  }
  
  if (currentPage >= totalPages - 2) {
    return [1, '...', totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
  }
  
  return [
    1,
    '...',
    currentPage - 1,
    currentPage,
    currentPage + 1,
    '...',
    totalPages
  ];
}

export default function MappingsTable({ 
  mappings, 
  collections, 
  onUpdateMapping, 
  onUpload, 
  isUploading,
  selectedMappings = [],
  onSelectMappings,
  dspaceUrl
}) {
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 5;

  const getConfidenceColor = (confidence) => {
    if (confidence >= 80) return 'text-green-600';
    if (confidence >= 60) return 'text-yellow-600';
    return 'text-red-600';
  };

  const getConfidenceBadge = (confidence) => {
    if (confidence >= 80) return '🟢 High';
    if (confidence >= 60) return '🟡 Medium';
    return '🔴 Low';
  };

  const collectionsByComm = React.useMemo(() => {
    const grouped = {};
    collections.forEach(col => {
      const commName = col.communityName || 'Other';
      if (!grouped[commName]) {
        grouped[commName] = [];
      }
      grouped[commName].push(col);
    });
    return grouped;
  }, [collections]);

  const totalPages = Math.ceil(mappings.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const currentMappings = mappings.slice(startIndex, endIndex);

  const readyMappings = mappings.filter(m => m.status === 'ready' && m.collectionId);
  const readyCount = selectedMappings.length;

  const handleSelectAll = (checked) => {
    if (checked) {
      onSelectMappings(readyMappings.map(m => m.jobId || m.folderId));
    } else {
      onSelectMappings([]);
    }
  };

  const handleToggleMapping = (id) => {
    if (selectedMappings.includes(id)) {
      onSelectMappings(selectedMappings.filter(mId => mId !== id));
    } else {
      onSelectMappings([...selectedMappings, id]);
    }
  };

  const isAllSelected = readyMappings.length > 0 && selectedMappings.length === readyMappings.length;

  return (
    <div className="bg-white rounded-xl shadow-lg overflow-hidden">
      <div className="bg-white px-6 py-4 border-b-2 border-gray-200 relative z-10">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
              📊 AI Suggestions
              <span className="text-sm font-normal text-gray-500">
                ({mappings.length} total, {readyCount} selected)
              </span>
            </h2>
            {collections.length > 0 && (
              <p className="text-xs text-gray-500 mt-1">
                With context from {new Set(collections.map(c => c.communityName)).size} communities
              </p>
            )}
          </div>
          
          <button
            onClick={onUpload}
            disabled={isUploading || readyCount === 0}
            className={`
              bg-green-600 text-white px-6 py-2.5 rounded-lg font-medium 
              shadow-lg transition-all duration-200
              ${readyCount > 0 
                ? 'opacity-100 visible hover:bg-green-700 hover:shadow-xl transform hover:-translate-y-0.5' 
                : 'opacity-0 invisible pointer-events-none'
              }
              disabled:bg-gray-400 disabled:cursor-not-allowed
            `}
          >
            {isUploading ? '⏳ Uploading...' : `🚀 Push ${readyCount} to DSpace`}
          </button>
        </div>
      </div>

      {mappings.length === 0 ? (
        <div className="p-12 text-center">
          <div className="text-gray-400 mb-3">
            <svg className="w-16 h-16 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <p className="text-gray-500 text-lg font-medium">No AI suggestions yet</p>
          <p className="text-gray-400 text-sm mt-1">Select completed jobs and click Analyze</p>
        </div>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full table-fixed">
              <colgroup>
                <col className="w-12" />
                <col className="w-80" />
                <col className="w-80" />
                <col className="w-28" />
                <col className="w-96" />
              </colgroup>
              <thead className="bg-gray-50 border-b-2 border-gray-200">
                <tr>
                  <th className="px-6 py-4 text-left">
                    <input
                      type="checkbox"
                      onChange={(e) => handleSelectAll(e.target.checked)}
                      checked={isAllSelected}
                      className="w-4 h-4 text-blue-600 rounded focus:ring-2 focus:ring-blue-500 cursor-pointer"
                    />
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Title</th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                    Suggested Collection
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Confidence</th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Reasoning</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {currentMappings.map((mapping, idx) => {
                  const globalIdx = startIndex + idx;
                  const mappingId = mapping.jobId || mapping.folderId;
                  const isSelected = selectedMappings.includes(mappingId);
                  const isReady = mapping.status === 'ready' && mapping.collectionId;
                  
                  return (
                    <tr 
                      key={mappingId || globalIdx}
                      onClick={() => isReady && handleToggleMapping(mappingId)}
                      className={`
                        transition-all duration-150
                        border-l-4
                        ${isSelected 
                          ? 'bg-blue-50 border-l-blue-500' 
                          : mapping.status === 'error' 
                            ? 'bg-red-50 border-l-red-500' 
                            : 'border-l-transparent hover:bg-gray-50'
                        }
                        ${isReady ? 'cursor-pointer' : 'cursor-default'}
                      `}
                    >
                      <td className="px-6 py-4" onClick={(e) => e.stopPropagation()}>
                        {isReady && (
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => handleToggleMapping(mappingId)}
                            className="w-4 h-4 text-blue-600 rounded focus:ring-2 focus:ring-blue-500 cursor-pointer"
                          />
                        )}
                      </td>
                      <td className="px-6 py-4 text-sm">
                        <TooltipTitle title={mapping.title} folderName={mapping.folderName} />
                      </td>
                      
                      <td className="px-6 py-4 text-sm" onClick={(e) => e.stopPropagation()}>
                        {mapping.status === 'error' ? (
                          <span className="text-red-600 font-medium">{mapping.collectionName}</span>
                        ) : (
                          <div className="space-y-2">
                            <select
                              value={mapping.collectionId ?? ''}
                              onChange={(e) => {
                                const col = collections.find(c => (c.id ?? c.uuid) === e.target.value);
                                onUpdateMapping(
                                  mappingId, 
                                  e.target.value, 
                                  col?.displayName ?? col?.name ?? ''
                                );
                              }}
                              className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-blue-500 transition-shadow"
                            >
                              {Object.entries(collectionsByComm).map(([commName, cols]) => (
                                <optgroup key={commName} label={`📁 ${commName}`}>
                                  {cols.map(col => (
                                    <option key={col.id ?? col.uuid} value={col.id ?? col.uuid}>
                                      {col.name}
                                      {col.archivedItemsCount > 0 && ` (${col.archivedItemsCount} items)`}
                                    </option>
                                  ))}
                                </optgroup>
                              ))}
                            </select>
                            
                            <CommunityBadge communityName={mapping.communityName} />
                          </div>
                        )}
                      </td>
                      
                      <td className="px-6 py-4 text-sm">
                        <div className={`font-semibold ${getConfidenceColor(mapping.confidence)}`}>
                          {getConfidenceBadge(mapping.confidence)}
                        </div>
                        <div className="text-xs text-gray-500">{mapping.confidence}%</div>
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-600">
                        <TooltipReasoning reasoning={mapping.reasoning} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="bg-gray-50 px-6 py-4 flex items-center justify-between border-t border-gray-200">
              <div className="text-sm text-gray-600">
                Showing <span className="font-semibold">{startIndex + 1}</span> to{' '}
                <span className="font-semibold">{Math.min(endIndex, mappings.length)}</span> of{' '}
                <span className="font-semibold">{mappings.length}</span> suggestions
              </div>
              
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                  disabled={currentPage === 1}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2 font-medium text-gray-700"
                >
                  <ChevronLeft className="w-4 h-4" />
                  Previous
                </button>
                
                <div className="flex gap-1">
                  {getPageNumbers(currentPage, totalPages).map((page, idx) => {
                    if (page === '...') {
                      return (
                        <span 
                          key={`ellipsis-${idx}`} 
                          className="w-10 h-10 flex items-center justify-center text-gray-400 font-bold"
                        >
                          •••
                        </span>
                      );
                    }
                    
                    return (
                      <button
                        key={page}
                        onClick={() => setCurrentPage(page)}
                        className={`w-10 h-10 rounded-lg font-medium transition-all ${
                          currentPage === page
                            ? 'bg-blue-600 text-white shadow-lg'
                            : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50'
                        }`}
                      >
                        {page}
                      </button>
                    );
                  })}
                </div>
                
                <button
                  onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                  disabled={currentPage === totalPages}
                  className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2 font-medium text-gray-700"
                >
                  Next
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}