import { Suspense } from "react";
import { Console } from "./Console";

export const metadata = { title: "Console | ProofBox" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <Console />
    </Suspense>
  );
}
