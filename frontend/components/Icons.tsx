/** Isometric monochrome icons for the sample tiles. Graphite tones only,
 *  in the spirit of SF Symbols: color lives in the content, not the chrome. */
const L = "#86868b";
const D = "#1d1d1f";
const X = "#424245";

export function IconWire() {
  return (
    <svg className="icon" viewBox="0 0 120 120" fill="none" stroke={L} strokeWidth="1.5" strokeLinejoin="round" aria-hidden="true">
      <polygon points="60,14 100,37 60,60 20,37" />
      <polygon points="20,37 60,60 60,106 20,83" />
      <polygon points="100,37 60,60 60,106 100,83" />
      <polyline points="40,25.5 80,48.5" strokeOpacity=".5" />
      <polyline points="40,48.5 80,71.5" strokeOpacity=".5" />
      <polyline points="60,60 60,14" strokeOpacity=".5" />
    </svg>
  );
}

export function IconStairs() {
  return (
    <svg className="icon" viewBox="0 0 120 120" aria-hidden="true">
      <polygon points="14,92 44,75 44,63 14,80" fill={D} />
      <polygon points="14,80 44,63 74,80 44,97" fill={L} opacity=".0" />
      <polygon points="44,75 74,58 74,46 44,63" fill={D} />
      <polygon points="74,58 104,41 104,29 74,46" fill={D} />
      <polygon points="14,80 44,63 44,51 14,68" fill={L} />
      <polygon points="44,63 74,46 74,34 44,51" fill={L} />
      <polygon points="74,46 104,29 104,17 74,34" fill={L} />
      <polygon points="14,92 44,109 44,97 14,80" fill={X} />
      <polygon points="44,97 74,80 74,92 44,109" fill={X} opacity=".7" />
    </svg>
  );
}

export function IconLayers() {
  return (
    <svg className="icon" viewBox="0 0 120 120" aria-hidden="true">
      <polygon points="60,66 104,86 60,106 16,86" fill={X} />
      <polygon points="60,46 104,66 60,86 16,66" fill={D} />
      <polygon points="60,26 104,46 60,66 16,46" fill={L} />
      <polygon points="16,46 60,66 60,74 16,54" fill={D} />
      <polygon points="104,46 60,66 60,74 104,54" fill={X} />
    </svg>
  );
}
