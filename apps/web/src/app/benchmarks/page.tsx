import { BenchmarksPage } from "@/components/benchmarks/benchmarks-page";
import { PublicShell } from "@/components/shared/public-shell";

export const metadata = { title: "Benchmarks | Gauntlet" };

export default function Page() {
  return (
    <PublicShell
      title="Benchmarks"
      intro="Studies of Gauntlet itself, run from committed scripts. Numbers are published whether or not they flatter the product; every metric comes with an interval and its limitations."
    >
      <BenchmarksPage />
    </PublicShell>
  );
}
