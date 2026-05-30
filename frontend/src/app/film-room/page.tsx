"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useRef, useState } from "react";
import { FootballShell } from "@/components/football-shell";
import { useAppState } from "@/lib/app-state";
import { LibraryView } from "@/app/library/library-view";
import { VideoAndPlays, ClipsHighlights } from "@/components/page-renderer";
import { UploadProcessFilm } from "@/components/film-room/upload-process";

const TABS = [
  { key: "browse", label: "Browse Film" },
  { key: "review", label: "Review & Tag Plays" },
  { key: "clips", label: "Clips & Highlights" },
  { key: "upload", label: "Upload / Process Film" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

function isTabKey(value: string | null): value is TabKey {
  return TABS.some((t) => t.key === value);
}

export default function FilmRoomPage() {
  return (
    <FootballShell activePage="film-room">
      <Suspense
        fallback={
          <section className="panel panel-pad">
            <p className="kicker">Loading Film Room…</p>
          </section>
        }
      >
        <FilmRoomContent />
      </Suspense>
    </FootballShell>
  );
}

function FilmRoomContent() {
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const activeTab: TabKey = isTabKey(tabParam) ? tabParam : "browse";

  const { addUploads } = useAppState();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);

  const handleUploadClick = () => fileInputRef.current?.click();

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    try {
      const created = await addUploads(files);
      setUploadStatus(
        `Uploaded ${created.length} clip${created.length === 1 ? "" : "s"} — open the Upload / Process Film tab to start processing.`,
      );
      setTimeout(() => setUploadStatus(null), 5000);
    } catch (err) {
      setUploadStatus(`Upload failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      event.target.value = "";
    }
  };

  return (
    <>
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept="video/*"
        multiple
        style={{ display: "none" }}
      />

      <nav className="tabs" aria-label="Film Room sections" style={{ marginBottom: 12 }}>
        {TABS.map((tab) => (
          <Link
            key={tab.key}
            href={`/film-room/?tab=${tab.key}`}
            className={`tab-button ${tab.key === activeTab ? "active" : ""}`}
            aria-current={tab.key === activeTab ? "page" : undefined}
            data-testid={`film-room-tab-${tab.key}`}
          >
            {tab.label}
          </Link>
        ))}
      </nav>

      {uploadStatus && (
        <div
          className="upload-toast"
          style={{
            marginBottom: 8,
            padding: "6px 12px",
            borderRadius: 8,
            border: "1px solid var(--line-soft)",
            background: "oklch(0.30 0.10 145 / 0.55)",
            color: "var(--text)",
            fontSize: "0.78rem",
            fontWeight: 700,
          }}
        >
          {uploadStatus}
        </div>
      )}

      {activeTab === "browse" && <LibraryView />}
      {activeTab === "review" && <VideoAndPlays onUploadClick={handleUploadClick} />}
      {activeTab === "clips" && <ClipsHighlights />}
      {activeTab === "upload" && <UploadProcessFilm onUploadClick={handleUploadClick} />}
    </>
  );
}
