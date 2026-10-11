import type { Generation } from "../api";
export default function GenerationPanel({ generation, running, busy, error, title, onStart, onCancel }: {
  generation: Generation<unknown> | null; running: boolean; busy: boolean; error: string; title: string;
  onStart: () => void; onCancel: () => void;
}) {
  return <div className="panel flex flex-wrap items-center justify-between gap-4">
    <div className="min-w-0"><p className="font-semibold">{title}</p>
      <p className="mt-1 text-sm text-slate-500" aria-live="polite">{running ? generation?.progress || "대기 중…" : "원문 근거를 대조한 뒤 결과를 저장합니다."}</p>
      {(error || generation?.error) && <p className="error mt-2" role="alert">{error || generation?.error}</p>}
      {generation?.status === "cancelled" && <p className="mt-1 text-sm text-slate-500">생성이 취소되었습니다.</p>}
      {!!generation?.data && generation.status !== "done" && <p className="mt-1 text-xs text-slate-500">아래에는 이전에 완료된 결과를 표시합니다.</p>}
    </div>
    {running ? <button className="btn-secondary" disabled={busy} onClick={onCancel}>생성 취소</button> :
      <button className="btn-primary" disabled={busy} onClick={onStart}>{busy ? "요청 중…" : generation?.status === "done" ? "다시 생성" : "생성하기"}</button>}
  </div>;
}
