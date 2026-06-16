import { PRInput } from "@/components/PRInput";
import { RecentReviews } from "@/components/RecentReviews";

export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-[640px] flex flex-col items-center">
        <div className="w-full mb-8">
          <div className="flex items-baseline justify-between mb-1">
            <h1 className="font-display font-bold text-[3rem] text-primary leading-none">
              PRISM
            </h1>
            <span className="font-code text-muted text-[0.75rem]">v0.1</span>
          </div>
          <p className="font-body text-muted">
            Autonomous pull-request intelligence
          </p>
        </div>
        
        <PRInput />
        <RecentReviews />
      </div>
    </main>
  );
}
