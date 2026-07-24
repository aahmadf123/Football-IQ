"use client";

/**
 * Reports (extracted from the old page-renderer monolith).
 *
 * Backend-wired end to end: create report jobs (POST /api/v1/reports), poll
 * their status, and fetch signed download URLs. The old faux "report preview"
 * mock-up was reduced to an honest summary of the selected sections/format.
 */

import { Download, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAppState } from "@/lib/app-state";
import {
  createReport,
  getReport,
  getReportDownloadUrl,
  listReports,
} from "@/lib/api";
import { useUploadWidget } from "@/components/shared/upload-widget";
import type { ReportFormat, ReportJob } from "@/lib/types";

const REPORT_SECTIONS: readonly string[] = [
  "Self-scout exposure",
  "Position group development",
  "Model quality",
  "Opponent prep package",
] as const;

const REPORT_POLL_INTERVAL_MS = 2000;
const REPORT_POLL_TIMEOUT_MS = 120_000;

export function ReportsView() {
  const { authToken } = useAppState();
  const { openFilePicker, widget } = useUploadWidget();
  const [selections, setSelections] = useState<Record<string, boolean>>({});
  const [format, setFormat] = useState<ReportFormat>("pdf");
  const [reports, setReports] = useState<ReportJob[]>([]);
  const [listStatus, setListStatus] = useState<"idle" | "loading" | "error">("idle");
  const [listError, setListError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const pollHandles = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());

  const refreshList = useCallback(async () => {
    if (!authToken) {
      setReports([]);
      setListStatus("idle");
      setListError(null);
      return;
    }
    setListStatus("loading");
    setListError(null);
    try {
      const items = await listReports(authToken);
      setReports(items);
      setListStatus("idle");
    } catch (err) {
      setListError(err instanceof Error ? err.message : String(err));
      setListStatus("error");
    }
  }, [authToken]);

  useEffect(() => {
    void refreshList();
  }, [refreshList]);

  // Clean up outstanding polls on unmount.
  useEffect(() => {
    const handles = pollHandles.current;
    return () => {
      handles.forEach((h) => clearTimeout(h));
      handles.clear();
    };
  }, []);

  const pollReport = useCallback(
    (reportId: string) => {
      if (!authToken) return;
      const start = Date.now();
      const tick = async () => {
        try {
          const job = await getReport(reportId, authToken);
          setReports((cur) => cur.map((r) => (r.id === reportId ? job : r)));
          if (job.status === "succeeded" || job.status === "failed" || job.status === "cancelled") {
            return;
          }
          if (Date.now() - start > REPORT_POLL_TIMEOUT_MS) return;
          const h = setTimeout(() => {
            pollHandles.current.delete(h);
            void tick();
          }, REPORT_POLL_INTERVAL_MS);
          pollHandles.current.add(h);
        } catch {
          // On a transient error, stop polling — the user can refresh manually.
        }
      };
      void tick();
    },
    [authToken],
  );

  const handleGenerate = async () => {
    if (!authToken) {
      setGenerateError("You must be signed in to generate a report.");
      return;
    }
    const picked = REPORT_SECTIONS.filter((s) => selections[s] !== false);
    if (picked.length === 0) {
      setGenerateError("Select at least one section to include.");
      return;
    }
    setGenerating(true);
    setGenerateError(null);
    try {
      const job = await createReport(
        { report_type: "coaching_summary", format, sections: [...picked] },
        authToken,
      );
      setReports((cur) => [job, ...cur]);
      pollReport(job.id);
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : String(err));
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = async (reportId: string) => {
    if (!authToken) return;
    setDownloadingId(reportId);
    try {
      const { download_url } = await getReportDownloadUrl(reportId, authToken);
      window.location.href = download_url;
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : String(err));
    } finally {
      setDownloadingId(null);
    }
  };

  const pickedSections = REPORT_SECTIONS.filter((s) => selections[s] !== false);

  return (
    <>
      {widget}
      <div className="content-grid">
        <section className="panel panel-pad span-4">
          <h2 className="panel-title">Report Builder</h2>
          {REPORT_SECTIONS.map((label) => (
            <div key={label} className="form-control" style={{ marginTop: 10 }}>
              <label>{label}</label>
              <select
                value={selections[label] === false ? "skip" : "include"}
                onChange={(e) =>
                  setSelections((cur) => ({ ...cur, [label]: e.target.value === "include" }))
                }
              >
                <option value="include">Include in packet</option>
                <option value="skip">Skip this section</option>
              </select>
            </div>
          ))}
          <div className="form-control" style={{ marginTop: 10 }}>
            <label>Format</label>
            <select value={format} onChange={(e) => setFormat(e.target.value as ReportFormat)}>
              <option value="pdf">PDF</option>
              <option value="csv">CSV</option>
              <option value="json">JSON</option>
            </select>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button
              className="control-button primary"
              onClick={handleGenerate}
              disabled={generating || !authToken}
            >
              <Download size={15} /> {generating ? "Requesting…" : "Generate Report"}
            </button>
            <button className="control-button" onClick={openFilePicker}>
              <Upload size={15} /> Add Film
            </button>
          </div>
          {!authToken && (
            <p className="kicker" style={{ marginTop: 8 }}>
              Sign in to generate and download reports.
            </p>
          )}
          {generateError && (
            <p className="kicker" style={{ marginTop: 8, color: "var(--danger, crimson)" }}>
              {generateError}
            </p>
          )}
        </section>
        <section className="panel panel-pad span-4">
          <h2 className="panel-title">Packet Summary</h2>
          <p className="kicker" style={{ marginTop: 10 }}>
            The generated report is built from live database aggregates on the
            backend at request time.
          </p>
          <p className="kicker" style={{ marginTop: 8 }}>
            <strong>Format:</strong> {format.toUpperCase()}
          </p>
          <p className="kicker" style={{ marginTop: 4 }}>
            <strong>Sections selected:</strong>{" "}
            {pickedSections.length > 0 ? pickedSections.join(", ") : "none"}
          </p>
        </section>
        <section className="panel panel-pad span-4">
          <h2 className="panel-title">Export Queue</h2>
          {listStatus === "loading" && (
            <p className="kicker" style={{ marginTop: 12 }}>
              Loading reports…
            </p>
          )}
          {listStatus === "error" && (
            <p className="kicker" style={{ marginTop: 12, color: "var(--danger, crimson)" }}>
              {listError ?? "Failed to load reports."}
            </p>
          )}
          {listStatus === "idle" && reports.length === 0 && (
            <p className="kicker" style={{ marginTop: 12 }}>
              No reports yet — pick sections and click Generate.
            </p>
          )}
          {reports.length > 0 && (
            <div className="list-stack" style={{ marginTop: 12 }}>
              {reports.map((report) => (
                <ReportRow
                  key={report.id}
                  report={report}
                  downloading={downloadingId === report.id}
                  onDownload={() => handleDownload(report.id)}
                />
              ))}
            </div>
          )}
        </section>
      </div>
    </>
  );
}

function ReportRow({
  report,
  downloading,
  onDownload,
}: {
  report: ReportJob;
  downloading: boolean;
  onDownload: () => void;
}) {
  const stamp = new Date(report.created_at).toLocaleString();
  const subtitle =
    report.status === "failed" && report.error_message
      ? `failed: ${report.error_message}`
      : `${report.format.toUpperCase()} · ${stamp}`;
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 8,
        padding: "8px 4px",
        borderBottom: "1px solid var(--line-soft)",
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: "0.85rem" }}>{report.status}</div>
        <div
          className="kicker"
          style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
        >
          {subtitle}
        </div>
      </div>
      {report.status === "succeeded" ? (
        <button className="control-button" onClick={onDownload} disabled={downloading}>
          <Download size={13} /> {downloading ? "…" : "Download"}
        </button>
      ) : (
        <span className="kicker">{report.status === "failed" ? "—" : "in progress"}</span>
      )}
    </div>
  );
}
