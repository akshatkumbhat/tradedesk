export function ConnectPrompt() {
  return (
    <div className="card p-10 max-w-lg mx-auto mt-16 text-center">
      <div className="w-12 h-12 mx-auto mb-5 rounded-2xl bg-accent/10 flex items-center justify-center">
        <svg viewBox="0 0 24 24" className="w-6 h-6 text-accent" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M8 12h8M12 8v8" /><circle cx="12" cy="12" r="9" />
        </svg>
      </div>
      <h2 className="text-[19px] font-semibold mb-2">Connect Alpaca</h2>
      <p className="text-[14px] text-ink-soft leading-relaxed mb-6">
        Add your free paper-trading keys to bring the dashboard to life. Keys are stored in a
        local <code className="text-[12px] bg-canvas px-1.5 py-0.5 rounded">.env</code> file
        and never leave this Mac.
      </p>
      <ol className="text-[13px] text-ink-soft text-left mx-auto max-w-xs space-y-2 mb-2">
        <li>1. Sign up at <span className="text-accent">app.alpaca.markets</span></li>
        <li>2. Open the Paper account → generate API keys</li>
        <li>3. Copy <code className="text-[12px] bg-canvas px-1.5 py-0.5 rounded">.env.example</code> → <code className="text-[12px] bg-canvas px-1.5 py-0.5 rounded">.env</code>, paste keys, restart backend</li>
      </ol>
    </div>
  )
}
