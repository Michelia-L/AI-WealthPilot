import { getHealth } from "@/lib/api";

/** API status chip shown at the bottom of the sidebar. */
export default async function HealthBadge() {
  const health = await getHealth();
  if (!health) {
    return (
      <span className="inline-block rounded-full bg-rose-900/60 px-3 py-1 text-xs font-medium text-rose-300">
        API 离线
      </span>
    );
  }
  return (
    <span className="inline-block rounded-full bg-emerald-900/60 px-3 py-1 text-xs font-medium text-emerald-300">
      API 在线 · v{health.version}
    </span>
  );
}
