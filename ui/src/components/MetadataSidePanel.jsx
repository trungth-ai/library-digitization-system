"use client";

import React, { useState, useEffect, useRef } from "react";
import { X, Save, Upload, RotateCcw, Plus, Trash2, ChevronDown, Pencil } from "lucide-react";

// Client gọi qua proxy same-origin của Next (/api/ocr/...) — KHÔNG dùng URL tuyệt đối tới
// FastAPI: trình duyệt không chắc tới được địa chỉ đó, và URL http:// trên trang https sẽ bị
// chặn vì mixed content. Đây là nguyên nhân lỗi "Failed to fetch" khi lưu collection.

// ─── Dublin Core catalog ─────────────────────────────────────────────────────
const DC_CATALOG = [
  { key: "dc.title",                group: "Bibliographic", label: "Title",            lang: "vi_VN" },
  { key: "dc.title.alternative",    group: "Bibliographic", label: "Alternative Title", lang: "en_US" },
  { key: "dc.contributor.author",   group: "Bibliographic", label: "Author",            lang: "vi_VN", multi: true },
  { key: "dc.contributor.advisor",  group: "Bibliographic", label: "Advisor",           lang: "vi_VN", multi: true },
  { key: "dc.contributor.editor",   group: "Bibliographic", label: "Editor",            lang: "vi_VN", multi: true },
  { key: "dc.publisher",            group: "Bibliographic", label: "Publisher",         lang: "vi_VN" },
  { key: "dc.date.issued",          group: "Bibliographic", label: "Year",              lang: null    },
  { key: "dc.identifier.isbn",      group: "Bibliographic", label: "ISBN",              lang: null    },
  { key: "dc.source",               group: "Bibliographic", label: "Source",            lang: null    },
  { key: "dc.subject",              group: "Content",       label: "Subject",           lang: "vi_VN", multi: true },
  { key: "dc.description.abstract", group: "Content",       label: "Abstract",          lang: "vi_VN", textarea: true },
  { key: "dc.description",          group: "Content",       label: "Description",       lang: "vi_VN", textarea: true },
  { key: "dc.type",                 group: "Content",       label: "Type",              lang: "en_US" },
  { key: "dc.language.iso",         group: "Content",       label: "Language",          lang: null    },
  { key: "dc.description.degree",   group: "Content",       label: "Degree",            lang: "vi_VN" },
  { key: "dc.department",           group: "Content",       label: "Department",        lang: "en_US" },
  { key: "dc.coverage",             group: "Content",       label: "Coverage",          lang: "vi_VN" },
  { key: "dc.format.extent",        group: "Technical",     label: "Pages",             lang: null    },
  { key: "dc.size",                 group: "Technical",     label: "File Size",         lang: null    },
  { key: "dc.format.mimetype",      group: "Technical",     label: "MIME Type",         lang: null,    readonly: true },
  { key: "dc.rights",               group: "Technical",     label: "Rights",            lang: "en_US" },
  { key: "dc.identifier.uri",       group: "Technical",     label: "URI",               lang: null    },
  { key: "dc.relation",             group: "Technical",     label: "Relation",          lang: null    },
];

const KEY_LABELS    = Object.fromEntries(DC_CATALOG.map(d => [d.key, d.label]));
const KEY_META      = Object.fromEntries(DC_CATALOG.map(d => [d.key, d]));
const TEXTAREA_KEYS = new Set(DC_CATALOG.filter(d => d.textarea).map(d => d.key));
const MULTI_KEYS    = new Set(DC_CATALOG.filter(d => d.multi).map(d => d.key));
const READONLY_KEYS = new Set(DC_CATALOG.filter(d => d.readonly).map(d => d.key));

const GROUPS = [
  { label: "Bibliographic", keys: DC_CATALOG.filter(d => d.group === "Bibliographic").map(d => d.key) },
  { label: "Content",       keys: DC_CATALOG.filter(d => d.group === "Content").map(d => d.key)       },
  { label: "Technical",     keys: DC_CATALOG.filter(d => d.group === "Technical").map(d => d.key)     },
];

// ─── Main component ───────────────────────────────────────────────────────────
export default function MetadataSidePanel({ job, onClose, onSaved, onPush }) {
  const [fields,  setFields]  = useState([]);
  const [saving,  setSaving]  = useState(false);
  const [pushing, setPushing] = useState(false);
  const [dirty,   setDirty]   = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);

  useEffect(() => {
    if (!job) return;
    const load = async () => {
      try {
        const res  = await fetch(`/api/ocr/jobs/${job.job_id}/metadata`);
        if (!res.ok) throw new Error();
        const data = await res.json();
        setFields(data.metadata || []);
        setDirty(false);
      } catch { /* silent */ }
    };
    load();
  }, [job?.job_id]);

  const markDirty = () => { setDirty(true); setSaveMsg(null); };

  const handleChange = (idx, value) => {
    setFields(prev => { const n = [...prev]; n[idx] = { ...n[idx], value }; return n; });
    markDirty();
  };

  const handleRemove = (idx) => {
    setFields(prev => prev.filter((_, i) => i !== idx));
    markDirty();
  };

  const handleAddField = (key, value, language) => {
    setFields(prev => [...prev, { key, value, language }]);
    markDirty();
  };

  const handleSave = async () => {
    setSaving(true); setSaveMsg(null);
    try {
      const res = await fetch(`/api/ocr/jobs/${job.job_id}/metadata`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metadata: fields }),
      });
      if (!res.ok) throw new Error();
      setDirty(false); setSaveMsg("saved");
      onSaved?.(job.job_id, fields);
      setTimeout(() => setSaveMsg(null), 2500);
    } catch { setSaveMsg("error"); }
    finally { setSaving(false); }
  };

  const handlePush = async () => {
    if (dirty) await handleSave();
    setPushing(true);
    try { await onPush(job.job_id); }
    finally { setPushing(false); }
  };

  if (!job) return null;

  const groupedKeys  = new Set(GROUPS.flatMap(g => g.keys));
  const otherFields  = fields.map((f, i) => ({ ...f, idx: i })).filter(f => !groupedKeys.has(f.key));
  const existingKeys = new Set(fields.map(f => f.key));

  return (
    <>
      <div className="fixed inset-0 bg-black/10 z-30 backdrop-blur-[1px]" onClick={onClose} />

      <div className="fixed right-0 top-0 h-full w-full max-w-lg bg-white shadow-2xl z-40 flex flex-col animate-slide-in-right">

        {/* Header */}
        <div className="flex items-start justify-between px-6 py-4 border-b border-gray-100 shrink-0">
          <div className="flex-1 min-w-0 pr-4">
            <p className="text-xs text-gray-400 font-medium uppercase tracking-wider mb-1">Edit Metadata</p>
            <h3 className="text-sm font-semibold text-gray-900 truncate">{job.filename}</h3>
          </div>
          <button onClick={onClose} className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Save status */}
        {saveMsg && (
          <div className={`px-6 py-2 text-xs font-medium shrink-0 ${saveMsg === "saved" ? "bg-green-50 text-green-700 border-b border-green-100" : "bg-red-50 text-red-700 border-b border-red-100"}`}>
            {saveMsg === "saved" ? "✓ Saved successfully" : "✗ Save failed, please try again"}
          </div>
        )}

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">

          {/* Grouped existing fields */}
          {GROUPS.map(group => {
            const gf = fields.map((f, idx) => ({ ...f, idx })).filter(f => group.keys.includes(f.key));
            if (gf.length === 0) return null;
            return (
              <div key={group.label}>
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">{group.label}</p>
                <div className="space-y-3">
                  {/* Render theo tung key, Add button nam ngay duoi field cuoi cua key do */}
                  {group.keys
                    .filter(k => gf.some(f => f.key === k))
                    .map(k => {
                      const keyFields = gf.filter(f => f.key === k);
                      const isMulti   = MULTI_KEYS.has(k);
                      const sample    = keyFields[0];
                      return (
                        <div key={k} className="space-y-3">
                          {keyFields.map(f => (
                            <FieldRow
                              key={`${f.key}-${f.idx}`}
                              field={f}
                              onChange={val => handleChange(f.idx, val)}
                              onRemove={isMulti && keyFields.length > 1 ? () => handleRemove(f.idx) : null}
                            />
                          ))}
                          {/* Add button nam ngay duoi fields cua chinh key nay */}
                          {isMulti && (
                            <button
                              onClick={() => handleAddField(k, "", sample?.language || "")}
                              className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 font-medium px-1"
                            >
                              <Plus className="w-3.5 h-3.5" />
                              Add {KEY_LABELS[k] || k}
                            </button>
                          )}
                        </div>
                      );
                    })
                  }
                </div>
              </div>
            );
          })}

          {/* Other / custom fields already added */}
          {otherFields.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">Other</p>
              <div className="space-y-3">
                {otherFields.map(f => (
                  <FieldRow
                    key={`${f.key}-${f.idx}`}
                    field={f}
                    onChange={val => handleChange(f.idx, val)}
                    onRemove={() => handleRemove(f.idx)}
                    showKey
                  />
                ))}
              </div>
            </div>
          )}

          {/* Add Field section */}
          <AddFieldSection existingKeys={existingKeys} onAdd={handleAddField} />

        </div>

        {/* Footer */}
        <div className="shrink-0 px-6 py-4 border-t border-gray-100 flex items-center gap-3 bg-gray-50/50">
          <button
            onClick={handleSave}
            disabled={saving || !dirty}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-white border border-gray-200 text-gray-700 hover:border-gray-300 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm"
          >
            {saving ? <RotateCcw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {dirty ? "Save Changes" : "Saved"}
          </button>
          <button
            onClick={handlePush}
            disabled={pushing || job.dspace_status === "uploaded"}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-sm"
          >
            {pushing ? <RotateCcw className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            {job.dspace_status === "uploaded" ? "Already Uploaded" : "Save & Push to DSpace"}
          </button>
        </div>
      </div>

      <style jsx>{`
        @keyframes slide-in-right {
          from { transform: translateX(100%); }
          to   { transform: translateX(0); }
        }
        .animate-slide-in-right { animation: slide-in-right 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
      `}</style>
    </>
  );
}

// ─── AddFieldSection ──────────────────────────────────────────────────────────
function AddFieldSection({ existingKeys, onAdd }) {
  const [open,     setOpen]     = useState(false);
  const [mode,     setMode]     = useState("pick");
  const [pickKey,  setPickKey]  = useState("");
  const [pickVal,  setPickVal]  = useState("");
  const [custKey,  setCustKey]  = useState("");
  const [custVal,  setCustVal]  = useState("");
  const [custLang, setCustLang] = useState("");
  const [keyError, setKeyError] = useState("");
  const valRef = useRef(null);

  // Keys chua co (bao gom multi-value duoc phep them nhieu lan)
  const availableByGroup = {};
  DC_CATALOG.forEach(d => {
    if (d.readonly) return;
    if (existingKeys.has(d.key) && !d.multi) return;
    if (!availableByGroup[d.group]) availableByGroup[d.group] = [];
    availableByGroup[d.group].push(d);
  });

  const reset = () => {
    setOpen(false); setMode("pick"); setPickKey(""); setPickVal("");
    setCustKey(""); setCustVal(""); setCustLang(""); setKeyError("");
  };

  const handlePickAdd = () => {
    if (!pickKey || !pickVal.trim()) return;
    const meta = KEY_META[pickKey];
    onAdd(pickKey, pickVal.trim(), meta?.lang ?? "");
    setPickVal("");
    // Giu key de co the them tiep (huu ich cho multi-value)
  };

  const handleCustomAdd = () => {
    const k = custKey.trim().toLowerCase();
    if (!k) { setKeyError("Key is required"); return; }
    if (!/^[a-z]+(\.[a-z]+)+$/.test(k)) {
      setKeyError("Must be namespace.element format (e.g. dc.title)");
      return;
    }
    if (!custVal.trim()) { setKeyError("Value is required"); return; }
    onAdd(k, custVal.trim(), custLang.trim() || null);
    setCustKey(""); setCustVal(""); setCustLang(""); setKeyError("");
  };

  useEffect(() => {
    if (pickKey && valRef.current) valRef.current.focus();
  }, [pickKey]);

  const selectedMeta   = pickKey ? KEY_META[pickKey] : null;
  const isPickTextarea = selectedMeta?.textarea;

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 border border-dashed border-indigo-200 transition-colors"
      >
        <Plus className="w-4 h-4" />
        Add Field
      </button>
    );
  }

  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50/40 p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-indigo-700 uppercase tracking-wider">Add Field</p>
        <button onClick={reset} className="w-6 h-6 flex items-center justify-center text-gray-400 hover:text-gray-600 rounded transition-colors">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Mode tabs */}
      <div className="flex gap-1 p-0.5 bg-white rounded-lg border border-gray-200">
        <button
          onClick={() => setMode("pick")}
          className={`flex-1 py-1.5 rounded-md text-xs font-medium transition-colors ${mode === "pick" ? "bg-indigo-600 text-white shadow-sm" : "text-gray-500 hover:text-gray-700"}`}
        >
          Quick Pick
        </button>
        <button
          onClick={() => setMode("custom")}
          className={`flex-1 py-1.5 rounded-md text-xs font-medium transition-colors flex items-center justify-center gap-1 ${mode === "custom" ? "bg-indigo-600 text-white shadow-sm" : "text-gray-500 hover:text-gray-700"}`}
        >
          <Pencil className="w-3 h-3" />
          Custom Key
        </button>
      </div>

      {/* Quick Pick */}
      {mode === "pick" && (
        <div className="space-y-2">
          <div className="relative">
            <select
              value={pickKey}
              onChange={e => {
                if (e.target.value === "__custom__") { setMode("custom"); setPickKey(""); return; }
                setPickKey(e.target.value); setPickVal("");
              }}
              className="w-full text-sm text-gray-800 bg-white border border-gray-200 rounded-lg px-3 py-2 pr-8 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 appearance-none cursor-pointer"
            >
              <option value="">— Select a field —</option>
              {Object.entries(availableByGroup).map(([grp, items]) => (
                <optgroup key={grp} label={grp}>
                  {items.map(d => (
                    <option key={d.key} value={d.key}>{d.label}</option>
                  ))}
                </optgroup>
              ))}
              <optgroup label="─────────────">
                <option value="__custom__">✏️  Enter custom key...</option>
              </optgroup>
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
          </div>

          {pickKey && (
            <>
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">
                  {KEY_LABELS[pickKey]} value
                  {selectedMeta?.lang && (
                    <span className="ml-1.5 text-gray-300 font-normal">[{selectedMeta.lang}]</span>
                  )}
                </label>
                {isPickTextarea ? (
                  <textarea
                    ref={valRef}
                    value={pickVal}
                    onChange={e => setPickVal(e.target.value)}
                    rows={3}
                    placeholder={`Enter ${KEY_LABELS[pickKey]}...`}
                    className="w-full text-sm text-gray-900 bg-white border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 resize-none transition-colors"
                  />
                ) : (
                  <input
                    ref={valRef}
                    type="text"
                    value={pickVal}
                    onChange={e => setPickVal(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && handlePickAdd()}
                    placeholder={`Enter ${KEY_LABELS[pickKey]}...`}
                    className="w-full text-sm text-gray-900 bg-white border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-colors"
                  />
                )}
              </div>
              <button
                onClick={handlePickAdd}
                disabled={!pickVal.trim()}
                className="w-full py-2 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Add {KEY_LABELS[pickKey]}
              </button>
            </>
          )}
        </div>
      )}

      {/* Custom Key */}
      {mode === "custom" && (
        <div className="space-y-2">
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Key</label>
            <input
              type="text"
              value={custKey}
              onChange={e => { setCustKey(e.target.value); setKeyError(""); }}
              onKeyDown={e => e.key === "Enter" && handleCustomAdd()}
              placeholder="e.g. dc.identifier.doi"
              spellCheck={false}
              className={`w-full text-sm font-mono text-gray-900 bg-white border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 transition-colors ${keyError ? "border-red-300 focus:border-red-400" : "border-gray-200 focus:border-indigo-400"}`}
            />
            {keyError && <p className="text-xs text-red-500 mt-1">{keyError}</p>}
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Value</label>
            <input
              type="text"
              value={custVal}
              onChange={e => setCustVal(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleCustomAdd()}
              placeholder="Enter value..."
              className="w-full text-sm text-gray-900 bg-white border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">
              Language
              <span className="text-gray-400 font-normal ml-1">(optional)</span>
            </label>
            <input
              type="text"
              value={custLang}
              onChange={e => setCustLang(e.target.value)}
              placeholder="e.g. vi_VN, en_US"
              className="w-full text-sm text-gray-900 bg-white border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition-colors"
            />
          </div>
          <button
            onClick={handleCustomAdd}
            disabled={!custKey.trim() || !custVal.trim()}
            className="w-full py-2 rounded-lg text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Add Custom Field
          </button>
        </div>
      )}
    </div>
  );
}

// ─── FieldRow ─────────────────────────────────────────────────────────────────
function FieldRow({ field, onChange, onRemove, showKey = false }) {
  const label    = KEY_LABELS[field.key] || field.key;
  const readonly = READONLY_KEYS.has(field.key);
  const isArea   = TEXTAREA_KEYS.has(field.key);

  return (
    <div className="group flex gap-2 items-start">
      <div className="flex-1">
        <label className="block text-xs font-medium text-gray-500 mb-1">
          {label}
          {showKey && label !== field.key && (
            <span className="ml-1.5 text-gray-300 font-mono font-normal text-[10px]">{field.key}</span>
          )}
          {field.language && (
            <span className="ml-1.5 text-gray-300 font-normal">[{field.language}]</span>
          )}
        </label>
        {isArea ? (
          <textarea
            value={field.value}
            onChange={e => onChange(e.target.value)}
            disabled={readonly}
            rows={3}
            className="w-full text-sm text-gray-900 bg-white border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed transition-colors resize-none"
          />
        ) : (
          <input
            type="text"
            value={field.value}
            onChange={e => onChange(e.target.value)}
            disabled={readonly}
            className="w-full text-sm text-gray-900 bg-white border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed transition-colors"
          />
        )}
      </div>
      {onRemove && (
        <button
          onClick={onRemove}
          className="mt-5 w-7 h-7 flex items-center justify-center text-gray-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors shrink-0"
          title="Remove"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}