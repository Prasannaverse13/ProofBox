export function LogoMark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <polygon points="16,2 29,9.5 16,17 3,9.5" fill="#d2d2d7" />
      <polygon points="3,9.5 16,17 16,30 3,22.5" fill="#1d1d1f" />
      <polygon points="29,9.5 16,17 16,30 29,22.5" fill="#6e6e73" />
      <polygon points="16,9 22,12.5 16,16 10,12.5" fill="#fff" opacity="0.9" />
    </svg>
  );
}
