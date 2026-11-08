import Link from "next/link";
import { LogoMark } from "./Logo";

export function Footer() {
  return (
    <footer className="footer">
      <div className="wrap footer-inner">
        <div style={{ maxWidth: 340 }}>
          <span className="logo" style={{ fontSize: 18 }}>
            <LogoMark size={22} />
            ProofBox
          </span>
          <p style={{ marginTop: 12 }}>
            Bugs with proof. Built for the Vultr Agent Rush hackathon. MIT licensed.
          </p>
        </div>
        <div className="footer-cols">
          <div>
            <h5>Product</h5>
            <Link href="/#how">How it works</Link>
            <Link href="/#containment">Containment</Link>
            <Link href="/console">Console</Link>
          </div>
          <div>
            <h5>Runs on</h5>
            <a href="https://www.vultr.com/products/serverless-inference/" rel="noreferrer">Vultr Serverless Inference</a>
            <a href="https://www.vultr.com/products/cloud-compute/" rel="noreferrer">Vultr Cloud Compute</a>
          </div>
        </div>
      </div>
    </footer>
  );
}
