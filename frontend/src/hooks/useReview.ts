import { useState, useEffect, useRef } from "react";
import { AgentFinding, PRReviewResponse, SeverityLevel } from "../lib/types";

export type AgentStatus = "pending" | "running" | "done";

const severityWeights: Record<SeverityLevel, number> = {
  CRITICAL: 5,
  HIGH: 4,
  MEDIUM: 3,
  LOW: 2,
  SUGGESTION: 1,
};

function getWorstSeverity(findings: AgentFinding[]): string {
  if (findings.length === 0) return "LOW";
  let worst: SeverityLevel = "SUGGESTION";
  for (const f of findings) {
    if (severityWeights[f.severity] > severityWeights[worst]) {
      worst = f.severity;
    }
  }
  return worst;
}

export function useReview(urlParam: string | null) {
  const [status, setStatus] = useState<string>("Initializing...");
  const [findings, setFindings] = useState<AgentFinding[]>([]);
  const [agentStatus, setAgentStatus] = useState<Record<string, AgentStatus>>({
    fetch_pr: "pending",
    build_rag: "pending",
    bug_detector: "pending",
    security_scanner: "pending",
    logic_auditor: "pending",
    style_checker: "pending",
    synthesizer: "pending",
  });
  const [agentCounts, setAgentCounts] = useState<Record<string, number>>({});
  const [agentSeverity, setAgentSeverity] = useState<Record<string, string>>({});
  const [finalReview, setFinalReview] = useState<PRReviewResponse | null>(null);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);

  const findingsRef = useRef<AgentFinding[]>([]);

  useEffect(() => {
    if (!isStreaming) return;
    const interval = setInterval(() => {
      setElapsedSeconds((s) => s + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, [isStreaming]);

  useEffect(() => {
    if (!urlParam) return;

    setIsStreaming(true);
    setFindings([]);
    findingsRef.current = [];
    setError(null);

    // Assuming the input URL is like: https://github.com/owner/repo/pull/123
    const match = urlParam.match(/github\.com\/([^\/]+)\/([^\/]+)\/pull\/(\d+)/);
    if (!match) {
      setError("Invalid GitHub PR URL format.");
      setIsStreaming(false);
      return;
    }
    const [, owner, repo, pr] = match;

    const eventSource = new EventSource(
      `/api/review?repo_owner=${owner}&repo_name=${repo}&pr_number=${pr}`
    );

    eventSource.onmessage = (event) => {
      // EventSource wrapper if backend uses standard SSE format without explicit event fields, 
      // but we expect the backend uses `event:` field and standard SSE.
    };

    eventSource.addEventListener("status", (e: MessageEvent) => {
      setStatus(JSON.parse(e.data));
    });

    eventSource.addEventListener("node_start", (e: MessageEvent) => {
      const node = JSON.parse(e.data);
      setAgentStatus((prev) => ({ ...prev, [node]: "running" }));
    });

    eventSource.addEventListener("finding", (e: MessageEvent) => {
      const finding: AgentFinding = JSON.parse(e.data);
      findingsRef.current = [...findingsRef.current, finding];
      setFindings(findingsRef.current);
    });

    eventSource.addEventListener("agent_done", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      const agentName = data.agent;
      setAgentStatus((prev) => ({ ...prev, [agentName]: "done" }));
      setAgentCounts((prev) => ({ ...prev, [agentName]: data.count }));

      // Compute worst severity for this agent
      const agentFindings = findingsRef.current.filter(
        (f) => f.agent_source === agentName
      );
      const worst = getWorstSeverity(agentFindings);
      setAgentSeverity((prev) => ({ ...prev, [agentName]: worst }));
    });

    eventSource.addEventListener("complete", (e: MessageEvent) => {
      const data: PRReviewResponse = JSON.parse(e.data);
      setFinalReview(data);
      setAgentStatus((prev) => ({ ...prev, synthesizer: "done" }));
      setStatus("Review complete.");
      setIsStreaming(false);
      eventSource.close();
    });

    eventSource.addEventListener("saved", (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setReviewId(data.id);
    });

    eventSource.addEventListener("error", (e: MessageEvent) => {
      setError(e.data || "An error occurred during the review stream.");
      setIsStreaming(false);
      eventSource.close();
    });

    eventSource.onerror = () => {
      setError("Lost connection to the server.");
      setIsStreaming(false);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [urlParam]);

  return {
    status,
    findings,
    agentStatus,
    agentCounts,
    agentSeverity,
    finalReview,
    reviewId,
    isStreaming,
    error,
    elapsedSeconds,
  };
}
