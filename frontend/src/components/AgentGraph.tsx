"use client";

import { motion } from "framer-motion";
import { AgentStatus } from "@/hooks/useReview";

const severityColors: Record<string, string> = {
  CRITICAL: "var(--color-critical)",
  HIGH: "var(--color-high)",
  MEDIUM: "var(--color-medium)",
  LOW: "var(--color-low)",
  SUGGESTION: "var(--color-suggest)",
};

interface AgentGraphProps {
  agentStatus: Record<string, AgentStatus>;
  agentSeverity: Record<string, string>;
  agentCounts: Record<string, number>;
}

export function AgentGraph({ agentStatus, agentSeverity, agentCounts }: AgentGraphProps) {
  const nodes = [
    { id: "fetch_pr", label: "FETCH", x: 10, y: 57 },
    { id: "build_rag", label: "RAG", x: 80, y: 57 },
    { id: "bug_detector", label: "BUG", x: 150, y: 0 },
    { id: "security_scanner", label: "SEC", x: 150, y: 38 },
    { id: "logic_auditor", label: "LOG", x: 150, y: 76 },
    { id: "style_checker", label: "STY", x: 150, y: 114 },
    { id: "synthesizer", label: "SYNTH", x: 220, y: 57 },
  ];

  const edges = [
    { id: "e1", d: "M 58 71 L 80 71", trigger: "build_rag" },
    { id: "e2", d: "M 128 71 L 139 71 L 139 14 L 150 14", trigger: "bug_detector" },
    { id: "e3", d: "M 128 71 L 139 71 L 139 52 L 150 52", trigger: "security_scanner" },
    { id: "e4", d: "M 128 71 L 139 71 L 139 90 L 150 90", trigger: "logic_auditor" },
    { id: "e5", d: "M 128 71 L 139 71 L 139 128 L 150 128", trigger: "style_checker" },
    { id: "e6", d: "M 198 14 L 209 14 L 209 71 L 220 71", trigger: "synthesizer" },
    { id: "e7", d: "M 198 52 L 209 52 L 209 71 L 220 71", trigger: "synthesizer" },
    { id: "e8", d: "M 198 90 L 209 90 L 209 71 L 220 71", trigger: "synthesizer" },
    { id: "e9", d: "M 198 128 L 209 128 L 209 71 L 220 71", trigger: "synthesizer" },
  ];

  const getFill = (id: string, status: string) => {
    if (status !== "done") return "transparent";
    const sev = agentSeverity[id];
    return sev ? severityColors[sev] : severityColors["LOW"]; // default low if no findings
  };

  return (
    <div className="w-full">
      <svg viewBox="0 0 280 142" className="w-full h-auto">
        {edges.map((e) => {
          const active = agentStatus[e.trigger] === "running" || agentStatus[e.trigger] === "done";
          const done = agentStatus["synthesizer"] === "done";
          return (
            <motion.path
              key={e.id}
              d={e.d}
              fill="none"
              stroke={done ? "var(--color-prism)" : "var(--color-line)"}
              strokeWidth={1}
              initial={{ pathLength: 0 }}
              animate={{ pathLength: active ? 1 : 0 }}
              transition={{ duration: 0.4, ease: "linear" }}
            />
          );
        })}

        {nodes.map((n) => {
          const status = agentStatus[n.id] || "pending";
          const isRunning = status === "running";
          const isDone = status === "done";
          const borderColor = isRunning || isDone ? "var(--color-prism)" : "var(--color-line)";
          const textColor = isRunning || isDone ? "var(--color-primary)" : "var(--color-muted)";
          const fill = getFill(n.id, status);

          return (
            <motion.g
              key={n.id}
              initial={false}
              animate={{ scale: isRunning ? [1, 1.03, 1] : 1 }}
              transition={{ duration: 0.6, ease: "easeInOut" }}
            >
              <rect
                x={n.x}
                y={n.y}
                width={48}
                height={28}
                rx={4}
                stroke={borderColor}
                strokeWidth={1}
                fill={fill}
                style={{ transition: "fill 0.3s ease, stroke 0.3s ease" }}
              />
              <text
                x={n.x + 24}
                y={n.y + 15}
                dominantBaseline="middle"
                textAnchor="middle"
                fill={textColor}
                fontSize="10"
                fontFamily="var(--font-code)"
                style={{ transition: "fill 0.3s ease" }}
              >
                {n.label}
              </text>
            </motion.g>
          );
        })}
      </svg>
      <div className="mt-6 flex flex-col gap-2">
        {[
          { id: "bug_detector", label: "🐛 Bug Detector" },
          { id: "security_scanner", label: "🔒 Security" },
          { id: "logic_auditor", label: "🧠 Logic" },
          { id: "style_checker", label: "✨ Style" },
        ].map((agent) => {
          const status = agentStatus[agent.id] || "pending";
          const count = agentCounts[agent.id] ?? 0;
          const isPending = status === "pending";
          return (
            <div
              key={agent.id}
              className={`flex justify-between font-code text-[0.875rem] ${
                isPending ? "text-dim" : "text-primary"
              } transition-colors duration-300`}
            >
              <span>{agent.label}</span>
              <span>{isPending ? "" : `${count} findings`}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
