export default function MobileBlock() {
  return (
    <div className="card">
      <h2 style={{ marginBottom: "0.75rem" }}>Desktop required</h2>
      <p style={{ color: "var(--muted)", lineHeight: 1.6 }}>
        Please use a desktop or laptop for the interview. Mobile devices and
        tablets are not supported for proctored sessions — this matches
        industry-standard interview platforms that require a stable webcam,
        keyboard, and fullscreen experience.
      </p>
    </div>
  );
}
