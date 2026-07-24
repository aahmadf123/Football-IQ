"use client";

/**
 * Shared film-upload widget (previously duplicated between the page shell and
 * the Film Room hub).
 *
 * `useUploadWidget()` returns:
 *   - `openFilePicker` — hand this to any "Upload Film" button
 *   - `widget`         — render once near the top of the page; it contains the
 *                        hidden `<input type="file">` and the status toast
 *
 * Uploads flow through `useAppState().addUploads` (Worker upload-url → R2 PUT
 * → backend register), so this widget is purely the trigger + feedback shell.
 */

import { useRef, useState } from "react";
import { useAppState } from "@/lib/app-state";

export function useUploadWidget(options?: {
  successMessage?: (count: number) => string;
}): { openFilePicker: () => void; widget: React.ReactNode } {
  const { addUploads } = useAppState();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);

  const openFilePicker = () => fileInputRef.current?.click();

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    try {
      const created = await addUploads(files);
      setUploadStatus(
        options?.successMessage?.(created.length) ??
          `Uploaded ${created.length} clip${created.length === 1 ? "" : "s"} — track processing in Film Room → Upload / Process Film.`,
      );
      setTimeout(() => setUploadStatus(null), 5000);
    } catch (err) {
      setUploadStatus(`Upload failed: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      // Reset input so the same file can be re-selected.
      event.target.value = "";
    }
  };

  const widget = (
    <>
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept="video/*"
        multiple
        style={{ display: "none" }}
      />
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
    </>
  );

  return { openFilePicker, widget };
}
