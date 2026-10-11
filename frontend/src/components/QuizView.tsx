import { useEffect, useState } from "react";
import { api, type Grade, type Question, type StudyResult } from "../api";
import { useGeneration } from "../hooks/useGeneration";
import GenerationPanel from "./GenerationPanel";
import PageRefs from "./PageRefs";
const TYPES = { multiple: "객관식", ox: "OX", short: "단답형" } as const;
export default function QuizView({ docId, onJump }: { docId: number; onJump: (n: number) => void }) {
  const job = useGeneration<StudyResult>(docId, "quiz");
  const [questions, setQuestions] = useState<Question[]>([]);
  const [wrong, setWrong] = useState(false);
  const [count, setCount] = useState(20);
  const [types, setTypes] = useState<string[]>(["multiple", "ox", "short"]);
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [grades, setGrades] = useState<Record<number, Grade>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true; setLoading(true);
    api.questions(docId, wrong).then(rows => { if (alive) { setQuestions(rows); setIndex(0); setAnswers({}); setGrades({}); setError(""); } })
      .catch(e => { if (alive) setError(e.message); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [docId, wrong, job.generation?.id, job.generation?.status]);
  const q = questions[index], grade = q ? grades[q.id] : undefined;
  async function submit() {
    if (!q || !answers[q.id]?.trim()) return;
    setBusy(true); setError("");
    try { const result = await api.answer(q.id, answers[q.id]); setGrades(previous => ({ ...previous, [q.id]: result })); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="space-y-5">
    <div className="panel flex flex-wrap items-center gap-4 text-sm">
      <label>문제 수 <input aria-label="문제 수" type="number" min={1} max={40} value={count} onChange={e => setCount(Number(e.target.value))} className="field ml-2 w-20" /></label>
      {Object.entries(TYPES).map(([value, label]) => <label key={value} className="flex items-center gap-2"><input type="checkbox" checked={types.includes(value)} onChange={e => setTypes(e.target.checked ? [...types, value] : types.filter(t => t !== value))} />{label}</label>)}
    </div>
    <GenerationPanel {...job} title="원문 기반 퀴즈" onCancel={() => void job.cancel()} onStart={() => {
      if (!types.length || count < 1 || count > 40) { setError("문제 유형과 1~40개의 문제 수를 선택해 주세요."); return; }
      void job.start({ count, types, force: job.generation?.status === "done", wrong_only: wrong });
    }} />
    {job.generation?.data && <p className="text-sm text-slate-500">요청 {job.generation.data.requested}개 · 저장 {job.generation.data.kept}개 · 검증 제외 {job.generation.data.rejected}개. {job.generation.data.note}</p>}
    <div className="flex flex-wrap items-center justify-between gap-3">
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={wrong} onChange={e => setWrong(e.target.checked)} />오답만 다시 풀기</label>
      <span className="text-sm text-slate-500">이번 풀이 {Object.keys(grades).length}/{questions.length} · 정답 {Object.values(grades).filter(g => g.correct).length}개</span>
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {loading ? <p className="muted">문제를 불러오는 중…</p> : q ? <section className="panel space-y-5">
      <div className="flex justify-between text-sm text-slate-500"><span>{TYPES[q.type]} · {q.concept}</span><span>{index + 1} / {questions.length}</span></div>
      <h3 className="text-lg font-semibold leading-relaxed">{q.question}</h3>
      <fieldset disabled={busy || !!grade} className="space-y-2">
        <legend className="sr-only">답 선택</legend>
        {q.type === "short" ? <input className="field w-full" aria-label="단답형 답" placeholder="답을 입력하세요" value={answers[q.id] || ""} onChange={e => setAnswers({ ...answers, [q.id]: e.target.value })} onKeyDown={e => { if (e.key === "Enter") void submit(); }} /> :
          q.choices.map((choice, i) => <label key={i} className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 ${answers[q.id] === choice ? "border-teal-500 bg-teal-50" : "border-slate-200"}`}><input type="radio" name={`question-${q.id}`} value={choice} checked={answers[q.id] === choice} onChange={() => setAnswers({ ...answers, [q.id]: choice })} className="mt-1" /><span>{choice}</span></label>)}
      </fieldset>
      {grade ? <div className={`rounded-xl p-4 ${grade.correct ? "bg-teal-50" : "bg-amber-50"}`} aria-live="polite">
        <p className="font-semibold">{grade.correct ? "정답입니다" : "다시 기억해 볼 내용"}</p>
        <p className="mt-2 text-sm">정답: {grade.answer}</p><p className="mt-2 whitespace-pre-wrap text-sm leading-7">{grade.feedback}</p>
        <PageRefs pages={[...new Set(grade.evidence.map(e => e.page))]} onJump={onJump} />
      </div> : <button className="btn-primary" disabled={busy || !answers[q.id]?.trim()} onClick={() => void submit()}>{busy ? "채점 중…" : "정답 확인"}</button>}
      <div className="flex justify-between border-t border-slate-100 pt-4"><button className="btn-secondary" disabled={index === 0 || busy} onClick={() => setIndex(index - 1)}>이전 문제</button><button className="btn-secondary" disabled={index >= questions.length - 1 || busy} onClick={() => setIndex(index + 1)}>다음 문제</button></div>
    </section> : <div className="empty">{wrong ? "복습할 오답이 없습니다." : "퀴즈를 생성하면 이곳에서 바로 풀 수 있어요."}</div>}
  </div>;
}
