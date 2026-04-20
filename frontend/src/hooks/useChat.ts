import { useState, useCallback, useRef } from 'react';
import type { Message, SourceMetadata } from '../types';
import { uploadFiles, uploadUrl, removeSource, createSession, getSession, sendQueryStream, type UrlUploadOptions } from '../services/api';

export function useChat() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sources, setSources] = useState<SourceMetadata[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [streaming, setStreaming] = useState('');
  const sidRef = useRef<string | null>(null);
  const fullTextRef = useRef('');
  const abortRef = useRef<AbortController | null>(null);

  const init = useCallback(async () => {
    try {
      const id = await createSession();
      sidRef.current = id;
      setSessionId(id);
      setMessages([]);
      setSources([]);
      setStreaming('');
      return id;
    } catch { return null; }
  }, []);

  const load = useCallback(async (id: string) => {
    sidRef.current = id;
    setSessionId(id);
    try {
      const d = await getSession(id);
      setMessages(d.messages);
      setSources(d.sources);
    } catch {}
  }, []);

  const ensure = useCallback(async () => sidRef.current || (await init()), [init]);

  const stopStream = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const send = useCallback(async (query: string) => {
    if (loading) return;
    const sid = await ensure();
    if (!sid) return;

    setMessages(prev => [...prev, { role: 'user', content: query }]);
    setLoading(true);
    setStreaming('');
    fullTextRef.current = '';

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    let savedMeta: Message['metadata'] = {};

    try {
      await sendQueryStream(sid, query, {
        onMeta: (m) => {
          savedMeta = {
            intent: m.intent,
            chart_data: m.chart_data,
            sql_used: m.sql_used,
            sources_used: m.sources_used,
            has_chart: m.chart_data !== null,
          };
        },
        onToken: (token) => {
          fullTextRef.current += token;
          setStreaming(fullTextRef.current);
        },
        onDone: () => {
          const finalText = fullTextRef.current;
          setStreaming('');
          // If the user aborted, `finalText` may be partial — still save what we got,
          // with a small marker so they know it was stopped.
          const wasAborted = ctrl.signal.aborted;
          const content = wasAborted && finalText
            ? `${finalText}\n\n_(stopped)_`
            : finalText || (wasAborted ? '_(stopped)_' : '');
          setMessages(prev => [
            ...prev,
            { role: 'assistant', content, metadata: savedMeta },
          ]);
          fullTextRef.current = '';
          setLoading(false);
          abortRef.current = null;
        },
        onError: (err) => {
          setStreaming('');
          setMessages(prev => [
            ...prev,
            { role: 'assistant', content: `Something went wrong: ${err}` },
          ]);
          fullTextRef.current = '';
          setLoading(false);
          abortRef.current = null;
        },
      }, ctrl.signal);
    } catch (e: any) {
      setStreaming('');
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `Error: ${e.message || e}` },
      ]);
      fullTextRef.current = '';
      setLoading(false);
      abortRef.current = null;
    }
  }, [loading, ensure]);

  const upload = useCallback(async (files: File[]) => {
    const sid = await ensure();
    if (!sid) throw new Error('No session');
    setUploading(true);
    try {
      const results = await uploadFiles(sid, files);
      const newSources = results
        .filter(r => r.status === 'success' && r.metadata)
        .map(r => r.metadata!);
      setSources(prev => [...prev, ...newSources]);
      return results;
    } finally {
      setUploading(false);
    }
  }, [ensure]);

  const removeSrc = useCallback(async (sourceName: string) => {
    const sid = sidRef.current;
    if (!sid) return;
    // Optimistic update.
    setSources(prev => prev.filter(s => s.source_name !== sourceName));
    try {
      await removeSource(sid, sourceName);
    } catch {
      // Roll back by refetching the session on failure.
      try {
        const d = await getSession(sid);
        setSources(d.sources);
      } catch {}
      throw new Error(`Could not remove ${sourceName}`);
    }
  }, []);

  const uploadLink = useCallback(async (url: string, opts: UrlUploadOptions = {}) => {
    const sid = await ensure();
    if (!sid) throw new Error('No session');
    setUploading(true);
    try {
      const res = await uploadUrl(sid, url, opts);
      if (res.status === 'success' && res.metadata) {
        setSources(prev => [...prev, res.metadata as SourceMetadata]);
      }
      return res;
    } finally {
      setUploading(false);
    }
  }, [ensure]);

  return { sessionId, messages, sources, loading, uploading, streaming, init, load, send, upload, uploadLink, removeSrc, stopStream };
}
