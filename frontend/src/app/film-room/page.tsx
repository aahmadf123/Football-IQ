"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { FootballShell } from "@/components/football-shell";
import { LibraryView } from "@/app/library/library-view";
import { ReviewTab } from "@/components/film-room/review-tab";
import { UploadProcessFilm } from "@/components/film-room/upload-process";
import { useUploadWidget } from "@/components/shared/upload-widget";

// "Clips & Highlights" was folded away with the mock clip grid (#96): Browse
// Film is the clip library (real sessions → videos → clips), Review & Tag
// Plays is the per-video clip inventory that deep-links into clip review.
const TABS = [
  { key: "browse", label: "Browse Film" },
  { key: "review", label: "Review & Tag Plays" },
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

  const { openFilePicker: handleUploadClick, widget } = useUploadWidget({
    successMessage: (count) =>
      `Uploaded ${count} clip${count === 1 ? "" : "s"} — track processing in the Upload / Process Film tab.`,
  });

  return (
    <>
      {widget}

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

      {activeTab === "browse" && <LibraryView />}
      {activeTab === "review" && <ReviewTab />}
      {activeTab === "upload" && <UploadProcessFilm onUploadClick={handleUploadClick} />}
    </>
  );
}
