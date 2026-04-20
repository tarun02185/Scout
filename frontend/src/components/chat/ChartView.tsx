import { useMemo } from 'react';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import type { ChartData } from '../../types';

const COLORS = ['#7C3AED', '#A78BFA', '#C4B5FD', '#6D28D9', '#8B5CF6', '#5B21B6', '#DDD6FE'];

function isNum(val: unknown) { return typeof val === 'number' || (typeof val === 'string' && val.trim() !== '' && !isNaN(Number(val))); }
function isNumCol(col: string, rows: Record<string, unknown>[], dtypes: Record<string, string>) {
  const t = (dtypes[col] || '').toLowerCase();
  if (/int|float|double|decimal|numeric|bigint|real|number/.test(t)) return true;
  return rows.slice(0, 5).some((r) => isNum(r[col]));
}

function pickType(data: ChartData, intent?: string): 'bar' | 'line' | 'pie' | 'none' {
  const { columns, rows, dtypes } = data;
  if (rows.length <= 1 && columns.length <= 2) return 'none';
  const nums = columns.filter((c) => isNumCol(c, rows, dtypes));
  if (nums.length === 0) return 'none';
  const hasDate = columns.some((c) => /date|month|year|week|quarter|period/i.test(c));
  if (intent === 'change' || intent === 'compare') return hasDate ? 'line' : 'bar';
  if (intent === 'breakdown' && rows.length <= 8) return 'pie';
  if (hasDate) return 'line';
  return 'bar';
}

export default function ChartView({ data, intent }: { data: ChartData; intent?: string }) {
  const type = useMemo(() => pickType(data, intent), [data, intent]);
  if (type === 'none' || !data.rows.length) return null;

  const nums = data.columns.filter((c) => isNumCol(c, data.rows, data.dtypes));
  const cats = data.columns.filter((c) => !isNumCol(c, data.rows, data.dtypes));
  const xKey = cats[0] || data.columns[0];
  const rows = data.rows.map((r) => {
    const o: Record<string, unknown> = {};
    data.columns.forEach((c) => { o[c] = isNumCol(c, data.rows, data.dtypes) ? Number(r[c]) || 0 : r[c]; });
    return o;
  });

  const style = { backgroundColor: '#fff', border: '1px solid #e5e7eb', borderRadius: '8px', fontSize: '12px' };

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
      <ResponsiveContainer width="100%" height={280}>
        {type === 'line' ? (
          <LineChart data={rows}><CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" /><XAxis dataKey={xKey} tick={{ fontSize: 11 }} stroke="#9ca3af" /><YAxis tick={{ fontSize: 11 }} stroke="#9ca3af" /><Tooltip contentStyle={style} /><Legend />
            {nums.map((c, i) => <Line key={c} type="monotone" dataKey={c} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={{ r: 3 }} />)}
          </LineChart>
        ) : type === 'pie' ? (
          <PieChart><Pie data={rows} dataKey={nums[0]} nameKey={xKey} cx="50%" cy="50%" outerRadius={95} label={({ name, percent }: any) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}>
            {rows.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
          </Pie><Tooltip /><Legend /></PieChart>
        ) : (
          <BarChart data={rows}><CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" /><XAxis dataKey={xKey} tick={{ fontSize: 11 }} stroke="#9ca3af" /><YAxis tick={{ fontSize: 11 }} stroke="#9ca3af" /><Tooltip contentStyle={style} /><Legend />
            {nums.map((c, i) => <Bar key={c} dataKey={c} fill={COLORS[i % COLORS.length]} radius={[4, 4, 0, 0]} />)}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
