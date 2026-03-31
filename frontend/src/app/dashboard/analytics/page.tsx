"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { analyticsApi } from "@/lib/api";
import { formatCurrency, formatNumber, formatPercent, compactNumber } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageLoader } from "@/components/ui/spinner";
import { BarChart3, TrendingUp, PieChart as PieChartIcon, Activity } from "lucide-react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, AreaChart, Area,
} from "recharts";

export default function AnalyticsPage() {
  const { data: kpis, isLoading, isError } = useQuery({
    queryKey: ["analytics-kpis"],
    queryFn: () => analyticsApi.kpis().then((r) => r.data),
    retry: false,
  });

  const { data: trends } = useQuery({
    queryKey: ["analytics-trends"],
    queryFn: () => analyticsApi.trends({ metric: "total_ar", granularity: "monthly" }).then((r) => r.data),
    retry: false,
  });

  if (isLoading) return <PageLoader />;

  const kpiData = kpis || {};
  const trendData = Array.isArray(trends?.data) ? trends.data : Array.isArray(trends) ? trends : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Analytics</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          KPI trends, comparative analysis, and performance reporting
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 mb-1">Total AR</p>
            <p className="text-xl font-bold text-slate-900">{formatCurrency(kpiData.total_ar)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 mb-1">DSO</p>
            <p className="text-xl font-bold text-slate-900">
              {kpiData.dso != null ? `${formatNumber(kpiData.dso)} days` : "—"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 mb-1">Collection Rate</p>
            <p className="text-xl font-bold text-emerald-600">
              {formatPercent(kpiData.collection_rate)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 mb-1">Overdue %</p>
            <p className="text-xl font-bold text-red-600">
              {formatPercent(kpiData.overdue_percentage)}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Total AR Trend</CardTitle></CardHeader>
        <CardContent>
          <div className="h-72">
            {trendData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="period" fontSize={11} />
                  <YAxis fontSize={11} tickFormatter={(v: number) => compactNumber(v)} />
                  <Tooltip formatter={(v: number) => [formatCurrency(v), "Total AR"]} />
                  <Area type="monotone" dataKey="value" stroke="#6366f1" fill="#eef2ff" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-slate-400">
                Import data or generate demo data to see analytics trends
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
