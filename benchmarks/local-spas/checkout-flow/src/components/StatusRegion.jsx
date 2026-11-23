export function StatusRegion({ message }) {
  return (
    <div
      className={message ? "status-region" : "status-region is-empty"}
      role="status"
      aria-live="polite"
      data-testid="status-region"
    >
      {message}
    </div>
  );
}
