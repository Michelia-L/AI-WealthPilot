"use client";

import { useState } from "react";
import Icon from "./ui/icon";

/**
 * 思考过程 —— 流式渲染模型的 reasoning 内容（DeepSeek reasoner 类模型经
 * delta.reasoning_content 下发）。弱化样式，生成开始自动展开、结束自动折叠，
 * 用户可随时手动开关；无推理内容的模型此区不渲染（优雅降级）。
 */
export default function ReasoningSection({
  text,
  streaming,
  reasoningTokens,
}: {
  text: string;
  streaming: boolean;
  reasoningTokens?: number | null;
}) {
  const [open, setOpen] = useState(true);
  // render 期条件调整（React 官方模式）：流式状态翻转时重置展开态
  const [wasStreaming, setWasStreaming] = useState(streaming);
  if (streaming !== wasStreaming) {
    setWasStreaming(streaming);
    setOpen(streaming);
  }

  if (!text) return null;

  return (
    <div className="mb-4 rounded-xl border border-white/[0.06] bg-white/[0.02]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-left"
      >
        <Icon
          name={open ? "chevronDown" : "chevronRight"}
          size={13}
          className="shrink-0 text-mist-500"
        />
        <span className="text-xs font-medium text-mist-400">思考过程</span>
        {streaming && (
          <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-gold-400" />
        )}
        {reasoningTokens != null && reasoningTokens > 0 && (
          <span className="tnum ml-auto font-mono text-[11px] text-mist-600">
            思考 {reasoningTokens.toLocaleString()} tokens
          </span>
        )}
      </button>
      {open && (
        <div className="max-h-64 overflow-y-auto px-4 pb-3">
          <p className="text-xs leading-6 whitespace-pre-wrap text-mist-500">
            {text}
          </p>
        </div>
      )}
    </div>
  );
}
