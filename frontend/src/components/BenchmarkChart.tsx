"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { BenchmarkResult } from "@/lib/types";

export function BenchmarkChart({ data }: { data: BenchmarkResult[] }) {
  const chartData = data.map((d) => ({
    name: `PR #${d.pr_number}`,
    Human: d.human_findings_count,
    PRISM: d.prism_findings_count,
  }));

  return (
    <div className="w-full h-[400px] bg-void border border-line p-4 mt-8">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={chartData}
          margin={{ top: 20, right: 30, left: 0, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#1C1C2E" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fill: "#5A5A7A", fontFamily: "var(--font-geist-mono)", fontSize: 12 }}
            axisLine={{ stroke: "#1C1C2E" }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#5A5A7A", fontFamily: "var(--font-geist-mono)", fontSize: 12 }}
            axisLine={{ stroke: "#1C1C2E" }}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#0F0F18",
              borderColor: "#1C1C2E",
              fontFamily: "var(--font-geist-mono)",
            }}
            itemStyle={{ color: "#E2E2F0" }}
          />
          <Legend
            wrapperStyle={{ fontFamily: "var(--font-geist)", fontSize: 12, color: "#5A5A7A" }}
          />
          <Bar dataKey="Human" fill="#5A5A7A" radius={0} />
          <Bar dataKey="PRISM" fill="#4F7FFF" radius={0} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
