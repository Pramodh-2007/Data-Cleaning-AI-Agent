export default function ActionLog({ actions }) {
  if (!actions.length) {
    return <p className="empty-note">No issues found — the file was already clean.</p>;
  }
  return (
    <div className="action-list">
      {actions.map((a, i) => (
        <div className="action-row" key={i}>
          <div className="top-line">
            <span>
              <span className="col-tag">{a.column}</span> — {a.issue} → {a.action}
            </span>
            {a.rows_affected > 0 && (
              <span className="rows-affected">{a.rows_affected} rows</span>
            )}
          </div>
          <div className="details">{a.details}</div>
        </div>
      ))}
    </div>
  );
}
