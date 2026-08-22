"use client";

import { useState } from "react";
import Link from "next/link";
import { deleteBatch, type Batch } from "@/lib/api";

const STATUS_COLORS: Record<Batch["status"], string> = {
  pending: "bg-gray-700 text-gray-200",
  processing: "bg-yellow-700 text-yellow-100",
  completed: "bg-green-700 text-green-100",
  failed: "bg-red-800 text-red-100",
};

export default function BatchList({ batches, onDeleted }: { batches: Batch[]; onDeleted: () => void }) {
  const [deletingId, setDeletingId] = useState<string | null>(null);

  if (batches.length === 0) {
    return <p className="text-sm text-gray-500">No batches uploaded yet.</p>;
  }

  async function handleDelete(b: Batch) {
    if (!window.confirm(`Delete "${b.name}"? This cannot be undone.`)) return;
    setDeletingId(b.id);
    try {
      await deleteBatch(b.id);
      onDeleted();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Failed to delete batch");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="overflow-hidden rounded-lg border border-gray-800">
      <table className="w-full text-sm">
        <thead className="bg-gray-900 text-left text-gray-400">
          <tr>
            <th className="px-4 py-2">Name</th>
            <th className="px-4 py-2">Status</th>
            <th className="px-4 py-2">Progress</th>
            <th className="px-4 py-2">Created</th>
            <th className="px-4 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {batches.map((b) => (
            <tr key={b.id} className="border-t border-gray-800 hover:bg-gray-900/50">
              <td className="px-4 py-3">
                <Link href={`/batches/${b.id}`} className="text-indigo-400 hover:underline">
                  {b.name}
                </Link>
              </td>
              <td className="px-4 py-3">
                <span className={`rounded px-2 py-0.5 text-xs ${STATUS_COLORS[b.status]}`}>{b.status}</span>
              </td>
              <td className="px-4 py-3 text-gray-300">
                {b.processed_files + b.failed_files}/{b.total_files}
                {b.failed_files > 0 && <span className="ml-2 text-red-400">({b.failed_files} failed)</span>}
              </td>
              <td className="px-4 py-3 text-gray-500">{new Date(b.created_at).toLocaleString()}</td>
              <td className="px-4 py-3 text-right">
                <button
                  onClick={() => handleDelete(b)}
                  disabled={deletingId === b.id}
                  className="rounded border border-gray-700 px-2 py-1 text-xs text-red-400 hover:bg-red-950 disabled:opacity-50"
                >
                  {deletingId === b.id ? "Deleting..." : "Delete"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
