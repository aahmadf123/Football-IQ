"use client";

import { useEffect, useState } from "react";
import { footballData } from "./mock-data";
import type { ApiJob, ApiVideo, FootballData, SelfScoutResponse, PlaySummary } from "./types";

type DataSource = "fallback" | "api";

export function useFootballIqData() {
  const [data, setData] = useState<FootballData>(footballData);
  const [source, setSource] = useState<DataSource>("fallback");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load dynamically added clips from localStorage
  useEffect(() => {
    try {
      const stored = localStorage.getItem("football_iq_custom_clips");
      if (stored) {
        const customNames = JSON.parse(stored) as string[];
        if (customNames && customNames.length > 0) {
          integrateCustomClips(customNames);
        }
      }
    } catch (e) {
      console.error(e);
    }
  }, []);

  const integrateCustomClips = (names: string[]) => {
    setData((current) => {
      // Avoid duplicate integration
      const filteredNames = names.filter(
        name => !current.videos.some(v => v.filename === name)
      );
      if (filteredNames.length === 0) return current;

      const newVideos = [
        ...current.videos,
        ...filteredNames.map((name, i) => ({
          id: `custom-v-${Date.now()}-${i}`,
          filename: name,
          status: "ready",
          duration_seconds: 12,
          fps: 60,
          width: 1920,
          height: 1080,
          created_at: new Date().toISOString()
        }))
      ];

      const newClips = [
        ...current.clips,
        ...filteredNames.map((name, i) => ({
          id: `custom-clip-${Date.now()}-${i}`,
          title: name.replace(/\.[^/.]+$/, ""),
          subtitle: "Newly uploaded play film",
          duration: "00:12",
          tag: "Upload"
        }))
      ];

      // Add a play item for each custom uploaded clip so total count of plays increases
      const nextPlayNumber = current.plays.length > 0 
        ? Math.max(...current.plays.map(p => p.number)) + 1 
        : 1;

      const newPlays: PlaySummary[] = [
        ...current.plays,
        ...filteredNames.map((name, i) => ({
          number: nextPlayNumber + i,
          formation: "Trips Right",
          personnel: "11",
          concept: "Custom Pass/Run",
          result: "Processed",
          yards: 6,
          confidence: 0.95
        }))
      ];

      return {
        ...current,
        videos: newVideos,
        clips: newClips,
        plays: newPlays
      };
    });
  };

  const refresh = (newUploadedFileName?: string) => {
    if (newUploadedFileName) {
      try {
        const stored = localStorage.getItem("football_iq_custom_clips");
        const currentList = stored ? JSON.parse(stored) as string[] : [];
        if (!currentList.includes(newUploadedFileName)) {
          currentList.push(newUploadedFileName);
          localStorage.setItem("football_iq_custom_clips", JSON.stringify(currentList));
        }
        integrateCustomClips([newUploadedFileName]);
      } catch (e) {
        console.error(e);
      }
    }
  };

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

        setData((current) => {
          const apiVideos = valueOrFallback(videos, current.videos);
          const apiJobs = valueOrFallback(jobs, current.jobs);
          const apiSelfScout = valueOrFallback(selfScout, current.selfScout);
          
          return {
            ...current,
            videos: apiVideos,
            jobs: apiJobs,
            selfScout: apiSelfScout,
          };
        });
        setSource("api");
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "API unavailable");
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

  return { data, source, loading, error, refresh };
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
