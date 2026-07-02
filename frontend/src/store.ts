import { create } from 'zustand'
import type { Account, ActivityItem, Health, PendingOrder, Position, Run, WsPayload } from './api'

export type Page = 'overview' | 'strategies' | 'chart' | 'backtest' | 'activity'

interface AppState {
  page: Page
  setPage: (p: Page) => void
  symbol: string
  setSymbol: (s: string) => void
  health: Health | null
  setHealth: (h: Health | null) => void
  // pushed over the websocket
  runs: Run[]
  activity: ActivityItem[]
  approvals: PendingOrder[]
  account: Account | null
  positions: Position[] | null
  mode: 'paper' | 'live'
  wsConnected: boolean
  applyWs: (p: WsPayload) => void
  setActivity: (a: ActivityItem[]) => void
  setWsConnected: (v: boolean) => void
}

export const useApp = create<AppState>((set) => ({
  page: 'overview',
  setPage: (page) => set({ page }),
  symbol: 'AAPL',
  setSymbol: (symbol) => set({ symbol }),
  health: null,
  setHealth: (health) => set({ health }),
  runs: [],
  activity: [],
  approvals: [],
  account: null,
  positions: null,
  mode: 'paper',
  wsConnected: false,
  applyWs: (p) =>
    set({
      runs: p.runs,
      activity: p.activity,
      approvals: p.approvals ?? [],
      account: p.account ?? null,
      positions: p.positions ?? null,
      mode: p.mode,
    }),
  setActivity: (activity) => set({ activity }),
  setWsConnected: (wsConnected) => set({ wsConnected }),
}))

/** Open the dashboard websocket; reconnects with a small backoff. Returns a disposer. */
export function connectWs(): () => void {
  let ws: WebSocket | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  let disposed = false

  const open = () => {
    if (disposed) return
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/ws`)
    ws.onopen = () => useApp.getState().setWsConnected(true)
    ws.onmessage = (ev) => useApp.getState().applyWs(JSON.parse(ev.data))
    ws.onclose = () => {
      useApp.getState().setWsConnected(false)
      if (!disposed) timer = setTimeout(open, 3000)
    }
  }
  open()
  return () => {
    disposed = true
    if (timer) clearTimeout(timer)
    ws?.close()
  }
}
