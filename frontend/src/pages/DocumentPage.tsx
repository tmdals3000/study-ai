import { lazy, Suspense, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, type Doc, type FigureResult, type Page, type Summary } from "../api";
import SummaryView from "../components/SummaryView";
import GenerationPanel from "../components/GenerationPanel";
import QuizView from "../components/QuizView";
import CardsView from "../components/CardsView";
import TutorView from "../components/TutorView";
import { useGeneration } from "../hooks/useGeneration";
const MindmapView = lazy(() => import("../components/MindmapView"));
const TABS = ["원문", "요약", "마인드맵", "퀴즈", "플래시카드", "튜터"] as const;
export default function DocumentRoute() {
  const id = Number(useParams().id);
  return <DocumentPage key={id} id={id} />;
}
function DocumentPage({ id }: { id: number }) {
  const [doc, setDoc] = useState<Doc | null>(null), [pages, setPages] = useState<Page[]>([]);
  const [params, setParams] = useSearchParams();
  const [current, setCurrent] = useState(Number(params.get("page")) || 1);
  const initialTab = params.get("tab");
  const [tab, setTab] = useState<string>(initialTab && TABS.includes(initialTab as typeof TABS[number]) ? initialTab : "원문");
  const [error, setError] = useState("");
  const job = useGeneration<Summary>(id, "summary");
  const figures = useGeneration<FigureResult>(id, "figures");
  const [showText, setShowText] = useState(true);
  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const [d, p] = await Promise.all([api.getDocument(id), api.getPages(id)]);
        if (alive) { setDoc(d); setPages(p); setError(""); setCurrent(c => Math.max(1, Math.min(c, d.pages || 1))); }
      } catch (e) { if (alive) setError((e as Error).message); }
    }
    void load();
    const timer = setInterval(() => { if (doc?.status === "processing") void load(); }, 2000);
    return () => { alive = false; clearInterval(timer); };
  }, [id, doc?.status]);
  // 그림 판독이 끝나면 페이지(판독 결과 포함)를 다시 불러온다
  useEffect(() => {
    if (figures.generation?.status === "done") api.getPages(id).then(setPages).catch(() => {});
  }, [id, figures.generation?.id, figures.generation?.status]);
  function changeTab(next: string) { setTab(next); setParams({ tab: next, page: String(current) }, { replace: true }); }
  function jumpTo(n: number) { setCurrent(n); setTab("원문"); setParams({ tab: "원문", page: String(n) }, { replace: true }); window.scrollTo({ top: 0, behavior: "smooth" }); }
  if (!doc) return <div className="panel">{error ? <p className="error">{error}</p> : <p className="muted">자료를 불러오는 중…</p>}<Link to="/" className="text-link mt-4 inline-block">자료실로 돌아가기</Link></div>;
  const page = pages.find(p => p.page_no === current), summary = job.generation?.data;
  return <div className="space-y-6">
    <Link to="/" className="text-link">← 내 자료실</Link>
    <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="eyebrow">DOCUMENT WORKSPACE</p><h1 className="mt-2 break-words text-2xl font-bold tracking-tight sm:text-3xl">{doc.title}</h1><p className="muted mt-2">{doc.pages}페이지 · 원문을 근거로 공부하는 공간</p></div><a className="btn-secondary" target="_blank" rel="noreferrer" href={`/api/documents/${id}/file#page=${current}`}>PDF 원본 열기 ↗</a></div>
    {error && <p className="error" role="alert">{error}</p>}
    {doc.status !== "ready" && <div className="panel">{doc.status === "processing" ? "PDF를 처리 중입니다…" : doc.error}</div>}
    <nav aria-label="문서 학습 메뉴" className="flex gap-1 overflow-x-auto border-b border-slate-200">
      {TABS.map(t => <button key={t} disabled={doc.status !== "ready" && t !== "원문"} onClick={() => changeTab(t)} aria-current={tab === t ? "page" : undefined} className={`shrink-0 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${tab === t ? "border-teal-700 text-teal-800" : "border-transparent text-slate-500 hover:text-slate-900"}`}>{t}</button>)}
    </nav>
    {tab === "원문" && <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-3"><button className="btn-secondary" aria-label="이전 페이지" disabled={current <= 1} onClick={() => setCurrent(current - 1)}>←</button><label className="flex items-center gap-2 text-sm"><span className="sr-only">페이지 번호</span><input className="field w-20 text-center" type="number" min={1} max={doc.pages || 1} value={current} onChange={e => setCurrent(Math.max(1, Math.min(Number(e.target.value) || 1, doc.pages || 1)))} /><span>/ {doc.pages}페이지</span></label><button className="btn-secondary" aria-label="다음 페이지" disabled={current >= doc.pages} onClick={() => setCurrent(current + 1)}>→</button></div>
      {doc.status === "ready" && <img key={current} src={`/api/documents/${id}/pages/${current}/image`} alt={`${current}페이지 원본`} loading="lazy" className="w-full rounded-2xl border border-slate-200 bg-white" />}
      {page?.figure_text && <div className="panel border-amber-200 bg-amber-50/40">
        <p className="text-sm font-semibold text-amber-900">그림에서 읽은 내용</p>
        <p className="mt-1 text-xs text-amber-800">AI가 이 페이지의 그림을 읽고, 이미지와 다시 대조해 확인된 항목만 남겼습니다. 위 원본과 비교해 확인할 수 있어요.</p>
        <p className="mt-3 whitespace-pre-wrap text-sm leading-7">{page.figure_text}</p>
      </div>}
      <button className="text-link" onClick={() => setShowText(v => !v)}>{showText ? "추출된 텍스트 숨기기" : "추출된 텍스트 보기"}</button>
      {showText && <article className="panel min-h-40 whitespace-pre-wrap text-sm leading-8">{page?.text.trim() || <span className="muted">추출된 텍스트가 없습니다. 이미지로 된 PDF라면 OCR 설정 후 다시 처리해 주세요.</span>}</article>}
      {doc.status === "ready" && <GenerationPanel {...figures} title="그림 내용 읽기"
        onStart={() => void figures.start({ force: figures.generation?.status === "done" })} onCancel={() => void figures.cancel()} />}
      {figures.generation?.data && <p className="muted">그림이 있는 {figures.generation.data.pages}페이지를 확인해 {figures.generation.data.pages_with_figures}페이지에서 내용을 읽었습니다 · 판독 {figures.generation.data.generated}개 중 이미지 대조를 통과한 {figures.generation.data.kept}개만 저장. 이후 생성하는 요약·퀴즈·카드·튜터가 이 내용을 근거로 사용합니다.</p>}
    </section>}
    {(tab === "요약" || tab === "마인드맵") && <div className="space-y-5">
      <GenerationPanel {...job} title="요약과 마인드맵" onStart={() => void job.start({ force: job.generation?.status === "done" })} onCancel={() => void job.cancel()} />
      {summary && (tab === "요약" ? <SummaryView summary={summary} onJump={jumpTo} /> : <Suspense fallback={<p className="muted">마인드맵을 불러오는 중…</p>}><MindmapView markdown={summary.mindmap} /></Suspense>)}
      {!summary && !job.running && <div className="empty">한 줄 요약, 핵심 개념, 구간별 노트와 시험 포인트를 한곳에 정리합니다.</div>}
    </div>}
    {tab === "퀴즈" && <QuizView docId={id} onJump={jumpTo} />}
    {tab === "플래시카드" && <CardsView docId={id} onJump={jumpTo} />}
    {tab === "튜터" && <TutorView docId={id} onJump={jumpTo} />}
  </div>;
}
