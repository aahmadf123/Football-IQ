"use client";

/**
 * Sign-in / first-run registration page.
 *
 * The very first account registered against a fresh backend becomes the
 * admin (server-side rule), so this page doubles as the bootstrap flow.
 * Static-export compatible: pure client-side rendering, no route handlers.
 */

import { useRouter } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";

import { useAuth } from "@/lib/auth";

function LoginForm() {
  const router = useRouter();
  const { token, ready, authRequired, login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (ready && (token || !authRequired)) router.replace("/");
  }, [ready, token, authRequired, router]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, fullName || email.split("@")[0]);
      }
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-screen">
      <form className="auth-card" onSubmit={onSubmit} aria-label="Sign in">
        <div className="auth-brand">
          <span className="auth-brand-mark">FIQ</span>
          <div>
            <h1 className="auth-title">Football-IQ</h1>
            <p className="auth-subtitle">Toledo Rockets film intelligence</p>
          </div>
        </div>

        <div className="auth-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "login"}
            className={mode === "login" ? "auth-tab active" : "auth-tab"}
            onClick={() => setMode("login")}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "register"}
            className={mode === "register" ? "auth-tab active" : "auth-tab"}
            onClick={() => setMode("register")}
          >
            Create account
          </button>
        </div>

        {mode === "register" ? (
          <label className="auth-field">
            <span>Full name</span>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              autoComplete="name"
              placeholder="Coach Smith"
            />
          </label>
        ) : null}

        <label className="auth-field">
          <span>Email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
            placeholder="you@utoledo.edu"
          />
        </label>

        <label className="auth-field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            required
            minLength={8}
          />
        </label>

        {error ? (
          <p className="auth-error" role="alert">
            {error}
          </p>
        ) : null}

        <button className="auth-submit" type="submit" disabled={busy}>
          {busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
        </button>

        {mode === "register" ? (
          <p className="auth-hint">
            The first account on a new installation becomes the administrator;
            later accounts start as viewers until an admin grants a role.
          </p>
        ) : null}
      </form>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
