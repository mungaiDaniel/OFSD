import type { BatchStage } from "@/lib/types";
import { STAGE_LABELS } from "@/lib/constants";

interface BatchStageStepperProps {
  currentStage: BatchStage;
  /** Optional: show compact inline version (for table rows) */
  compact?: boolean;
}

export function BatchStageStepper({ currentStage, compact = false }: BatchStageStepperProps) {
  const stages: BatchStage[] = [1, 2, 3, 4];

  if (compact) {
    return (
      <div className="flex items-center gap-0">
        {stages.map((stage, i) => (
          <div key={stage} className="flex items-center">
            <div
              className="w-2 h-2 rounded-full"
              style={{
                background:
                  stage <= currentStage
                    ? "var(--color-brand-400)"
                    : "var(--color-border-default)",
              }}
            />
            {i < stages.length - 1 && (
              <div
                className="w-3 h-0.5"
                style={{
                  background:
                    stage < currentStage
                      ? "var(--color-brand-400)"
                      : "var(--color-border-default)",
                }}
              />
            )}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex items-center w-full">
      {stages.map((stage, i) => {
        const isComplete = stage < currentStage;
        const isCurrent = stage === currentStage;
        const isPending = stage > currentStage;

        return (
          <div key={stage} className="flex items-center flex-1 last:flex-none">
            {/* Step circle + label */}
            <div className="flex flex-col items-center">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-xs fw-bold border-2 transition-colors"
                style={{
                  background: isComplete || isCurrent
                    ? "var(--color-brand-400)"
                    : "transparent",
                  borderColor: isComplete || isCurrent
                    ? "var(--color-brand-400)"
                    : "var(--color-border-default)",
                  color: isComplete || isCurrent
                    ? "#FFFFFF"
                    : "var(--color-text-tertiary)",
                  boxShadow: isCurrent
                    ? "0 0 0 4px rgba(59, 111, 212, 0.2)"
                    : "none",
                }}
              >
                {isComplete ? "✓" : stage}
              </div>
              <span
                className="text-[11px] font-medium mt-2 whitespace-nowrap"
                style={{
                  color: isCurrent
                    ? "var(--color-text-primary)"
                    : isPending
                      ? "var(--color-text-tertiary)"
                      : "var(--color-text-secondary)",
                }}
              >
                {STAGE_LABELS[stage]}
              </span>
            </div>

            {/* Connector line */}
            {i < stages.length - 1 && (
              <div
                className="flex-1 h-0.5 mx-3 mt-[-20px]"
                style={{
                  background: isComplete
                    ? "var(--color-brand-400)"
                    : "var(--color-border-default)",
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
