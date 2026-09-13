const STEPS = ["Upload", "Profile", "Review", "Export"];

export default function StepRail({ currentIndex }) {
  return (
    <div className="step-rail">
      {STEPS.map((label, i) => {
        const state = i < currentIndex ? "done" : i === currentIndex ? "active" : "";
        return (
          <div className="step-unit" key={label}>
            {i > 0 && <div className={`step-connector ${i <= currentIndex ? "done" : ""}`} />}
            <div className={`step ${state}`}>
              <span className="step-index">{i < currentIndex ? "✓" : i + 1}</span>
              <span>{label}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
