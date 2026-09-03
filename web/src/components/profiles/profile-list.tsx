"use client";

import Link from "next/link";
import { useRef } from "react";
import type { ProfileSummary } from "@/lib/api";
import { fmtLocal } from "@/lib/format";
import { useLocale, useT } from "@/components/locale-context";
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
 * 画像列表 —— 工具栏（目录导入 / 上传 JSON / 对比所选）、选择勾选与 CRUD 操作列。
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
  onUpload,
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
  onUpload: (files: File[]) => void;
  onEdit: (id: number) => void;
  onDelete: (p: ProfileSummary) => void;
  onCreate: () => void;
}) {
  const t = useT();
  const { locale } = useLocale();
  const fileInput = useRef<HTMLInputElement>(null);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="secondary"
          icon="download"
          onClick={onImport}
          disabled={busy}
        >
          {t.profiles.importFromJson}
        </Button>
        <input
          ref={fileInput}
          type="file"
          accept=".json,application/json"
          multiple
          hidden
          onChange={(e) => {
            onUpload(Array.from(e.target.files ?? []));
            e.target.value = ""; // allow picking the same file again
          }}
        />
        <Button
          variant="secondary"
          icon="upload"
          onClick={() => fileInput.current?.click()}
          disabled={busy}
        >
          {t.profiles.uploadJson}
        </Button>
        <Button
          variant="secondary"
          icon="layers"
          onClick={onCompare}
          disabled={comparing || selected.length < 2}
        >
          {comparing
            ? t.profiles.comparing
            : t.profiles.compareSelected(selected.length)}
        </Button>
        {selected.length > 0 && selected.length < 2 && (
          <span className="text-xs text-mist-500">
            {t.profiles.selectOneMoreHint(MAX_COMPARE)}
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
        <ApiOffline resource={t.profiles.listResource} />
      ) : profiles.length === 0 ? (
        <Panel pad={false}>
          <EmptyState
            icon="users"
            title={t.profiles.emptyTitle}
            hint={t.profiles.emptyHint}
            action={
              <Button icon="plus" onClick={onCreate}>
                {t.profiles.createProfile}
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
                  <span className="sr-only">{t.profiles.selectSrOnly}</span>
                </TH>
                <TH>{t.profiles.fieldName}</TH>
                <TH className="text-right">{t.profiles.fieldAge}</TH>
                <TH>{t.profiles.colRiskLevel}</TH>
                <TH>{t.profiles.colUpdated}</TH>
                <TH className="text-right">{t.profiles.colActions}</TH>
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
                      aria-label={t.profiles.selectForCompareAria(p.name)}
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
                    <RiskBadge
                      level={p.risk_level}
                      locale={locale}
                      unassessed={t.profiles.unassessed}
                    />
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
                        aria-label={t.profiles.editAria(p.name)}
                        onClick={() => onEdit(p.id)}
                        disabled={busy}
                      />
                      <Button
                        variant="ghost"
                        size="sm"
                        icon="trash"
                        aria-label={t.profiles.deleteAria(p.name)}
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
