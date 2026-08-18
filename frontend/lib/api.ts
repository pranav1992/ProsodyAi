const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Batch = {
  id: string;
  name: string;
  status: "pending" | "processing" | "completed" | "failed";
  total_files: number;
  processed_files: number;
  failed_files: number;
  created_at: string;
  completed_at: string | null;
};

export type AudioResult = {
  id: string;
  filename: string;
  status: "pending" | "processing" | "done" | "error";
  error_message: string | null;
  emotional_tone: string | null;
  emotional_intensity: string | null;
  background_noise_present: boolean | null;
  background_noise_type: string | null;
  background_noise_severity: string | null;
  audio_quality: string | null;
  speaker_overlap_present: boolean | null;
  long_silence_present: boolean | null;
  confidence: number | null;
  processing_ms: number | null;
  audio_duration_seconds: number | null;
};

export type BatchDetail = Batch & { results: AudioResult[] };

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("autoace_token");
}

export function setToken(token: string) {
  window.localStorage.setItem("autoace_token", token);
}

export function clearToken() {
  window.localStorage.removeItem("autoace_token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { ...(options.headers as Record<string, string> || {}) };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail));
  }
  return res.json();
}

export async function login(email: string, password: string): Promise<string> {
  const data = await request<{ access_token: string }>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return data.access_token;
}

export function listBatches(): Promise<Batch[]> {
  return request<Batch[]>("/batches");
}

export function getBatch(id: string): Promise<BatchDetail> {
  return request<BatchDetail>(`/batches/${id}`);
}

export async function uploadBatch(file: File, name: string): Promise<BatchDetail> {
  const form = new FormData();
  form.append("file", file);
  const token = getToken();
  const res = await fetch(`${API_URL}/batches?name=${encodeURIComponent(name)}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail));
  }
  return res.json();
}

export async function downloadResults(batchId: string, format: "csv" | "json"): Promise<void> {
  const token = getToken();
  const res = await fetch(`${API_URL}/batches/${batchId}/download?format=${format}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Failed to download results");

  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${batchId}_results.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}
