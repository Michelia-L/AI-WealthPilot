"""Request locale resolution + bilingual user-facing messages (Phase 22).

The Next.js frontend resolves a visitor's locale from its ``wp_locale``
cookie and forwards it to this API as the ``X-Locale`` request header
(``en`` / ``zh``). ``get_request_locale`` maps that header to a supported
locale — anything missing or unrecognized falls back to English, matching
the frontend default for new visitors.

``msg`` renders one entry of the message table below. The table is grouped
by owning module and every key carries both languages, with the pre-i18n
Chinese copy kept verbatim as ``zh``. New user-facing copy (HTTPException
details, SSE event messages/labels) must be added here in both languages —
never inline Chinese in routers.
"""

from typing import Any

from fastapi import Request

SUPPORTED_LOCALES = ("en", "zh")
DEFAULT_LOCALE = "en"

LOCALE_HEADER = "X-Locale"


def get_request_locale(request: Request) -> str:
    """Resolve the X-Locale header to a supported locale (default English)."""
    value = request.headers.get(LOCALE_HEADER, "").strip().lower()
    return value if value in SUPPORTED_LOCALES else DEFAULT_LOCALE


_MESSAGES: dict[str, dict[str, dict[str, str]]] = {
    # Shared across routers.
    "common": {
        "llm_not_configured": {
            "zh": "DEEPSEEK_API_KEY 未配置，请在 api 服务的 .env 中设置后重启；或设置 DEMO_MODE=1 进入演示模式。",
            "en": "DEEPSEEK_API_KEY is not configured. Set it in the api service's .env and restart, or set DEMO_MODE=1 to enter demo mode.",
        },
        "profile_not_found": {
            "zh": "画像不存在（id={id}）",
            "en": "Profile not found (id={id})",
        },
        "ips_doc_not_found": {
            "zh": "IPS 文档不存在",
            "en": "IPS document not found",
        },
        "task_not_found": {
            "zh": "任务不存在",
            "en": "Task not found",
        },
        "report_not_found": {
            "zh": "报告不存在",
            "en": "Report not found",
        },
        "stream_interrupted": {
            "zh": "流式生成中断: {error}",
            "en": "Streaming generation interrupted: {error}",
        },
        "no_report_generated": {
            "zh": "生成器未返回报告",
            "en": "The generator returned no report",
        },
    },
    "advisor": {
        "invalid_export_format": {
            "zh": "format 必须是 {formats}",
            "en": "format must be {formats}",
        },
    },
    "ips": {
        "workflow_no_ips": {
            "zh": "工作流未产出 IPS（可能被升级人工处理）",
            "en": "The workflow produced no IPS (it may have been escalated for manual handling)",
        },
        "generation_failed": {
            "zh": "IPS 生成失败: {error}",
            "en": "IPS generation failed: {error}",
        },
        # Workflow node labels (SSE progress timeline in the UI).
        "node.generate_cme": {
            "zh": "生成资本市场预期 (CME)",
            "en": "Generate capital market expectations (CME)",
        },
        "node.generate": {
            "zh": "生成 IPS 初稿",
            "en": "Generate IPS draft",
        },
        "node.select_docs": {
            "zh": "选择评审参考文档",
            "en": "Select review reference documents",
        },
        "node.review_suitability": {
            "zh": "评审：适当性",
            "en": "Review: suitability",
        },
        "node.review_compliance": {
            "zh": "评审：合规性",
            "en": "Review: compliance",
        },
        "node.review_consistency": {
            "zh": "评审：一致性",
            "en": "Review: consistency",
        },
        "node.validate_saa": {
            "zh": "量化验证 SAA",
            "en": "Quantitative SAA validation",
        },
        "node.revise": {
            "zh": "修订 IPS",
            "en": "Revise IPS",
        },
        "node.finalize": {
            "zh": "定稿",
            "en": "Finalize",
        },
    },
    "monitoring": {
        "invalid_backtest_period": {
            "zh": "不支持的回测区间：{period}（可选：{options}）。",
            "en": "Unsupported backtest period: {period} (available: {options}).",
        },
        "fee_no_disclosure": {
            "zh": "IPS 未包含费用披露，回测未计费用拖累。",
            "en": "The IPS has no fee disclosure; no fee drag was applied in the backtest.",
        },
        "fee_ter_missing": {
            "zh": "IPS 费用披露缺少 total_expense_ratio，按管理费+托管费+交易成本合计 {components:.2%} 计入费用拖累。",
            "en": "The IPS fee disclosure is missing total_expense_ratio; the sum of management, custody and transaction costs ({components:.2%}) was used as the fee drag.",
        },
    },
    "portfolio": {
        "invalid_weights": {
            "zh": "weights 需为 1–30 个 ticker 的权重映射。",
            "en": "weights must be a weight map of 1–30 tickers.",
        },
        "long_only": {
            "zh": "回测仅支持多头权重（不允许负权重）。",
            "en": "Backtests support long-only weights (negative weights are not allowed).",
        },
        "bad_weight_total": {
            "zh": "权重合计异常（{total:.2f}），应在 0.5–1.5 之间。",
            "en": "Invalid weight total ({total:.2f}); it should be between 0.5 and 1.5.",
        },
        "price_fetch_failed": {
            "zh": "行情数据获取失败（{tickers}），请稍后重试。",
            "en": "Failed to fetch market data ({tickers}); please try again later.",
        },
        "risk_constraints_mvo_only": {
            "zh": "风险约束当前仅支持经典 MVO 方法",
            "en": "Risk constraints currently support only the classic MVO method",
        },
        "frontier_failed": {
            "zh": "有效前沿求解失败：当前资产组合在该历史窗口下无法构成有效前沿，请调整资产选择或历史窗口。",
            "en": "Failed to solve the efficient frontier: the selected assets cannot form an efficient frontier over this historical window. Adjust the asset selection or the window.",
        },
        "node_fetch": {
            "zh": "获取行情数据",
            "en": "Fetching market data",
        },
        "node_solve": {
            "zh": "组合优化计算中",
            "en": "Computing portfolio optimization",
        },
        "node_solve_resampled": {
            "zh": "重采样优化计算中（{n_simulations} 次模拟，通常需要数分钟）",
            "en": "Running resampled optimization ({n_simulations} simulations; this usually takes a few minutes)",
        },
        "optimize_failed": {
            "zh": "优化失败: {error}",
            "en": "Optimization failed: {error}",
        },
        "bl_requires_view": {
            "zh": "Black-Litterman 需要至少一条投资者观点（bl.views 不能为空）。",
            "en": "Black-Litterman requires at least one investor view (bl.views must be non-empty).",
        },
        "surplus_requires_inputs": {
            "zh": "盈余优化需要负债参数（surplus.liability_ratio + surplus.liability_duration）或包含投资目标的客户画像（profile_id）。",
            "en": "Surplus optimization requires liability inputs (surplus.liability_ratio + surplus.liability_duration) or a client profile with investment goals (profile_id).",
        },
        "surplus_profile_unusable": {
            "zh": "该画像无法推导负债：需要至少一个目标金额为正的投资目标，且可投资资产大于零。",
            "en": "Cannot derive liabilities from this profile: it needs at least one goal with a positive target amount and positive investable assets.",
        },
        "surplus_invalid_proxy": {
            "zh": "无效的负债对冲代理：{proxy}（可选：{options}）。",
            "en": "Invalid liability hedge proxy: {proxy} (available: {options}).",
        },
        "cme_source_not_bl": {
            "zh": "CME 预期收益不适用于 Black-Litterman 方法（BL 已内置均衡收益与观点后验）。",
            "en": "CME expected returns do not apply to Black-Litterman (BL already blends equilibrium returns with investor views).",
        },
        "cme_unavailable": {
            "zh": "资本市场预期（CME）全部数据源失效，无法提供预期收益，请改用历史样本或稍后重试。",
            "en": "All Capital Market Expectations data sources failed; expected returns are unavailable — use sample means or retry later.",
        },
        "min_assets": {
            "zh": "至少需要 2 个有效资产类别。可选：{keys}",
            "en": "At least 2 valid asset classes are required. Valid keys: {keys}",
        },
    },
    "profiles": {
        "ids_not_integers": {
            "zh": "ids 必须为逗号分隔的整数",
            "en": "ids must be comma-separated integers",
        },
        "compare_min": {
            "zh": "至少需要 2 个画像才能进行对比",
            "en": "At least 2 profiles are required for comparison",
        },
        "compare_max": {
            "zh": "一次最多对比 {max_count} 个画像",
            "en": "At most {max_count} profiles can be compared at a time",
        },
        "compare_duplicate_names": {
            "zh": "所选画像存在重名，对比结果会互相覆盖；请改名后再试",
            "en": "The selected profiles have duplicate names; comparison results would overwrite each other. Rename them and try again.",
        },
    },
    "settings": {
        "custom_endpoint_fields_required": {
            "zh": "设置自定义端点时，base_url 与 model 均不能为空。",
            "en": "When configuring a custom endpoint, base_url and model must not be empty.",
        },
        "endpoint_unreachable": {
            "zh": "无法连接到该端点，请检查地址与网络",
            "en": "Could not connect to this endpoint. Check the address and your network.",
        },
        "endpoint_auth_failed": {
            "zh": "端点认证失败，请检查 API Key",
            "en": "Endpoint authentication failed. Check the API key.",
        },
        "models_fetch_failed": {
            "zh": "获取模型列表失败：{error}",
            "en": "Failed to fetch the model list: {error}",
        },
    },
    "tasks": {
        "task_interrupted": {
            "zh": "服务已重启，任务被中断（以上为重启前的进度回放）",
            "en": "The server was restarted and the task was interrupted (the progress above is a replay from before the restart)",
        },
    },
}


def msg(key: str, locale: str, **fmt: Any) -> str:
    """Render message ``key`` ("<group>.<name>") in ``locale``.

    Template placeholders are filled with ``str.format(**fmt)``. Unknown
    keys raise KeyError so missing entries fail loudly in tests; an
    unsupported locale falls back to the English template.
    """
    group, _, name = key.partition(".")
    try:
        entry = _MESSAGES[group][name]
    except KeyError:
        raise KeyError(f"Unknown i18n message key: {key}") from None
    template = entry.get(locale) or entry[DEFAULT_LOCALE]
    return template.format(**fmt) if fmt else template
