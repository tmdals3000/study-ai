import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { api } from "./api";
import "./index.css";
import DocumentPage from "./pages/DocumentPage";
import Library from "./pages/Library";
import ReviewPage from "./pages/ReviewPage";
function App() {
  const [session, setSession] = useState<{ required: boolean; authenticated: boolean } | null>(null);
  const [password, setPassword] = useState(""), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const [online, setOnline] = useState(navigator.onLine);
  async function refreshAuth() { try { setSession(await api.auth()); setError(""); } catch (e) { setError((e as Error).message); } }
  useEffect(() => {
    void refreshAuth();
    const expire = () => setSession({ required: true, authenticated: false });
    const connection = () => setOnline(navigator.onLine);
    window.addEventListener("session-expired", expire); window.addEventListener("online", connection); window.addEventListener("offline", connection);
    return () => { window.removeEventListener("session-expired", expire); window.removeEventListener("online", connection); window.removeEventListener("offline", connection); };
  }, []);
  async function login(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try { await api.login(password); setPassword(""); await refreshAuth(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  if (!session) return <div className="mx-auto mt-20 max-w-md px-5"><div className="panel"><h1 className="text-xl font-semibold">Study AI</h1><p className="muted mt-3">{error || "학습 공간을 여는 중…"}</p>{error && <button className="btn-primary mt-4" onClick={() => void refreshAuth()}>다시 연결</button>}</div></div>;
  if (!session.authenticated) return <div className="mx-auto mt-20 max-w-md px-5"><form className="panel space-y-5" onSubmit={login}><p className="eyebrow">PRIVATE STUDY SPACE</p><h1 className="text-2xl font-bold">내 학습 공간에 로그인</h1><label className="block text-sm">비밀번호<input autoFocus autoComplete="current-password" type="password" className="field mt-2 w-full" value={password} onChange={e => setPassword(e.target.value)} /></label>{error && <p className="error" role="alert">{error}</p>}<button className="btn-primary w-full" disabled={busy || !password}>{busy ? "확인 중…" : "로그인"}</button></form></div>;
  return <BrowserRouter>
    <header className="border-b border-slate-200/70 bg-white"><div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-5 sm:px-8"><NavLink to="/" className="flex items-center gap-3"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-teal-800 text-lg font-bold text-white">S</span><span className="font-bold tracking-tight">Study AI</span></NavLink><nav className="flex items-center gap-5 text-sm" aria-label="메인 메뉴"><NavLink to="/" end className={({ isActive }) => isActive ? "font-semibold text-teal-800" : "text-slate-500"}>자료실</NavLink><NavLink to="/review" className={({ isActive }) => isActive ? "font-semibold text-teal-800" : "text-slate-500"}>카드 복습</NavLink>{session.required && <button className="text-xs text-slate-500" onClick={() => api.logout().then(refreshAuth).catch(e => setError(e.message))}>로그아웃</button>}</nav></div></header>
    {!online && <div className="bg-amber-50 p-3 text-center text-sm text-amber-900">오프라인 상태입니다. 학습 자료를 불러오려면 실행 중인 PC에 연결해 주세요.</div>}
    <main className="mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-10"><Routes><Route path="/" element={<Library />} /><Route path="/documents/:id" element={<DocumentPage />} /><Route path="/review" element={<ReviewPage />} /><Route path="*" element={<div className="empty">페이지를 찾을 수 없습니다. <a className="text-link" href="/">자료실로 이동</a></div>} /></Routes></main>
    <footer className="mx-auto max-w-6xl px-5 pb-8 pt-4 text-xs text-slate-400 sm:px-8">Study AI · 자료와 학습 기록은 내 PC에 저장됩니다.</footer>
  </BrowserRouter>;
}
createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
if (import.meta.env.PROD && "serviceWorker" in navigator) window.addEventListener("load", () => { navigator.serviceWorker.register("/sw.js").catch(() => {}); });
