"use client";

import Link from "next/link";
import type { ProfileSummary } from "@/lib/api";
import { fmtLocal } from "@/lib/format";
import { ApiOffline } from "@/components/api-offline";
import {
  Button,
  EmptyState,
  Icon,
  Panel,
  Table,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui";
import { MAX_COMPARE, RiskBadge } from "./shared";

/**
 * 画像列表 —— 工具栏（导入 / 对比所选）、选择勾选与 CRUD 操作列。
 * 新建入口在页头 SectionHeader，删除确认由 ProfilesManager 的 ConfirmDialog 承担。
 */
export default function ProfileList({
  profiles,
  selected,
  onToggleSelect,
  comparing,
  onCompare,
  busy,
  notice,
  error,
  onImport,
  onEdit,
  onDelete,
  onCreate,
}: {
  profiles: ProfileSummary[] | null;
  selected: number[];
  onToggleSelect: (id: number) => void;
  comparing: boolean;
  onCompare: () => void;
  busy: boolean;
  notice: string | null;
  error: string | null;
  onImport: () => void;
  onEdit: (id: number) => void;
  onDelete: (p: ProfileSummary) => void;
  onCreate: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="secondary"
          icon="download"
          onClick={onImport}
          disabled={busy}
        >
          从 JSON 导入
        </Button>
        <Button
          variant="secondary"
          icon="layers"
          onClick={onCompare}
          disabled={comparing || selected.length < 2}
        >
          {comparing ? "对比中…" : `对比所选（${selected.length}）`}
        </Button>
        {selected.length > 0 && selected.length < 2 && (
          <span className="text-xs text-mist-500">
            再选 1 个即可对比（最多 {MAX_COMPARE} 个）
          </span>
        )}
        {notice && (
          <span className="flex items-center gap-1.5 text-sm text-jade-400">
            <Icon name="check" size={14} />
            {notice}
          </span>
        )}
        {error && (
          <span className="flex items-center gap-1.5 text-sm text-cinnabar-400">
            <Icon name="warning" size={14} />
            {error}
          </span>
        )}
      </div>

      {profiles === null ? (
        <ApiOffline resource="画像列表" />
      ) : profiles.length === 0 ? (
        <Panel pad={false}>
          <EmptyState
            icon="users"
            title="还没有客户画像"
            hint="建立第一份双轨风险评估画像，或从 Streamlit 时代的 JSON 文件导入。"
            action={
              <Button icon="plus" onClick={onCreate}>
                新建画像
              </Button>
            }
          />
        </Panel>
      ) : (
        <Panel pad={false} innerClassName="overflow-hidden">
          <Table className="min-w-[640px]">
            <THead>
              <tr>
                <TH className="w-10">
                  <span className="sr-only">选择</span>
                </TH>
                <TH>姓名</TH>
                <TH className="text-right">年龄</TH>
                <TH>风险等级</TH>
                <TH>更新时间</TH>
                <TH className="text-right">操作</TH>
              </tr>
            </THead>
            <tbody>
              {profiles.map((p) => (
                <TR key={p.id}>
                  <TD>
                    <input
                      type="checkbox"
                      checked={selected.includes(p.id)}
                      onChange={() => onToggleSelect(p.id)}
                      aria-label={`选择 ${p.name} 参与对比`}
                      className="h-4 w-4 accent-gold-500"
                    />
                  </TD>
                  <TD>
                    <Link
                      href={`/profiles/${p.id}`}
                      className="font-medium text-mist-100 transition-colors duration-300 hover:text-gold-300"
                    >
                      {p.name}
                    </Link>
                  </TD>
                  <TD className="text-right font-mono">{p.age}</TD>
                  <TD>
                    <RiskBadge level={p.risk_level} />
                  </TD>
                  <TD className="font-mono text-xs text-mist-500">
                    {fmtLocal(p.updated_at)}
                  </TD>
                  <TD className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        icon="pencil"
                        aria-label={`编辑 ${p.name}`}
                        onClick={() => onEdit(p.id)}
                        disabled={busy}
                      />
                      <Button
                        variant="ghost"
                        size="sm"
                        icon="trash"
                        aria-label={`删除 ${p.name}`}
                        className="hover:text-cinnabar-300"
                        onClick={() => onDelete(p)}
                        disabled={busy}
                      />
                    </div>
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        </Panel>
      )}
    </div>
  );
}
