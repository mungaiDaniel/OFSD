import { Line } from "react-chartjs-2";
import { baseChartOptions, getFundColor } from "@/lib/chartConfig";
import type { ChartData, ChartOptions } from "chart.js";

interface FundPerformanceData {
  labels: string[];
  funds: { name: string; data: (number | null)[] }[];
}

interface Props {
  data: FundPerformanceData;
  height?: number;
}

export function FundPerformanceLineChart({ data, height = 280 }: Props) {
  const chartData: ChartData<"line"> = {
    labels: data.labels,
    datasets: data.funds.map((fund) => ({
      label: fund.name,
      data: fund.data,
      borderColor: getFundColor(fund.name),
      backgroundColor: getFundColor(fund.name) + "14",
      fill: true,
      tension: 0.3,
      pointRadius: 3,
      pointBackgroundColor: getFundColor(fund.name),
      borderWidth: 2,
    })),
  };

  const options: ChartOptions<"line"> = {
    ...baseChartOptions,
    interaction: {
      mode: "index",
      intersect: false,
    },
    plugins: {
      ...baseChartOptions.plugins,
      tooltip: {
        callbacks: {
          label: function (context) {
            const val = context.raw as number;
            return `${val.toFixed(2)}%`;
          },
          afterLabel: function (context) {
            // Show "Last Valuation" text on the final data point
            const isLastPoint = context.dataIndex === data.labels.length - 1;
            if (isLastPoint && data.labels.length > 0) {
              return "Last Valuation: " + data.labels[context.dataIndex];
            }
            return "";
          }
        }
      }
    },
    scales: {
      ...baseChartOptions.scales,
      y: {
        ...baseChartOptions.scales?.y,
        ticks: {
          ...((baseChartOptions.scales?.y as Record<string, unknown>)?.ticks as object),
          callback: (v) => v + "%",
        },
      },
    },
  };

  return (
    <div style={{ position: "relative", height }}>
      <Line data={chartData} options={options} />
    </div>
  );
}
