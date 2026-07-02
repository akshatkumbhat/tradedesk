import { useEffect, useRef, useState } from 'react'
import type { ActivityItem } from '../api'
import { useApp } from '../store'

interface Toast extends ActivityItem {
  expires: number
}

/** Pops alert/error activity items as transient banners (in-app alerts). */
export function Toasts() {
  const activity = useApp((s) => s.activity)
  const [toasts, setToasts] = useState<Toast[]>([])
  const lastSeen = useRef<number | null>(null)

  useEffect(() => {
    if (activity.length === 0) return
    const newestId = activity[0].id
    if (lastSeen.current === null) {
      lastSeen.current = newestId // don't toast history on first load
      return
    }
    const fresh = activity.filter(
      (a) => a.id > (lastSeen.current as number) && (a.kind === 'alert' || a.kind === 'error'),
    )
    lastSeen.current = newestId
    if (fresh.length)
      setToasts((t) => [...fresh.map((a) => ({ ...a, expires: Date.now() + 7000 })), ...t].slice(0, 4))
  }, [activity])

  useEffect(() => {
    if (!toasts.length) return
    const id = setInterval(() => setToasts((t) => t.filter((x) => x.expires > Date.now())), 1000)
    return () => clearInterval(id)
  }, [toasts.length])

  if (!toasts.length) return null
  return (
    <div className="fixed top-5 right-5 z-50 flex flex-col gap-2 w-96 max-w-[calc(100vw-2.5rem)]">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`card px-4 py-3 border-l-4 ${t.kind === 'error' ? 'border-loss' : 'border-amber-400'}`}
        >
          <div className="flex items-start gap-2">
            <span className="text-[12px] font-semibold uppercase tracking-wide text-ink-soft">
              {t.kind}
            </span>
            <button
              onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}
              className="ml-auto text-ink-soft hover:text-ink text-[14px] leading-none"
            >
              ×
            </button>
          </div>
          <p className="text-[13px] mt-0.5 leading-snug">{t.detail}</p>
        </div>
      ))}
    </div>
  )
}
