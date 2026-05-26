"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { footballData } from "./mock-data";
import { emptyFootballData } from "./empty-data";
import { useMocks } from "./mock-flag";
import type {
  ApiJob,
  ApiVideo,
  ClipSummary,
  FootballData,
  PlayerSummary,
  PlaySummary,
  SelfScoutResponse,
} from "./types";

export type SessionType = "all" | "practice" | "game" | "scrimmage";
export type SideOfBall = "all" | "offense" | "defense" | "special";
export type ApiStatus = "idle" | "loading" | "live" | "offline" | "mock";

const SESSION_LABELS: Record<SessionType, string> = {
  all: "Practice & Games",
  practice: "Practice Only",
  game: "Games Only",
  scrimmage: "Scrimmages",
};

const SIDE_LABELS: Record<SideOfBall, string> = {
  all: "All (Off & Def)",
  offense: "Offense",
  defense: "Defense",
  special: "Special Teams",
};

const POSITION_BY_SIDE: Record<SideOfBall, string[] | null> = {
  all: null,
  offense: ["QB", "RB", "WR", "TE", "OL", "C", "G", "T"],
  defense: ["DL", "DE", "DT", "LB", "MLB", "OLB", "CB", "S", "FS", "SS", "DB"],
  special: ["K", "P", "LS", "RET"],
};

const STORAGE_KEY = "football_iq_app_state_v1";

export interface UploadedClip {
  id: string;
  filename: string;
  objectUrl?: string;
  sizeBytes: number;
  uploadedAt: string;
}

interface PersistedState {
  sessionType: SessionType;
  sideOfBall: SideOfBall;
  selectedDate: string;
  uploadedNames: string[];
}

interface AppStateValue {
  // Filters
  sessionType: SessionType;
  setSessionType: (v: SessionType) => void;
  sideOfBall: SideOfBall;
  setSideOfBall: (v: SideOfBall) => void;
  selectedDate: string;
  setSelectedDate: (v: string) => void;
  availableDates: string[];

  // Data
  data: FootballData;
  filteredPlayers: PlayerSummary[];
  filteredPlays: PlaySummary[];

  // Connectivity
  apiStatus: ApiStatus;
  mockMode: boolean;

  // Selection
  currentPlayIndex: number;
  setCurrentPlayIndex: (n: number) => void;
  nextPlay: () => void;
  prevPlay: () => void;
  currentPlay: PlaySummary | undefined;

  selectedPlayerId: string;
  setSelectedPlayerId: (id: string) => void;
  selectedPlayer: PlayerSummary | undefined;
  getPlayerById: (id: string) => PlayerSummary | undefined;

  // Upload
  uploads: UploadedClip[];
  addUploads: (files: FileList | File[]) => Promise<UploadedClip[]>;
  removeUpload: (id: string) => void;
}

const AppStateContext = createContext<AppStateValue | null>(null);

function loadPersisted(): PersistedState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PersistedState;
  } catch {
    return null;
  }
}

function savePersisted(state: PersistedState) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* ignore */
  }
}

function todayISO() {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}

function buildDates(uploads: UploadedClip[], videos: ApiVideo[]): string[] {
  const set = new Set<string>();
  set.add(todayISO());
  for (const v of videos) {
    if (v.created_at) set.add(v.created_at.slice(0, 10));
  }
  for (const u of uploads) {
    set.add(u.uploadedAt.slice(0, 10));
  }
  return Array.from(set).sort().reverse();
}

export function AppStateProvider({ children }: { children: React.ReactNode }) {
  const mockMode = useMocks();
  const initialData = mockMode ? footballData : emptyFootballData;

  const persisted = typeof window !== "undefined" ? loadPersisted() : null;

  const [sessionType, setSessionType] = useState<SessionType>(persisted?.sessionType ?? "all");
  const [sideOfBall, setSideOfBall] = useState<SideOfBall>(persisted?.sideOfBall ?? "all");
  const [selectedDate, setSelectedDate] = useState<string>(persisted?.selectedDate ?? todayISO());
  const [uploads, setUploads] = useState<UploadedClip[]>([]);

  const [data, setData] = useState<FootballData>(initialData);
  const [apiStatus, setApiStatus] = useState<ApiStatus>(mockMode ? "mock" : "idle");
  const [currentPlayIndex, setCurrentPlayIndex] = useState(0);
  const [selectedPlayerId, setSelectedPlayerId] = useState<string>(
    initialData.players[0]?.id ?? "",
  );

  // Hydrate uploaded clip names from storage on mount
  useEffect(() => {
    const p = loadPersisted();
    if (p?.uploadedNames?.length) {
      // Rehydrate as metadata-only entries (object URLs don't persist across reloads)
      const rehydrated: UploadedClip[] = p.uploadedNames.map((name, i) => ({
        id: `persist-${i}-${name}`,
        filename: name,
        sizeBytes: 0,
        uploadedAt: new Date().toISOString(),
      }));
      setUploads(rehydrated);
      mergeUploadsIntoData(rehydrated);
    }
  }, []);

  // Persist filters and upload names
  useEffect(() => {
    savePersisted({
      sessionType,
      sideOfBall,
      selectedDate,
      uploadedNames: uploads.map((u) => u.filename),
    });
  }, [sessionType, sideOfBall, selectedDate, uploads]);

  // Fetch live data when the API is configured and we are not in mock mode.
  // Empty responses are accepted as valid live data; failures degrade to offline
  // without silently substituting mock data.
  useEffect(() => {
    if (mockMode) {
      setApiStatus("mock");
      return;
    }
    const baseUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) {
      setApiStatus("offline");
      return;
    }
    let cancelled = false;
    setApiStatus("loading");
    (async () => {
      try {
        const [videosRes, jobsRes, scoutRes] = await Promise.allSettled([
          fetch(`${baseUrl}/api/v1/videos`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`videos ${r.status}`)))),
          fetch(`${baseUrl}/api/v1/jobs`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`jobs ${r.status}`)))),
          fetch(`${baseUrl}/api/v1/self-scout/tendencies`).then((r) =>
            r.ok ? r.json() : Promise.reject(new Error(`self-scout ${r.status}`)),
          ),
        ]);
        if (cancelled) return;
        const anyFulfilled =
          videosRes.status === "fulfilled" ||
          jobsRes.status === "fulfilled" ||
          scoutRes.status === "fulfilled";
        if (!anyFulfilled) {
          setApiStatus("offline");
          return;
        }
        setData((cur) => ({
          ...cur,
          videos: pickArrLive<ApiVideo>(videosRes, cur.videos),
          jobs: pickArrLive<ApiJob>(jobsRes, cur.jobs),
          selfScout: pickObjLive<SelfScoutResponse>(scoutRes, cur.selfScout),
        }));
        setApiStatus("live");
      } catch {
        if (!cancelled) setApiStatus("offline");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mockMode]);

  function mergeUploadsIntoData(newUploads: UploadedClip[]) {
    setData((cur) => {
      const existing = new Set(cur.videos.map((v) => v.filename));
      const additions = newUploads.filter((u) => !existing.has(u.filename));
      if (!additions.length) return cur;

      const newVideos: ApiVideo[] = [
        ...cur.videos,
        ...additions.map((u) => ({
          id: u.id,
          filename: u.filename,
          status: "uploaded",
          duration_seconds: null,
          fps: null,
          width: null,
          height: null,
          created_at: u.uploadedAt,
        })),
      ];

      // Only synthesize fake clips/plays in mock mode. In default mode the
      // upload is a real local file but has not been processed yet, so it
      // contributes nothing to plays/clips until the backend produces them.
      if (!mockMode) {
        return { ...cur, videos: newVideos };
      }

      const newClips: ClipSummary[] = [
        ...cur.clips,
        ...additions.map((u) => ({
          id: `clip-${u.id}`,
          title: u.filename.replace(/\.[^/.]+$/, ""),
          subtitle: "Newly uploaded film",
          duration: "00:12",
          tag: "Upload",
        })),
      ];

      const nextNum = cur.plays.length
        ? Math.max(...cur.plays.map((p) => p.number)) + 1
        : 1;
      const newPlays: PlaySummary[] = [
        ...cur.plays,
        ...additions.map((_, i) => ({
          number: nextNum + i,
          formation: "Trips Right",
          personnel: "11",
          concept: "Uploaded Clip",
          result: "Processed",
          yards: 6,
          confidence: 0.9,
        })),
      ];

      return { ...cur, videos: newVideos, clips: newClips, plays: newPlays };
    });
  }

  const addUploads = useCallback(async (files: FileList | File[]) => {
    const arr = Array.from(files);
    const created: UploadedClip[] = arr.map((f, i) => ({
      id: `up-${Date.now()}-${i}`,
      filename: f.name,
      objectUrl: typeof URL !== "undefined" ? URL.createObjectURL(f) : undefined,
      sizeBytes: f.size,
      uploadedAt: new Date().toISOString(),
    }));
    setUploads((cur) => [...cur, ...created]);
    mergeUploadsIntoData(created);
    return created;
  }, []);

  const removeUpload = useCallback((id: string) => {
    setUploads((cur) => {
      const target = cur.find((u) => u.id === id);
      if (target?.objectUrl) {
        try { URL.revokeObjectURL(target.objectUrl); } catch { /* ignore */ }
      }
      return cur.filter((u) => u.id !== id);
    });
  }, []);

  // Derived: filter plays/players by side of ball
  const filteredPlayers = useMemo(() => {
    const allowed = POSITION_BY_SIDE[sideOfBall];
    if (!allowed) return data.players;
    return data.players.filter((p) => allowed.includes(p.position));
  }, [data.players, sideOfBall]);

  const filteredPlays = useMemo(() => {
    if (sideOfBall === "all") return data.plays;
    const offenseConcepts = ["Zone", "Duo", "Mesh", "Stick", "Boot", "PA", "Pass", "Run", "Inside", "Outside", "Custom"];
    if (sideOfBall === "offense") {
      return data.plays.filter((p) => offenseConcepts.some((c) => p.concept.includes(c)));
    }
    if (sideOfBall === "defense") {
      return data.plays.filter((p) => /cover|blitz|stunt/i.test(p.concept));
    }
    return data.plays.filter((p) => /punt|kick|return|FG/i.test(p.concept));
  }, [data.plays, sideOfBall]);

  // Keep currentPlayIndex in range when filteredPlays changes
  useEffect(() => {
    if (filteredPlays.length === 0) {
      setCurrentPlayIndex(0);
    } else if (currentPlayIndex >= filteredPlays.length) {
      setCurrentPlayIndex(filteredPlays.length - 1);
    }
  }, [filteredPlays.length, currentPlayIndex]);

  const currentPlay = filteredPlays[currentPlayIndex];

  const nextPlay = useCallback(() => {
    setCurrentPlayIndex((i) =>
      filteredPlays.length ? (i + 1) % filteredPlays.length : 0,
    );
  }, [filteredPlays.length]);

  const prevPlay = useCallback(() => {
    setCurrentPlayIndex((i) =>
      filteredPlays.length ? (i - 1 + filteredPlays.length) % filteredPlays.length : 0,
    );
  }, [filteredPlays.length]);

  const getPlayerById = useCallback(
    (id: string) => data.players.find((p) => p.id === id || p.jersey === id),
    [data.players],
  );

  const selectedPlayer = useMemo(() => {
    return (
      getPlayerById(selectedPlayerId) ??
      filteredPlayers[0] ??
      data.players[0]
    );
  }, [getPlayerById, selectedPlayerId, filteredPlayers, data.players]);

  const availableDates = useMemo(
    () => buildDates(uploads, data.videos),
    [uploads, data.videos],
  );

  const value: AppStateValue = {
    sessionType,
    setSessionType,
    sideOfBall,
    setSideOfBall,
    selectedDate,
    setSelectedDate,
    availableDates,
    data,
    filteredPlayers,
    filteredPlays,
    apiStatus,
    mockMode,
    currentPlayIndex,
    setCurrentPlayIndex,
    nextPlay,
    prevPlay,
    currentPlay,
    selectedPlayerId,
    setSelectedPlayerId,
    selectedPlayer,
    getPlayerById,
    uploads,
    addUploads,
    removeUpload,
  };

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState(): AppStateValue {
  const ctx = useContext(AppStateContext);
  if (!ctx) {
    throw new Error("useAppState must be used inside <AppStateProvider>");
  }
  return ctx;
}

export { SESSION_LABELS, SIDE_LABELS };

// Returns the API value as-is on success (including empty arrays — empty is
// valid live data, not a signal to substitute mock). Falls back only on a
// rejection or a non-array payload.
function pickArrLive<T>(r: PromiseSettledResult<unknown>, fallback: T[]): T[] {
  if (r.status === "fulfilled" && Array.isArray(r.value)) {
    return r.value as T[];
  }
  return fallback;
}

function pickObjLive<T>(r: PromiseSettledResult<unknown>, fallback: T): T {
  if (r.status === "fulfilled" && r.value && typeof r.value === "object") {
    return r.value as T;
  }
  return fallback;
}
