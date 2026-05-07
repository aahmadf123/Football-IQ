export default function Home() {
  return (
    <main
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "100vh",
        fontFamily: "system-ui, sans-serif",
        background: "#0a0a0a",
        color: "#ffffff",
      }}
    >
      <h1 style={{ fontSize: "2.5rem", marginBottom: "0.5rem" }}>
        ⚡ Football-IQ
      </h1>
      <p style={{ color: "#888", fontSize: "1.1rem" }}>
        Toledo Football Computer Vision Platform — coming soon.
      </p>
    </main>
  );
}
