export function StatusBar({
  status,
  isComplete,
  elapsedSeconds,
}: {
  status: string;
  isComplete: boolean;
  elapsedSeconds: number;
}) {
  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  return (
    <div className="flex items-center justify-between px-6 py-4 bg-void border-b border-line sticky top-0 z-10">
      <div className="flex items-center gap-3">
        <div
          className="text-prism text-[1.2rem] leading-none"
          style={{
            animation: !isComplete
              ? "pulse-dot 1.5s infinite ease-in-out"
              : "none",
          }}
        >
          ●
        </div>
        <span className="font-code text-prism text-[0.875rem]">{status}</span>
      </div>
      <div className="font-code text-muted text-[0.875rem]">
        {formatTime(elapsedSeconds)}
      </div>
      <style>{`
        @keyframes pulse-dot {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
    </div>
  );
}
