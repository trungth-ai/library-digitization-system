"use client"

import { useState, useEffect, useCallback, useRef } from 'react';

const OCR_API_URL = process.env.NEXT_PUBLIC_OCR_API_URL;

export function useOCRJobs() {
  const [jobs, setJobs]       = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  const esRef = useRef(null);

  // ---------------------------------------------------------------
  // fetchJobs
  // ---------------------------------------------------------------
  const fetchJobs = useCallback(async (status = null, includeMetadata = false) => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (status)          params.append('status', status);
      if (includeMetadata) params.append('include_metadata', 'true');

      const url = params.toString()
        ? `/api/ocr/jobs?${params.toString()}`
        : `/api/ocr/jobs`;

      const res = await fetch(url);
      if (!res.ok) throw new Error('Failed to fetch jobs');

      const data = await res.json();
      setJobs(data.jobs || []);
    } catch (err) {
      setError(err.message);
      console.error('Fetch jobs error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // ---------------------------------------------------------------
  // SSE
  // ---------------------------------------------------------------
  const connectSSE = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
    }

    const es = new EventSource(`${OCR_API_URL}/api/v2/jobs/stream`);
    esRef.current = es;

    es.addEventListener('job_update', (e) => {
      try {
        const updated = JSON.parse(e.data);

        // Fix 7: Khong goi fetchJobs() ben trong setJobs() updater
        // React StrictMode goi updater 2 lan → fetchJobs chay 2 lan song song
        // Kiem tra truoc, neu job moi thi fetch ben ngoai updater
        setJobs(prev => {
          const exists = prev.some(j => j.job_id === updated.job_id);

          if (!exists) {
            // Schedule fetch ben ngoai cycle hien tai bang setTimeout(0)
            setTimeout(() => fetchJobs(), 0);
            return prev;
          }

          return prev.map(job => {
            if (job.job_id !== updated.job_id) return job;
            return {
              ...job,
              status:   updated.status,
              progress: updated.progress,
              error:    updated.error || job.error,
              ...(isTerminalStatus(updated.status) && {
                finished_at: new Date().toISOString(),
              }),
            };
          });
        });
      } catch (err) {
        console.error('SSE parse error:', err);
      }
    });

    es.addEventListener('connected', () => {
      console.log('SSE stream connected');
    });

    es.onerror = () => {
      console.warn('SSE lost, reconnecting in 3s...');
      es.close();
      esRef.current = null;
      setTimeout(connectSSE, 3000);
    };
  }, [fetchJobs]);

  // ---------------------------------------------------------------
  // Lifecycle
  // ---------------------------------------------------------------
  useEffect(() => {
    fetchJobs();
    connectSSE();

    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
    };
  }, [fetchJobs, connectSSE]);

  // ---------------------------------------------------------------
  // ACTIONS
  // ---------------------------------------------------------------

  const uploadFile = async (file, collection = 'default', language = 'vie') => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('collection', collection);
    formData.append('language', language);

    const res = await fetch('/api/ocr/upload', { method: 'POST', body: formData });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'Upload failed');
    }

    const data = await res.json();

    setJobs(prev => [{
      job_id:        data.job_id,
      filename:      data.filename,
      status:        'queued',
      progress:      10,
      created_at:    new Date().toISOString(),
      finished_at:   null,
      error:         null,
      dspace_status: 'pending',
    }, ...prev]);

    return data;
  };

  // Native browser download — browser hien dialog chon noi luu file
  // /api/ocr/download/:id la Next.js route, no se forward sang FastAPI
  const downloadJob = (jobId) => {
    window.location.href = `/api/ocr/download/${jobId}`;
  };

  const deleteJob = async (jobId) => {
    const res = await fetch(`/api/ocr/jobs/${jobId}`, { method: 'DELETE' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'Delete failed');
    }
    setJobs(prev => prev.filter(j => j.job_id !== jobId));
    return await res.json();
  };

  // ---------------------------------------------------------------
  // DSPACE TRACKING
  // ---------------------------------------------------------------

  const saveDSpaceCollection = async (jobId, collectionId, collectionName, communityName = '') => {
    const res = await fetch(`${OCR_API_URL}/api/v2/jobs/${jobId}/dspace-collection`, {
      method:  'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        collection_id:   collectionId,
        collection_name: collectionName,
        community_name:  communityName,
      }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to save collection');
    }
    setJobs(prev => prev.map(j =>
      j.job_id === jobId
        ? { ...j, dspace_collection_id: collectionId, dspace_collection_name: collectionName, dspace_community_name: communityName }
        : j
    ));
    return await res.json();
  };

  const updateDSpaceStatus = async (jobId, dspaceStatus, { itemId, handle, error } = {}) => {
    const res = await fetch(`${OCR_API_URL}/api/v2/jobs/${jobId}/dspace-status`, {
      method:  'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dspace_status: dspaceStatus,
        item_id:       itemId || null,
        handle:        handle || null,
        error:         error  || null,
      }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to update DSpace status');
    }
    setJobs(prev => prev.map(j =>
      j.job_id === jobId
        ? {
            ...j,
            dspace_status:  dspaceStatus,
            dspace_item_id: itemId || j.dspace_item_id,
            dspace_handle:  handle || j.dspace_handle,
          }
        : j
    ));
    return await res.json();
  };

  const resetDSpaceUpload = async (jobId) => {
    const res = await fetch(`${OCR_API_URL}/api/v2/jobs/${jobId}/dspace-reset`, {
      method: 'POST',
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Failed to reset');
    }
    setJobs(prev => prev.map(j =>
      j.job_id === jobId ? { ...j, dspace_status: 'pending' } : j
    ));
    return await res.json();
  };

  return {
    jobs,
    loading,
    error,
    fetchJobs,
    uploadFile,
    downloadJob,
    deleteJob,
    saveDSpaceCollection,
    updateDSpaceStatus,
    resetDSpaceUpload,
  };
}

// ---------------------------------------------------------------
// UTILS
// ---------------------------------------------------------------
function isTerminalStatus(status) {
  return ['completed', 'failed', 'cancelled'].includes(status);
}