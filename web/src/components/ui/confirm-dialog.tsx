"use client";

import Button from "./button";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** 确认对话框 —— 取代 window.confirm 的破坏性操作确认。 */
export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "确认",
  cancelLabel = "取消",
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
    >
      <div
        className="animate-fade-in absolute inset-0 bg-ink-950/75 backdrop-blur-sm"
        onClick={onCancel}
      />
      <div className="animate-fade-up relative w-full max-w-sm rounded-[1.4rem] border border-white/[0.08] bg-ink-900 p-6 shadow-[0_32px_64px_-24px_rgb(0_0_0/0.8)]">
        <h3 className="font-display text-lg text-mist-100">{title}</h3>
        {description && (
          <p className="mt-2 text-sm leading-6 text-mist-400">{description}</p>
        )}
        <div className="mt-6 flex justify-end gap-3">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button
            variant={danger ? "danger" : "primary"}
            size="sm"
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
