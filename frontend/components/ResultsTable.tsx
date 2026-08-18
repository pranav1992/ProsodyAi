"use client";

import type { AudioResult } from "@/lib/api";

const STATUS_COLORS: Record<AudioResult["status"], string> = {
  pending: "bg-gray-700 text-gray-200",
  processing: "bg-yellow-700 text-yellow-100",
  done: "bg-green-700 text-green-100",
  error: "bg-red-800 text-red-100",
};

export default function ResultsTable({ results }: { results: AudioResult[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800">
      <table className="w-full min-w-[900px] text-sm">
        <thead className="bg-gray-900 text-left text-gray-400">
          <tr>
            <th className="px-3 py-2">File</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Tone</th>
            <th className="px-3 py-2">Intensity</th>
            <th className="px-3 py-2">Noise</th>
            <th className="px-3 py-2">Noise severity</th>
            <th className="px-3 py-2">Audio quality</th>
            <th className="px-3 py-2">Overlap</th>
            <th className="px-3 py-2">Long silence</th>
            <th className="px-3 py-2">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {results.map((r) => (
            <tr key={r.id} className="border-t border-gray-800 hover:bg-gray-900/50">
              <td className="px-3 py-2 font-mono text-xs text-gray-300">{r.filename}</td>
              <td className="px-3 py-2">
                <span className={`rounded px-2 py-0.5 text-xs ${STATUS_COLORS[r.status]}`}>{r.status}</span>
              </td>
              {r.status === "error" ? (
                <td colSpan={8} className="px-3 py-2 text-red-400">{r.error_message}</td>
              ) : (
                <>
                  <td className="px-3 py-2 text-gray-200">{r.emotional_tone ?? "-"}</td>
                  <td className="px-3 py-2 text-gray-200">{r.emotional_intensity ?? "-"}</td>
                  <td className="px-3 py-2 text-gray-200">
                    {r.background_noise_present === null ? "-" : r.background_noise_present ? r.background_noise_type || "yes" : "none"}
                  </td>
                  <td className="px-3 py-2 text-gray-200">{r.background_noise_severity ?? "-"}</td>
                  <td className="px-3 py-2 text-gray-200">{r.audio_quality ?? "-"}</td>
                  <td className="px-3 py-2 text-gray-200">{r.speaker_overlap_present === null ? "-" : r.speaker_overlap_present ? "yes" : "no"}</td>
                  <td className="px-3 py-2 text-gray-200">{r.long_silence_present === null ? "-" : r.long_silence_present ? "yes" : "no"}</td>
                  <td className="px-3 py-2 text-gray-200">{r.confidence !== null ? r.confidence.toFixed(2) : "-"}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
