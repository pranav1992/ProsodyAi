"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { clearToken, listBatches, type Batch } from "@/lib/api";
import UploadForm from "@/components/UploadForm";
import BatchList from "@/components/BatchList";

export default function DashboardPage() {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const refresh = useCallback(async () => {
    try {
      setBatches(await listBatches());
    } catch (err) {
      if (err instanceof Error && err.message.toLowerCase().includes("token")) {
        clearToken();
        router.push("/login");
      }
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 4000); // poll for batch progress
    return () => clearInterval(interval);
  }, [refresh]);

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  return (
    <div>
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">AutoAce Voice Tone &amp; Noise Dashboard</h1>
          <p className="text-sm text-gray-400">Batch analysis of production call audio</p>
        </div>
        <button onClick={handleLogout} className="rounded border border-gray-700 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-800">
          Log out
        </button>
      </div>

      <div className="mb-8">
        <UploadForm onUploaded={refresh} />
      </div>

      <h2 className="mb-3 text-lg font-semibold text-white">Batches</h2>
      {loading ? <p className="text-sm text-gray-500">Loading...</p> : <BatchList batches={batches} />}
    </div>
  );
}
