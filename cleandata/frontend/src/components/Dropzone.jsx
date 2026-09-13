import { useRef, useState } from "react";

function FunnelIcon() {
  return (
    <svg
      width="56"
      height="52"
      viewBox="0 0 56 52"
      fill="none"
      aria-hidden="true"
      style={{ marginBottom: 14, filter: "drop-shadow(0 0 5px rgba(36,231,255,0.45))" }}
    >
      {/* messy values falling in */}
      <circle cx="8" cy="4" r="2" fill="var(--muted)" opacity="0.5" />
      <circle cx="20" cy="1.5" r="1.4" fill="var(--muted)" opacity="0.5" />
      <circle cx="34" cy="3" r="2.2" fill="var(--muted)" opacity="0.5" />
      <circle cx="46" cy="5.5" r="1.4" fill="var(--muted)" opacity="0.5" />

      {/* funnel */}
      <path
        d="M4 10 H52 L32 30 V40 H24 V30 L4 10 Z"
        stroke="var(--cyan)"
        strokeWidth="1.6"
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* clean rows out */}
      <line x1="18" y1="47" x2="26" y2="47" stroke="var(--cyan)" strokeWidth="1.6" strokeLinecap="round" />
      <line x1="30" y1="47" x2="38" y2="47" stroke="var(--cyan)" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export default function Dropzone({ onFile, disabled }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  function handleDrop(e) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) onFile(file);
  }

  return (
    <div
      className={`dropzone ${dragging ? "dragging" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => !disabled && inputRef.current?.click()}
      role="button"
      tabIndex={0}
      aria-disabled={disabled}
    >
      <FunnelIcon />
      <p>
        Drop a CSV or TSV file here, or <span className="browse">browse</span>
      </p>
      <p className="hint">Nothing leaves your machine — cleaning runs on your local backend.</p>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.tsv"
        hidden
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
    </div>
  );
}
