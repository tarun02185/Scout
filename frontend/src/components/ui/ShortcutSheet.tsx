import Modal from './Modal';

interface Props {
  open: boolean;
  onClose: () => void;
}

const isMac = typeof navigator !== 'undefined' && /Mac/.test(navigator.platform);
const MOD = isMac ? '⌘' : 'Ctrl';

const GROUPS: { heading: string; items: { label: string; keys: string[] }[] }[] = [
  {
    heading: 'Navigation',
    items: [
      { label: 'New chat', keys: [MOD, 'K'] },
      { label: 'Focus the ask-anything input', keys: ['/'] },
    ],
  },
  {
    heading: 'During a response',
    items: [
      { label: 'Stop generating', keys: ['Esc'] },
      { label: 'New line in input', keys: ['Shift', 'Enter'] },
      { label: 'Send message', keys: ['Enter'] },
    ],
  },
  {
    heading: 'Help & privacy',
    items: [
      { label: 'Open this shortcut sheet', keys: ['?'] },
      { label: 'Open the privacy panel', keys: ['P'] },
      { label: 'Close any dialog', keys: ['Esc'] },
    ],
  },
];

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="min-w-[22px] h-6 px-1.5 inline-flex items-center justify-center rounded-md border border-gray-200 bg-gray-50 text-[11px] font-semibold text-gray-700 shadow-[inset_0_-1px_0_rgba(0,0,0,0.06)]">
      {children}
    </kbd>
  );
}

export default function ShortcutSheet({ open, onClose }: Props) {
  return (
    <Modal open={open} onClose={onClose} title="Keyboard shortcuts">
      <div className="space-y-5">
        {GROUPS.map((g) => (
          <section key={g.heading}>
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-400 mb-2">{g.heading}</h3>
            <ul className="space-y-1.5">
              {g.items.map((item) => (
                <li key={item.label} className="flex items-center justify-between">
                  <span className="text-[13px] text-gray-700">{item.label}</span>
                  <div className="flex items-center gap-1">
                    {item.keys.map((k, i) => (
                      <span key={i} className="flex items-center gap-1">
                        {i > 0 && <span className="text-[11px] text-gray-300">+</span>}
                        <Kbd>{k}</Kbd>
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </Modal>
  );
}
