import { PRReviewResponse, BenchmarkSummary } from "./types";
import benchmarkFallback from "@/data/benchmark.json";

async function resolveBackendUrl(): Promise<string> {
  try {
    const res = await fetch("/api/config");
    if (res.ok) {
      const data = await res.json();
      if (data.backendUrl) {
        return data.backendUrl;
      }
    }
  } catch {
    // ignore network errors
  }
  return "https://prism-backend-qboc.onrender.com";
}

export async function getRecentReviews(): Promise<PRReviewResponse[]> {
  try {
    const res = await fetch("/api/reviews");
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // try direct backend fallback
  }

  try {
    const backend = await resolveBackendUrl();
    const res = await fetch(`${backend}/reviews`);
    if (res.ok) {
      return await res.json();
    }
  } catch (err) {
    console.warn("Could not fetch recent reviews:", err);
  }

  return [];
}

export async function getReview(id: string): Promise<PRReviewResponse> {
  try {
    const res = await fetch(`/api/review/${id}`);
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // try direct backend fallback
  }

  try {
    const backend = await resolveBackendUrl();
    const res = await fetch(`${backend}/review/${id}`);
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // error handled below
  }

  throw new Error("Failed to fetch review");
}

export async function getBenchmark(): Promise<BenchmarkSummary> {
  try {
    const res = await fetch("/api/benchmark");
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // try direct backend fallback
  }

  try {
    const backend = await resolveBackendUrl();
    const res = await fetch(`${backend}/benchmark`);
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // fallback to bundled benchmark
  }

  return benchmarkFallback as unknown as BenchmarkSummary;
}
