"use client";

import React, { useState, useCallback } from "react";
import OCRUploader from "@/components/OCRUploader";
import OCRJobsList from "@/components/OCRJobsList";
import ReadyForDSpaceTable from "@/components/ReadyForDSpaceTable";
import MetadataSidePanel from "@/components/MetadataSidePanel";
import { useOCRJobs } from "@/hooks/useOCRJobs";

// Client gọi qua proxy same-origin của Next (/api/ocr/...) — KHÔNG dùng URL tuyệt đối tới
// FastAPI: trình duyệt không chắc tới được địa chỉ đó, và URL http:// trên trang https sẽ bị
// chặn vì mixed content. Đây là nguyên nhân lỗi "Failed to fetch" khi lưu collection.
const DSPACE_URL  = process.env.NEXT_PUBLIC_DSPACE_URL;


// Doc LY DO THAT tu phan hoi loi.
// Cac route da tra ve {error, status, detail} nhung truoc day client bo het va nem mot cau chung
// ("Failed to create DSpace item"), nen toast chi noi "Failed to push" — khong ai biet vuong o dau.
async function errorFromResponse(res, step) {
  let detail = "";
  try {
    const body = await res.json();
    detail = body.detail || body.error || JSON.stringify(body);
  } catch {
    try { detail = await res.text(); } catch { /* than rong */ }
  }
  // Than loi cua Tomcat/DSpace la ca trang HTML -> boc the va cat ngan cho vua toast
  detail = String(detail).replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim().slice(0, 300);
  return new Error(`${step} (HTTP ${res.status})${detail ? ": " + detail : ""}`);
}

export default function PageClient({ session, initialCollections = [] }) {
  const collections = initialCollections;

  const {
    jobs,
    fetchJobs,
    deleteJob,
    downloadJob,
    saveDSpaceCollection,
    updateDSpaceStatus,
    resetDSpaceUpload,
  } = useOCRJobs();

  const [editingJob,  setEditingJob]  = useState(null);
  const [pushingIds,  setPushingIds]  = useState(new Set());
  const [isUploading, setIsUploading] = useState(false);   // batch push dang chay
  const [isBatchPushing, setIsBatchPushing] = useState(false); // chi disable toolbar
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [toast,       setToast]       = useState(null);

  const showToast = (msg, type = "info") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  // ---------------------------------------------------------------
  // Fix 8: Helper kiem tra va refresh DSpace session neu can
  // ---------------------------------------------------------------
  const checkDSpaceSession = useCallback(async () => {
    try {
      const res = await fetch("/api/dspace/status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ dspaceUrl: DSPACE_URL }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      return data.authenticated === true;
    } catch {
      return false;
    }
  }, []);

  // ---------------------------------------------------------------
  // Helper: cap nhat dc.department trong metadata khi collection thay doi
  // ---------------------------------------------------------------
  const updateDepartmentMetadata = useCallback(async (jobId, collectionName) => {
    if (!jobId || !collectionName) return;
    try {
      // Lay metadata hien tai
      const res = await fetch(`/api/ocr/jobs/${jobId}/metadata`);
      if (!res.ok) return;
      const data = await res.json();
      const fields = data.metadata || [];

      // Tim va cap nhat dc.department, hoac them moi neu chua co
      const idx = fields.findIndex(f => f.key === "dc.department");
      let updated;
      if (idx !== -1) {
        updated = fields.map((f, i) =>
          i === idx ? { ...f, value: collectionName } : f
        );
      } else {
        updated = [...fields, { key: "dc.department", value: collectionName, language: "en_US" }];
      }

      await fetch(`/api/ocr/jobs/${jobId}/metadata`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metadata: updated }),
      });
    } catch (err) {
      console.warn(`Could not update dc.department for ${jobId}:`, err);
    }
  }, []);

  // ---------------------------------------------------------------
  // Upload
  // ---------------------------------------------------------------
  const handleUploadSuccess = () => fetchJobs();

  // ---------------------------------------------------------------
  // Delete / Cancel (bang 1)
  // ---------------------------------------------------------------
  const handleDelete = async (jobId) => {
    try {
      await deleteJob(jobId);
    } catch (err) {
      showToast(`Delete failed: ${err.message}`, "error");
    }
  };

  // ---------------------------------------------------------------
  // Collection change tu select (bang 2)
  // ---------------------------------------------------------------
  const handleCollectionChange = useCallback(async (jobId, collectionId, collectionName, communityName) => {
    try {
      await saveDSpaceCollection(jobId, collectionId, collectionName, communityName);
      // Cap nhat dc.department = ten collection vua chon
      await updateDepartmentMetadata(jobId, collectionName);
    } catch (err) {
      showToast(`Could not save collection: ${err.message}`, "error");
    }
  }, [saveDSpaceCollection, updateDepartmentMetadata]);

  // ---------------------------------------------------------------
  // AI Suggest
  // ---------------------------------------------------------------
  const handleAISuggest = useCallback(async (selectedJobs) => {
    if (!selectedJobs.length) { showToast("No jobs selected", "warning"); return; }

    setIsAnalyzing(true);
    showToast(`Analyzing ${selectedJobs.length} documents...`, "info");

    try {
      // Fetch metadata tat ca jobs song song
      const metaResults = await Promise.allSettled(
        selectedJobs.map(async job => {
          const res  = await fetch(`/api/ocr/jobs/${job.job_id}/metadata`);
          const data = res.ok ? await res.json() : { metadata: [] };
          const title = data.metadata?.find(m => m.key === "dc.title")?.value || job.filename;
          return {
            jobId:      job.job_id,
            folderName: job.filename.replace(".pdf", ""),
            title,
            metadata:   data.metadata || [],
          };
        })
      );

      const documents = metaResults
        .filter(r => r.status === "fulfilled")
        .map(r => r.value);

      if (!documents.length) { showToast("No metadata found", "error"); return; }

      const aiRes = await fetch("/api/ai/suggest-collection-batch", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ documents, collections }),
      });
      if (!aiRes.ok) throw new Error((await aiRes.json()).error || "AI failed");
      const { suggestions } = await aiRes.json();

      const results = await Promise.allSettled(
        suggestions.map(async sug => {
          const col   = collections.find(c => (c.id || c.uuid) === sug.collectionId);
          const jobId = sug.jobId || documents.find(d => d.folderName === sug.folderName)?.jobId;
          if (!jobId) return;
          await saveDSpaceCollection(jobId, sug.collectionId, sug.collectionName, col?.communityName || "");
          // Cap nhat dc.department = ten collection AI goi y
          await updateDepartmentMetadata(jobId, sug.collectionName);
        })
      );

      const ok   = results.filter(r => r.status === "fulfilled").length;
      const fail = results.filter(r => r.status === "rejected").length;
      showToast(`AI suggested ${ok} collections${fail ? `, ${fail} failed` : ""}`, "success");

    } catch (err) {
      showToast(`AI analysis failed: ${err.message}`, "error");
    } finally {
      setIsAnalyzing(false);
    }
  }, [collections, saveDSpaceCollection, updateDepartmentMetadata]);

  // ---------------------------------------------------------------
  // Push to DSpace
  // ---------------------------------------------------------------
  const pushJob = useCallback(async (job) => {
    if (!job.dspace_collection_id) {
      showToast(`Hãy chọn collection cho "${job.filename}" trước`, "warning");
      return { ok: false, error: "Chưa chọn collection" };
    }

    setPushingIds(prev => new Set([...prev, job.job_id]));
    try {
      // Fix 8: Kiem tra session truoc khi push, canh bao neu het han
      const sessionOk = await checkDSpaceSession();
      if (!sessionOk) {
        throw new Error("Phiên DSpace đã hết hạn — tải lại trang và đăng nhập lại");
      }

      await updateDSpaceStatus(job.job_id, "uploading").catch(() => {});

      // Lay metadata moi nhat tu DB
      const metaRes  = await fetch(`/api/ocr/jobs/${job.job_id}/metadata`);
      const metaData = metaRes.ok ? await metaRes.json() : { metadata: [] };

      // Tao item
      const createRes = await fetch("/api/dspace/create-item", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          collectionId: job.dspace_collection_id,
          metadata:     metaData.metadata,
          dspaceUrl:    DSPACE_URL,
        }),
      });
      if (!createRes.ok) throw await errorFromResponse(createRes, "Tạo item trên DSpace thất bại");
      const itemData = await createRes.json();

      // Resolve itemId
      let itemId = itemData.itemId;
      if (!itemId && itemData.handle) {
        const hRes = await fetch("/api/dspace/get-item-by-handle", {
          method: "POST", headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ handle: itemData.handle, dspaceUrl: DSPACE_URL }),
        });
        if (hRes.ok) itemId = (await hRes.json()).id;
      }
      if (!itemId) throw new Error("DSpace tạo được item nhưng không trả về ID/handle để tải file lên");

      // Upload PDF
      const dlRes  = await fetch(`/api/ocr/download/${job.job_id}`);
      if (!dlRes.ok) throw await errorFromResponse(dlRes, "Không tải được file đã xử lý từ backend");

      const JSZip  = (await import("jszip")).default;
      const zip    = await new JSZip().loadAsync(await dlRes.blob());
      const pdfKey = Object.keys(zip.files).find(n => n.endsWith(".pdf") && !n.includes("metadata"));
      if (!pdfKey) throw new Error("Không tìm thấy PDF trong kết quả xử lý (kiểm tra worker đã OCR xong chưa)");

      const upRes = await fetch(
        `/api/dspace/upload-bitstream?itemId=${encodeURIComponent(itemId)}&fileName=${encodeURIComponent(pdfKey)}&dspaceUrl=${encodeURIComponent(DSPACE_URL)}`,
        { method: "POST", credentials: "include",
          headers: { "Content-Type": "application/octet-stream" },
          body: await zip.files[pdfKey].async("blob") }
      );
      if (!upRes.ok) throw await errorFromResponse(upRes, "Tải PDF lên DSpace thất bại");

      await updateDSpaceStatus(job.job_id, "uploaded", {
        itemId: itemData.itemId || itemId,
        handle: itemData.handle || null,
      });
      return { ok: true, error: null };

    } catch (err) {
      console.error(`Push failed for ${job.filename}:`, err);
      // Luu ly do vao DB (cot dspace_error) de con tra duoc sau, khong chi hien tam tren toast
      await updateDSpaceStatus(job.job_id, "upload_failed", { error: err.message }).catch(() => {});
      return { ok: false, error: err.message };
    } finally {
      setPushingIds(prev => { const n = new Set(prev); n.delete(job.job_id); return n; });
    }
  }, [updateDSpaceStatus, checkDSpaceSession]);

  const handleDownloadBatch = useCallback((jobIds) => {
    // Tao URL voi query params va redirect - batch ZIP endpoint
    const params = new URLSearchParams();
    jobIds.forEach(id => params.append("ids", id));
    window.location.href = `/api/ocr/download/batch?${params.toString()}`;
  }, []);

  const handlePushSingle = useCallback(async (job) => {
    const { ok, error } = await pushJob(job);
    showToast(
      ok ? `Đã đẩy "${job.filename}" lên DSpace`
         : `Đẩy "${job.filename}" thất bại — ${error}`,
      ok ? "success" : "error"
    );
  }, [pushJob]);

  const handlePushSelected = useCallback(async (selectedJobs) => {
    const pushable = selectedJobs.filter(j => j.dspace_collection_id && j.dspace_status !== "uploaded");
    if (!pushable.length) { showToast("Select a collection for each job first", "warning"); return; }

    setIsUploading(true);
    setIsBatchPushing(true);
    showToast(`Pushing ${pushable.length} items... (3 at a time)`, "info");

    // Fix 6: Chay theo lo 3 jobs cung luc thay vi tat ca song song
    // Tranh DSpace bi qua tai / session timeout
    const CONCURRENCY = 3;
    let okCount = 0;
    let failCount = 0;
    let firstError = null;   // neu ly do dau tien trong toast tong ket

    for (let i = 0; i < pushable.length; i += CONCURRENCY) {
      const batch = pushable.slice(i, i + CONCURRENCY);
      const results = await Promise.allSettled(batch.map(j => pushJob(j)));

      okCount   += results.filter(r => r.value?.ok === true).length;
      const failedResults = results.filter(r => r.value?.ok !== true);
      failCount += failedResults.length;
      if (failedResults.length && !firstError) {
        firstError = failedResults[0].value?.error
                  || failedResults[0].reason?.message
                  || "lỗi không rõ";
      }

      // Cap nhat toast sau moi lo
      if (i + CONCURRENCY < pushable.length) {
        showToast(
          `Progress: ${Math.min(i + CONCURRENCY, pushable.length)}/${pushable.length} processed...`,
          "info"
        );
      }
    }

    showToast(
      `Xong: ${okCount} thành công`
        + (failCount ? `, ${failCount} thất bại — ${firstError}` : ""),
      failCount === 0 ? "success" : "warning"
    );
    setIsUploading(false);
    setIsBatchPushing(false);
  }, [pushJob]);

  // ---------------------------------------------------------------
  // Retry DSpace upload — reset trang thai roi push lai
  // ---------------------------------------------------------------
  const handleRetryJob = useCallback(async (jobId) => {
    try {
      await resetDSpaceUpload(jobId);
      const job = jobs.find(j => j.job_id === jobId);
      if (job) await handlePushSingle(job);
    } catch (err) {
      showToast(`Retry failed: ${err.message}`, "error");
    }
  }, [resetDSpaceUpload, jobs, handlePushSingle]);

  // ---------------------------------------------------------------
  // Metadata saved callback
  // ---------------------------------------------------------------
  const handleMetadataSaved = useCallback(() => {
    showToast("Metadata saved", "success");
  }, []);

  // ---------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------
  return (
    <div className="space-y-4">

      {collections.length > 0 && (
        <div className="flex items-center gap-2 px-4 py-2.5 bg-green-50 border border-green-200 rounded-xl text-sm text-green-700">
          <span>✅</span>
          <span className="font-medium">{collections.length} collections</span>
          <span className="text-green-600">
            from {new Set(collections.map(c => c.communityName)).size} communities loaded
          </span>
        </div>
      )}

      <OCRUploader onUploadSuccess={handleUploadSuccess} showToast={showToast} />

      <OCRJobsList jobs={jobs} onDelete={handleDelete} />

      <ReadyForDSpaceTable
        jobs={jobs}
        collections={collections}
        onEditJob={setEditingJob}
        onPushSingle={handlePushSingle}
        onPushSelected={handlePushSelected}
        onAISuggest={handleAISuggest}
        onCollectionChange={handleCollectionChange}
        onDownloadJob={downloadJob}
        onDownloadBatch={handleDownloadBatch}
        onDeleteJob={handleDelete}
        onRetryJob={handleRetryJob}
        dspaceUrl={DSPACE_URL}
        isAnalyzing={isAnalyzing}
        isUploading={isBatchPushing}
        pushingIds={pushingIds}
      />

      {editingJob && (
        <MetadataSidePanel
          job={jobs.find(j => j.job_id === editingJob.job_id) || editingJob}
          onClose={() => setEditingJob(null)}
          onSaved={handleMetadataSaved}
          onPush={async (jobId) => {
            const job = jobs.find(j => j.job_id === jobId);
            if (job) await handlePushSingle(job);
          }}
        />
      )}

      {toast && (
        <div className={`fixed bottom-5 right-5 z-50 px-4 py-3 rounded-xl text-sm font-semibold shadow-lg animate-fade-in-up pointer-events-none ${toast.type === "success" ? "bg-green-600 text-white" : toast.type === "error" ? "bg-red-600 text-white" : toast.type === "warning" ? "bg-amber-500 text-white" : "bg-gray-800 text-white"}`}
        >
          {toast.msg}
        </div>
      )}

      <style jsx>{`
        @keyframes fade-in-up {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .animate-fade-in-up { animation: fade-in-up 0.2s ease-out; }
      `}</style>
    </div>
  );
}