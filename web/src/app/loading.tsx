import { Skeleton } from "@/components/ui";

/** Root-level page skeleton shown while a route segment streams in. */
export default function Loading() {
  return (
    <div className="space-y-6" aria-busy="true">
      <Skeleton className="h-9 w-56" />
      <Skeleton className="h-44 w-full rounded-xl" />
      <Skeleton className="h-72 w-full rounded-xl" />
    </div>
  );
}
