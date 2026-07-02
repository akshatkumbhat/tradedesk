import type { ReactElement } from 'react'
import { useApp, type Page } from '../store'

const items: { id: Page; label: string; icon: ReactElement }[] = [
  {
    id: 'overview',
    label: 'Overview',
    icon: (
      <svg viewBox="0 0 20 20" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 10.5 10 4l7 6.5" /><path d="M5 9.5V16h10V9.5" />
      </svg>
    ),
  },
  {
    id: 'strategies',
    label: 'Strategies',
    icon: (
      <svg viewBox="0 0 20 20" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="10" cy="10" r="7" /><path d="M10 6.5V10l2.5 2" />
      </svg>
    ),
  },
  {
    id: 'chart',
    label: 'Chart',
    icon: (
      <svg viewBox="0 0 20 20" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 16.5 8 11l3 3 6-7" />
      </svg>
    ),
  },
  {
    id: 'backtest',
    label: 'Backtest',
    icon: (
      <svg viewBox="0 0 20 20" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 4v12h12" /><path d="M7 12l3-3 2 2 4-5" />
      </svg>
    ),
  },
  {
    id: 'activity',
    label: 'Activity',
    icon: (
      <svg viewBox="0 0 20 20" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 10h3l2.5-5 3 10L14 10h3" />
      </svg>
    ),
  },
]

export function Sidebar() {
  const { page, setPage } = useApp()
  return (
    <aside className="w-56 shrink-0 h-full flex flex-col px-3 py-6">
      <div className="px-3 mb-8 flex items-center gap-2">
        <div className="w-7 h-7 rounded-lg bg-ink flex items-center justify-center">
          <svg viewBox="0 0 20 20" className="w-4 h-4 text-white" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M4 14l4-5 3 3 5-7" />
          </svg>
        </div>
        <span className="font-semibold tracking-tight text-[17px]">Tradedesk</span>
      </div>
      <nav className="flex flex-col gap-1">
        {items.map((it) => (
          <button
            key={it.id}
            onClick={() => setPage(it.id)}
            className={`flex items-center gap-3 px-3 py-2 rounded-xl text-[14px] font-medium transition-colors ${
              page === it.id
                ? 'bg-white text-ink shadow-[0_1px_3px_rgba(0,0,0,0.08)]'
                : 'text-ink-soft hover:text-ink hover:bg-black/[0.04]'
            }`}
          >
            {it.icon}
            {it.label}
          </button>
        ))}
      </nav>
      <div className="mt-auto px-3 text-[11px] text-ink-soft leading-relaxed">
        Local-first. Your data never leaves this Mac.
      </div>
    </aside>
  )
}
