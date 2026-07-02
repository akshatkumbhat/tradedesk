import { useEffect } from 'react'
import { api } from './api'
import { Header } from './components/Header'
import { Sidebar } from './components/Sidebar'
import { Toasts } from './components/Toasts'
import { Activity } from './pages/Activity'
import { Backtest } from './pages/Backtest'
import { ChartPage } from './pages/ChartPage'
import { Overview } from './pages/Overview'
import { Strategies } from './pages/Strategies'
import { connectWs, useApp } from './store'

function App() {
  const { page, setHealth } = useApp()

  // Poll backend health so the header dot reflects reality.
  useEffect(() => {
    const check = () => api.health().then(setHealth).catch(() => setHealth(null))
    check()
    const id = setInterval(check, 10_000)
    return () => clearInterval(id)
  }, [setHealth])

  // Live dashboard state over the websocket.
  useEffect(() => connectWs(), [])

  return (
    <div className="h-full flex">
      <Toasts />
      <Sidebar />
      <main className="flex-1 min-w-0 h-full overflow-y-auto">
        <Header />
        {page === 'overview' && <Overview />}
        {page === 'chart' && <ChartPage />}
        {page === 'strategies' && <Strategies />}
        {page === 'backtest' && <Backtest />}
        {page === 'activity' && <Activity />}
      </main>
    </div>
  )
}

export default App
