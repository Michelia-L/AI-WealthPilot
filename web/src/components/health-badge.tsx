import { getHealth } from "@/lib/api";
import { getDict } from "@/lib/i18n/server";
import { Badge } from "./ui/chip";

/** API 状态徽章，显示在侧边栏底部。 */
export default async function HealthBadge() {
  const [health, t] = await Promise.all([getHealth(), getDict()]);
  if (!health) {
    return (
      <Badge tone="cinnabar" dot>
        {t.health.offline}
      </Badge>
    );
  }
  return (
    <Badge tone="jade" dot>
      {t.health.online} · v{health.version}
    </Badge>
  );
}
