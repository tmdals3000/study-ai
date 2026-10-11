import { useEffect, useRef, useState } from "react";
import { api, chat, type ChatMessage } from "../api";
import PageRefs from "./PageRefs";
export default function TutorView({ docId, onJump }: { docId: number; onJump: (n: number) => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]), [question, setQuestion] = useState(""), [mode, setMode] = useState("explain");
  const [busy, setBusy] = useState(false), [status, setStatus] = useState(""), [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { let alive = true; api.messages(docId).then(m => { if (alive) setMessages(m); }).catch(e => { if (alive) setError(e.message); }); return () => { alive = false; controller.current?.abort(); }; }, [docId]);
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [messages, busy]);
  async function send(e: React.FormEvent) {
    e.preventDefault(); if (!question.trim() || busy) return;
    const text = question.trim(); setQuestion(""); setBusy(true); setError(""); setStatus("원문을 찾는 중…");
    setMessages(previous => [...previous, { id: -Date.now(), role: "user", content: text, citations: [], mode }]);
    controller.current = new AbortController();
    try {
      await chat(docId, text, mode, setStatus, message => setMessages(previous => [...previous, message]), controller.current.signal);
      setMessages(await api.messages(docId));
    } catch (e) {
      if ((e as Error).name !== "AbortError") { setError((e as Error).message); setQuestion(text); api.messages(docId).then(setMessages).catch(() => {}); }
    } finally { setBusy(false); setStatus(""); }
  }
  return <section className="panel space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="font-semibold">문서와 함께 생각하기</h3><p className="muted mt-1">출처 검증을 마친 답변과 페이지를 함께 보여드립니다.</p></div><label className="text-sm"><span className="sr-only">튜터 모드</span><select className="field" value={mode} disabled={busy} onChange={e => setMode(e.target.value)}><option value="explain">개념 설명</option><option value="socratic">질문으로 생각하기</option></select></label></div>
    <div className="max-h-[55vh] min-h-48 space-y-4 overflow-y-auto pr-1" aria-live="polite">
      {!messages.length && <div className="empty border-0">어려운 개념이나 비교하고 싶은 내용을 질문해 보세요.</div>}
      {messages.map(m => <article key={m.id} className={`rounded-2xl p-4 text-sm leading-7 ${m.role === "user" ? "ml-8 bg-teal-50" : "mr-4 bg-slate-50"}`}><p className="mb-1 text-xs font-semibold text-slate-500">{m.role === "user" ? "나" : "학습 튜터"}</p><p className="whitespace-pre-wrap">{m.content}</p>{!!m.citations.length && <details className="mt-3"><summary className="cursor-pointer text-xs text-teal-700">출처 확인</summary>{m.citations.map((c, i) => <p key={i} className="mt-2 border-l-2 border-teal-200 pl-3"><PageRefs pages={[c.page]} onJump={onJump} /> {c.figure && <span className="rounded bg-amber-100 px-1 text-xs text-amber-800">그림</span>} {c.quote}</p>)}</details>}</article>)}
      {busy && <p className="muted animate-pulse">{status}</p>}<div ref={end} />
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    <form onSubmit={send} className="flex items-end gap-2"><textarea aria-label="튜터에게 질문" className="field min-h-20 flex-1 resize-y" placeholder="예: 이 문서에서 설명하는 핵심 원리는 무엇인가요?" value={question} maxLength={3000} onChange={e => setQuestion(e.target.value)} disabled={busy} /><button className="btn-primary" disabled={busy || !question.trim()}>{busy ? "답변 중…" : "질문하기"}</button></form>
  </section>;
}
