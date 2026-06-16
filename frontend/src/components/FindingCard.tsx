"use client";

import { motion, useReducedMotion } from "framer-motion";
import { AgentFinding } from "@/lib/types";
import { SeverityBadge } from "./SeverityBadge";

export function FindingCard({ finding }: { finding: AgentFinding }) {
  const shouldReduceMotion = useReducedMotion();

  const borderColorMap: Record<string, string> = {
    CRITICAL: "border-critical",
    HIGH: "border-high",
    MEDIUM: "border-medium",
    LOW: "border-low",
    SUGGESTION: "border-suggest",
  };
  const borderColor = borderColorMap[finding.severity] || "border-muted";

  const itemVariants = {
    hidden: { opacity: 0, x: shouldReduceMotion ? 0 : 24 },
    visible: {
      opacity: 1,
      x: 0,
      transition: { duration: 0.2, ease: [0.2, 0, 0, 1] as const },
    },
  };

  return (
    <motion.div
      variants={itemVariants}
      className="bg-surface border border-line rounded mb-2 p-4"
    >
      <div className="flex justify-between items-start mb-2">
        <SeverityBadge severity={finding.severity} />
        <span className="font-code text-muted text-[0.875rem]">
          {finding.agent_source}
        </span>
      </div>
      <div
        className={`font-code text-[0.8rem] text-muted mb-2 border-l-2 pl-2 ${borderColor}`}
      >
        {finding.file}:{finding.line_start}-{finding.line_end}
      </div>
      <div className="font-finding-msg text-primary text-[0.875rem] leading-[1.6]">
        {finding.message}
      </div>
    </motion.div>
  );
}
