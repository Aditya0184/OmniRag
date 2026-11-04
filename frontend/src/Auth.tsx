import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import App from "./App";
import { request, setCsrfToken } from "./api";

type Session = { enabled: boolean; authenticated: boolean; configured?: boolean; csrf?: string };

export default function Auth() {
  const [session, setSession] = useState<Session | null>(null);
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [changing, setChanging] = useState(false);

  async function refresh() {
    try {
      const state = await request<Session>("/auth/session");
      setCsrfToken(state.csrf || "");
      setSession(state);
      setError("");
    } catch (e) { setError((e as Error).message); }
  }
  useEffect(() => {
    void refresh();
    const expire = () => { setCsrfToken(""); setSession({ enabled: true, authenticated: false, configured: true }); };
    window.addEventListener("omnirag-session-expired", expire);
    return () => window.removeEventListener("omnirag-session-expired", expire);
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await request(changing ? "/auth/password" : "/auth/login", {
        method: "POST", headers: { "Content-Type": "application/json", "X-OmniRAG-Login": "1" },
        body: JSON.stringify(changing ? { current_password: password, new_password: newPassword } : { password }),
      });
      setPassword(""); setNewPassword(""); setChanging(false); await refresh();
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function logout() {
    try { await request("/auth/logout", { method: "POST" }); await refresh(); }
    catch (e) { setError((e as Error).message); }
  }

  if (session?.authenticated && !changing) return <>
    {session.enabled && <div className="account-bar">
      <span>Private Mac workspace</span>
      <button onClick={() => { setError(""); setChanging(true); }}>Change password</button>
      <button onClick={() => void logout()}>Sign out</button>
      {error && <span role="alert">{error}</span>}
    </div>}
    <App authenticated={session.enabled} />
  </>;

  return <main className="auth-page"><form className="auth-card" onSubmit={submit}>
    <p className="eyebrow">OMNIRAG · PRIVATE WORKSPACE</p>
    <h1>{changing ? "Change your password" : "Sign in to your documents"}</h1>
    {!session ? <p>Connecting to your Mac…</p> : session.configured === false ?
      <p>The owner account has not been configured. Run the local owner setup command from the project README.</p> : <>
        <label htmlFor="owner-password">{changing ? "Current password" : "Password"}</label>
        <input id="owner-password" type="password" autoComplete="current-password" required maxLength={128}
          value={password} onChange={e => setPassword(e.target.value)} autoFocus />
        {changing && <><label htmlFor="new-password">New password (at least 15 characters)</label>
          <input id="new-password" type="password" autoComplete="new-password" required minLength={15} maxLength={128}
            value={newPassword} onChange={e => setNewPassword(e.target.value)} /></>}
        <button type="submit" disabled={busy}>{busy ? "Please wait…" : changing ? "Save password and sign out" : "Sign in"}</button>
        {changing && <button type="button" onClick={() => { setChanging(false); setPassword(""); setNewPassword(""); }}>Cancel</button>}
      </>}
    {error && <p role="alert">{error}</p>}
    {!session && error && <button type="button" onClick={() => void refresh()}>Retry connection</button>}
    <small>Your documents stay on this Mac.</small>
  </form></main>;
}
