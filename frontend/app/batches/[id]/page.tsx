"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { downloadResults, getBatch, type BatchDetail } from "@/lib/api";
import ResultsTable from "@/components/ResultsTable";

export default function BatchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [batch, setBatch] = useState<BatchDetail | null>(null);
  const router = useRouter();

  const refresh = useCallback(async () => {
    try {
      setBatch(await getBatch(id));
    } catch {
      router.push("/dashboard");
    }
  }, [id, router]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
  }, [refresh]);

  if (!batch) return <p className="text-sm text-gray-500">Loading...</p>;

  const isDone = batch.status === "completed" || batch.status === "failed";

  return (
    <div>
      <button onClick={() => router.push("/dashboard")} className="mb-4 text-sm text-gray-400 hover:text-white">
        &larr; Back to batches
      </button>

      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">{batch.name}</h1>
          <p className="text-sm text-gray-400">
            {batch.status} &middot; {batch.processed_files + batch.failed_files}/{batch.total_files} processed
            {batch.failed_files > 0 && <span className="text-red-400"> ({batch.failed_files} failed)</span>}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => downloadResults(batch.id, "csv")}
            disabled={!isDone}
            className="rounded border border-gray-700 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-800 disabled:opacity-40"
          >
            Download CSV
          </button>
          <button
            onClick={() => downloadResults(batch.id, "json")}
            disabled={!isDone}
            className="rounded border border-gray-700 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-800 disabled:opacity-40"
          >
            Download JSON
          </button>
        </div>
      </div>

      <ResultsTable results={batch.results} />
    </div>
  );
}
