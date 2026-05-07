export default function Home() {
  return (
    <main
      style={{
        fontFamily: "system-ui, -apple-system, sans-serif",
        background: "#0a0a0a",
        color: "#ffffff",
        minHeight: "100vh",
        padding: "0",
        margin: "0",
      }}
    >
      {/* Header */}
      <header
        style={{
          background: "#111",
          borderBottom: "1px solid #222",
          padding: "0 2rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          height: "60px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <span style={{ fontSize: "1.5rem" }}>🏈</span>
          <span style={{ fontWeight: 700, fontSize: "1.15rem", letterSpacing: "-0.01em" }}>
            Football-IQ
          </span>
        </div>
        <nav style={{ display: "flex", gap: "1.5rem", fontSize: "0.9rem", color: "#aaa" }}>
          <a href="#videos" style={{ color: "#aaa", textDecoration: "none" }}>
            Videos
          </a>
          <a href="#clips" style={{ color: "#aaa", textDecoration: "none" }}>
            Clips
          </a>
          <a href="#tracking" style={{ color: "#aaa", textDecoration: "none" }}>
            Tracking
          </a>
          <a href="#jobs" style={{ color: "#aaa", textDecoration: "none" }}>
            Jobs
          </a>
        </nav>
      </header>

      {/* Hero */}
      <section
        style={{
          padding: "4rem 2rem 3rem",
          maxWidth: "1200px",
          margin: "0 auto",
        }}
      >
        <h1
          style={{
            fontSize: "clamp(1.8rem, 4vw, 3rem)",
            fontWeight: 800,
            letterSpacing: "-0.03em",
            marginBottom: "1rem",
            background: "linear-gradient(135deg, #fff 60%, #888)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
          }}
        >
          Toledo Football
          <br />
          Computer Vision Platform
        </h1>
        <p style={{ color: "#777", fontSize: "1.1rem", maxWidth: "520px", lineHeight: 1.6 }}>
          Phase 1 MVP — video ingestion, play segmentation, field calibration, player detection
          &amp; tracking for practice film analysis.
        </p>
      </section>

      {/* Feature grid */}
      <section
        id="features"
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          padding: "0 2rem 4rem",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
          gap: "1rem",
        }}
      >
        {[
          {
            icon: "📤",
            title: "Video Ingestion",
            status: "ready",
            desc: "Upload practice film directly to Cloudflare R2. Track processing status in real time.",
          },
          {
            icon: "✂️",
            title: "Play Segmentation",
            status: "ready",
            desc: "System proposes per-play boundaries on continuous film. Coaches can edit with one click.",
          },
          {
            icon: "📐",
            title: "Field Calibration",
            status: "ready",
            desc: "Homography maps pixels → yard-line coordinates. Metrics are suppressed when confidence is low.",
          },
          {
            icon: "👤",
            title: "Player Detection",
            status: "ready",
            desc: "Bounding boxes and team-level tracks per frame via YOLO; full identity resolution in progress.",
          },
          {
            icon: "📍",
            title: "Player Tracking",
            status: "ready",
            desc: "Tracklets with frame ranges, XY coordinates, and per-track confidence score.",
          },
          {
            icon: "🔗",
            title: "Clip-Linked Metrics",
            status: "ready",
            desc: "Every metric links directly to its source clip — evidence always within 2 clicks.",
          },
          {
            icon: "✏️",
            title: "Coach Correction UI",
            status: "ready",
            desc: "Staff correct boundaries, tags, and player identities. Corrections become training labels.",
          },
          {
            icon: "🔖",
            title: "Model Versioning",
            status: "ready",
            desc: "Every output records model version, calibration version, and job ID for full lineage.",
          },
          {
            icon: "🔍",
            title: "Job Observability",
            status: "ready",
            desc: "Failed jobs show error reason, stage, input file, and a one-click retry option.",
          },
          {
            icon: "🔐",
            title: "Role-Based Access",
            status: "ready",
            desc: "Coaches, analysts, sports performance, and admins have separate, enforced permissions.",
          },
        ].map((f) => (
          <div
            key={f.title}
            style={{
              background: "#141414",
              border: "1px solid #222",
              borderRadius: "12px",
              padding: "1.5rem",
              transition: "border-color 0.2s",
            }}
          >
            <div
              style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem" }}
            >
              <span style={{ fontSize: "1.5rem" }}>{f.icon}</span>
              <span style={{ fontWeight: 600, fontSize: "0.95rem" }}>{f.title}</span>
              <span
                style={{
                  marginLeft: "auto",
                  fontSize: "0.7rem",
                  padding: "2px 8px",
                  borderRadius: "99px",
                  background: f.status === "ready" ? "#14532d" : "#1e3a5f",
                  color: f.status === "ready" ? "#86efac" : "#93c5fd",
                }}
              >
                {f.status === "ready" ? "✓ MVP" : "planned"}
              </span>
            </div>
            <p style={{ color: "#777", fontSize: "0.85rem", lineHeight: 1.55, margin: 0 }}>{f.desc}</p>
          </div>
        ))}
      </section>

      {/* API endpoints summary */}
      <section
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          padding: "0 2rem 4rem",
        }}
      >
        <h2
          style={{
            fontSize: "1.25rem",
            fontWeight: 700,
            marginBottom: "1rem",
            color: "#ddd",
          }}
        >
          REST API — Phase 1 Endpoints
        </h2>
        <div
          style={{
            background: "#111",
            border: "1px solid #222",
            borderRadius: "12px",
            padding: "1.5rem",
            fontSize: "0.82rem",
            fontFamily: "monospace",
            lineHeight: 2,
            color: "#aaa",
          }}
        >
          {[
            "POST   /api/v1/auth/register         → create account",
            "POST   /api/v1/auth/login            → JWT access + refresh tokens",
            "POST   /api/v1/auth/refresh          → exchange refresh token",
            "GET    /api/v1/videos                → list videos (auth)",
            "POST   /api/v1/videos                → register uploaded video",
            "GET    /api/v1/videos/{id}           → video details + status",
            "PATCH  /api/v1/videos/{id}/status    → update processing status",
            "GET    /api/v1/videos/{id}/jobs      → jobs for a video",
            "GET    /api/v1/videos/{id}/clips     → clips for a video",
            "POST   /api/v1/videos/{id}/clips     → propose play boundary",
            "GET    /api/v1/clips/{id}            → clip details",
            "PATCH  /api/v1/clips/{id}            → coach boundary correction",
            "GET    /api/v1/clips/{id}/metrics    → metrics with evidence link",
            "GET    /api/v1/clips/{id}/tracklets  → tracklet list",
            "POST   /api/v1/tracklets             → store tracking output",
            "GET    /api/v1/tracklets/{id}        → tracklet + track points",
            "POST   /api/v1/calibrations          → store calibration result",
            "GET    /api/v1/videos/{id}/calibrations → video calibrations",
            "GET    /api/v1/jobs                  → list jobs (filterable)",
            "POST   /api/v1/jobs                  → submit processing job",
            "GET    /api/v1/jobs/{id}             → job details + error info",
            "PATCH  /api/v1/jobs/{id}             → GPU worker status callback",
            "POST   /api/v1/jobs/{id}/retry       → retry failed job",
            "POST   /api/v1/corrections           → coach correction",
            "GET    /api/v1/corrections           → list corrections",
            "POST   /api/v1/corrections/export    → export labels for training",
          ].map((line) => (
            <div key={line} style={{ color: line.startsWith("POST") ? "#86efac" : line.startsWith("PATCH") ? "#fde68a" : "#93c5fd" }}>
              {line}
            </div>
          ))}
        </div>
      </section>

      <footer
        style={{
          borderTop: "1px solid #1a1a1a",
          padding: "1.5rem 2rem",
          textAlign: "center",
          color: "#444",
          fontSize: "0.8rem",
        }}
      >
        Football-IQ — Phase 1 MVP — Toledo Football Computer Vision Platform
      </footer>
    </main>
  );
}
