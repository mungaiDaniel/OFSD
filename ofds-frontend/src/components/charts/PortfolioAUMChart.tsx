import { Line } from "react-chartjs-2";
import { baseChartOptions, getFundColor } from "@/lib/chartConfig";
import type { ChartData, ChartOptions } from "chart.js";

interface PortfolioAUMData {
  labels: string[];
  funds: { name: string; data: number[]; growth: number[] }[];
}

interface Props {
  data: PortfolioAUMData;
  height?: number;
}

export function PortfolioAUMChart({ data, height = 280 }: Props) {
  // Filter out funds with zero data to avoid broken segments
  const activeFunds = data.funds.filter((fund) => fund.data.some((val) => val > 0));

  const chartData: ChartData<"line"> = {
    labels: data.labels,
    datasets: activeFunds.map((fund) => {
      const fundColor = getFundColor(fund.name);
      const rgbaColor = fundColor.replace("#", "").match(/.{1,2}/g)?.map(x => parseInt(x, 16)).join(",");
      
      return {
        label: fund.name,
        data: fund.data,
        growthData: fund.growth, // custom property for tooltips
        borderColor: fundColor, // Use fund-specific color (Axiom: #0066ff, Atium: #22c55e)
        backgroundColor: `rgba(${rgbaColor}, 0.15)`, // Soft transparent fill per fund
        fill: true,
        tension: 0.3,
        pointRadius: 3,
        pointBackgroundColor: fundColor,
        borderWidth: 2,
      };
    }),
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
            const rawValue = context.raw as number;
            
            // Format currency
            const formattedBal = new Intl.NumberFormat('en-US', {
              style: 'currency',
              currency: 'USD',
              minimumFractionDigits: 2,
            }).format(rawValue);

            const dataset = context.dataset as any;
            const growth = dataset.growthData ? dataset.growthData[context.dataIndex] : 0;
            const growthStr = growth >= 0 ? `+${growth.toFixed(2)}%` : `${growth.toFixed(2)}%`;

            return `Balance: ${formattedBal} | Growth: ${growthStr}`;
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
      x: {
        ...baseChartOptions.scales?.x,
        grid: {
          display: false, // Remove vertical grid lines
        }
      },
      y: {
        ...baseChartOptions.scales?.y,
        grid: {
          display: false, // Remove horizontal grid lines
        },
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
      <Line data={chartData} options={options} />
    </div>
  );
}
