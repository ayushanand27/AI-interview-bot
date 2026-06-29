import "../recruiter-portal.css";

export default function PrivacyPolicy() {
  return (
    <div className="recruiter-portal">
      <header>
        <h1>Privacy Policy</h1>
        <p>SmartSkale AI Interview Platform — last updated June 2026</p>
      </header>

      <div className="rp-card rp-card-wide rp-card-spacing">
        <section className="privacy-section">
          <h2>Overview</h2>
          <p>
            SmartSkale helps recruiters run AI-assisted technical interviews and
            review candidate performance. This policy describes what data we
            collect, how we use it, and your choices.
          </p>
        </section>

        <section className="privacy-section">
          <h2>Data we collect</h2>
          <ul>
            <li>
              <strong>Account data:</strong> name, email, password (hashed), and
              role (candidate or recruiter).
            </li>
            <li>
              <strong>Interview content:</strong> job descriptions, resume text,
              spoken answers (transcribed), AI-generated questions, and scoring
              feedback.
            </li>
            <li>
              <strong>Proctoring data:</strong> webcam snapshots during the
              interview, identity verification images (ID and selfie when
              provided), and integrity signals such as tab switches or face
              detection events.
            </li>
            <li>
              <strong>Recordings:</strong> optional session recordings when
              enabled by the recruiter.
            </li>
          </ul>
        </section>

        <section className="privacy-section">
          <h2>How we use data</h2>
          <ul>
            <li>Conduct and score interviews using AI models (Groq).</li>
            <li>Generate reports for recruiters and optional candidate summaries.</li>
            <li>Detect proctoring violations and flag sessions for human review.</li>
            <li>Authenticate users and secure the platform.</li>
          </ul>
        </section>

        <section className="privacy-section">
          <h2>Storage &amp; retention</h2>
          <p>
            Data is stored on servers controlled by the platform operator.
            Interview sessions and reports are retained so recruiters can review
            completed interviews. You may request deletion of your account data
            by contacting your recruiter or platform administrator.
          </p>
        </section>

        <section className="privacy-section">
          <h2>Third parties</h2>
          <p>
            We use Groq for question generation, transcription, and answer
            judging. Email delivery may use SMTP providers configured by the
            operator. We do not sell personal data.
          </p>
        </section>

        <section className="privacy-section">
          <h2>Your rights</h2>
          <p>
            Depending on your jurisdiction, you may have rights to access,
            correct, or delete personal data. Contact the recruiter or
            organization that invited you to exercise these rights.
          </p>
        </section>

        <section className="privacy-section">
          <h2>Contact</h2>
          <p>
            For privacy questions, contact the organization operating this
            SmartSkale instance or email the address shown on your interview
            invite.
          </p>
        </section>

        <p className="rp-muted-small">
          <a href="/">← Back to home</a>
        </p>
      </div>
    </div>
  );
}
