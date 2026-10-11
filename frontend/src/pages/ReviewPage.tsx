import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type Card } from "../api";
export default function ReviewPage() {
  const [params] = useSearchParams(); const docId = Number(params.get("doc")) || undefined;
  const [cards, setCards] = useState<Card[]>([]), [revealed, setRevealed] = useState(false);
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [reviewed, setReviewed] = useState(0), [nextDue, setNextDue] = useState("");
  useEffect(() => { let alive = true; setLoading(true); api.cards(docId, true).then(c => { if (alive) { setCards(c); setRevealed(false); setReviewed(0); } }).catch(e => { if (alive) setError(e.message); }).finally(() => { if (alive) setLoading(false); }); return () => { alive = false; }; }, [docId]);
  const card = cards[0];
  async function rate(rating: number) {
    if (!card || busy) return; setBusy(true); setError("");
    try { const updated = await api.review(card, rating); setNextDue(new Date(updated.due_at).toLocaleString("ko-KR")); setCards(previous => previous.filter(c => c.id !== card.id)); setRevealed(false); setReviewed(n => n + 1); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <div className="mx-auto max-w-2xl space-y-6">
    <div><p className="eyebrow">SPACED REPETITION</p><h1 className="mt-3 text-3xl font-bold">조금씩, 오래 기억하기.</h1><p className="muted mt-3">완료 {reviewed}장 · 남은 카드 {cards.length}장</p></div>
    {error && <p className="error" role="alert">{error}</p>}
    {loading ? <div className="panel">복습할 카드를 불러오는 중…</div> : card ? <section className="panel space-y-6 text-center">
      <p className="eyebrow">먼저 답을 떠올려 보세요</p><h2 className="py-8 text-xl font-semibold leading-relaxed">{card.front}</h2>
      {revealed ? <><p className="border-t border-slate-100 pt-6 text-left text-base leading-8 whitespace-pre-wrap">{card.back}</p><Link className="text-link inline-block" to={`/documents/${card.doc_id}?page=${card.evidence[0]?.page || 1}`}>원문에서 확인 →</Link><div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{["다시", "어려움", "보통", "쉬움"].map((label, i) => <button className={i === 2 ? "btn-primary" : "btn-secondary"} key={label} disabled={busy} onClick={() => void rate(i + 1)}>{label}</button>)}</div><p className="text-xs text-slate-400">기억한 정도에 따라 다음 복습 시간이 조정됩니다.</p></> : <button className="btn-primary w-full" onClick={() => setRevealed(true)}>답 보기</button>}
    </section> : <section className="panel py-12 text-center"><span className="text-4xl text-teal-700">✓</span><h2 className="mt-5 text-xl font-semibold">{reviewed ? "이번 복습을 마쳤어요." : "지금 복습할 카드가 없어요."}</h2><p className="muted mt-3">{reviewed ? `${reviewed}장의 기억을 한 번 더 다졌습니다.` : "자료에서 카드를 생성하거나 다음 복습 시간에 돌아오세요."}</p><Link to="/" className="btn-primary mt-6 inline-flex">자료실로 돌아가기</Link></section>}
    {nextDue && <p className="muted text-center" aria-live="polite">방금 카드의 다음 복습: {nextDue}</p>}
  </div>;
}
