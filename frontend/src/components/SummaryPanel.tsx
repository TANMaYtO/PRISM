"use client";

import { motion, useReducedMotion } from "framer-motion";
import { PRReviewResponse } from "@/lib/types";
import { SeverityBadge } from "./SeverityBadge";

export function SummaryPanel({ review }: { review: PRReviewResponse | null }) {
  const shouldReduceMotion = useReducedMotion();

  if (!review) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: shouldReduceMotion ? 0 : 40 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.2, 0, 0, 1] as const }}
      className="p-6 bg-surface border-t border-line mt-auto"
    >
      <div className="flex justify-between items-start mb-4">
        <div>
          <div className="font-label text-muted mb-1">RISK RATING</div>
          <SeverityBadge severity={review.risk_rating} />
        </div>
        <button
          onClick={() => {
            navigator.clipboard.writeText(review.summary);
          }}
          className="bg-prism text-void font-display font-bold text-[0.875rem] px-4 py-2 rounded tracking-wider hover:opacity-85 transition-opacity"
        >
          COPY AS GITHUB COMMENT
        </button>
      </div>
      <div className="font-body text-primary leading-[1.6]">
        {review.summary}
      </div>
    </motion.div>
  );
}
