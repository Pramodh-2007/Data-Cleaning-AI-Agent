export default function DataTable({ rows, changedColumns = [] }) {
  if (!rows.length) return <p className="empty-note">No rows to show.</p>;
  const columns = Object.keys(rows[0]);

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => {
                const val = row[c];
                const isChanged = changedColumns.includes(c);
                const isEmpty = val === null || val === undefined || val === "";
                return (
                  <td key={c} className={`${isChanged ? "changed" : ""} ${isEmpty ? "empty" : ""}`}>
                    {isEmpty ? "—" : String(val)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
