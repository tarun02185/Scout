import { useState, useEffect, useRef } from 'react';
import type { Session, SourceMetadata } from '../../types';
import { listSessions, deleteSession } from '../../services/api';

interface Props {
  sessionId: string | null;
  sources: SourceMetadata[];
  onNew: () => void;
  onSelect: (id: string) => void;
  onUpload: (files: File[]) => void;
  onUploadUrl: (url: string, pathFilter?: string) => void;
  onRemoveSource: (sourceName: string) => void;
  onOpenPrivacy: () => void;
  onOpenShortcuts: () => void;
  uploading: boolean;
  onLogout: () => void;
  userName: string;
}

const TYPE_BADGE: Record<string, { label: string; color: string }> = {
  structured: { label: 'CSV', color: 'bg-emerald-100 text-emerald-700' },
  document:   { label: 'PDF', color: 'bg-blue-100 text-blue-700' },
  image:      { label: 'IMG', color: 'bg-violet-100 text-violet-700' },
  log:        { label: 'LOG', color: 'bg-amber-100 text-amber-700' },
  database:   { label: 'DB',  color: 'bg-slate-100 text-slate-600' },
  url:        { label: 'WEB', color: 'bg-pink-100 text-pink-700' },
};

function meta(s: SourceMetadata): string {
  if (s.source_type === 'structured') return `${s.row_count?.toLocaleString() ?? 0} rows · ${s.column_count ?? 0} cols`;
  if (s.source_type === 'document') return `${s.page_count ?? '?'} pages · ${s.chunk_count ?? 0} chunks`;
  if (s.source_type === 'log') return `${s.line_count?.toLocaleString() ?? 0} lines`;
  if (s.source_type === 'database') return `${s.table_count ?? 0} tables`;
  if (s.source_type === 'image') return 'Image';
  if (s.source_type === 'url') return `${s.pages_crawled ?? 0} pages · ${s.chunks ?? 0} chunks`;
  return '';
}

export default function Sidebar({
  sessionId, sources, onNew, onSelect, onUpload, onUploadUrl, onRemoveSource,
  onOpenPrivacy, onOpenShortcuts, uploading, onLogout, userName,
}: Props) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const [urlInput, setUrlInput] = useState('');
  const [pathFilter, setPathFilter] = useState('');
  const [showUrlForm, setShowUrlForm] = useState(false);

  const submitUrl = () => {
    const u = urlInput.trim();
    if (!u) return;
    onUploadUrl(u, pathFilter.trim() || undefined);
    setUrlInput('');
    setPathFilter('');
    setShowUrlForm(false);
  };

  useEffect(() => { listSessions().then(setSessions).catch(() => {}); }, [sessionId]);

  const del = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm('Delete this chat and its messages?')) return;
    await deleteSession(id);
    setSessions((p) => p.filter((s) => s.id !== id));
    if (id === sessionId) onNew();
  };

  return (
    <nav aria-label="Scout sidebar" className="w-[268px] bg-white border-r border-gray-200 flex flex-col h-screen select-none">
      <input
        ref={fileRef}
        type="file"
        multiple
        className="hidden"
        aria-label="Choose files to upload"
        onChange={(e) => { const f = Array.from(e.target.files || []); if (f.length) onUpload(f); e.target.value = ''; }}
        accept=".csv,.xlsx,.xls,.json,.parquet,.pdf,.txt,.md,.log,.png,.jpg,.jpeg,.gif,.db,.sqlite"
      />

      {/* Logo + new-chat */}
      <div className="px-5 pt-5 pb-4 border-b border-gray-100">
        <div className="flex items-center gap-2.5 mb-4">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-purple-600 to-indigo-600 flex items-center justify-center text-white font-bold text-sm shadow-sm shadow-purple-200" aria-hidden="true">S</div>
          <div>
            <p className="font-bold text-gray-900 text-[15px] leading-tight">Scout</p>
            <p className="text-[10.5px] text-gray-400">Talk to your data</p>
          </div>
        </div>
        <button
          onClick={onNew}
          className="w-full py-2.5 bg-purple-600 text-white rounded-xl text-[13px] font-semibold hover:bg-purple-700 transition-colors cursor-pointer flex items-center justify-center gap-1.5 shadow-sm shadow-purple-200"
          aria-label="New chat (⌘K)"
          title="New chat · ⌘K"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" d="M12 4.5v15m7.5-7.5h-15"/>
          </svg>
          New Chat
        </button>
      </div>

      {/* Sources */}
      <div className="px-4 pt-4 pb-2">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">Sources · {sources.length}</span>
          <div className="flex gap-0.5">
            <button
              onClick={() => setShowUrlForm((v) => !v)}
              aria-label="Add website URL"
              aria-expanded={showUrlForm}
              title="Add website URL"
              className="p-1 rounded-md text-pink-600 hover:bg-pink-50 cursor-pointer transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244"/>
              </svg>
            </button>
            <button
              onClick={() => fileRef.current?.click()}
              aria-label="Upload file"
              title="Upload file"
              className="p-1 rounded-md text-purple-600 hover:bg-purple-50 cursor-pointer transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5"/>
              </svg>
            </button>
          </div>
        </div>

        {showUrlForm && (
          <div className="mb-3 p-2.5 rounded-lg border border-pink-200 bg-pink-50/50 space-y-1.5 anim-fade-up">
            <input
              type="url"
              placeholder="https://en.wikipedia.org/wiki/..."
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submitUrl(); }}
              disabled={uploading}
              aria-label="Website URL"
              className="w-full px-2 py-1.5 text-[12px] bg-white border border-pink-200 rounded-md focus:outline-none focus:ring-2 focus:ring-pink-300"
            />
            <input
              type="text"
              placeholder="Path filter (optional, e.g. /wiki/Python)"
              value={pathFilter}
              onChange={(e) => setPathFilter(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submitUrl(); }}
              disabled={uploading}
              aria-label="Optional path filter"
              className="w-full px-2 py-1.5 text-[11px] bg-white border border-pink-200 rounded-md focus:outline-none focus:ring-2 focus:ring-pink-300"
            />
            <div className="flex gap-1">
              <button
                onClick={submitUrl}
                disabled={uploading || !urlInput.trim()}
                className="flex-1 py-1 text-[11px] bg-pink-600 text-white rounded-md hover:bg-pink-700 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                Crawl
              </button>
              <button
                onClick={() => { setShowUrlForm(false); setUrlInput(''); setPathFilter(''); }}
                className="px-2 py-1 text-[11px] text-gray-500 hover:bg-white rounded-md cursor-pointer"
              >
                Cancel
              </button>
            </div>
            <p className="text-[10px] text-gray-400 leading-tight">Up to 30 pages, same domain.</p>
          </div>
        )}

        <div className="space-y-1 max-h-56 overflow-y-auto">
          {sources.map((s, i) => {
            const badge = TYPE_BADGE[s.source_type] || TYPE_BADGE.database;
            return (
              <div key={i} className="group flex items-center gap-2.5 px-2 py-2 rounded-lg hover:bg-gray-50 transition-colors">
                <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-bold ${badge.color}`} aria-label={`${badge.label} source`}>{badge.label}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-medium text-gray-800 truncate" title={s.source_name}>{s.source_name}</p>
                  <p className="text-[11px] text-gray-400 truncate">{meta(s)}</p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm(`Remove "${s.source_name}"? This deletes its data and chunks from this chat.`)) {
                      onRemoveSource(s.source_name);
                    }
                  }}
                  disabled={uploading}
                  aria-label={`Remove ${s.source_name}`}
                  title="Remove source"
                  className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 p-1 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 cursor-pointer transition-opacity disabled:cursor-not-allowed"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12"/>
                  </svg>
                </button>
              </div>
            );
          })}
          {sources.length === 0 && !uploading && (
            <button
              onClick={() => fileRef.current?.click()}
              aria-label="Upload files to start"
              className="w-full flex flex-col items-center gap-1.5 py-5 border-2 border-dashed border-gray-200 rounded-xl text-gray-400 hover:border-purple-300 hover:text-purple-500 hover:bg-purple-50/40 transition-all cursor-pointer"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5"/>
              </svg>
              <span className="text-xs">Upload files to start</span>
            </button>
          )}
        </div>
      </div>

      {/* Chat history */}
      <div className="flex-1 overflow-y-auto px-4 pt-3">
        <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Chats</p>
        <ul className="space-y-0.5" role="list">
          {sessions.slice(0, 12).map((s) => (
            <li key={s.id}>
              <div
                onClick={() => onSelect(s.id)}
                role="button"
                tabIndex={0}
                aria-current={s.id === sessionId ? 'page' : undefined}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(s.id); } }}
                className={`group flex items-center gap-2 px-2.5 py-2 rounded-lg cursor-pointer transition-colors text-[13px] ${
                  s.id === sessionId ? 'bg-purple-50 text-purple-700 font-medium' : 'text-gray-500 hover:bg-gray-50'
                }`}
              >
                <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z"/>
                </svg>
                <span className="flex-1 truncate">{s.title}</span>
                <button
                  onClick={(e) => del(s.id, e)}
                  aria-label={`Delete chat ${s.title}`}
                  className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 p-0.5 hover:bg-red-50 rounded cursor-pointer transition-opacity"
                >
                  <svg className="w-3.5 h-3.5 text-red-400" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0"/>
                  </svg>
                </button>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-gray-100 space-y-2">
        <div className="flex items-center gap-1">
          <button
            onClick={onOpenPrivacy}
            className="flex-1 flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-[12px] text-gray-500 hover:text-purple-600 hover:bg-purple-50/60 cursor-pointer transition-colors"
            aria-label="Open privacy panel (P)"
            title="Privacy · P"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z"/>
            </svg>
            Privacy
          </button>
          <button
            onClick={onOpenShortcuts}
            className="px-2 py-1.5 rounded-lg text-[12px] text-gray-500 hover:text-purple-600 hover:bg-purple-50/60 cursor-pointer transition-colors"
            aria-label="Keyboard shortcuts (?)"
            title="Shortcuts · ?"
          >
            <kbd className="inline-flex items-center justify-center w-5 h-5 rounded border border-gray-200 bg-gray-50 text-[10px] font-semibold text-gray-600">?</kbd>
          </button>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-purple-100 flex items-center justify-center text-purple-600 text-xs font-bold" aria-hidden="true">
              {userName?.charAt(0)?.toUpperCase() || 'G'}
            </div>
            <span className="text-[13px] text-gray-600 truncate max-w-[120px]">{userName}</span>
          </div>
          <button
            onClick={onLogout}
            className="text-xs text-gray-400 hover:text-red-500 cursor-pointer transition-colors"
            aria-label="Sign out"
          >
            Sign out
          </button>
        </div>
      </div>
    </nav>
  );
}
