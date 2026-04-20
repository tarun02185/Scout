import { useEffect, useState } from 'react';

/** Possible states of the in-progress ingestion banner. */
export type StatusKind = 'idle' | 'upload' | 'crawl' | 'thinking';

interface Props {
  kind: StatusKind;
  label?: string;
  /** If provided, a determinate progress bar is shown. Otherwise: indeterminate. */
  percent?: number;
}

/**
 * Persistent top-of-content banner that surfaces long-running work (upload,
 * crawl, thinking) so it's always visible — addressing the "Visibility of
 * system status" heuristic. Ephemeral toasts are still used for terminal
 * success/failure messages.
 */
export default function StatusBanner({ kind, label, percent }: Props) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (kind === 'idle') {
      setElapsed(0);
      return;
    }
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [kind]);

  if (kind === 'idle') return null;

  const tone =
    kind === 'crawl' ? 'from-pink-500 to-rose-500' :
    kind === 'upload' ? 'from-purple-500 to-indigo-500' :
    'from-amber-500 to-orange-500';

  const defaultLabel =
    kind === 'crawl' ? 'Crawling website — indexing pages' :
    kind === 'upload' ? 'Processing your files' :
    'Thinking';

  return (
    <div
      role="status"
      aria-live="polite"
      className="bg-white border-b border-gray-200 px-5 py-2.5 flex items-center gap-3 shrink-0"
    >
      <span className={`w-1.5 h-1.5 rounded-full bg-gradient-to-r ${tone} animate-pulse`} />
      <span className="text-[13px] text-gray-700 font-medium">
        {label || defaultLabel}
        <span className="text-gray-400 font-normal ml-1.5">· {elapsed}s</span>
      </span>
      <div className="flex-1 h-1 bg-gray-100 rounded-full overflow-hidden max-w-[280px] ml-2">
        {typeof percent === 'number' ? (
          <div
            className={`h-full bg-gradient-to-r ${tone} transition-[width] duration-300`}
            style={{ width: `${Math.max(5, Math.min(100, percent))}%` }}
          />
        ) : (
          <div className={`h-full bg-gradient-to-r ${tone} animate-[scout-slide_1.2s_ease-in-out_infinite]`} style={{ width: '40%' }} />
        )}
      </div>
    </div>
  );
}
