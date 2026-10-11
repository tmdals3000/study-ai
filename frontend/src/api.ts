export type Doc = { id: number; title: string; pages: number; status: "processing" | "ready" | "error"; error: string | null; created_at: string };
export type Page = { id: number; doc_id: number; page_no: number; text: string; figure_text: string | null };
// figure: 인용이 원문 텍스트가 아니라 검증된 그림 판독 내용에서 나왔음
export type Evidence = { page: number; quote: string; figure?: boolean };
export type Point = { id: string; heading: string; kind: string; content: string; pages: number[]; evidence: Evidence[]; corrected: boolean };
export type Summary = {
  title: string; one_line: { text: string; pages: number[] } | null;
  key_concepts: { name: string; description: string; pages: number[] }[];
  exam_points: { text: string; pages: number[] }[];
  sections: { title: string; pages: [number, number]; points: Point[] }[];
  mindmap: string;
  stats: { generated: number; kept: number; no_evidence: number; unsupported: number; corrected: number };
};
export type Generation<T> = { id: number; status: "queued" | "running" | "done" | "error" | "cancelled"; progress: string | null; error: string | null; data: T | null; updated_at: string };
export type StudyResult = { requested: number; generated: number; kept: number; rejected: number; note: string };
export type Kind = "summary" | "quiz" | "cards" | "figures";
export type FigureResult = { pages: number; pages_with_figures: number; generated: number; kept: number };
export type GenerateOptions = { force?: boolean; count?: number; types?: string[]; wrong_only?: boolean };
export type Question = { id: number; type: "multiple" | "ox" | "short"; question: string; choices: string[]; difficulty: string; concept: string };
export type Grade = { correct: boolean; feedback: string; answer: string; explanation: string; evidence: Evidence[] };
export type Card = { id: number; doc_id: number; front: string; back: string; evidence: Evidence[]; due_at: string; version: number; edited: boolean };
export type ChatMessage = { id: number; role: "user" | "assistant"; content: string; citations: Evidence[]; mode: string };
export type Dashboard = { documents: number; cards: number; due: number; attempts: number; correct: number };

export async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: "same-origin", ...init });
  if (!response.ok) {
    if (response.status === 401 && !url.endsWith("/login")) window.dispatchEvent(new Event("session-expired"));
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : "입력 내용을 확인해 주세요.";
    throw new Error(body.detail ? detail : `${response.status} ${response.statusText}`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
const json = (body: unknown, method = "POST"): RequestInit => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const api = {
  auth: () => request<{ required: boolean; authenticated: boolean }>("/api/auth"),
  login: (password: string) => request("/api/auth/login", json({ password })),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  health: () => request<{ ok: boolean; llm_provider: string; model: string; retrieval: string }>("/api/health"),
  dashboard: () => request<Dashboard>("/api/dashboard"),
  listDocuments: () => request<Doc[]>("/api/documents"),
  getDocument: (id: number) => request<Doc>(`/api/documents/${id}`),
  getPages: (id: number) => request<Page[]>(`/api/documents/${id}/pages`),
  deleteDocument: (id: number) => request<void>(`/api/documents/${id}`, { method: "DELETE" }),
  retryDocument: (id: number) => request(`/api/documents/${id}/retry`, { method: "POST" }),
  uploadDocument: (file: File) => { const body = new FormData(); body.append("file", file); return request<Doc>("/api/documents", { method: "POST", body }); },
  generation: <T,>(id: number, kind: Kind) => request<Generation<T> | null>(`/api/documents/${id}/generations/${kind}`),
  generate: <T,>(id: number, kind: Kind, options: GenerateOptions = {}) => request<Generation<T>>(`/api/documents/${id}/generate/${kind}`, json(options)),
  cancel: (id: number) => request(`/api/generations/${id}/cancel`, { method: "POST" }),
  questions: (id: number, wrong = false) => request<Question[]>(`/api/documents/${id}/questions?wrong_only=${wrong}`),
  answer: (id: number, answer: string) => request<Grade>(`/api/questions/${id}/answer`, json({ answer })),
  cards: (id?: number, due = false) => request<Card[]>(`/api/cards?due_only=${due}${id ? "&doc_id=" + id : ""}`),
  editCard: (card: Card, front: string, back: string) => request<Card>(`/api/cards/${card.id}`, json({ front, back, version: card.version }, "PATCH")),
  review: (card: Card, rating: number) => request<Card>(`/api/cards/${card.id}/review`, json({ rating, version: card.version })),
  messages: (id: number) => request<ChatMessage[]>(`/api/documents/${id}/messages`),
  pingLLM: () => request<{ result: string }>("/api/llm/ping", { method: "POST" }),
};
export async function chat(id: number, question: string, mode: string, onStatus: (s: string) => void, onMessage: (m: ChatMessage) => void, signal: AbortSignal) {
  const response = await fetch(`/api/documents/${id}/chat`, { ...json({ question, mode }), signal });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "답변을 요청하지 못했습니다.");
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error("스트리밍 응답을 읽을 수 없습니다.");
  const decoder = new TextDecoder();
  let buffer = "", completed = false;
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
        const event = block.split("\n").find(line => line.startsWith("event:"))?.slice(6).trim();
        const payload = block.split("\n").filter(line => line.startsWith("data:")).map(line => line.slice(5).trimStart()).join("\n");
        if (!payload) continue;
        const data = JSON.parse(payload);
        if (event === "error") throw new Error(data.message);
        if (event === "status") onStatus(data.message);
        if (event === "message") { onMessage(data); completed = true; }
      }
      if (done) break;
    }
    if (!completed) throw new Error("연결이 끊겼습니다. 잠시 후 대화 기록을 새로고침해 주세요.");
  } finally { reader.releaseLock(); }
}
