import { useEffect } from 'react'
import { api, type ActivityItem } from '../api'
import { useApp } from '../store'

const fmtTime = (iso: string) =>
  new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })

function Row({ a }: { a: ActivityItem }) {
  return (
    <tr className="border-t border-black/5">
      <td className="py-2.5 text-ink-soft whitespace-nowrap">{fmtTime(a.time)}</td>
      <td className="py-2.5">
        <span
          className={`px-2 py-0.5 rounded-full text-[10.5px] font-semibold ${
            a.kind === 'order'
              ? a.side === 'buy'
                ? 'bg-gain/15 text-[#248a3d]'
                : 'bg-loss/10 text-loss'
              : a.kind === 'error'
                ? 'bg-loss/10 text-loss'
                : a.kind === 'alert'
                  ? 'bg-amber-400/20 text-amber-700'
                  : 'bg-black/[0.05] text-ink-soft'
          }`}
        >
          {a.kind === 'order' ? a.side : a.kind}
        </span>
      </td>
      <td className="py-2.5 font-semibold">{a.symbol ?? ''}</td>
      <td className="py-2.5 text-right">{a.qty ?? ''}</td>
      <td className="py-2.5 text-right">{a.price != null ? a.price.toFixed(2) : ''}</td>
      <td className="py-2.5 pl-6 text-ink-soft">{a.detail}</td>
      <td className="py-2.5 text-right">
        <span className={`px-2 py-0.5 rounded-full text-[10.5px] font-semibold ${a.mode === 'live' ? 'bg-loss/10 text-loss' : 'bg-gain/15 text-[#248a3d]'}`}>
          {a.mode}
        </span>
      </td>
    </tr>
  )
}

export function Activity() {
  const { activity, setActivity } = useApp()

  // Seed immediately from REST; websocket keeps it fresh afterwards.
  useEffect(() => {
    if (activity.length === 0) api.activity().then(setActivity).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="px-8 pb-8">
      <div className="card p-6">
        {activity.length === 0 ? (
          <p className="text-[13px] text-ink-soft">
            Nothing yet. Start a strategy from the Strategies page and its orders will appear here.
          </p>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-left text-ink-soft">
                <th className="font-medium pb-3">Time</th>
                <th className="font-medium pb-3">Type</th>
                <th className="font-medium pb-3">Symbol</th>
                <th className="font-medium pb-3 text-right">Qty</th>
                <th className="font-medium pb-3 text-right">Price</th>
                <th className="font-medium pb-3 pl-6">Detail</th>
                <th className="font-medium pb-3 text-right">Mode</th>
              </tr>
            </thead>
            <tbody>
              {activity.map((a) => <Row key={a.id} a={a} />)}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
