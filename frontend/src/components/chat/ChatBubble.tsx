import ReactMarkdown from 'react-markdown';
import type { Message } from '../../types';
import ChartView from './ChartView';
import SourcesPanel from './SourcesPanel';
import CopyButton from '../ui/CopyButton';

export default function ChatBubble({ message }: { message: Message }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end anim-fade-up">
        <div className="max-w-[75%] bg-purple-600 text-white px-4 py-3 rounded-2xl rounded-tr-sm text-[14px] leading-relaxed shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }

  const m = message.metadata;

  return (
    <div className="anim-fade-up space-y-3 group">
      {message.content && (
        <div className="relative bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm">
          <div className="markdown-content text-[14px] text-gray-800 leading-relaxed">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
          <div className="absolute top-2.5 right-2.5 opacity-0 group-hover:opacity-100 transition-opacity">
            <CopyButton text={message.content} label="Copy" />
          </div>
        </div>
      )}

      {m?.has_chart && m?.chart_data && (
        <ChartView data={m.chart_data} intent={m.intent?.intent} />
      )}

      {(m?.sources_used?.length || m?.sql_used) && (
        <SourcesPanel sources={m?.sources_used || []} sql={m?.sql_used || undefined} />
      )}
    </div>
  );
}
