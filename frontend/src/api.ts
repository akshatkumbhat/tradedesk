// Thin API client for the local backend. All calls stay on this machine.

export interface Health {
  status: string
  broker: string
  keys_configured: boolean
  live_keys_configured: boolean
  mode: 'paper' | 'live'
}

export interface Account {
  equity: number
  cash: number
  buying_power: number
  currency: string
  paper: boolean
}

export interface Position {
  symbol: string
  qty: number
  avg_entry_price: number
  current_price: number
  market_value: number
  unrealized_pl: number
  unrealized_pl_pct: number
}

export interface Bar {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export class ApiError extends Error {
  status: number
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new ApiError(res.status, body.detail ?? res.statusText)
  }
  return res.json()
}

export interface StrategyInfo {
  id: string
  name: string
  description: string
  params: Record<string, number>
  builtin: boolean
}

export interface BacktestRequest {
  strategy_id: string
  symbol: string
  timeframe?: string
  start?: string
  end?: string
  params?: Record<string, number>
  initial_cash?: number
}

export interface Trade {
  entry_time: string
  exit_time: string
  qty: number
  entry_price: number
  exit_price: number
  pnl: number
  return_pct: number
}

export interface BacktestResult {
  strategy_id: string
  params: Record<string, number>
  stats: {
    start: string
    end: string
    initial_cash: number
    final_equity: number
    total_return_pct: number
    cagr_pct: number | null
    sharpe: number | null
    max_drawdown_pct: number
    num_trades: number
    win_rate_pct: number | null
  }
  equity_curve: { time: string; equity: number }[]
  trades: Trade[]
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const b = await res.json().catch(() => ({ detail: res.statusText }))
    throw new ApiError(res.status, typeof b.detail === 'string' ? b.detail : JSON.stringify(b.detail))
  }
  return res.json()
}

export interface Run {
  id: string
  strategy_id: string
  symbol: string
  timeframe: string
  params: Record<string, number>
  allocation: number
  status: 'running' | 'paused' | 'stopped' | 'error'
  error: string | null
  mode: 'paper' | 'live'
  started_at: string
  stopped_at: string | null
  cash: number
  position: number
  entry_price: number
  last_bar_time: string | null
  active: boolean
  paused: boolean
  max_trade_size: number | null
  max_daily_loss: number | null
  stop_loss_pct: number | null
  take_profit_pct: number | null
  auto_approve_below: number | null
}

export interface PendingOrder {
  id: number
  run_id: string
  time: string
  symbol: string
  side: 'buy' | 'sell'
  qty: number
  est_price: number
  notional: number
  mode: 'paper' | 'live'
  status: string
}

export interface ActivityItem {
  id: number
  run_id: string | null
  time: string
  kind: 'order' | 'info' | 'error' | 'alert'
  symbol: string | null
  side: 'buy' | 'sell' | null
  qty: number | null
  price: number | null
  status: string | null
  mode: 'paper' | 'live'
  detail: string | null
}

export interface WsPayload {
  runs: Run[]
  activity: ActivityItem[]
  approvals: PendingOrder[]
  keys_configured: boolean
  live_keys_configured: boolean
  mode: 'paper' | 'live'
  account?: Account
  positions?: Position[]
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(path, { method: 'DELETE' })
  if (!res.ok) {
    const b = await res.json().catch(() => ({ detail: res.statusText }))
    throw new ApiError(res.status, b.detail ?? res.statusText)
  }
  return res.json()
}

export const api = {
  health: () => get<Health>('/api/health'),
  runs: () => get<Run[]>('/api/runs'),
  startRun: (req: {
    strategy_id: string
    symbol: string
    timeframe: string
    params: Record<string, number>
    allocation: number
    max_trade_size?: number | null
    max_daily_loss?: number | null
    stop_loss_pct?: number | null
    take_profit_pct?: number | null
    auto_approve_below?: number | null
  }) => post<Run>('/api/runs', req),
  stopRun: (id: string) => del<Run>(`/api/runs/${id}`),
  pauseRun: (id: string) => post<Run>(`/api/runs/${id}/pause`, {}),
  resumeRun: (id: string) => post<Run>(`/api/runs/${id}/resume`, {}),
  activity: () => get<ActivityItem[]>('/api/activity'),
  setMode: (mode: 'paper' | 'live', confirmation = '') =>
    post<{ mode: string }>('/api/mode', { mode, confirmation }),
  emergencyStop: (flatten: boolean) => post<{ stopped: boolean }>(`/api/emergency-stop?flatten=${flatten}`, {}),
  approve: (id: number) => post<{ status: string }>(`/api/approvals/${id}/approve`, {}),
  reject: (id: number) => post<{ status: string }>(`/api/approvals/${id}/reject`, {}),
  account: () => get<Account>('/api/account'),
  positions: () => get<Position[]>('/api/positions'),
  bars: (symbol: string, timeframe = '1Day', limit = 500) =>
    get<Bar[]>(`/api/bars/${encodeURIComponent(symbol)}?timeframe=${timeframe}&limit=${limit}`),
  strategies: () => get<{ strategies: StrategyInfo[]; errors: string[] }>('/api/strategies'),
  backtest: (req: BacktestRequest) => post<BacktestResult>('/api/backtest', req),
}
