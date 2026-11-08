/** The product shot: a slowly turning aluminium box. It is the sandbox.
 *  Studio lit on white with a soft contact shadow, like a product render. */
export function Cube() {
  return (
    <div className="hero-stage" aria-hidden="true">
      <div className="halo" />
      <div className="floor" />
      <div className="cube-scene">
        <div className="cube">
          {(["top", "front", "right", "back", "left", "bottom"] as const).map((f) => (
            <div key={f} className={`face ${f}`}>
              <div className="grid" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
