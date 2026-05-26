"use client";

import { useEffect, useState } from "react";
import { footballData } from "./mock-data";
import type { ApiJob, ApiVideo, FootballData, SelfScoutResponse } from "./types";

type DataSource = "fallback" | "api";

export function useFootballIqData() {
  const [data, setData] = useState<FootballData>(footballData);
  const [source, setSource] = useState<DataSource>("fallback");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    async function load() {
      try {
        const [videos, jobs, selfScout] = await Promise.allSettled([
          apiGet<ApiVideo[]>("/api/v1/videos"),
          apiGet<ApiJob[]>("/api/v1/jobs"),
          apiGet<SelfScoutResponse>("/api/v1/self-scout/tendencies"),
        ]);

        if (cancelled) return;

        setData({
          ...footballData,
          videos: valueOrFallback(videos, footballData.videos),
          jobs: valueOrFallback(jobs, footballData.jobs),
          selfScout: valueOrFallback(selfScout, footballData.selfScout),
        });
        setSource("api");
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "API unavailable");
          setData(footballData);
          setSource("fallback");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return { data, source, loading, error };
}

async function apiGet<T>(path: string): Promise<T> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? "";
  const response = await fetch(`${baseUrl}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return (await response.json()) as T;
}

function valueOrFallback<T>(result: PromiseSettledResult<T>, fallback: T): T {
  if (result.status === "fulfilled") {
    if (Array.isArray(result.value) && result.value.length === 0) return fallback;
    return result.value;
  }
  return fallback;
}
