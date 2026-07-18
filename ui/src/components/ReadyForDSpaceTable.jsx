"use client";

import React, { useState, useMemo, useEffect } from "react";
import { Upload, Pencil, Loader2, Sparkles, ChevronLeft, ChevronRight, Download, Trash2, RotateCcw } from "lucide-react";

const DSPACE_STATUS_CONFIG = {
  pending:      { label: "Pending",    dot: "bg-gray-300",   text: "text-gray-500"  },
  uploading:    { label: "Uploading",  dot: "bg-blue-400 animate-pulse", text: "text-blue-600" },
  uploaded:     { label: "Uploaded",   dot: "bg-green-400",  text: "text-green-600" },
  upload_failed:{ label: "Failed",     dot: "bg-red-400",    text: "text-red-600"   },
};

const ITEMS_PER_PAGE = 8;

export default function ReadyForDSpaceTable({
  jobs,
  collections,
  onEditJob,
  onPushSingle,
  onPushSelected,
  onAISuggest,
  onCollectionChange,
  onDownloadJob,
  onDownloadBatch,
  onDeleteJob,
  onRetryJob,
  dspaceUrl,
  isAnalyzing,
  isUploading,
  pushingIds = new Set(),
}) {
  const [deletingId, setDeletingId] = useState(null);
  const [selectedIds, setSelectedIds]   = useState(new Set());
  const [currentPage, setCurrentPage]   = useState(1);

  // Chi hien thi completed jobs
  const completedJobs = useMemo(
    () => jobs.filter(j => j.status === "completed"),
    [jobs]
  );

  const totalPages = Math.ceil(completedJobs.length / ITEMS_PER_PAGE);
  const pageJobs   = completedJobs.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE
  );

  // Collections grouped by community cho <select>
  const collectionsByComm = useMemo(() => {
    const grouped = {};
    collections.forEach(c => {
      const comm = c.communityName || "Other";
      if (!grouped[comm]) grouped[comm] = [];
      grouped[comm].push(c);
    });
    return grouped;
  }, [collections]);

  // Reset ve trang 1 neu currentPage vuot qua totalPages sau khi xoa jobs
  useEffect(() => {
    if (currentPage > 1 && currentPage > Math.ceil(completedJobs.length / ITEMS_PER_PAGE)) {
      setCurrentPage(1);
    }
  }, [completedJobs.length, currentPage]);

  const toggleSelect = (jobId) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.has(jobId) ? next.delete(jobId) : next.add(jobId);
      return next;
    });
  };

  const toggleAll = (checked) => {
    setSelectedIds(checked ? new Set(pageJobs.map(j => j.job_id)) : new Set());
  };

  const isAllSelected = pageJobs.length > 0 &&
    pageJobs.every(j => selectedIds.has(j.job_id));

  const selectedJobsList = completedJobs.filter(j => selectedIds.has(j.job_id));
  const pushableSelected = selectedJobsList.filter(j =>
    j.dspace_collection_id && j.dspace_status !== "uploaded"
  );

  if (completedJobs.length === 0) return null;

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">

      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-100">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2.5">
            <span className="text-sm font-semibold text-gray-700 tracking-wide uppercase">
              Ready for DSpace
            </span>
            <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full font-medium">
              {completedJobs.length}
            </span>
          </div>

          {/* Toolbar actions - chi hien khi co selection */}
          {selectedIds.size > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500 font-medium">
                {selectedIds.size} selected
              </span>

              <button
                onClick={() => onAISuggest(selectedJobsList)}
                disabled={isAnalyzing}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-violet-50 text-violet-700 border border-violet-200 hover:bg-violet-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isAnalyzing
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <Sparkles className="w-3.5 h-3.5" />
                }
                AI Suggest
              </button>

              <button
                onClick={() => onPushSelected(selectedJobsList)}
                disabled={isUploading || pushableSelected.length === 0}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
              >
                {isUploading
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <Upload className="w-3.5 h-3.5" />
                }
                Push {pushableSelected.length > 0 ? pushableSelected.length : ""} to DSpace
              </button>

              <button
                onClick={() => {
                  // Neu 1 file: dung window.location.href binh thuong
                  // Neu nhieu file: goi batch endpoint tra ve 1 ZIP
                  if (selectedJobsList.length === 1) {
                    onDownloadJob(selectedJobsList[0].job_id);
                  } else {
                    onDownloadBatch(selectedJobsList.map(j => j.job_id));
                  }
                }}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-gray-50 text-gray-700 border border-gray-200 hover:bg-gray-100 transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
                Download {selectedJobsList.length > 1 ? `(${selectedJobsList.length})` : ""}
              </button>

              <button
                onClick={async () => {
                  if (!confirm(`Delete ${selectedIds.size} job(s)? This cannot be undone.`)) return;
                  await Promise.allSettled(selectedJobsList.map(j => onDeleteJob(j.job_id)));
                  setSelectedIds(new Set());
                }}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-red-50 text-red-600 border border-red-200 hover:bg-red-100 transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Delete {selectedJobsList.length > 0 ? `(${selectedJobsList.length})` : ""}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50/50">
              <th className="w-10 px-5 py-3">
                <input
                  type="checkbox"
                  checked={isAllSelected}
                  onChange={e => toggleAll(e.target.checked)}
                  className="w-4 h-4 rounded text-indigo-600 border-gray-300 focus:ring-indigo-500 cursor-pointer"
                />
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
                File
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider min-w-52">
                Collection
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Status
              </th>
              <th className="px-4 py-3 text-right text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {pageJobs.map(job => {
              const dsCfg    = DSPACE_STATUS_CONFIG[job.dspace_status] || DSPACE_STATUS_CONFIG.pending;
              const selected = selectedIds.has(job.job_id);
              const pushing  = pushingIds.has(job.job_id);
              return (
                <tr
                  key={job.job_id}
                  className={`transition-colors ${selected ? "bg-indigo-50/40" : "hover:bg-gray-50/60"}`}
                >
                  {/* Checkbox */}
                  <td className="px-5 py-3.5" onClick={e => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => toggleSelect(job.job_id)}
                      className="w-4 h-4 rounded text-indigo-600 border-gray-300 focus:ring-indigo-500 cursor-pointer"
                    />
                  </td>

                  {/* Filename */}
                  <td className="px-4 py-3.5 max-w-[160px]">
                    <p className="text-sm text-gray-700 truncate font-medium" title={job.filename}>
                      {job.filename}
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {job.finished_at
                        ? new Date(job.finished_at).toLocaleDateString("vi-VN")
                        : "—"}
                    </p>
                  </td>

                  {/* Collection select */}
                  <td className="px-4 py-3.5" onClick={e => e.stopPropagation()}>
                    <div className="space-y-1">
                      <select
                        value={job.dspace_collection_id || ""}
                        onChange={e => {
                          const col = collections.find(c => (c.id || c.uuid) === e.target.value);
                          onCollectionChange(job.job_id, e.target.value, col?.name || "", col?.communityName || "");
                        }}
                        className="w-full text-xs text-gray-700 bg-white border border-gray-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-colors appearance-none cursor-pointer"
                      >
                        <option value="">— Select collection —</option>
                        {Object.entries(collectionsByComm).map(([comm, cols]) => (
                          <optgroup key={comm} label={comm}>
                            {cols.map(col => (
                              <option key={col.id || col.uuid} value={col.id || col.uuid}>
                                {col.name}
                              </option>
                            ))}
                          </optgroup>
                        ))}
                      </select>

                      {/* Community badge */}
                      {job.dspace_community_name && (
                        <p className="text-xs text-gray-400 truncate pl-0.5">
                          📁 {job.dspace_community_name}
                        </p>
                      )}
                    </div>
                  </td>

                  {/* DSpace Status */}
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    <div className="flex items-center gap-1.5">
                      <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${dsCfg.dot}`} />
                      <span className={`text-xs font-medium ${dsCfg.text}`}>
                        {dsCfg.label}
                      </span>
                    </div>
                    {job.dspace_handle && (
                      <a
                        href={`${dspaceUrl || ""}/handle/${job.dspace_handle}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={e => e.stopPropagation()}
                        className="text-xs text-indigo-500 hover:text-indigo-700 hover:underline mt-0.5 truncate block"
                        title="Open in DSpace"
                      >
                        ↗ {job.dspace_handle}
                      </a>
                    )}
                  </td>

                  {/* Actions */}
                  <td className="px-4 py-3.5" onClick={e => e.stopPropagation()}>
                    <div className="flex items-center justify-end gap-1.5">

                      {/* Edit metadata */}
                      <button
                        onClick={() => onEditJob(job)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-gray-600 bg-gray-50 border border-gray-200 hover:bg-gray-100 hover:text-gray-800 transition-colors"
                        title="Edit metadata"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                        Edit
                      </button>

                      {/* Download */}
                      <button
                        onClick={() => onDownloadJob(job.job_id)}
                        className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
                        title="Download processed files"
                      >
                        <Download className="w-3.5 h-3.5" />
                      </button>

                      {/* Delete */}
                      <button
                        onClick={async () => {
                          if (confirm(`Delete "${job.filename}"? This cannot be undone.`)) {
                            setDeletingId(job.job_id);
                            try { await onDeleteJob(job.job_id); }
                            finally { setDeletingId(null); }
                          }
                        }}
                        disabled={deletingId === job.job_id}
                        className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 hover:text-red-500 hover:bg-red-50 disabled:opacity-40 transition-colors"
                        title="Delete job"
                      >
                        {deletingId === job.job_id
                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          : <Trash2 className="w-3.5 h-3.5" />
                        }
                      </button>

                      {/* Retry - chi hien khi upload_failed */}
                      {job.dspace_status === "upload_failed" && onRetryJob && (
                        <button
                          onClick={() => onRetryJob(job.job_id)}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-amber-700 bg-amber-50 border border-amber-200 hover:bg-amber-100 transition-colors"
                          title="Reset and retry DSpace upload"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                          Retry
                        </button>
                      )}

                      {/* Push single */}
                      {job.dspace_status !== "uploaded" && job.dspace_status !== "upload_failed" && (
                        <button
                          onClick={() => onPushSingle(job)}
                          disabled={pushing || !job.dspace_collection_id || isUploading}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
                          title={!job.dspace_collection_id ? "Select a collection first" : "Push to DSpace"}
                        >
                          {pushing
                            ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            : <Upload className="w-3.5 h-3.5" />
                          }
                          Push
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="px-5 py-3 border-t border-gray-100 flex items-center justify-between bg-gray-50/30">
          <span className="text-xs text-gray-400">
            {(currentPage - 1) * ITEMS_PER_PAGE + 1}–{Math.min(currentPage * ITEMS_PER_PAGE, completedJobs.length)} of {completedJobs.length}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
              <button
                key={p}
                onClick={() => setCurrentPage(p)}
                className={`w-7 h-7 rounded-lg text-xs font-medium transition-colors ${
                  p === currentPage
                    ? "bg-indigo-600 text-white"
                    : "text-gray-500 hover:bg-gray-100"
                }`}
              >
                {p}
              </button>
            ))}
            <button
              onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}