"use client";

/**
 * Zero-shot concept search box (Issue #144).
 *
 * Lets a coach type a football concept ("mesh", "cover 3 trips", "jet sweep")
 * and surfaces matching reps from the existing library — no labelling and no
 * Toledo-specific fine-tuning required. The backend grounds the query against
 * structured labels and, when a play-embedding model is promoted, expands it
 * with similar reps from pgvector (Issue #8).
 *
 * Honesty rules (matching the backend contract):
 *   • every result set is marked APPROXIMATE (zero-shot concept→label mapping);
 *   • embedding-expansion rows are additionally marked EXPERIMENTAL;
 *   • in mock mode we never fabricate results — we say search needs a backend.
 */

import { useState } from "react";
import { searchConcepts } from "@/lib/api";
import { useAppState } from "@/lib/app-state";
import type { ConceptSearchResponse } from "@/lib/types";
import { ExperimentalBadge } from "./experimental-badge";

type SearchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "mock" }
  | { kind: "done"; response: ConceptSearchResponse };

function shortId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}

function summarizeLabels(labelData: Record<string, unknown> | null): string | null {
  if (!labelData) return null;
  const parts: string[] = [];
  for (const key of ["formation", "coverage"]) {
    const node = labelData[key];
    if (node && typeof node === "object" && "generic" in (node as Record<string, unknown>)) {
      const generic = (node as Record<string, unknown>).generic;
      if (typeof generic === "string") parts.push(generic);
    }
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

export function ConceptSearch() {
  const { authToken, mockMode } = useAppState();
  const [query, setQuery] = useState("");
  const [state, setState] = useState<SearchState>({ kind: "idle" });

  async function runSearch(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    if (mockMode) {
      // Never display mock data as a real search result.
      setState({ kind: "mock" });
      return;
    }
    setState({ kind: "loading" });
    try {
      const response = await searchConcepts(q, { k: 20 }, authToken);
      setState({ kind: "done", response });
    } catch (err) {
      setState({ kind: "error", message: err instanceof Error ? err.message : "Search failed" });
    }
  }

  return (
    <section className="panel panel-pad span-12" data-testid="concept-search">
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <h2 className="panel-title">Concept search</h2>
        <ExperimentalBadge label="Approximate" />
      </div>
      <p className="kicker" style={{ marginTop: 4 }}>
        Ask for a concept in plain football — “mesh”, “cover 3 trips”, “jet sweep”,
        “play action boot”. Results are zero-shot and approximate until validated
        on corrected Toledo clips.
      </p>

      <form
        onSubmit={runSearch}
        style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}
      >
        <label className="form-control" style={{ flex: "1 1 240px" }}>
          <span className="small-label">Concept query</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. cover 3 trips"
            aria-label="Concept search query"
          />
        </label>
        <button
          className="control-button primary"
          type="submit"
          style={{ alignSelf: "flex-end" }}
        >
          Search
        </button>
      </form>

      {state.kind === "loading" && (
        <p className="kicker" style={{ marginTop: 12 }}>
          Searching…
        </p>
      )}

      {state.kind === "mock" && (
        <p className="kicker" style={{ marginTop: 12 }}>
          Concept search needs a live backend connection — it is disabled in mock
          mode so demo data is never shown as a real result.
        </p>
      )}

      {state.kind === "error" && (
        <p
          className="kicker"
          style={{ marginTop: 12, color: "var(--accent-red, #f87171)" }}
          data-testid="concept-search-error"
        >
          {state.message}
        </p>
      )}

      {state.kind === "done" && <Results response={state.response} />}
    </section>
  );
}

function Results({ response }: { response: ConceptSearchResponse }) {
  return (
    <div style={{ marginTop: 12 }} data-testid="concept-search-results">
      {response.matched_concepts.length > 0 && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
          {response.matched_concepts.map((m) => (
            <span
              key={m.concept_id}
              className="chip"
              style={{
                display: "inline-flex",
                alignItems: "center",
                padding: "2px 10px",
                borderRadius: 999,
                background: "var(--navy-900, #1b2740)",
                color: "var(--text, #f2f5fb)",
                fontSize: "0.72rem",
                fontWeight: 600,
              }}
            >
              {m.display_name}
            </span>
          ))}
        </div>
      )}

      {response.experimental && (
        <p className="kicker" style={{ marginBottom: 8 }}>
          Includes <strong>experimental</strong> embedding matches — reps that look
          similar but are not yet labelled with this concept.
        </p>
      )}

      {response.results.length === 0 ? (
        <p className="kicker">{response.reason ?? "No matching reps yet."}</p>
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {response.results.map((r) => {
            const labels = summarizeLabels(r.label_data);
            return (
              <li
                key={`${r.clip_id}-${r.source}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "8px 0",
                  borderBottom: "1px solid var(--navy-900, #1b2740)",
                  flexWrap: "wrap",
                }}
              >
                <code style={{ fontSize: "0.78rem" }}>{shortId(r.clip_id)}</code>
                {labels && (
                  <span className="kicker" style={{ margin: 0 }}>
                    {labels}
                  </span>
                )}
                <span
                  className="small-label"
                  style={{ marginLeft: "auto" }}
                  title={`source: ${r.source}`}
                >
                  {r.source} · {(r.confidence * 100).toFixed(0)}%
                </span>
                {r.is_experimental && <ExperimentalBadge />}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
