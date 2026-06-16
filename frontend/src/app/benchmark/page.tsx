"use client";

import { useEffect, useState } from "react";
import { BenchmarkSummary } from "@/lib/types";
import { getBenchmark } from "@/lib/api";
import { BenchmarkChart } from "@/components/BenchmarkChart";

export default function BenchmarkPage() {
  const [summary, setSummary] = useState<BenchmarkSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getBenchmark()
      .then((data) => {
        setSummary(data);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <div className="p-8 text-muted font-body">Loading benchmark data...</div>;
  }

  if (!summary) {
    return <div className="p-8 text-critical font-code">Error loading benchmark data.</div>;
  }

  const metrics = [
    { label: "AVG PRECISION", value: summary.avg_precision.toFixed(3) },
    { label: "AVG RECALL", value: summary.avg_recall.toFixed(3) },
    { label: "AVG F1 SCORE", value: summary.avg_f1.toFixed(3) },
    { label: "AVG SEVERITY SCORE", value: summary.avg_severity_weighted.toFixed(3) },
  ];

  return (
    <main className="min-h-screen bg-void p-6 md:p-12 max-w-[1280px] mx-auto">
      <h1 className="font-display font-bold text-[2rem] text-primary mb-8 uppercase tracking-wider">
        Benchmark
      </h1>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
        {metrics.map((m) => (
          <div key={m.label} className="bg-surface border border-line rounded p-6">
            <div className="font-heading text-muted text-[0.75rem] mb-2">{m.label}</div>
            <div className="font-display font-bold text-[2.5rem] text-prism leading-none">
              {m.value}
            </div>
          </div>
        ))}
      </div>

      <BenchmarkChart data={summary.results} />

      <div className="mt-8 border border-line rounded overflow-x-auto">
        <table className="w-full text-left font-code text-[0.875rem]">
          <thead className="bg-surface border-b border-line text-muted">
            <tr>
              <th className="p-4 font-normal">PR #</th>
              <th className="p-4 font-normal">Precision</th>
              <th className="p-4 font-normal">Recall</th>
              <th className="p-4 font-normal">F1</th>
              <th className="p-4 font-normal">Human Findings</th>
              <th className="p-4 font-normal">PRISM Findings</th>
            </tr>
          </thead>
          <tbody>
            {summary.results.map((r, i) => (
              <tr 
                key={r.pr_number} 
                className={i % 2 === 0 ? "bg-void" : "bg-surface"}
              >
                <td className="p-4 border-t border-line text-primary">#{r.pr_number}</td>
                <td className="p-4 border-t border-line text-primary">{r.precision.toFixed(3)}</td>
                <td className="p-4 border-t border-line text-primary">{r.recall.toFixed(3)}</td>
                <td className="p-4 border-t border-line text-primary">{r.f1_score.toFixed(3)}</td>
                <td className="p-4 border-t border-line text-muted">{r.human_findings_count}</td>
                <td className="p-4 border-t border-line text-prism">{r.prism_findings_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
