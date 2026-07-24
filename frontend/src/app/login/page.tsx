"use client";

/**
 * Sign-in / first-run registration page.
 *
 * The very first account registered against a fresh backend becomes the
 * admin (server-side rule), so this page doubles as the bootstrap flow.
 * Static-export compatible: pure client-side rendering, no route handlers.
 */

import Image from "next/image";
import { useRouter } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";

import { useAuth } from "@/lib/auth";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

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
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <Image
            src="/brand/toledo-rocket.png"
            width={184}
            height={78}
            alt="Toledo Rockets"
            className="h-16 w-auto object-contain"
            priority
          />
          <h1 className="mt-4 font-display text-3xl font-semibold uppercase tracking-wide text-foreground">
            Football-IQ
          </h1>
          <p className="mt-1 font-display text-sm font-medium uppercase tracking-[0.14em] text-primary">
            See more. Coach smarter. Win together.
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Toledo Rockets film intelligence
          </p>
        </div>

        <Card>
          <CardContent>
            <form onSubmit={onSubmit} aria-label="Sign in" className="flex flex-col gap-4">
              <Tabs
                value={mode}
                onValueChange={(v) => {
                  setMode(v as "login" | "register");
                  setError(null);
                }}
              >
                <TabsList className="w-full">
                  <TabsTrigger value="login" className="flex-1">
                    Sign in
                  </TabsTrigger>
                  <TabsTrigger value="register" className="flex-1">
                    Create account
                  </TabsTrigger>
                </TabsList>
              </Tabs>

              {mode === "register" ? (
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="auth-full-name">Full name</Label>
                  <Input
                    id="auth-full-name"
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    autoComplete="name"
                    placeholder="Coach Smith"
                  />
                </div>
              ) : null}

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="auth-email">Email</Label>
                <Input
                  id="auth-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                  placeholder="you@utoledo.edu"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="auth-password">Password</Label>
                <Input
                  id="auth-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={mode === "login" ? "current-password" : "new-password"}
                  required
                  minLength={8}
                />
              </div>

              {error ? (
                <Alert variant="destructive" role="alert">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              ) : null}

              <Button type="submit" disabled={busy} className="w-full font-semibold">
                {busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
              </Button>

              {mode === "register" ? (
                <p className="text-xs leading-relaxed text-muted-foreground">
                  The first account on a new installation becomes the administrator;
                  later accounts start as viewers until an admin grants a role.
                </p>
              ) : null}
            </form>
          </CardContent>
        </Card>
      </div>
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
