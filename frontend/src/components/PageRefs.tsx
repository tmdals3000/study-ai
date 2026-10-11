export default function PageRefs({ pages, onJump }: { pages: number[]; onJump: (page: number) => void }) {
  return (
    <span className="inline-flex flex-wrap gap-1 align-middle">
      {pages.map((p) => (
        <button
          key={p}
          onClick={() => onJump(p)}
          title="원문 페이지로 이동"
          className="rounded bg-indigo-50 px-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-100"
        >
          p.{p}
        </button>
      ))}
    </span>
  );
}
