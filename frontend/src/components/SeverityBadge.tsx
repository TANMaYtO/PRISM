import { SeverityLevel } from "@/lib/types";

export function SeverityBadge({ severity }: { severity: string }) {
  const colors: Record<string, string> = {
    CRITICAL: "bg-critical text-void",
    HIGH: "bg-high text-void",
    MEDIUM: "bg-medium text-void",
    LOW: "bg-low text-void",
    SUGGESTION: "bg-suggest text-primary",
    CLEAN: "bg-low text-void",
    MODERATE: "bg-medium text-void",
  };

  const bgClass = colors[severity] || "bg-muted text-primary";

  return (
    <span
      className={`inline-block rounded-sm px-2 py-0.5 text-[0.625rem] font-bold uppercase tracking-wider ${bgClass}`}
    >
      {severity}
    </span>
  );
}
