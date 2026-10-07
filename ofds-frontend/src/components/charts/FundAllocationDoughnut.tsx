import { Doughnut } from "react-chartjs-2";
import { doughnutOptions, getFundColor } from "@/lib/chartConfig";
import type { ChartData } from "chart.js";

interface AllocationData {
  funds: { name: string; value: number }[];
}

interface Props {
  data: AllocationData;
  height?: number;
}

export function FundAllocationDoughnut({ data, height = 280 }: Props) {
  const total = data.funds.reduce((sum, f) => sum + f.value, 0);

  const chartData: ChartData<"doughnut"> = {
    labels: data.funds.map((f) => f.name),
    datasets: [
      {
        data: data.funds.map((f) => f.value),
        backgroundColor: data.funds.map((f) => getFundColor(f.name)),
        borderWidth: 0,
        hoverOffset: 6,
      },
    ],
  };

  return (
    <div style={{ position: "relative", height }}>
      <Doughnut data={chartData} options={doughnutOptions} />
      {/* Center label */}
      <div
        className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none"
      >
        <span
          className="text-lg fw-bold"
          style={{ fontFamily: "var(--font-mono)", color: "var(--color-text-primary)" }}
        >
          {total >= 1_000_000
            ? `$${(total / 1_000_000).toFixed(1)}M`
            : `$${(total / 1_000).toFixed(0)}K`}
        </span>
        <span className="text-[10px]" style={{ color: "var(--color-text-tertiary)" }}>
          Total AUM
        </span>
      </div>
    </div>
  );
}
