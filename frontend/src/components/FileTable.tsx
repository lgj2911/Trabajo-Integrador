import type { FileEntry } from "../api/types";

interface FileTableProps {
  items: FileEntry[];
}

export function FileTable({ items }: FileTableProps) {
  if (items.length === 0) {
    return <p className="empty-state">No files match the current filters.</p>;
  }

  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>Filename</th>
            <th>Category</th>
            <th>Source</th>
            <th>Session</th>
            <th>Downloaded at</th>
            <th>Source URL</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={`${item.session_id}-${item.dest_path}`}>
              <td>{item.filename}</td>
              <td>{item.category}</td>
              <td>{item.source}</td>
              <td>
                <span className="mono">{item.session_id}</span>
              </td>
              <td>{item.downloaded_at}</td>
              <td>
                <a href={item.source_url} target="_blank" rel="noreferrer">
                  link
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
