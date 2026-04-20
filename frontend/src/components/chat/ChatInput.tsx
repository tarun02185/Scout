import { forwardRef, useImperativeHandle, useRef, useEffect, useState } from 'react';

interface Props {
  onSend: (m: string) => void;
  onFiles?: (files: File[]) => void;
  onStop?: () => void;
  loading: boolean;
  placeholder?: string;
}

export interface ChatInputHandle {
  focus: () => void;
}

const ChatInput = forwardRef<ChatInputHandle, Props>(function ChatInput(
  { onSend, onFiles, onStop, loading, placeholder }: Props,
  ref,
) {
  const [val, setVal] = useState('');
  const taRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useImperativeHandle(ref, () => ({
    focus: () => taRef.current?.focus(),
  }), []);

  useEffect(() => {
    if (taRef.current) {
      taRef.current.style.height = 'auto';
      taRef.current.style.height = Math.min(taRef.current.scrollHeight, 140) + 'px';
    }
  }, [val]);

  const send = () => {
    const t = val.trim();
    if (!t || loading) return;
    onSend(t);
    setVal('');
  };

  const handleFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length && onFiles) onFiles(files);
    e.target.value = '';
  };

  const canSend = val.trim().length > 0 && !loading;

  return (
    <div className="relative">
      <input
        ref={fileRef}
        type="file"
        multiple
        className="hidden"
        aria-label="Choose files to attach"
        onChange={handleFiles}
        accept=".csv,.xlsx,.xls,.json,.parquet,.pdf,.txt,.md,.log,.png,.jpg,.jpeg,.gif,.db,.sqlite"
      />

      {loading && (
        <div className="absolute -top-8 left-1/2 -translate-x-1/2 flex items-center gap-2 px-3 py-1 bg-purple-50 text-purple-600 rounded-full text-[11px] font-medium shadow-sm">
          <span className="flex gap-0.5" aria-hidden="true">
            {[0, 150, 300].map((d) => (
              <span key={d} className="w-1 h-1 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: d + 'ms' }} />
            ))}
          </span>
          Thinking…
          {onStop && (
            <button
              type="button"
              onClick={onStop}
              className="ml-1 px-1.5 py-0.5 rounded-md bg-white/70 hover:bg-white text-purple-700 text-[10.5px] font-semibold cursor-pointer"
              aria-label="Stop generating (Esc)"
            >
              Stop · Esc
            </button>
          )}
        </div>
      )}

      <div className="flex items-end gap-2 bg-white border border-gray-200 rounded-2xl px-3 py-2.5 shadow-sm focus-within:border-purple-400 focus-within:ring-2 focus-within:ring-purple-100 transition-all">
        {onFiles && (
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className="p-2 rounded-lg text-gray-400 hover:text-purple-600 hover:bg-purple-50 transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-purple-500 focus-visible:outline-offset-2"
            aria-label="Attach files"
            title="Attach files (CSV, PDF, images, etc.)"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="m18.375 12.739-7.693 7.693a4.5 4.5 0 0 1-6.364-6.364l10.94-10.94A3 3 0 1 1 19.5 7.372L8.552 18.32m.009-.01-.01.01m5.699-9.941-7.81 7.81a1.5 1.5 0 0 0 2.112 2.13" />
            </svg>
          </button>
        )}

        <textarea
          ref={taRef}
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder={placeholder || 'Ask anything about your data… (press / to focus)'}
          rows={1}
          disabled={loading}
          aria-label="Ask a question about your data"
          className="flex-1 resize-none bg-transparent text-[14px] text-gray-800 placeholder-gray-400 focus:outline-none leading-relaxed"
        />

        {loading && onStop ? (
          <button
            type="button"
            onClick={onStop}
            className="p-2 rounded-lg bg-red-50 text-red-600 hover:bg-red-100 transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-red-500 focus-visible:outline-offset-2"
            aria-label="Stop generating"
            title="Stop generating (Esc)"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          </button>
        ) : (
          <button
            type="button"
            onClick={send}
            disabled={!canSend}
            aria-label="Send message"
            className={`p-2 rounded-lg transition-colors focus-visible:outline-2 focus-visible:outline-purple-500 focus-visible:outline-offset-2 ${
              canSend
                ? 'bg-purple-600 text-white hover:bg-purple-700 cursor-pointer'
                : 'bg-gray-100 text-gray-300 cursor-not-allowed'
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
});

export default ChatInput;
