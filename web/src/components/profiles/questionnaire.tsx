"use client";

import type {
  ProfilePayload,
  QuestionnaireQuestion,
  QuestionnaireResponse,
} from "@/lib/api";
import { classifyRiskPreview, scoreFromAnswers } from "@/lib/api";
import { Badge, Chip, Slider, StatTile } from "@/components/ui";
import { riskTone } from "./shared";

/** 单轨问卷（能力或意愿）：题目 + Chip 选项，再次点击已选选项即取消作答。 */
function QuestionTrack({
  title,
  questions,
  answers,
  onAnswer,
}: {
  title: string;
  questions: QuestionnaireQuestion[];
  answers: Record<string, string>;
  onAnswer: (questionKey: string, optionKey: string) => void;
}) {
  return (
    <div className="space-y-5">
      <h4 className="text-[11px] font-medium tracking-[0.14em] text-mist-500 uppercase">
        {title}
      </h4>
      {questions.map((q, qi) => (
        <div key={q.key}>
          <p className="text-sm leading-snug text-mist-200">
            <span className="tnum mr-1.5 font-mono text-xs text-mist-500">
              {qi + 1}.
            </span>
            {q.question}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {q.options.map((o) => (
              <Chip
                key={o.key}
                selected={answers[q.key] === o.key}
                onClick={() => onAnswer(q.key, o.key)}
              >
                {o.label}
              </Chip>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * 双轨风险问卷：客观能力 5 题 + 主观意愿 4 题，附实时风险预览。
 * 问卷加载失败（API 未就绪）时回退为手动评分滑杆，0 表示未评估。
 */
export default function RiskQuestionnaire({
  questionnaire,
  form,
  onAnswer,
  onRiskScoreChange,
}: {
  questionnaire: QuestionnaireResponse | null;
  form: ProfilePayload;
  onAnswer: (
    track: "ability_answers" | "willingness_answers",
    questionKey: string,
    optionKey: string
  ) => void;
  onRiskScoreChange: (
    key: "ability_score" | "willingness_score",
    value: number
  ) => void;
}) {
  // Mirror of the server-side precedence: a track with answers derives its
  // score from the questionnaire; an unanswered track keeps manual scores.
  const abilityScore =
    questionnaire && Object.keys(form.ability_answers).length > 0
      ? scoreFromAnswers(questionnaire.ability, form.ability_answers)
      : form.risk_scores.ability_score;
  const willingnessScore =
    questionnaire && Object.keys(form.willingness_answers).length > 0
      ? scoreFromAnswers(questionnaire.willingness, form.willingness_answers)
      : form.risk_scores.willingness_score;
  const preview = classifyRiskPreview(abilityScore, willingnessScore);
  const finalScore =
    abilityScore > 0 && willingnessScore > 0
      ? Math.min(abilityScore, willingnessScore)
      : 0;
  const fmtScore = (v: number) => (v === 0 ? "—" : v.toFixed(1));

  return (
    <div className="space-y-5">
      {/* 实时风险预览 —— 客户端镜像算分，保存时以服务端重算为准 */}
      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile label="风险承受能力" value={fmtScore(abilityScore)} />
        <StatTile label="风险承受意愿" value={fmtScore(willingnessScore)} />
        <StatTile
          label="综合 = min(能力, 意愿)"
          value={fmtScore(finalScore)}
          tone="gold"
        />
      </div>
      <div className="flex items-center gap-2.5">
        <span className="text-xs text-mist-500">实时预览</span>
        <Badge tone={riskTone(preview)} dot>
          {preview}
        </Badge>
      </div>

      {questionnaire ? (
        <>
          <div className="grid gap-6 lg:grid-cols-2">
            <QuestionTrack
              title="风险承受能力（客观 · 5 题）"
              questions={questionnaire.ability}
              answers={form.ability_answers}
              onAnswer={(q, o) => onAnswer("ability_answers", q, o)}
            />
            <QuestionTrack
              title="风险承受意愿（主观 · 4 题）"
              questions={questionnaire.willingness}
              answers={form.willingness_answers}
              onAnswer={(q, o) => onAnswer("willingness_answers", q, o)}
            />
          </div>
          <p className="text-xs leading-5 text-mist-600">
            已答题目自动算分（未答题不参与平均），保存时覆盖手动评分；再次点击选项可取消作答。全部留空则保留手动评分，0
            表示未评估。
          </p>
        </>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            <Slider
              label="风险承受能力"
              min={0}
              max={5}
              step={0.5}
              value={form.risk_scores.ability_score}
              format={(v) => (v === 0 ? "未评估" : v.toFixed(1))}
              onChange={(v) => onRiskScoreChange("ability_score", v)}
            />
            <Slider
              label="风险承受意愿"
              min={0}
              max={5}
              step={0.5}
              value={form.risk_scores.willingness_score}
              format={(v) => (v === 0 ? "未评估" : v.toFixed(1))}
              onChange={(v) => onRiskScoreChange("willingness_score", v)}
            />
          </div>
          <p className="text-xs leading-5 text-mist-600">
            风险问卷加载失败（API 未就绪），暂以手动评分代替；评分为 0 表示未评估。
          </p>
        </>
      )}
    </div>
  );
}
