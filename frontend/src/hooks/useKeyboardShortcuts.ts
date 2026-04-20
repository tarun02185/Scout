import { useEffect } from 'react';

type ShortcutHandler = () => void;

export interface Shortcuts {
  onNewChat?: ShortcutHandler;
  onFocusInput?: ShortcutHandler;
  onToggleHelp?: ShortcutHandler;
  onEscape?: ShortcutHandler;
  onTogglePrivacy?: ShortcutHandler;
}

// Returns true if the event originated inside an editable control we shouldn't hijack.
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === 'INPUT' ||
    tag === 'TEXTAREA' ||
    tag === 'SELECT' ||
    target.isContentEditable
  );
}

export function useKeyboardShortcuts(s: Shortcuts) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;

      // ⌘K → new chat
      if (mod && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        s.onNewChat?.();
        return;
      }

      // Esc works everywhere (including inside inputs) — used to cancel stream / close modal.
      if (e.key === 'Escape') {
        s.onEscape?.();
        return;
      }

      // The remaining shortcuts must not fire while typing in a field.
      if (isTyping(e.target)) return;

      // "/" → focus the main input.
      if (e.key === '/') {
        e.preventDefault();
        s.onFocusInput?.();
        return;
      }

      // "?" (Shift + "/") → open shortcut sheet.
      if (e.key === '?') {
        e.preventDefault();
        s.onToggleHelp?.();
        return;
      }

      // "p" → toggle privacy drawer.
      if (e.key === 'p' || e.key === 'P') {
        e.preventDefault();
        s.onTogglePrivacy?.();
        return;
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [s.onNewChat, s.onFocusInput, s.onToggleHelp, s.onEscape, s.onTogglePrivacy]);
}
