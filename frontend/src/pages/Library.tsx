import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Dashboard, type Doc } from "../api";
const STATUS = { processing: "처리 중", ready: "학습 준비됨", error: "다시 확인 필요" };
export default function Library() {
  const [docs, setDocs] = useState<Doc[]>([]), [stats, setStats] = useState<Dashboard | null>(null);
  const [error, setError] = useState(""), [uploading, setUploading] = useState(false), [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState(""), [ping, setPing] = useState(""), [pinging, setPinging] = useState(false);
  const input = useRef<HTMLInputElement>(null), uploadLock = useRef(false);
  const load = useCallback(async () => {
    try { const [d, s] = await Promise.all([api.listDocuments(), api.dashboard()]); setDocs(d); setStats(s); setError(""); }
    catch (e) { setError((e as Error).message); } finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (!docs.some(d => d.status === "processing")) return; const timer = setInterval(() => void load(), 2000); return () => clearInterval(timer); }, [docs, load]);
  async function upload(files: FileList | null) {
    if (!files?.length || uploadLock.current) return;
    uploadLock.current = true; setUploading(true); setError("");
    const errors: string[] = [];
    for (const file of Array.from(files)) {
      try { await api.uploadDocument(file); } catch (e) { errors.push(`${file.name}: ${(e as Error).message}`); }
    }
    await load(); if (errors.length) setError(errors.join("\n"));
    setUploading(false); uploadLock.current = false; if (input.current) input.current.value = "";
  }
  async function remove(doc: Doc) {
    if (!confirm(`“${doc.title}”과 이 문서의 학습·복습 기록을 삭제할까요?`)) return;
    try { await api.deleteDocument(doc.id); await load(); } catch (e) { setError((e as Error).message); }
  }
  async function retry(doc: Doc) {
    try { await api.retryDocument(doc.id); await load(); } catch (e) { setError((e as Error).message); }
  }
  async function pingLLM() {
    setPinging(true); setPing("");
    try { setPing((await api.pingLLM()).result); } catch (e) { setPing((e as Error).message); } finally { setPinging(false); }
  }
  const shown = docs.filter(d => d.title.toLowerCase().includes(filter.toLowerCase()));
  return <div className="space-y-8">
    <section className="flex flex-wrap items-end justify-between gap-5"><div><p className="eyebrow">YOUR PERSONAL STUDY SPACE</p><h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-4xl">읽은 것을, 내 지식으로.</h1><p className="mt-3 text-sm leading-7 text-slate-500">강의 자료를 정리하고, 풀어 보고, 다시 기억하세요.</p></div><Link to="/review" className="btn-primary">오늘의 복습 시작 →</Link></section>
    <section className="grid grid-cols-3 gap-3" aria-label="학습 현황">{[["내 자료", stats?.documents ?? "—", "개"], ["지금 복습할 카드", stats?.due ?? "—", "장"], ["풀어 본 문제", stats?.attempts ?? "—", "회"]].map(([label, n, unit]) => <div className="panel" key={label}><p className="text-xs text-slate-500 sm:text-sm">{label}</p><p className="mt-3 text-2xl font-semibold sm:text-3xl">{n}<span className="ml-1 text-xs font-normal text-slate-400">{unit}</span></p></div>)}</section>
    <label className={`flex cursor-pointer flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-teal-200 bg-teal-50/40 px-5 py-9 text-center transition-colors hover:bg-teal-50 ${uploading ? "pointer-events-none opacity-60" : ""}`} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); void upload(e.dataTransfer.files); }}>
      <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-white text-2xl text-teal-700" aria-hidden="true">↑</span>
      <span className="font-semibold">{uploading ? "자료를 업로드하는 중…" : "공부할 PDF를 여기에 놓아주세요"}</span>
      <span className="text-xs text-slate-500">또는 클릭해서 선택 · 여러 파일 업로드 가능</span>
      <input aria-label="PDF 업로드" ref={input} type="file" accept=".pdf,application/pdf" multiple disabled={uploading} className="sr-only" onChange={e => void upload(e.target.files)} />
    </label>
    {error && <div className="error whitespace-pre-wrap" role="alert">{error}<button className="ml-3 underline" onClick={() => void load()}>새로고침</button></div>}
    <section className="space-y-4"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold">내 자료실 <span className="ml-1 text-slate-400">{docs.length}</span></h2><input aria-label="자료 검색" className="field w-full sm:w-56" placeholder="자료 이름으로 검색" value={filter} onChange={e => setFilter(e.target.value)} /></div>
      {loading ? <p className="muted">자료를 불러오는 중…</p> : !shown.length ? <div className="empty">{filter ? "검색 결과가 없습니다." : "첫 강의 자료를 올리고 학습을 시작해 보세요."}</div> : <div className="grid gap-3 sm:grid-cols-2">{shown.map(doc => <article className="panel flex flex-col justify-between gap-5" key={doc.id}>
        <div className="flex items-start gap-3"><span className="rounded-lg bg-slate-100 px-2 py-3 text-xs font-bold text-slate-500">PDF</span><div className="min-w-0"><h3 className="break-words font-semibold">{doc.status === "ready" ? <Link to={`/documents/${doc.id}`} className="hover:text-teal-700">{doc.title}</Link> : doc.title}</h3><p className="mt-2 text-xs text-slate-500">{STATUS[doc.status]}{doc.status === "ready" && ` · ${doc.pages}페이지`}</p>{doc.error && <p className="mt-2 break-words text-xs text-rose-700">{doc.error}</p>}</div></div>
        <div className="flex items-center justify-between border-t border-slate-100 pt-3">{doc.status === "ready" ? <Link className="text-link" to={`/documents/${doc.id}`}>학습 열기 →</Link> : doc.status === "error" ? <button className="text-link" onClick={() => void retry(doc)}>다시 처리</button> : <span className="muted">텍스트를 추출 중입니다…</span>}<button className="text-xs text-slate-400 hover:text-rose-600 disabled:opacity-40" disabled={doc.status === "processing"} onClick={() => void remove(doc)} aria-label={`${doc.title} 삭제`}>삭제</button></div>
      </article>)}</div>}
    </section>
    <details className="panel text-sm"><summary className="cursor-pointer font-medium text-slate-600">연결 확인과 백업</summary><div className="mt-4 flex flex-wrap gap-3"><button className="btn-secondary" disabled={pinging} onClick={() => void pingLLM()}>{pinging ? "연결 확인 중…" : "AI 연결 확인"}</button><a className="btn-secondary" href="/api/backup" download>자료·학습 기록 백업</a></div>{ping && <p className="mt-3 whitespace-pre-wrap text-slate-600">{ping}</p>}</details>
  </div>;
}
