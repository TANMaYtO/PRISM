import { PRReviewResponse, BenchmarkSummary } from "./types";
import benchmarkFallback from "@/data/benchmark.json";

export async function getRecentReviews(): Promise<PRReviewResponse[]> {
  try {
    const res = await fetch("/api/reviews");
    if (!res.ok) {
      return [];
    }
    return await res.json();
  } catch (err) {
    console.warn("Could not fetch recent reviews from backend:", err);
    return [];
  }
}

export async function getReview(id: string): Promise<PRReviewResponse> {
  const res = await fetch(`/api/review/${id}`);
  if (!res.ok) {
    throw new Error("Failed to fetch review");
  }
  return res.json();
}

export async function getBenchmark(): Promise<BenchmarkSummary> {
  try {
    const res = await fetch("/api/benchmark");
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    console.warn("Backend /api/benchmark unavailable, using bundled fallback:", err);
  }
  return benchmarkFallback as unknown as BenchmarkSummary;
}
