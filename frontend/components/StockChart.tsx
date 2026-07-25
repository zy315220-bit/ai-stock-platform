"use client";

import {
  CandlestickSeries,
  ColorType,
  createChart,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import type { Candle, LinePoint } from "@/types/stock";

type Props = {
  candles: Candle[];
  ma20: LinePoint[];
  ma60: LinePoint[];
};

export default function StockChart({
  candles,
  ma20,
  ma60,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  const chartRef = useRef<IChartApi | null>(null);

  const candleSeriesRef =
    useRef<ISeriesApi<"Candlestick"> | null>(null);

  const ma20SeriesRef =
    useRef<ISeriesApi<"Line"> | null>(null);

  const ma60SeriesRef =
    useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    const container = containerRef.current;

    if (!container) {
      return;
    }

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 390,
      layout: {
        background: {
          type: ColorType.Solid,
          color: "#101722",
        },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: {
          color: "#1d2938",
        },
        horzLines: {
          color: "#1d2938",
        },
      },
      rightPriceScale: {
        borderColor: "#2a3647",
      },
      timeScale: {
        borderColor: "#2a3647",
      },
    });

    const candleSeries = chart.addSeries(
      CandlestickSeries,
      {
        upColor: "#ef4444",
        downColor: "#22c55e",
        borderVisible: false,
        wickUpColor: "#ef4444",
        wickDownColor: "#22c55e",
      },
    );

    const ma20Series = chart.addSeries(LineSeries, {
      color: "#38bdf8",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    const ma60Series = chart.addSeries(LineSeries, {
      color: "#a78bfa",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    ma20SeriesRef.current = ma20Series;
    ma60SeriesRef.current = ma60Series;

    const observer = new ResizeObserver(() => {
      const currentContainer = containerRef.current;

      if (!currentContainer) {
        return;
      }

      chart.applyOptions({
        width: currentContainer.clientWidth,
      });
    });

    observer.observe(container);

    return () => {
      observer.disconnect();
      chart.remove();

      chartRef.current = null;
      candleSeriesRef.current = null;
      ma20SeriesRef.current = null;
      ma60SeriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    candleSeriesRef.current?.setData(
      candles.map((item) => ({
        time: item.time as Time,
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close,
      })),
    );

    ma20SeriesRef.current?.setData(
      ma20.map((item) => ({
        time: item.time as Time,
        value: item.value,
      })),
    );

    ma60SeriesRef.current?.setData(
      ma60.map((item) => ({
        time: item.time as Time,
        value: item.value,
      })),
    );

    if (candles.length > 0) {
      chartRef.current?.timeScale().fitContent();
    }
  }, [candles, ma20, ma60]);

  return (
    <div
      className="chart-container"
      ref={containerRef}
    />
  );
}