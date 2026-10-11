import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Card, type StudyResult } from "../api";
import { useGeneration } from "../hooks/useGeneration";
import GenerationPanel from "./GenerationPanel";
import PageRefs from "./PageRefs";
function EditableCard({ card, onSaved, onJump }: { card: Card; onSaved: (c: Card) => void; onJump: (p: number) => void }) {
  const [editing, setEditing] = useState(false), [front, setFront] = useState(card.front), [back, setBack] = useState(card.back);
  const [error, setError] = useState(""), [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true); setError("");
    try { onSaved(await api.editCard(card, front, back)); setEditing(false); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <article className="panel space-y-3">
    {editing ? <><label className="block text-sm">앞면<input className="field mt-1 w-full" value={front} onChange={e => setFront(e.target.value)} /></label><label className="block text-sm">뒷면<textarea className="field mt-1 min-h-28 w-full" value={back} onChange={e => setBack(e.target.value)} /></label><div className="flex gap-2"><button className="btn-primary" disabled={busy || !front.trim() || !back.trim()} onClick={() => void save()}>저장</button><button className="btn-secondary" disabled={busy} onClick={() => { setEditing(false); setFront(card.front); setBack(card.back); }}>취소</button></div></> :
      <><div className="flex items-start justify-between gap-4"><h3 className="font-semibold">{card.front}</h3><button className="text-link shrink-0" onClick={() => setEditing(true)}>편집</button></div><p className="whitespace-pre-wrap text-sm leading-7 text-slate-600">{card.back}</p><div className="flex flex-wrap items-center gap-3 text-xs text-slate-500"><PageRefs pages={[...new Set(card.evidence.map(e => e.page))]} onJump={onJump} /><span>다음 복습 {new Date(card.due_at).toLocaleString("ko-KR")}</span>{card.edited && <span>직접 편집한 카드</span>}</div></>}
    {error && <p className="error" role="alert">{error}</p>}
  </article>;
}
export default function CardsView({ docId, onJump }: { docId: number; onJump: (p: number) => void }) {
  const job = useGeneration<StudyResult>(docId, "cards");
  const [cards, setCards] = useState<Card[]>([]), [error, setError] = useState("");
  useEffect(() => { let alive = true; api.cards(docId).then(c => { if (alive) setCards(c); }).catch(e => { if (alive) setError(e.message); }); return () => { alive = false; }; }, [docId, job.generation?.id, job.generation?.status]);
  return <div className="space-y-5">
    <GenerationPanel {...job} title="핵심 개념 플래시카드" onStart={() => void job.start({ force: job.generation?.status === "done" })} onCancel={() => void job.cancel()} />
    <div className="flex items-center justify-between"><p className="text-sm text-slate-500">{cards.length}장의 카드 · 다시 생성해도 편집 내용과 복습 기록은 유지됩니다.</p><Link className="btn-primary" to={`/review?doc=${docId}`}>복습하기</Link></div>
    {job.generation?.data && <p className="muted">이번에 {job.generation.data.kept}장 추가 · 검증 제외 {job.generation.data.rejected}개</p>}
    {error && <p className="error" role="alert">{error}</p>}
    {cards.map(card => <EditableCard key={card.id} card={card} onJump={onJump} onSaved={saved => setCards(previous => previous.map(c => c.id === saved.id ? saved : c))} />)}
    {!cards.length && <div className="empty">원문에서 기억할 개념을 카드로 만들어 보세요.</div>}
  </div>;
}
