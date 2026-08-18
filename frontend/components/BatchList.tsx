"use client";

import Link from "next/link";
import type { Batch } from "@/lib/api";

const STATUS_COLORS: Record<Batch["status"], string> = {
  pending: "bg-gray-700 text-gray-200",
  processing: "bg-yellow-700 text-yellow-100",
  completed: "bg-green-700 text-green-100",
  failed: "bg-red-800 text-red-100",
};

export default function BatchList({ batches }: { batches: Batch[] }) {
  if (batches.length === 0) {
    return <p className="text-sm text-gray-500">No batches uploaded yet.</p>;
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
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
