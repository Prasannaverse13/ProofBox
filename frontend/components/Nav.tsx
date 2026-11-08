"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogoMark } from "./Logo";

export function Nav() {
  const path = usePathname();
  const onConsole = path.startsWith("/console");
  return (
    <header className="nav">
      <div className="wrap nav-inner">
        <Link href="/" className="logo" aria-label="ProofBox home">
          <LogoMark />
          ProofBox
        </Link>
        <nav className="nav-links" aria-label="Main">
          <Link href="/#how">How it works</Link>
          <Link href="/#containment">Containment</Link>
          <Link href="/#samples">Samples</Link>
          <Link href="/console" aria-current={onConsole ? "page" : undefined}>Console</Link>
        </nav>
        <div className="nav-right">
          <Link href="/#containment" className="text-link">Docs</Link>
          <Link href="/console" className="btn pill small">Run an audit</Link>
        </div>
      </div>
    </header>
  );
}
