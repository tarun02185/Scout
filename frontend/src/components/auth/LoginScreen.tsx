import { useEffect, useRef } from 'react';

interface Props { onLogin: (c: string) => void; onGuest: () => void; loading: boolean; }

declare global { interface Window { google?: any; } }
const GID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

export default function LoginScreen({ onLogin, onGuest, loading }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!GID) return;
    const s = document.createElement('script');
    s.src = 'https://accounts.google.com/gsi/client'; s.async = true;
    s.onload = () => {
      if (window.google && ref.current) {
        window.google.accounts.id.initialize({ client_id: GID, callback: (r: any) => onLogin(r.credential) });
        window.google.accounts.id.renderButton(ref.current, { theme: 'outline', size: 'large', width: 280, shape: 'pill' });
      }
    };
    document.head.appendChild(s);
    return () => { document.head.removeChild(s); };
  }, [onLogin]);

  if (loading) return <div className="min-h-screen flex items-center justify-center"><div className="w-8 h-8 border-3 border-purple-200 border-t-purple-600 rounded-full animate-spin" /></div>;

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-purple-50 via-white to-indigo-50 px-4">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-xl border border-gray-100 p-8 text-center">
        <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-purple-600 to-indigo-600 flex items-center justify-center mx-auto mb-5 text-white text-xl font-bold shadow-lg shadow-purple-200">S</div>
        <h1 className="text-2xl font-bold text-gray-900 mb-1">Scout</h1>
        <p className="text-gray-400 text-sm mb-8">Talk to your data in plain English</p>
        <div className="space-y-3">
          {GID && <div className="flex justify-center"><div ref={ref} /></div>}
          {GID && <div className="flex items-center gap-3"><div className="flex-1 h-px bg-gray-200" /><span className="text-xs text-gray-400">or</span><div className="flex-1 h-px bg-gray-200" /></div>}
          <button onClick={onGuest} className="w-full py-2.5 bg-purple-600 text-white rounded-xl text-sm font-medium hover:bg-purple-700 transition-colors cursor-pointer shadow-sm shadow-purple-200">
            Continue as Guest
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-6">Your data stays private and is never stored permanently.</p>
      </div>
    </div>
  );
}
