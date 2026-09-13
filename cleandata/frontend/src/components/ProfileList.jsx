export default function ProfileList({ columns }) {
  return (
    <div className="profile-list">
      <div className="profile-row" style={{ color: "var(--muted)", fontSize: "0.75rem" }}>
        <span>Column</span>
        <span>Type</span>
        <span>Missing</span>
        <span>Unique</span>
      </div>
      {columns.map((c) => (
        <div className="profile-row" key={c.name}>
          <span className="col-name">{c.name}</span>
          <span className="dtype">{c.dtype}</span>
          <span>
            <div className="missing-bar-track">
              <div
                className="missing-bar-fill"
                style={{ width: `${Math.round(c.missing_pct * 100)}%` }}
              />
            </div>
          </span>
          <span>{c.unique}</span>
        </div>
      ))}
    </div>
  );
}
