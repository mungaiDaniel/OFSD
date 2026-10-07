import { Bar } from "react-chartjs-2";
import { baseChartOptions, FLOW_COLORS } from "@/lib/chartConfig";
import type { ChartData, ChartOptions } from "chart.js";

interface FlowData {
  labels: string[];
  deposits: number[];
  withdrawals: number[];
}

interface FlowDataset {
  label: string;
  data: number[];
  backgroundColor: string;
}

interface Props {
  data: FlowData;
  datasets?: FlowDataset[];
  height?: number;
}

export function DepositsWithdrawalsBarChart({ data, datasets, height = 280 }: Props) {
  const chartData: ChartData<"bar"> = {
    labels: data.labels,
    datasets: (datasets && datasets.length > 0 ? datasets : [
      {
        label: "Deposits",
        data: data.deposits,
        backgroundColor: FLOW_COLORS.deposit,
      },
      {
        label: "Withdrawals",
        data: data.withdrawals,
        backgroundColor: FLOW_COLORS.withdrawal,
      },
    ]).map((d) => ({
      ...d,
      borderRadius: 3,
      barPercentage: 0.7,
    })),
  };

  const options: ChartOptions<"bar"> = {
    ...baseChartOptions,
    scales: {
      ...baseChartOptions.scales,
      y: {
        ...baseChartOptions.scales?.y,
        ticks: {
          ...((baseChartOptions.scales?.y as Record<string, unknown>)?.ticks as object),
          callback: (v) => {
            const num = Number(v);
            if (num >= 1_000_000) return "$" + (num / 1_000_000).toFixed(1) + "M";
            if (num >= 1_000) return "$" + (num / 1_000).toFixed(0) + "K";
            return "$" + num;
          },
        },
      },
    },
  };

  return (
    <div style={{ position: "relative", height }}>
      <Bar data={chartData} options={options} />
    </div>
  );
}
