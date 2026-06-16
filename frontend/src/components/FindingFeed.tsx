"use client";

import { motion } from "framer-motion";
import { AgentFinding } from "@/lib/types";
import { FindingCard } from "./FindingCard";

export function FindingFeed({ findings }: { findings: AgentFinding[] }) {
  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.04,
      },
    },
  };

  if (findings.length === 0) {
    return <div className="text-muted font-body p-6">Waiting for findings...</div>;
  }

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="p-6 overflow-y-auto"
    >
      {findings.map((finding, idx) => (
        <FindingCard key={idx} finding={finding} />
      ))}
    </motion.div>
  );
}
