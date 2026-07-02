import { useEffect, useState } from 'react'
import { api, ApiError, type Run, type StrategyInfo } from '../api'
import { useApp } from '../store'

const fmtUsd = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })

function ApprovalsCard() {
  const approvals = useApp((s) => s.approvals)
  const [busy, setBusy] = useState<number | null>(null)
  if (approvals.length === 0) return null

  const act = async (id: number, fn: (id: number) => Promise<unknown>) => {
    setBusy(id)
    try {
      await fn(id)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="card p-6 border-l-4 border-amber-400">
      <h2 className="text-[15px] font-semibold mb-4">Orders awaiting your approval</h2>
      <div className="flex flex-col gap-2">
        {approvals.map((p) => (
          <div key={p.id} className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-canvas">
            <span className={`px-2 py-0.5 rounded-full text-[10.5px] font-semibold ${p.side === 'buy' ? 'bg-gain/15 text-[#248a3d]' : 'bg-loss/10 text-loss'}`}>
              {p.side}
            </span>
            <span className="text-[13px] font-semibold">{p.qty} {p.symbol}</span>
            <span className="text-[12px] text-ink-soft">~{fmtUsd(p.notional)} @ {p.est_price.toFixed(2)}</span>
            <span className={`px-2 py-0.5 rounded-full text-[10.5px] font-semibold ${p.mode === 'live' ? 'bg-loss/10 text-loss' : 'bg-gain/15 text-[#248a3d]'}`}>
              {p.mode}
            </span>
            <div className="ml-auto flex gap-2">
              <button
                onClick={() => act(p.id, api.approve)}
                disabled={busy === p.id}
                className="px-3.5 py-1.5 rounded-lg bg-accent text-white text-[12px] font-semibold hover:bg-accent/90 active:scale-[0.97] transition disabled:opacity-40"
              >
                Approve
              </button>
              <button
                onClick={() => act(p.id, api.reject)}
                disabled={busy === p.id}
                className="px-3.5 py-1.5 rounded-lg bg-white text-[12px] font-semibold text-loss shadow-[0_1px_2px_rgba(0,0,0,0.08)] hover:bg-loss/5 active:scale-[0.97] transition disabled:opacity-40"
              >
                Reject
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function RunRow({ run }: { run: Run }) {
  const [busy, setBusy] = useState(false)
  const call = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await fn()
    } finally {
      setBusy(false)
    }
  }
  const holding = run.position > 0
  return (
    <div className={`flex items-center gap-3 px-3 py-2.5 rounded-xl ${run.mode === 'live' ? 'bg-loss/[0.06]' : 'bg-canvas'}`}>
      <span className={`w-2 h-2 rounded-full ${run.paused ? 'bg-amber-400' : run.active ? 'bg-gain animate-pulse' : 'bg-black/20'}`} />
      <span className="text-[13px] font-semibold">{run.symbol}</span>
      <span className="text-[12px] text-ink-soft">{run.timeframe}</span>
      <span className="text-[12px] text-ink-soft">
        {holding ? `${run.position} sh @ ${run.entry_price.toFixed(2)}` : 'flat'} · {fmtUsd(run.cash)} cash
        {run.paused ? ' · paused' : ''}
      </span>
      <span className={`ml-auto px-2 py-0.5 rounded-full text-[10.5px] font-semibold ${run.mode === 'live' ? 'bg-loss/10 text-loss' : 'bg-gain/15 text-[#248a3d]'}`}>
        {run.mode}
      </span>
      {run.active && (
        <>
          <button
            onClick={() => call(() => (run.paused ? api.resumeRun(run.id) : api.pauseRun(run.id)))}
            disabled={busy}
            className="px-3 py-1 rounded-lg bg-white text-[12px] font-semibold text-ink-soft shadow-[0_1px_2px_rgba(0,0,0,0.08)] hover:text-ink active:scale-[0.97] transition disabled:opacity-40"
          >
            {run.paused ? 'Resume' : 'Pause'}
          </button>
          <button
            onClick={() => call(() => api.stopRun(run.id))}
            disabled={busy}
            className="px-3 py-1 rounded-lg bg-white text-[12px] font-semibold text-loss shadow-[0_1px_2px_rgba(0,0,0,0.08)] hover:bg-loss/5 active:scale-[0.97] transition disabled:opacity-40"
          >
            Stop
          </button>
        </>
      )}
    </div>
  )
}

const riskFields = [
  { key: 'max_trade_size', label: 'Max trade $' },
  { key: 'max_daily_loss', label: 'Max daily loss $' },
  { key: 'stop_loss_pct', label: 'Stop-loss %' },
  { key: 'take_profit_pct', label: 'Take-profit %' },
  { key: 'auto_approve_below', label: 'Auto-approve under $' },
] as const

function StrategyCard({ s, runs }: { s: StrategyInfo; runs: Run[] }) {
  const mode = useApp((st) => st.mode)
  const [symbol, setSymbol] = useState('AAPL')
  const [timeframe, setTimeframe] = useState('1Day')
  const [allocation, setAllocation] = useState(10000)
  const [params, setParams] = useState<Record<string, number>>({ ...s.params })
  const [risk, setRisk] = useState<Record<string, string>>({})
  const [showRisk, setShowRisk] = useState(false)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const myRuns = runs.filter((r) => r.strategy_id === s.id && (r.active || r.status === 'running' || r.status === 'paused'))

  const start = async () => {
    setStarting(true)
    setError(null)
    const riskNums = Object.fromEntries(
      riskFields.map((f) => [f.key, risk[f.key]?.trim() ? Number(risk[f.key]) : null]),
    )
    try {
      await api.startRun({
        strategy_id: s.id, symbol: symbol.toUpperCase(), timeframe, params, allocation,
        ...riskNums,
      })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="card p-6 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-[15.5px] font-semibold">{s.name}</h2>
        <span className="px-2.5 py-0.5 rounded-full bg-black/[0.05] text-[11px] font-medium text-ink-soft">
          {s.builtin ? 'Built-in' : 'Custom'}
        </span>
      </div>
      <p className="text-[13px] text-ink-soft leading-relaxed -mt-1">{s.description}</p>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-ink-soft">Symbol</span>
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            spellCheck={false}
            className="w-20 px-2.5 py-1.5 rounded-lg bg-canvas text-[12.5px] font-semibold uppercase outline-none focus:ring-2 focus:ring-accent/40"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-ink-soft">Timeframe</span>
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="px-2.5 py-1.5 rounded-lg bg-canvas text-[12.5px] font-medium outline-none focus:ring-2 focus:ring-accent/40"
          >
            {['1Day', '1Hour', '15Min', '5Min', '1Min'].map((tf) => <option key={tf}>{tf}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-medium text-ink-soft">Allocation $</span>
          <input
            type="number"
            value={allocation}
            onChange={(e) => setAllocation(Number(e.target.value))}
            className="w-24 px-2.5 py-1.5 rounded-lg bg-canvas text-[12.5px] font-medium outline-none focus:ring-2 focus:ring-accent/40"
          />
        </label>
        {Object.keys(s.params).map((k) => (
          <label key={k} className="flex flex-col gap-1">
            <span className="text-[11px] font-medium text-ink-soft">{k.replaceAll('_', ' ')}</span>
            <input
              type="number"
              value={params[k] ?? ''}
              onChange={(e) => setParams({ ...params, [k]: Number(e.target.value) })}
              className="w-20 px-2.5 py-1.5 rounded-lg bg-canvas text-[12.5px] font-medium outline-none focus:ring-2 focus:ring-accent/40"
            />
          </label>
        ))}
        <button
          onClick={start}
          disabled={starting || !symbol.trim()}
          className={`ml-auto px-4 py-2 rounded-xl text-white text-[12.5px] font-semibold active:scale-[0.98] transition disabled:opacity-40 ${
            mode === 'live' ? 'bg-loss hover:bg-loss/85' : 'bg-accent hover:bg-accent/90'
          }`}
        >
          {starting ? 'Starting…' : mode === 'live' ? 'Start (Live)' : 'Start'}
        </button>
      </div>

      <button
        onClick={() => setShowRisk(!showRisk)}
        className="self-start text-[12px] font-medium text-accent hover:underline"
      >
        {showRisk ? 'Hide risk limits' : 'Risk limits…'}
      </button>
      {showRisk && (
        <div className="flex flex-wrap gap-3 -mt-1">
          {riskFields.map((f) => (
            <label key={f.key} className="flex flex-col gap-1">
              <span className="text-[11px] font-medium text-ink-soft">{f.label}</span>
              <input
                type="number"
                placeholder="off"
                value={risk[f.key] ?? ''}
                onChange={(e) => setRisk({ ...risk, [f.key]: e.target.value })}
                className="w-28 px-2.5 py-1.5 rounded-lg bg-canvas text-[12.5px] font-medium outline-none focus:ring-2 focus:ring-accent/40"
              />
            </label>
          ))}
          <p className="basis-full text-[11.5px] text-ink-soft/80">
            Leave blank to disable a limit. Live runs require approval for every order unless you set an auto-approve threshold.
          </p>
        </div>
      )}

      {error && <p className="text-[12px] text-loss">{error}</p>}

      {myRuns.length > 0 && (
        <div className="flex flex-col gap-2">
          {myRuns.map((r) => <RunRow key={r.id} run={r} />)}
        </div>
      )}
    </div>
  )
}

export function Strategies() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [loadErrors, setLoadErrors] = useState<string[]>([])
  const runs = useApp((s) => s.runs)

  useEffect(() => {
    api.strategies().then((r) => {
      setStrategies(r.strategies)
      setLoadErrors(r.errors)
    }).catch(() => {})
  }, [])

  return (
    <div className="px-8 pb-8 space-y-5">
      <ApprovalsCard />
      {loadErrors.length > 0 && (
        <div className="card p-4 border border-loss/20">
          <p className="text-[12.5px] font-semibold text-loss mb-1">Some strategy files could not be loaded</p>
          {loadErrors.map((e, i) => (
            <p key={i} className="text-[12px] text-ink-soft font-mono">{e}</p>
          ))}
        </div>
      )}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {strategies.map((s) => <StrategyCard key={s.id} s={s} runs={runs} />)}
      </div>
      <p className="text-[12px] text-ink-soft">
        Add your own: drop a Python file in <code className="bg-white px-1.5 py-0.5 rounded">~/tradedesk/strategies/</code> — see{' '}
        <code className="bg-white px-1.5 py-0.5 rounded">example_momentum.py</code> there for the template. New files appear on refresh.
      </p>
    </div>
  )
}
