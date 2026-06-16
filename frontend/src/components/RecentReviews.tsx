"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PRReviewResponse } from "@/lib/types";
import { getRecentReviews } from "@/lib/api";
import { SeverityBadge } from "./SeverityBadge";

export function RecentReviews() {
  const [reviews, setReviews] = useState<PRReviewResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getRecentReviews()
      .then((data) => {
        setReviews(data.slice(0, 5));
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, []);

  const timeAgo = (dateStr: string) => {
    const d = new Date(dateStr);
    const now = new Date();
    const diff = Math.floor((now.getTime() - d.getTime()) / 1000);
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  };

  return (
    <div className="w-full mt-8 border-t border-line pt-8">
      <h2 className="font-heading text-muted text-[0.75rem] mb-4">
        RECENT REVIEWS
      </h2>
      {loading ? (
        <div className="text-muted font-body text-center">Loading...</div>
      ) : reviews.length === 0 ? (
        <div className="text-muted font-body text-center">No reviews yet.</div>
      ) : (
        <div className="flex flex-col border border-line rounded">
          {reviews.map((r, i) => (
            <Link
              key={r.id || r.pr_number}
              href={`/review?id=${r.id}`}
              className={`flex items-center justify-between p-4 hover:bg-overlay transition-colors ${
                i < reviews.length - 1 ? "border-b border-line" : ""
              }`}
            >
              <div className="font-code text-primary">
                {r.repo}#{r.pr_number}
              </div>
              <div className="flex items-center gap-4">
                <SeverityBadge severity={r.risk_rating} />
                <div className="font-body text-muted text-sm w-16 text-right">
                  {timeAgo(r.reviewed_at)}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
