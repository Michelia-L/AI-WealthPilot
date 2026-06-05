"""
AI WealthPilot - IPS Generator End-to-End Demo

Demonstrates the complete LangGraph-based IPS generation workflow:
    1. Create a sample ClientProfile
    2. Run the Generate → Review → Revise workflow
    3. Print progress at each stage
    4. Export the final IPS to Markdown

Usage:
    python examples/demo_ips_generator.py

Requirements:
    - DEEPSEEK_API_KEY configured in .env
    - All dependencies installed (langgraph, pydantic-ai)

CFA Reference:
    - CFA L3 PWM: Investment Policy Statement generation
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.profiler import (
    ClientProfile,
    FinancialSituation,
    InvestmentGoal,
    RiskProfile,
)
from src.agents.ips_workflow import generate_ips
from src.agents.ips_storage import (
    save_ips,
    export_ips_markdown,
    export_ips_to_file,
)

# Configure logging to show workflow progress
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def create_sample_profile() -> ClientProfile:
    """
    Create a sample ClientProfile for demo purposes.

    This profile represents a moderate-risk individual investor:
    - 35-year-old married professional with 1 child
    - Stable income, moderate savings
    - Goal: retirement + child education
    - Moderate risk tolerance with slight ability-willingness conflict

    Returns:
        Complete ClientProfile instance.
    """
    profile = ClientProfile(
        name="张明",
        age=35,
        marital_status="married",
        dependents=1,
        financial=FinancialSituation(
            annual_income=500000.0,
            annual_expenses=300000.0,
            investable_assets=2000000.0,
            total_liabilities=800000.0,
            emergency_fund_months=6.0,
        ),
        goals=[
            InvestmentGoal(
                name="退休储备",
                target_amount=10000000.0,
                years=25,
                priority="high",
            ),
            InvestmentGoal(
                name="子女教育基金",
                target_amount=1500000.0,
                years=15,
                priority="high",
            ),
            InvestmentGoal(
                name="购置改善型住房",
                target_amount=3000000.0,
                years=5,
                priority="medium",
            ),
        ],
        time_horizon_years=25,
        is_multi_stage=True,
        liquidity_needs=100000.0,
        tax_status="taxable",
        esg_preference=True,
        sector_restrictions=["tobacco", "gambling"],
        notes="家族企业持有约30万元公司股份，存在集中持仓风险",
        risk_profile=RiskProfile(
            ability_score=3.8,
            willingness_score=3.2,
            tolerance_level="Moderate / 平衡型",
        ),
    )
    return profile


def profile_to_dict(profile: ClientProfile) -> dict:
    """
    Convert ClientProfile to a serializable dict.

    Args:
        profile: ClientProfile instance.

    Returns:
        Dict representation.
    """
    from dataclasses import asdict
    return asdict(profile)


async def run_demo():
    """Run the full IPS generation demo."""
    print("\n" + "=" * 60)
    print("  AI WealthPilot — IPS 生成器演示")
    print("  LangGraph Multi-Agent Workflow Demo")
    print("=" * 60 + "\n")

    # Step 1: Create sample profile
    print("📋 步骤 1: 创建示例客户画像...")
    profile = create_sample_profile()
    profile_dict = profile_to_dict(profile)
    print(f"   客户: {profile.name}")
    print(f"   年龄: {profile.age}")
    print(f"   可投资资产: ¥{profile.financial.investable_assets:,.0f}")
    print(f"   风险等级: {profile.risk_profile.tolerance_level}")
    print(f"   投资目标: {', '.join(g.name for g in profile.goals)}")
    print()

    # Step 2: Run the IPS workflow
    print("🚀 步骤 2: 启动 LangGraph IPS 生成工作流...")
    print("   (生成 → 适配性审查 → 合规性审查 → 一致性审查 → [修订] → 终审)")
    print()

    result = await generate_ips(
        client_profile_dict=profile_dict,
        max_revisions=3,
        thread_id=f"demo_{profile.name}",
    )

    # Step 3: Display results
    print("\n" + "=" * 60)
    print("  📊 IPS 生成结果")
    print("=" * 60 + "\n")

    print(f"   状态: {result['status']}")
    print(f"   修订轮次: {result['revision_count']}")

    if result.get("error_message"):
        print(f"   ⚠️  错误: {result['error_message']}")

    if result.get("ips"):
        ips = result["ips"]
        print(f"\n   ✅ IPS 生成成功!")
        print(f"   客户: {ips.get('client_name', 'N/A')}")
        print(f"   风险等级: {ips.get('risk_tolerance', {}).get('overall_risk_level', 'N/A')}")

        # Print allocation summary
        guidelines = ips.get("investment_guidelines", {})
        allocation = guidelines.get("strategic_allocation", [])
        if allocation:
            print(f"\n   📊 战略性资产配置:")
            for a in allocation:
                print(f"      - {a['asset_class']}: {a['target_weight']:.1%}")

        # Step 4: Export
        print("\n📁 步骤 3: 导出 IPS...")

        # Save to data/ips/
        filepath = save_ips(
            ips_dict=result["ips"],
            audit_trail_dict=result.get("audit_trail", {}),
            client_name=profile.name,
        )
        print(f"   ✅ JSON 已保存: {filepath}")

        # Export to Markdown
        md_path = filepath.with_suffix(".md")
        export_ips_to_file(
            ips_dict=result["ips"],
            output_path=md_path,
            audit_trail_dict=result.get("audit_trail"),
            format="markdown",
        )
        print(f"   ✅ Markdown 已导出: {md_path}")

        # Print Markdown preview (first 50 lines)
        md_content = export_ips_markdown(result["ips"], result.get("audit_trail"))
        preview_lines = md_content.split("\n")[:50]
        print(f"\n{'─' * 60}")
        print("  📝 IPS Markdown 预览 (前 50 行)")
        print(f"{'─' * 60}\n")
        print("\n".join(preview_lines))
        print(f"\n... (共 {len(md_content.split(chr(10)))} 行)")

    else:
        print("\n   ❌ IPS 生成失败")
        if result.get("error_message"):
            print(f"   错误详情: {result['error_message']}")

    # Print audit trail summary
    audit = result.get("audit_trail")
    if audit:
        print(f"\n{'─' * 60}")
        print("  📋 审计追踪摘要")
        print(f"{'─' * 60}")
        print(f"   修订轮次: {audit.get('total_rounds', 0)}")
        print(f"   最终状态: {audit.get('final_status', 'N/A')}")
        for rev in audit.get("revision_history", []):
            print(f"\n   第 {rev['round_number']} 轮修订:")
            print(f"   版本变更: {rev.get('ips_version_before', '?')} → {rev.get('ips_version_after', '?')}")
            for change in rev.get("changes_made", [])[:3]:
                if change:
                    print(f"     - {change[:80]}...")

    print(f"\n{'=' * 60}")
    print("  演示结束")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(run_demo())
