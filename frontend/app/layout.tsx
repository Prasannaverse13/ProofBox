import type { Metadata, Viewport } from "next";
import "@fontsource-variable/inter";
import "@fontsource/fira-mono/400.css";
import "./globals.css";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";

export const metadata: Metadata = {
  title: "ProofBox | Bugs with proof, run on Vultr",
  description:
    "ProofBox is an AI auditor that proves every bug by running an exploit inside a locked sandbox on Vultr. No proof, no finding.",
};

export const viewport: Viewport = { themeColor: "#ffffff", colorScheme: "light" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Nav />
        <main>{children}</main>
        <Footer />
      </body>
    </html>
  );
}
