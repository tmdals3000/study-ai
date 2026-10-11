import type { Point, Summary } from "../api";
import PageRefs from "./PageRefs";

type Props = { summary: Summary; onJump: (page: number) => void };

function PointCard({ point, onJump }: { point: Point; onJump: (page: number) => void }) {
  return (
    <div className="rounded-lg border p-4">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="rounded bg-slate-100 px-1.5 text-xs text-slate-600">{point.kind}</span>
        <h4 className="font-semibold">{point.heading}</h4>
        <PageRefs pages={point.pages} onJump={onJump} />
        {point.corrected && (
          <span className="text-xs text-amber-700" title="검증 단계에서 원문 근거가 없는 문장을 삭제했습니다">
            일부 문장 삭제됨
          </span>
        )}
      </div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed">{point.content}</p>
      <details className="mt-2 text-xs text-slate-500">
        <summary className="cursor-pointer select-none">원문 근거 {point.evidence.length}개</summary>
        <ul className="mt-1 space-y-1">
          {point.evidence.map((e, i) => (
            <li key={i} className="border-l-2 border-slate-200 pl-2">
              <button onClick={() => onJump(e.page)} className="mr-1 text-indigo-600 hover:underline">
                p.{e.page}
              </button>
              “{e.quote}”
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

export default function SummaryView({ summary, onJump }: Props) {
  const { stats } = summary;
  return (
    <div className="space-y-6">
      {summary.one_line && (
        <section className="rounded-xl bg-indigo-50 p-4">
          <p className="font-medium">{summary.one_line.text}</p>
          <PageRefs pages={summary.one_line.pages} onJump={onJump} />
        </section>
      )}

      {summary.key_concepts.length > 0 && (
        <section>
          <h3 className="mb-2 text-lg font-semibold">핵심 개념</h3>
          <ul className="space-y-2">
            {summary.key_concepts.map((c, i) => (
              <li key={i} className="rounded-lg border bg-white p-3 text-sm">
                <span className="font-semibold">{c.name}</span> <PageRefs pages={c.pages} onJump={onJump} />
                <p className="mt-1 text-slate-700">{c.description}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {summary.exam_points.length > 0 && (
        <section>
          <h3 className="mb-2 text-lg font-semibold">시험 포인트</h3>
          <ul className="list-disc space-y-1 rounded-lg border bg-white py-3 pl-8 pr-3 text-sm">
            {summary.exam_points.map((e, i) => (
              <li key={i}>
                {e.text} <PageRefs pages={e.pages} onJump={onJump} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h3 className="mb-2 text-lg font-semibold">구간별 학습 노트</h3>
        {stats.kept === 0 && <p className="empty">검증 기준을 통과한 노트가 없습니다. 원문 추출 상태를 확인해 주세요.</p>}
        <div className="space-y-5">
          {summary.sections
            .filter((s) => s.points.length > 0)
            .map((s, i) => (
              <div key={i} className="rounded-xl border bg-white p-4">
                <h4 className="mb-3 font-bold">
                  {s.title} <span className="text-sm font-normal text-slate-500">p.{s.pages[0]}–{s.pages[1]}</span>
                </h4>
                <div className="space-y-3">
                  {s.points.map((p) => (
                    <PointCard key={p.id} point={p} onJump={onJump} />
                  ))}
                </div>
              </div>
            ))}
        </div>
      </section>

      <p className="text-xs text-slate-500">
        원문 대조 검증: 생성 {stats.generated}개 중 {stats.kept}개 통과
        {stats.no_evidence > 0 && ` · 인용 불일치로 ${stats.no_evidence}개 제외`}
        {stats.unsupported > 0 && ` · 근거 부족으로 ${stats.unsupported}개 제외`}
        {stats.corrected > 0 && ` · ${stats.corrected}개는 근거 없는 문장 삭제`}
      </p>
    </div>
  );
}
