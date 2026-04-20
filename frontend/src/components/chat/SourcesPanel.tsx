import { useState } from 'react';
import CopyButton from '../ui/CopyButton';

export default function SourcesPanel({ sources, sql }: { sources: string[]; sql?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-controls="sources-panel"
        className="text-xs text-purple-600 hover:text-purple-700 font-medium cursor-pointer flex items-center gap-1 focus-visible:outline-2 focus-visible:outline-purple-500 focus-visible:outline-offset-2 rounded"
      >
        <span className="inline-block transition-transform" style={{ transform: open ? 'rotate(90deg)' : 'none' }}>▸</span>
        {open ? 'Hide' : 'Show'} details &amp; sources
      </button>
      {open && (
        <div id="sources-panel" className="mt-2 p-3 bg-gray-50 rounded-lg border border-gray-100 space-y-2 anim-fade-up">
          {sources.length > 0 && (
            <div>
              <p className="text-[10.5px] font-semibold uppercase tracking-wider text-gray-400 mb-1.5">Sources used</p>
              <div className="flex flex-wrap gap-1">
                {sources.map((s, i) => (
                  <span key={i} className="px-2 py-0.5 bg-purple-100 text-purple-700 rounded-full text-[11px] font-medium">{s}</span>
                ))}
              </div>
            </div>
          )}
          {sql && (
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <p className="text-[10.5px] font-semibold uppercase tracking-wider text-gray-400">SQL executed</p>
                <CopyButton text={sql} label="Copy SQL" />
              </div>
              <pre className="bg-[#1e1e2e] text-green-400 p-3 rounded-lg overflow-x-auto font-mono text-xs whitespace-pre-wrap break-words">{sql}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
