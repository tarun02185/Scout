import { useEffect, useRef, useState } from 'react';
import { Toaster, toast } from 'react-hot-toast';
import { useChat } from './hooks/useChat';
import { useAuth } from './hooks/useAuth';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import Sidebar from './components/layout/Sidebar';
import ChatBubble from './components/chat/ChatBubble';
import ChatInput, { type ChatInputHandle } from './components/chat/ChatInput';
import WelcomeScreen from './components/chat/WelcomeScreen';
import LoginScreen from './components/auth/LoginScreen';
import StatusBanner, { type StatusKind } from './components/ui/StatusBanner';
import PrivacyDrawer from './components/ui/PrivacyDrawer';
import ShortcutSheet from './components/ui/ShortcutSheet';

export default function App() {
  const { user, loading: authLoading, login, loginGuest, logout } = useAuth();
  const {
    sessionId, messages, sources, loading, uploading, streaming,
    init, load, send, upload, uploadLink, removeSrc, stopStream,
  } = useChat();

  const endRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<ChatInputHandle>(null);

  const [privacyOpen, setPrivacyOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [statusKind, setStatusKind] = useState<StatusKind>('idle');
  const [statusLabel, setStatusLabel] = useState<string>('');

  useEffect(() => { if (user) init(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [user]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages, streaming]);

  // Derive status from transient app state.
  useEffect(() => {
    if (uploading && statusKind !== 'crawl') setStatusKind('upload');
    else if (loading && !streaming) setStatusKind('thinking');
    else if (!uploading && !loading) setStatusKind('idle');
    // streaming tokens arriving: keep 'thinking' banner off (the bubble handles it)
  }, [uploading, loading, streaming, statusKind]);

  useKeyboardShortcuts({
    onNewChat: () => { if (!loading) init(); },
    onFocusInput: () => chatInputRef.current?.focus(),
    onToggleHelp: () => setShortcutsOpen((v) => !v),
    onTogglePrivacy: () => setPrivacyOpen((v) => !v),
    onEscape: () => {
      // Precedence: close modals → stop stream.
      if (shortcutsOpen) setShortcutsOpen(false);
      else if (privacyOpen) setPrivacyOpen(false);
      else if (loading) stopStream();
    },
  });

  if (!user) {
    return (
      <LoginScreen
        onLogin={async (c) => { if (!(await login(c))) toast.error('Login failed'); }}
        onGuest={async () => { if (!(await loginGuest())) toast.error('Backend not running?'); }}
        loading={authLoading}
      />
    );
  }

  const onUpload = async (files: File[]) => {
    setStatusKind('upload');
    setStatusLabel(`Processing ${files.length} file${files.length > 1 ? 's' : ''}`);
    try {
      const res = await upload(files);
      res?.forEach((r) => {
        if (r.status === 'success') toast.success(`${r.file} · ready`);
        else if (r.status === 'error') toast.error(`${r.file}: ${r.error}`);
      });
    } catch { toast.error('Upload failed'); }
    finally { setStatusKind('idle'); setStatusLabel(''); }
  };

  const onUploadUrl = async (url: string, pathFilter?: string) => {
    setStatusKind('crawl');
    setStatusLabel(`Crawling ${new URL(url).hostname}${pathFilter ? ' · ' + pathFilter : ''}`);
    const t = toast.loading(`Crawling…`);
    try {
      const res = await uploadLink(url, { path_filter: pathFilter || undefined });
      toast.dismiss(t);
      const pages = res?.metadata?.pages_crawled ?? 0;
      toast.success(`${res.file} · ${pages} pages indexed`);
    } catch (e: any) {
      toast.dismiss(t);
      toast.error(e?.response?.data?.detail || 'URL crawl failed');
    } finally { setStatusKind('idle'); setStatusLabel(''); }
  };

  const hasMessages = messages.length > 0;
  const placeholder = sources.length === 0
    ? 'Upload a file or paste a URL, then ask anything…'
    : 'Ask anything about your data…  (press / to focus)';

  return (
    <div className="flex h-screen bg-[#f8f9fb]">
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <Toaster position="top-right" toastOptions={{ className: 'text-sm', duration: 3000, style: { borderRadius: '10px' } }} />

      <Sidebar
        sessionId={sessionId} sources={sources}
        onNew={() => init()} onSelect={(id) => load(id)}
        onUpload={onUpload} onUploadUrl={onUploadUrl} uploading={uploading}
        onRemoveSource={async (name) => {
          try { await removeSrc(name); toast.success(`Removed ${name}`); }
          catch (e: any) { toast.error(e?.message || 'Could not remove source'); }
        }}
        onOpenPrivacy={() => setPrivacyOpen(true)}
        onOpenShortcuts={() => setShortcutsOpen(true)}
        onLogout={logout} userName={user.name}
      />

      <main id="main-content" className="flex-1 flex flex-col h-screen min-w-0">
        {/* Header */}
        <div className="h-12 bg-white border-b border-gray-200 flex items-center px-5 gap-3 shrink-0">
          <span className="text-[13px] text-gray-500">
            {sources.length > 0
              ? `${sources.length} source${sources.length > 1 ? 's' : ''} loaded`
              : 'No sources loaded'}
          </span>
          <div className="flex-1" />
          <div className="flex gap-1.5 overflow-hidden">
            {sources.slice(0, 4).map((s, i) => (
              <span key={i} className="px-2.5 py-0.5 bg-purple-50 text-purple-600 rounded-md text-[11px] font-medium truncate max-w-[140px]" title={s.source_name}>
                {s.source_name}
              </span>
            ))}
            {sources.length > 4 && <span className="px-2 py-0.5 bg-gray-100 text-gray-400 rounded-md text-[11px]">+{sources.length - 4}</span>}
          </div>
          <button
            onClick={() => setPrivacyOpen(true)}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 text-[11px] font-medium hover:bg-emerald-100 cursor-pointer transition-colors"
            aria-label="Privacy details"
            title="Your data is protected by 5 guardrail layers — click for details"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z"/>
            </svg>
            Privacy on
          </button>
        </div>

        <StatusBanner kind={statusKind} label={statusLabel || undefined} />

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {!hasMessages ? (
            <WelcomeScreen
              hasData={sources.length > 0}
              onSuggestion={send}
              onFiles={onUpload}
              onUrl={onUploadUrl}
              onOpenPrivacy={() => setPrivacyOpen(true)}
              uploading={uploading}
            />
          ) : (
            <div className="max-w-3xl mx-auto px-6 py-6 space-y-5">
              {messages.map((m, i) => (
                <ChatBubble key={i} message={m} />
              ))}

              {streaming && (
                <div className="anim-fade-up">
                  <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm">
                    <pre className="text-[14px] text-gray-800 leading-relaxed whitespace-pre-wrap font-[inherit]">
                      {streaming}
                      <span className="inline-block w-1.5 h-4 bg-purple-500 rounded-sm animate-pulse ml-0.5 align-middle" />
                    </pre>
                  </div>
                </div>
              )}

              <div ref={endRef} />
            </div>
          )}
        </div>

        {/* Input */}
        <div className="shrink-0 px-6 pb-4 pt-2">
          <div className="max-w-3xl mx-auto">
            <ChatInput
              ref={chatInputRef}
              onSend={send}
              onFiles={onUpload}
              onStop={stopStream}
              loading={loading}
              placeholder={placeholder}
            />
            <p className="text-center text-[11px] text-gray-400 mt-2">
              Scout may produce inaccurate results. Press <kbd className="px-1 py-0.5 rounded border border-gray-200 bg-gray-50 text-[10px]">?</kbd> for shortcuts.
            </p>
          </div>
        </div>
      </main>

      <PrivacyDrawer open={privacyOpen} onClose={() => setPrivacyOpen(false)} />
      <ShortcutSheet open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
    </div>
  );
}
