import { useState } from 'react'
import { api, ApiError } from '../api'
import { useApp } from '../store'
import { Modal } from './Modal'

const titles: Record<string, string> = {
  overview: 'Overview',
  strategies: 'Strategies',
  chart: 'Chart',
  backtest: 'Backtest',
  activity: 'Activity',
}

const CONFIRM_PHRASE = 'TRADE LIVE'

export function Header() {
  const { page, health, mode, approvals, setPage } = useApp()
  const live = mode === 'live'
  const [modeModal, setModeModal] = useState(false)
  const [killModal, setKillModal] = useState(false)
  const [phrase, setPhrase] = useState('')
  const [flatten, setFlatten] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const toggleMode = async () => {
    if (live) {
      await api.setMode('paper') // dropping to paper never needs confirmation
      return
    }
    setPhrase('')
    setError(null)
    setModeModal(true)
  }

  const goLive = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.setMode('live', phrase)
      setModeModal(false)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const killAll = async () => {
    setBusy(true)
    try {
      await api.emergencyStop(flatten)
      setKillModal(false)
    } finally {
      setBusy(false)
    }
  }

  return (
    <header className="flex items-center justify-between px-8 pt-7 pb-5">
      <h1 className="text-[26px] font-semibold tracking-tight">{titles[page]}</h1>
      <div className="flex items-center gap-3">
        {approvals.length > 0 && (
          <button
            onClick={() => setPage('strategies')}
            className="px-3 py-1 rounded-full bg-amber-400/20 text-amber-700 text-[12px] font-semibold hover:bg-amber-400/30 transition"
          >
            {approvals.length} awaiting approval
          </button>
        )}
        {health && (
          <button
            onClick={toggleMode}
            title={live ? 'Switch back to paper trading' : 'Switch to live trading'}
            className={`px-3 py-1 rounded-full text-[12px] font-semibold transition ${
              live
                ? 'bg-loss text-white hover:bg-loss/85'
                : 'bg-gain/15 text-[#248a3d] hover:bg-gain/25'
            }`}
          >
            {live ? '● Live' : 'Paper'}
          </button>
        )}
        <button
          onClick={() => setKillModal(true)}
          title="Emergency stop — halts every strategy"
          className="px-3 py-1 rounded-full border border-loss/40 text-loss text-[12px] font-semibold hover:bg-loss/5 transition"
        >
          Stop All
        </button>
        <span
          className={`flex items-center gap-1.5 text-[12px] font-medium ${
            health ? 'text-ink-soft' : 'text-loss'
          }`}
        >
          <span className={`w-2 h-2 rounded-full ${health ? 'bg-gain' : 'bg-loss'}`} />
          {health ? 'Connected' : 'Backend offline'}
        </span>
      </div>

      {/* live-mode confirmation */}
      <Modal open={modeModal} onClose={() => setModeModal(false)}>
        <h2 className="text-[17px] font-semibold mb-2 text-loss">Enable live trading?</h2>
        <p className="text-[13px] text-ink-soft leading-relaxed mb-4">
          New runs will place <strong className="text-ink">real-money orders</strong> with your live
          Alpaca account. Live runs require your approval for every order unless you raise the
          auto-approve threshold. Existing paper runs are unaffected.
        </p>
        <p className="text-[13px] mb-2">
          Type <code className="bg-canvas px-1.5 py-0.5 rounded font-semibold">{CONFIRM_PHRASE}</code> to confirm:
        </p>
        <input
          value={phrase}
          onChange={(e) => setPhrase(e.target.value)}
          spellCheck={false}
          className="w-full px-3 py-2 rounded-xl bg-canvas text-[14px] font-semibold outline-none focus:ring-2 focus:ring-loss/40 mb-3"
        />
        {error && <p className="text-[12px] text-loss mb-3">{error}</p>}
        <div className="flex justify-end gap-2">
          <button onClick={() => setModeModal(false)} className="px-4 py-2 rounded-xl text-[13px] font-semibold text-ink-soft hover:bg-black/[0.04]">
            Cancel
          </button>
          <button
            onClick={goLive}
            disabled={busy || phrase !== CONFIRM_PHRASE}
            className="px-4 py-2 rounded-xl bg-loss text-white text-[13px] font-semibold hover:bg-loss/85 disabled:opacity-40"
          >
            {busy ? 'Switching…' : 'Go Live'}
          </button>
        </div>
      </Modal>

      {/* emergency stop */}
      <Modal open={killModal} onClose={() => setKillModal(false)}>
        <h2 className="text-[17px] font-semibold mb-2">Emergency stop</h2>
        <p className="text-[13px] text-ink-soft leading-relaxed mb-4">
          Stops every running strategy immediately.
        </p>
        <label className="flex items-center gap-2 text-[13px] mb-5">
          <input type="checkbox" checked={flatten} onChange={(e) => setFlatten(e.target.checked)} />
          Also sell all open positions at market
        </label>
        <div className="flex justify-end gap-2">
          <button onClick={() => setKillModal(false)} className="px-4 py-2 rounded-xl text-[13px] font-semibold text-ink-soft hover:bg-black/[0.04]">
            Cancel
          </button>
          <button
            onClick={killAll}
            disabled={busy}
            className="px-4 py-2 rounded-xl bg-loss text-white text-[13px] font-semibold hover:bg-loss/85 disabled:opacity-40"
          >
            {busy ? 'Stopping…' : 'Stop Everything'}
          </button>
        </div>
      </Modal>
    </header>
  )
}
