"use client";

import React, { useState } from "react";
import { Loader2, Trash2, AlertCircle, Clock, CheckCircle } from "lucide-react";

const ACTIVE_STATUSES = new Set(["queued", "processing", "ocr", "extracting", "exporting"]);

const STATUS_CONFIG = {
  queued:     { label: "Queued",      color: "text-amber-600",  bg: "bg-amber-50",  bar: "bg-amber-400" },
  processing: { label: "Processing",  color: "text-blue-600",   bg: "bg-blue-50",   bar: "bg-blue-500"  },
  ocr:        { label: "OCR",         color: "text-blue-600",   bg: "bg-blue-50",   bar: "bg-blue-500"  },
  extracting: { label: "Extracting",  color: "text-violet-600", bg: "bg-violet-50", bar: "bg-violet-500"},
  exporting:  { label: "Exporting",   color: "text-indigo-600", bg: "bg-indigo-50", bar: "bg-indigo-500"},
  failed:     { label: "Failed",      color: "text-red-600",    bg: "bg-red-50",    bar: "bg-red-500"   },
};

export default function OCRJobsList({ jobs, onDelete }) {
  const [deletingId, setDeletingId] = useState(null);

  // Chi hien thi active jobs va failed
  const visibleJobs = jobs.filter(
    j => ACTIVE_STATUSES.has(j.status) || j.status === "failed"
  );

  const handleDelete = async (job) => {
    const label = ACTIVE_STATUSES.has(job.status) ? "cancel" : "delete";
    if (!confirm(`${label === "cancel" ? "Cancel" : "Delete"} "${job.filename}"?`)) return;

    setDeletingId(job.job_id);
    try {
      await onDelete(job.job_id);
    } finally {
      setDeletingId(null);
    }
  };

  if (visibleJobs.length === 0) return null;

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          <span className="text-sm font-semibold text-gray-700 tracking-wide uppercase">
            Processing Queue
          </span>
          <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full font-medium">
            {visibleJobs.length}
          </span>
        </div>
      </div>

      {/* Job rows */}
      <div className="divide-y divide-gray-50">
        {visibleJobs.map(job => {
          const cfg      = STATUS_CONFIG[job.status] || STATUS_CONFIG.processing;
          const isActive = ACTIVE_STATUSES.has(job.status);
          const isDel    = deletingId === job.job_id;

          return (
            <div key={job.job_id} className="flex items-center gap-4 px-5 py-3.5 hover:bg-gray-50/50 transition-colors">
              {/* Status icon */}
              <div className={`shrink-0 w-8 h-8 rounded-full ${cfg.bg} flex items-center justify-center`}>
                {isActive ? (
                  <Loader2 className={`w-4 h-4 ${cfg.color} animate-spin`} />
                ) : (
                  <AlertCircle className="w-4 h-4 text-red-500" />
                )}
              </div>

              {/* Filename + progress */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">{job.filename}</p>
                <div className="flex items-center gap-2 mt-1.5">
                  <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${cfg.bar} ${isActive ? "animate-pulse" : ""}`}
                      style={{ width: `${job.progress}%` }}
                    />
                  </div>
                  <span className={`text-xs font-medium ${cfg.color} shrink-0`}>
                    {cfg.label} {job.progress}%
                  </span>
                </div>
                {job.status === "failed" && job.error && (
                  <p className="text-xs text-red-500 mt-1 truncate">{job.error}</p>
                )}
              </div>

              {/* Created at */}
              <span className="text-xs text-gray-400 shrink-0 hidden sm:block">
                {new Date(job.created_at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}
              </span>

              {/* Delete / Cancel button */}
              <button
                onClick={() => handleDelete(job)}
                disabled={isDel}
                className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors disabled:opacity-40"
                title={isActive ? "Cancel job" : "Delete job"}
              >
                {isDel
                  ? <Loader2 className="w-4 h-4 animate-spin" />
                  : <Trash2 className="w-4 h-4" />
                }
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}