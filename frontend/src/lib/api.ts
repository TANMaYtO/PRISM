import { PRReviewResponse, BenchmarkSummary } from "./types";

export async function getRecentReviews(): Promise<PRReviewResponse[]> {
  const res = await fetch("/api/reviews");
  if (!res.ok) {
    throw new Error("Failed to fetch recent reviews");
  }
  return res.json();
}

export async function getReview(id: string): Promise<PRReviewResponse> {
  const res = await fetch(`/api/review/${id}`);
  if (!res.ok) {
    throw new Error("Failed to fetch review");
  }
  return res.json();
}

export async function getBenchmark(): Promise<BenchmarkSummary> {
  const res = await fetch("/api/benchmark");
  if (!res.ok) {
    throw new Error("Failed to fetch benchmark");
  }
  return res.json();
}
