"use client";

import { Fragment, useEffect, useState } from "react";
import { BenchmarkSummary } from "@/lib/types";
import { getBenchmark } from "@/lib/api";
import { BenchmarkChart } from "@/components/BenchmarkChart";
import { SeverityBadge } from "@/components/SeverityBadge";

export default function BenchmarkPage() {
  const [summary, setSummary] = useState<BenchmarkSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedPrs, setExpandedPrs] = useState<Record<number, boolean>>({});

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

  const togglePr = (prNumber: number) => {
    setExpandedPrs((prev) => ({
      ...prev,
      [prNumber]: !prev[prNumber],
    }));
  };

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
              <th className="p-4 font-normal">Human Comments</th>
              <th className="p-4 font-normal">PRISM Findings</th>
              <th className="p-4 font-normal text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {summary.results.map((r, i) => {
              const isExpanded = !!expandedPrs[r.pr_number];
              const prismFindings = r.prism_findings || [];
              const humanComments = r.human_comments || [];

              return (
                <Fragment key={r.pr_number}>
                  <tr className={i % 2 === 0 ? "bg-void" : "bg-surface"}>
                    <td className="p-4 text-primary font-bold">#{r.pr_number}</td>
                    <td className="p-4 text-primary">{r.precision.toFixed(3)}</td>
                    <td className="p-4 text-primary">{r.recall.toFixed(3)}</td>
                    <td className="p-4 text-primary">{r.f1_score.toFixed(3)}</td>
                    <td className="p-4 text-muted">{r.human_findings_count}</td>
                    <td className="p-4 text-prism">{r.prism_findings_count}</td>
                    <td className="p-4 text-right">
                      <button
                        onClick={() => togglePr(r.pr_number)}
                        className="px-3 py-1 text-xs border border-line rounded hover:bg-overlay text-primary transition-colors"
                      >
                        {isExpanded ? "Hide Details" : "View Findings"}
                      </button>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr className="bg-overlay">
                      <td colSpan={7} className="p-6">
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                          <div>
                            <div className="flex items-center gap-2 mb-3">
                              <span className="font-heading text-xs text-prism font-bold tracking-wider">
                                PRISM DETECTED ({prismFindings.length})
                              </span>
                            </div>
                            {prismFindings.length === 0 ? (
                              <p className="text-muted text-xs font-body italic">
                                No specific findings recorded for this PR.
                              </p>
                            ) : (
                              <div className="flex flex-col gap-3 max-h-[360px] overflow-y-auto pr-2">
                                {prismFindings.map((f, fIdx) => (
                                  <div
                                    key={fIdx}
                                    className="p-3 bg-surface border border-line rounded text-xs font-body flex flex-col gap-1.5"
                                  >
                                    <div className="flex items-center justify-between gap-2">
                                      <span className="font-code text-muted truncate text-[0.75rem]">
                                        {f.file}
                                        {f.line_start ? `:${f.line_start}` : ""}
                                      </span>
                                      <SeverityBadge severity={f.severity} />
                                    </div>
                                    <p className="text-primary leading-relaxed">
                                      {f.message}
                                    </p>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>

                          <div>
                            <div className="flex items-center gap-2 mb-3">
                              <span className="font-heading text-xs text-muted font-bold tracking-wider">
                                HUMAN COMMENTS ({humanComments.length})
                              </span>
                            </div>
                            {humanComments.length === 0 ? (
                              <p className="text-muted text-xs font-body italic">
                                No human comments recorded for this PR.
                              </p>
                            ) : (
                              <div className="flex flex-col gap-3 max-h-[360px] overflow-y-auto pr-2">
                                {humanComments.map((c, cIdx) => (
                                  <div
                                    key={cIdx}
                                    className="p-3 bg-surface border border-line rounded text-xs font-body flex flex-col gap-1.5"
                                  >
                                    <div className="flex items-center justify-between gap-2">
                                      <span className="font-code text-muted truncate text-[0.75rem]">
                                        {c.file || "General Comment"}
                                      </span>
                                      {c.reviewer && (
                                        <span className="text-[0.7rem] text-muted">
                                          @{c.reviewer}
                                        </span>
                                      )}
                                    </div>
                                    <p className="text-muted leading-relaxed">
                                      {c.body || "(No message content)"}
                                    </p>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </main>
  );
}
