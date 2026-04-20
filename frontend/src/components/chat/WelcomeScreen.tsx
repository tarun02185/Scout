import { useState } from 'react';

interface Props {
  hasData: boolean;
  onSuggestion: (s: string) => void;
  onFiles: (f: File[]) => void;
  onUrl: (url: string, pathFilter?: string) => void;
  onOpenPrivacy: () => void;
  uploading: boolean;
}

const TYPES = [
  { label: 'CSV / Excel', color: 'bg-emerald-50 text-emerald-700 border-emerald-100' },
  { label: 'PDF',         color: 'bg-blue-50 text-blue-700 border-blue-100' },
  { label: 'Images',      color: 'bg-violet-50 text-violet-700 border-violet-100' },
  { label: 'Log files',   color: 'bg-amber-50 text-amber-700 border-amber-100' },
  { label: 'SQLite',      color: 'bg-slate-50 text-slate-700 border-slate-200' },
  { label: 'Website URL', color: 'bg-pink-50 text-pink-700 border-pink-100' },
];

// Grouped prompt examples so users can recognize rather than recall.
// Each group corresponds to a common intent the chat system handles well.
const GROUPED_PROMPTS: { title: string; prompts: string[] }[] = [
  { title: 'Summarize',  prompts: ['Give me a summary of this data', "What's this document about?"] },
  { title: 'Compare',    prompts: ['Compare the top 3 categories', 'North vs South region'] },
  { title: 'Explain',    prompts: ['Why did revenue drop?', 'What changed last month?'] },
  { title: 'Breakdown',  prompts: ['Break down sales by product', 'Show distribution by city'] },
];

export default function WelcomeScreen({ hasData, onSuggestion, onFiles, onUrl, onOpenPrivacy, uploading }: Props) {
  const [showUrl, setShowUrl] = useState(false);
  const [urlInput, setUrlInput] = useState('');
  const [pathFilter, setPathFilter] = useState('');

  const submitUrl = () => {
    const u = urlInput.trim();
    if (!u) return;
    onUrl(u, pathFilter.trim() || undefined);
    setUrlInput('');
    setPathFilter('');
    setShowUrl(false);
  };

  return (
    <div className="flex-1 flex flex-col items-center justify-start px-6 pt-16 pb-12 max-w-2xl mx-auto w-full">
      <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-purple-600 to-indigo-600 flex items-center justify-center text-white text-2xl font-bold mb-5 shadow-lg shadow-purple-200" aria-hidden="true">S</div>
      <h1 className="text-[28px] font-bold text-gray-900 mb-2 tracking-tight">Scout</h1>
      <p className="text-gray-500 text-sm text-center mb-8 max-w-md leading-relaxed">
        {hasData
          ? 'Your data is ready. Ask a question in plain English — I\'ll answer with sources and charts.'
          : 'Upload data or paste a URL, then ask anything in plain English.'}
      </p>

      {!hasData && (
        <>
          <label
            className="w-full max-w-lg flex flex-col items-center gap-3 py-10 rounded-2xl border-2 border-dashed border-gray-200 bg-white hover:border-purple-300 hover:bg-purple-50/30 transition-all cursor-pointer focus-within:border-purple-400 focus-within:ring-2 focus-within:ring-purple-200"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const f = Array.from(e.dataTransfer.files);
              if (f.length) onFiles(f);
            }}
          >
            <input
              type="file"
              multiple
              className="hidden"
              aria-label="Choose files to upload"
              onChange={(e) => {
                const f = Array.from(e.target.files || []);
                if (f.length) onFiles(f);
              }}
              accept=".csv,.xlsx,.xls,.json,.parquet,.pdf,.txt,.md,.log,.png,.jpg,.jpeg,.gif,.db,.sqlite"
            />
            {uploading ? (
              <>
                <div className="w-8 h-8 border-[3px] border-purple-200 border-t-purple-600 rounded-full animate-spin" />
                <p className="text-sm text-purple-600 font-medium">Processing…</p>
              </>
            ) : (
              <>
                <svg className="w-8 h-8 text-gray-300" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5"/>
                </svg>
                <p className="text-sm text-gray-600 font-medium">Drop files here, click to browse…</p>
                <p className="text-xs text-gray-400">or <button type="button" onClick={(e) => { e.preventDefault(); setShowUrl(true); }} className="text-purple-600 hover:text-purple-700 underline underline-offset-2 cursor-pointer">paste a website URL</button></p>
                <div className="flex flex-wrap gap-1.5 justify-center max-w-md mt-1">
                  {TYPES.map((t) => (
                    <span key={t.label} className={`px-2 py-0.5 text-[10.5px] rounded-full border ${t.color}`}>{t.label}</span>
                  ))}
                </div>
              </>
            )}
          </label>

          {showUrl && (
            <div className="w-full max-w-lg mt-3 p-3 rounded-xl border border-pink-200 bg-pink-50/50 space-y-2">
              <input
                type="url"
                autoFocus
                placeholder="https://en.wikipedia.org/wiki/..."
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') submitUrl(); }}
                className="w-full px-3 py-2 text-sm bg-white border border-pink-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-pink-300"
                aria-label="Website URL to crawl"
              />
              <input
                type="text"
                placeholder="Path filter (optional, e.g. /wiki/Python)"
                value={pathFilter}
                onChange={(e) => setPathFilter(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') submitUrl(); }}
                className="w-full px-3 py-1.5 text-xs bg-white border border-pink-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-pink-300"
                aria-label="Optional URL path filter"
              />
              <div className="flex gap-2">
                <button
                  onClick={submitUrl}
                  disabled={uploading || !urlInput.trim()}
                  className="flex-1 py-1.5 text-xs font-semibold bg-pink-600 text-white rounded-lg hover:bg-pink-700 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                >
                  Crawl website
                </button>
                <button
                  onClick={() => { setShowUrl(false); setUrlInput(''); setPathFilter(''); }}
                  className="px-3 py-1.5 text-xs text-gray-500 hover:bg-white rounded-lg cursor-pointer"
                >
                  Cancel
                </button>
              </div>
              <p className="text-[10.5px] text-gray-500 leading-tight">Up to 30 pages, same domain. Best on Wikipedia / docs / support portals.</p>
            </div>
          )}

          <button
            type="button"
            onClick={onOpenPrivacy}
            className="mt-7 inline-flex items-center gap-1.5 text-[12px] text-gray-500 hover:text-purple-600 cursor-pointer"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z"/>
            </svg>
            Learn how your data is protected
          </button>
        </>
      )}

      {hasData && (
        <div className="w-full max-w-xl space-y-4">
          {GROUPED_PROMPTS.map((g) => (
            <div key={g.title}>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-400 mb-1.5">{g.title}</p>
              <div className="flex flex-wrap gap-1.5">
                {g.prompts.map((p) => (
                  <button
                    key={p}
                    onClick={() => onSuggestion(p)}
                    className="px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-[12px] text-gray-700 hover:border-purple-300 hover:text-purple-700 hover:bg-purple-50/50 transition-all cursor-pointer shadow-sm focus-visible:outline-2 focus-visible:outline-purple-500 focus-visible:outline-offset-2"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
