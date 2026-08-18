"use client";

import { useState } from "react";
import { uploadBatch } from "@/lib/api";

export default function UploadForm({ onUploaded }: { onUploaded: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      await uploadBatch(file, name || file.name);
      setFile(null);
      setName("");
      onUploaded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border border-gray-800 bg-gray-900 p-6">
      <h2 className="mb-4 text-lg font-semibold text-white">Upload evaluation batch</h2>
      <p className="mb-4 text-sm text-gray-400">
        A .zip archive containing audio files at the root plus one CSV manifest
        (<code className="text-gray-300">name</code>, <code className="text-gray-300">result_json</code> columns).
      </p>

      <input
        type="text"
        placeholder="Batch name (optional)"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="mb-3 w-full rounded border border-gray-700 bg-gray-800 px-3 py-2 text-white"
      />

      <input
        type="file"
        accept=".zip"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="mb-4 w-full text-sm text-gray-300"
      />

      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      <button
        type="submit"
        disabled={!file || uploading}
        className="rounded bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
      >
        {uploading ? "Uploading..." : "Upload & process"}
      </button>
    </form>
  );
}
