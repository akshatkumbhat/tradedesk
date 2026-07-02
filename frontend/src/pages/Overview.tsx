import { useEffect, useState } from 'react'
import { api, ApiError, type Account, type Position } from '../api'
import { ConnectPrompt } from '../components/ConnectPrompt'

const fmt = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="card p-6 flex-1">
      <div className="text-[13px] font-medium text-ink-soft mb-1">{label}</div>
      <div className="text-[28px] font-semibold tracking-tight">{value}</div>
      {sub && <div className="text-[12px] text-ink-soft mt-1">{sub}</div>}
    </div>
  )
}

export function Overview() {
  const [account, setAccount] = useState<Account | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [needsKeys, setNeedsKeys] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const [a, p] = await Promise.all([api.account(), api.positions()])
        if (!alive) return
        setAccount(a)
        setPositions(p)
        setNeedsKeys(false)
        setError(null)
      } catch (e) {
        if (!alive) return
        if (e instanceof ApiError && e.status === 503) setNeedsKeys(true)
        else setError(e instanceof Error ? e.message : String(e))
      }
    }
    load()
    const id = setInterval(load, 15_000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  if (needsKeys) return <ConnectPrompt />
  if (error)
    return <div className="card p-6 text-[14px] text-loss max-w-lg mx-auto mt-16">{error}</div>
  if (!account) return null

  return (
    <div className="px-8 pb-8 space-y-5">
      <div className="flex gap-5">
        <Stat label="Equity" value={fmt(account.equity)} sub={account.paper ? 'Paper account' : 'Live account'} />
        <Stat label="Cash" value={fmt(account.cash)} />
        <Stat label="Buying Power" value={fmt(account.buying_power)} />
      </div>

      <div className="card p-6">
        <h2 className="text-[16px] font-semibold mb-4">Positions</h2>
        {positions.length === 0 ? (
          <p className="text-[13px] text-ink-soft">No open positions.</p>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-left text-ink-soft">
                <th className="font-medium pb-3">Symbol</th>
                <th className="font-medium pb-3 text-right">Qty</th>
                <th className="font-medium pb-3 text-right">Avg Entry</th>
                <th className="font-medium pb-3 text-right">Price</th>
                <th className="font-medium pb-3 text-right">Value</th>
                <th className="font-medium pb-3 text-right">Unrealized P&L</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.symbol} className="border-t border-black/5">
                  <td className="py-3 font-semibold">{p.symbol}</td>
                  <td className="py-3 text-right">{p.qty}</td>
                  <td className="py-3 text-right">{fmt(p.avg_entry_price)}</td>
                  <td className="py-3 text-right">{fmt(p.current_price)}</td>
                  <td className="py-3 text-right">{fmt(p.market_value)}</td>
                  <td className={`py-3 text-right font-medium ${p.unrealized_pl >= 0 ? 'text-[#248a3d]' : 'text-loss'}`}>
                    {fmt(p.unrealized_pl)} ({p.unrealized_pl_pct.toFixed(2)}%)
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
