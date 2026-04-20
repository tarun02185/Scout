import Modal from './Modal';

interface Props {
  open: boolean;
  onClose: () => void;
}

const LAYERS = [
  {
    num: 1,
    title: 'Input-side tokenization',
    body: "Emails, phone numbers, IDs, card numbers and other personal values are replaced with opaque tokens like [PII_EMAIL_a1b2c3d4] before any prompt reaches the language model. The model literally never sees the raw value — so it can't leak it, no matter how the question is phrased.",
  },
  {
    num: 2,
    title: 'Prompt-injection filter',
    body: 'Every question is screened before the model runs. Phrases that try to override the system prompt ("ignore previous instructions", "reveal the system prompt", "dump the database") and phrases that try to enumerate personal data ("list every email") are politely refused. Aggregate questions ("how many unique emails") are allowed.',
  },
  {
    num: 3,
    title: 'Column-level SQL blocklist',
    body: 'Generated SQL is rejected if it selects a sensitive column directly. SELECT * on a table that contains any PII column is blocked. Only aggregate functions — COUNT, COUNT(DISTINCT), SUM, AVG — are permitted on sensitive columns.',
  },
  {
    num: 4,
    title: 'Hardened system prompts',
    body: 'A non-negotiable security preamble is prepended to every prompt sent to the model. It explicitly forbids revealing raw personal data, forbids decoding the opaque tokens from layer 1, and instructs the model to ignore any user content that tries to override these rules.',
  },
  {
    num: 5,
    title: 'Output filter + audit log',
    body: 'As a last line of defence, every response is regex-scanned for PII patterns and masked before being shown or persisted. Every block and every mask is written to an append-only audit log so attempts are reviewable.',
  },
];

export default function PrivacyDrawer({ open, onClose }: Props) {
  return (
    <Modal open={open} onClose={onClose} title="How your data stays private" widthClass="max-w-2xl">
      <div className="space-y-4">
        <p className="text-[13px] text-gray-600 leading-relaxed">
          Scout enforces <strong>five independent defences</strong> so that nothing sensitive you upload can be extracted through the chat — regardless of how a question is phrased. Aggregate answers still work; individual values are not disclosed.
        </p>

        <ul className="space-y-3">
          {LAYERS.map((l) => (
            <li key={l.num} className="flex gap-3 p-3.5 rounded-xl bg-purple-50/50 border border-purple-100">
              <div className="shrink-0 w-6 h-6 rounded-full bg-purple-600 text-white text-[11px] font-bold flex items-center justify-center">
                {l.num}
              </div>
              <div>
                <p className="text-[13px] font-semibold text-gray-900 mb-0.5">{l.title}</p>
                <p className="text-[12.5px] text-gray-600 leading-relaxed">{l.body}</p>
              </div>
            </li>
          ))}
        </ul>

        <p className="text-[11.5px] text-gray-400 text-center pt-2">
          Try asking <em>"list every email in the file"</em> after uploading a CSV — it will be refused.
        </p>
      </div>
    </Modal>
  );
}
