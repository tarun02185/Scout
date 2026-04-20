import axios from 'axios';
import type { Session, FileUploadResult, SourceMetadata, ChartData } from '../types';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 120000, // 2 min — Render free tier can take 30s+ to wake
});

api.interceptors.request.use((c) => {
  const t = localStorage.getItem('auth_token');
  if (t) c.headers.Authorization = `Bearer ${t}`;
  return c;
});

// Auth
export interface User { id: string; email: string; name: string; picture: string; }
export const googleLogin = async (credential: string) => { const { data } = await api.post('/api/auth/google', { credential }); return data as { user: User; token: string }; };
export const guestLogin = async () => { const { data } = await api.post('/api/auth/guest'); return data as { user: User; token: string }; };
export const getMe = async (): Promise<User | null> => { try { const { data } = await api.get('/api/auth/me'); return data.user; } catch { return null; } };

// Sessions
export const createSession = async () => { const { data } = await api.post('/api/sessions'); return data.session_id as string; };
export const listSessions = async () => { const { data } = await api.get('/api/sessions'); return data.sessions as Session[]; };
export const getSession = async (id: string) => { const { data } = await api.get(`/api/sessions/${id}`); return data as { messages: any[]; sources: SourceMetadata[] }; };
export const deleteSession = async (id: string) => { await api.delete(`/api/sessions/${id}`); };

// Upload
export const uploadFiles = async (sid: string, files: File[]) => {
  const fd = new FormData();
  files.forEach((f) => fd.append('files', f));
  const { data } = await api.post(`/api/sessions/${sid}/upload`, fd, { headers: { 'Content-Type': 'multipart/form-data' } });
  return data.results as FileUploadResult[];
};

export interface UrlUploadOptions {
  crawl_multi?: boolean;
  max_pages?: number;
  max_depth?: number;
  path_filter?: string;
}
export const uploadUrl = async (sid: string, url: string, opts: UrlUploadOptions = {}) => {
  const { data } = await api.post(`/api/sessions/${sid}/url`, { url, ...opts }, { timeout: 180000 });
  return data as { file: string; status: string; metadata: any };
};

export const removeSource = async (sid: string, sourceName: string) => {
  const { data } = await api.delete(`/api/sessions/${sid}/sources/${encodeURIComponent(sourceName)}`);
  return data as { status: string; source_name: string };
};

// Streaming query
export interface StreamCB {
  onMeta: (m: { intent: any; chart_data: ChartData | null; sql_used: string | null; sources_used: string[] }) => void;
  onToken: (t: string) => void;
  onDone: () => void;
  onError: (e: string) => void;
}

function processSSEBuffer(buf: string, cb: StreamCB): string {
  const lines = buf.split('\n');
  const remainder = lines.pop() || '';
  for (const line of lines) {
    if (!line.startsWith('data: ')) continue;
    try {
      const ev = JSON.parse(line.slice(6));
      if (ev.type === 'metadata') cb.onMeta(ev);
      else if (ev.type === 'token') cb.onToken(ev.content || '');
      else if (ev.type === 'done') cb.onDone();
    } catch {}
  }
  return remainder;
}

export const sendQueryStream = async (
  sid: string,
  query: string,
  cb: StreamCB,
  signal?: AbortSignal,
) => {
  const url = `${import.meta.env.VITE_API_URL || ''}/api/query/stream`;
  const localCtrl = new AbortController();
  const timeout = setTimeout(() => localCtrl.abort(), 120000);
  // Merge the caller-provided signal with our local timeout-abort signal.
  const onExternalAbort = () => localCtrl.abort();
  if (signal) {
    if (signal.aborted) localCtrl.abort();
    else signal.addEventListener('abort', onExternalAbort, { once: true });
  }
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(localStorage.getItem('auth_token') ? { Authorization: `Bearer ${localStorage.getItem('auth_token')}` } : {}),
      },
      body: JSON.stringify({ session_id: sid, query }),
      signal: localCtrl.signal,
    });
    clearTimeout(timeout);
    if (!res.ok) { cb.onError(`Server error ${res.status}`); return; }
    const reader = res.body?.getReader();
    if (!reader) { cb.onError('No stream'); return; }

    const dec = new TextDecoder();
    let buf = '';
    let doneReceived = false;

    while (true) {
      const { done, value } = await reader.read();
      if (value) {
        buf += dec.decode(value, { stream: true });
        buf = processSSEBuffer(buf, {
          ...cb,
          onDone: () => { doneReceived = true; cb.onDone(); },
        });
      }
      if (done) break;
    }

    if (buf.trim()) {
      processSSEBuffer(buf + '\n', {
        ...cb,
        onDone: () => { doneReceived = true; cb.onDone(); },
      });
    }

    if (!doneReceived) {
      cb.onDone();
    }
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      // Aborted by user or timeout — emit a normal 'done' so the chat finalises.
      cb.onDone();
    } else {
      cb.onError(err.message || 'Stream failed');
    }
  } finally {
    clearTimeout(timeout);
    if (signal) signal.removeEventListener('abort', onExternalAbort);
  }
};
