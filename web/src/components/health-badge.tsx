import { getHealth } from "@/lib/api";
import { Badge } from "./ui/chip";

/** API 状态徽章，显示在侧边栏底部。 */
export default async function HealthBadge() {
  const health = await getHealth();
  if (!health) {
    return (
      <Badge tone="cinnabar" dot>
        API 离线
      </Badge>
    );
  }
  return (
    <Badge tone="jade" dot>
      API 在线 · v{health.version}
    </Badge>
  );
}
