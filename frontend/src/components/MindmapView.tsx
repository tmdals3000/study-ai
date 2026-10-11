import { Transformer } from "markmap-lib";
import { Markmap } from "markmap-view";
import { useEffect, useRef, useState } from "react";
const transformer = new Transformer([]);
transformer.md.set({ html: false, linkify: false });
export default function MindmapView({ markdown }: { markdown: string }) {
  const svg = useRef<SVGSVGElement>(null), instance = useRef<Markmap | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!svg.current) return;
    let alive = true;
    const map = Markmap.create(svg.current, { duration: 0 });
    instance.current = map;
    const { root } = transformer.transform(markdown);
    map.setData(root).then(() => { if (alive) return map.fit(); }).catch(e => { if (alive) setError(e.message); });
    const observer = new ResizeObserver(() => { if (alive) void map.fit(); });
    observer.observe(svg.current);
    return () => { alive = false; observer.disconnect(); map.destroy(); if (instance.current === map) instance.current = null; };
  }, [markdown]);
  function download() {
    const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "mindmap.md"; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <div className="space-y-3">
    <div className="flex justify-end gap-2"><button className="btn-secondary" onClick={() => void instance.current?.fit()}>화면에 맞추기</button><button className="btn-secondary" onClick={download}>마크다운 저장</button></div>
    {error && <p className="error">{error}</p>}
    <svg ref={svg} role="img" aria-label="문서 핵심 개념 마인드맵" className="h-[65vh] min-h-80 w-full rounded-2xl border border-slate-200 bg-white" />
    <p className="muted">가지를 클릭해 접고 펼치고, 확대하거나 드래그해 살펴보세요.</p>
  </div>;
}
