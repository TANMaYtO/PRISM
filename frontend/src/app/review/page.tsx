"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState, Suspense } from "react";
import { AgentGraph } from "@/components/AgentGraph";
import { FindingFeed } from "@/components/FindingFeed";
import { StatusBar } from "@/components/StatusBar";
import { SummaryPanel } from "@/components/SummaryPanel";
import { useReview } from "@/hooks/useReview";
import { getReview } from "@/lib/api";
import { PRReviewResponse, AgentFinding } from "@/lib/types";

function ReviewContent() {
  const searchParams = useSearchParams();
  const urlParam = searchParams.get("url");
  const idParam = searchParams.get("id");

  const [staticReview, setStaticReview] = useState<PRReviewResponse | null>(null);
  const [staticLoading, setStaticLoading] = useState(!!idParam);
  const [staticError, setStaticError] = useState<string | null>(null);

  const {
    status,
    findings,
    agentStatus,
    agentCounts,
    agentSeverity,
    finalReview,
    isStreaming,
    error: streamError,
    elapsedSeconds,
  } = useReview(urlParam);

  useEffect(() => {
    if (idParam) {
      getReview(idParam)
        .then((data) => {
          setStaticReview(data);
          setStaticLoading(false);
        })
        .catch(() => {
          setStaticError("Failed to load review.");
          setStaticLoading(false);
        });
    }
  }, [idParam]);

  if (staticLoading) {
    return <div className="p-8 text-muted font-body">Loading review...</div>;
  }

  if (staticError || streamError) {
    return (
      <div className="p-8 text-critical font-code">
        Error: {staticError || streamError}
      </div>
    );
  }

  const displayStatus = idParam ? "Review complete." : status;
  const isComplete = idParam ? true : !isStreaming && finalReview !== null;
  const displayFindings = idParam ? staticReview?.findings || [] : findings;
  const displayReview = idParam ? staticReview : finalReview;

  const displayAgentStatus = idParam
    ? {
        fetch_pr: "done",
        build_rag: "done",
        bug_detector: "done",
        security_scanner: "done",
        logic_auditor: "done",
        style_checker: "done",
        synthesizer: "done",
      }
    : agentStatus;

  let displayAgentCounts = agentCounts;
  let displayAgentSeverity = agentSeverity;

  if (idParam && staticReview) {
    const counts: Record<string, number> = {};
    const severities: Record<string, string> = {};
    const agents = ["bug_detector", "security_scanner", "logic_auditor", "style_checker"];
    
    agents.forEach(agent => {
      const agentFindings = staticReview.findings.filter(f => f.agent_source === agent);
      counts[agent] = agentFindings.length;
      if (agentFindings.length === 0) {
        severities[agent] = "LOW";
      } else {
        const order = ["SUGGESTION", "LOW", "MEDIUM", "HIGH", "CRITICAL"];
        let worst = -1;
        agentFindings.forEach(f => {
          const idx = order.indexOf(f.severity);
          if (idx > worst) worst = idx;
        });
        severities[agent] = order[worst];
      }
    });
    displayAgentCounts = counts;
    displayAgentSeverity = severities;
  }

  const stats = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
  displayFindings.forEach(f => {
    if (f.severity in stats) {
      stats[f.severity as keyof typeof stats]++;
    }
  });

  const prText = urlParam 
    ? urlParam.split("pull/")[1] || "Unknown" 
    : staticReview?.pr_number || "Unknown";

  const repoText = urlParam
    ? urlParam.match(/github\.com\/([^\/]+\/[^\/]+)/)?.[1] || "Unknown Repo"
    : staticReview?.repo || "Unknown Repo";

  return (
    <div className="flex flex-col md:flex-row h-screen overflow-hidden">
      <div className="w-full md:w-[280px] shrink-0 border-b md:border-b-0 md:border-r border-line bg-void flex flex-col md:h-full md:overflow-y-auto">
        <div className="p-6 border-b border-line hidden md:block">
          <div className="font-heading text-muted text-[0.75rem] mb-2">REVIEWING</div>
          <div className="font-code text-primary mb-1">{repoText}</div>
          <div className="font-display font-bold text-[2rem] leading-none mb-2">
            #{prText}
          </div>
        </div>
        <div className="p-6 md:hidden flex justify-between items-center border-b border-line">
          <div>
             <span className="font-code text-primary">{repoText}</span>
             <span className="font-display font-bold text-lg ml-2">#{prText}</span>
          </div>
        </div>

        <div className="p-6 border-b border-line">
          <div className="font-heading text-muted text-[0.75rem] mb-4">PIPELINE</div>
          <AgentGraph 
            agentStatus={displayAgentStatus as any} 
            agentSeverity={displayAgentSeverity} 
            agentCounts={displayAgentCounts} 
          />
        </div>

        <div className="p-6">
          <div className="font-heading text-muted text-[0.75rem] mb-4">FINDINGS</div>
          <div className="flex flex-col gap-3">
            {[
              { label: "CRITICAL", count: stats.CRITICAL, color: "text-critical" },
              { label: "HIGH", count: stats.HIGH, color: "text-high" },
              { label: "MEDIUM", count: stats.MEDIUM, color: "text-medium" },
              { label: "LOW", count: stats.LOW, color: "text-low" },
            ].map(stat => (
              <div key={stat.label} className="flex justify-between items-center">
                <span className="font-code text-muted text-[0.875rem]">{stat.label}</span>
                <span className={`font-display font-bold text-[1.2rem] ${stat.color}`}>
                  {stat.count}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 flex flex-col h-full bg-void relative">
        <StatusBar 
          status={displayStatus} 
          isComplete={isComplete} 
          elapsedSeconds={idParam ? staticReview?.stats.critical || 0 : elapsedSeconds}
        />
        <div className="flex-1 overflow-y-auto relative flex flex-col">
          <FindingFeed findings={displayFindings} />
          {isComplete && <SummaryPanel review={displayReview} />}
        </div>
      </div>
    </div>
  );
}

export default function ReviewPage() {
  return (
    <Suspense fallback={<div className="p-8 text-muted">Loading...</div>}>
      <ReviewContent />
    </Suspense>
  );
}
