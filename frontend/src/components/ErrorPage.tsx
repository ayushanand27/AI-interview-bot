interface ErrorPageProps {
  code: 404 | 500;
  title?: string;
  message?: string;
  onRetry?: () => void;
}

export default function ErrorPage({
  code,
  title,
  message,
  onRetry,
}: ErrorPageProps) {
  const defaultTitle = code === 404 ? "Page not found" : "Server error";
  const defaultMessage =
    code === 404
      ? "The page you requested does not exist."
      : "Something went wrong on our end. Please try again.";

  return (
    <div className="card error-page">
      <p className="error-page-code">{code}</p>
      <h2>{title ?? defaultTitle}</h2>
      <p className="error-page-message">
        {message ?? defaultMessage}
      </p>
      {onRetry && (
        <button type="button" className="primary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}
