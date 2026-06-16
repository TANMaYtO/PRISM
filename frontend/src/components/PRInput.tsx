"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function PRInput() {
  const [url, setUrl] = useState("");
  const [isInitializing, setIsInitializing] = useState(false);
  const router = useRouter();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    setIsInitializing(true);
    router.push(`/review?url=${encodeURIComponent(url)}`);
  };

  return (
    <form onSubmit={handleSubmit} className="w-full">
      <label className="block font-heading text-muted mb-2">
        PULL REQUEST URL
      </label>
      <input
        type="text"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="https://github.com/owner/repo/pull/123"
        className="w-full font-code text-[0.875rem] bg-surface border border-line focus:border-prism outline-none text-primary placeholder-dim rounded px-4 py-3 mb-4 transition-colors"
        disabled={isInitializing}
      />
      <button
        type="submit"
        disabled={isInitializing || !url.trim()}
        className="w-full bg-prism text-void font-display font-bold text-[0.875rem] tracking-[0.1em] rounded h-[44px] flex items-center justify-center hover:opacity-85 transition-opacity disabled:opacity-50"
      >
        {isInitializing ? (
          <span className="flex items-center">
            INITIALIZING
            <span className="animate-[blink_1s_infinite] ml-1">|</span>
          </span>
        ) : (
          "RUN REVIEW"
        )}
      </button>
      <style>{`
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
      `}</style>
    </form>
  );
}
