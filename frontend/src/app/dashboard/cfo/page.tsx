"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { cfoApi } from "@/lib/api";
import { formatCurrency, formatNumber, formatPercent, compactNumber } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PageLoader } from "@/components/ui/spinner";
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Clock,
  AlertCircle,
  BarChart3,
} from "lucide-react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from "recharts";

export default function CFODashboardPage() {
  const { data: dsoTrend, isLoading: dsoLoading, isError: dsoError } = useQuery({
    queryKey: ["cfo-dso-trend"],
    queryFn: () => cfoApi.dsoTrend().then((r) => r.data),
    retry: false,
  });

  const { data: overdueTrend } = useQuery({
    queryKey: ["cfo-overdue-trend"],
    queryFn: () => cfoApi.overdueTrend().then((r) => r.data),
    retry: false,
  });

  const { data: cashFlow } = useQuery({
    queryKey: ["cfo-cash-flow"],
    queryFn: () => cfoApi.cashFlowForecast().then((r) => r.data),
    retry: false,
  });

  const { data: topOverdue } = useQuery({
    queryKey: ["cfo-top-overdue"],
    queryFn: () => cfoApi.topOverdueCustomers(10).then((r) => r.data),
    retry: false,
  });

  if (dsoLoading) return <PageLoader />;

  const dsoData = Array.isArray(dsoTrend?.months) ? dsoTrend.months : Array.isArray(dsoTrend) ? dsoTrend : [];
  const overdueData = Array.isArray(overdueTrend?.months) ? overdueTrend.months : Array.isArray(overdueTrend) ? overdueTrend : [];
  const cashFlowData = cashFlow?.periods || cashFlow?.forecast || [];
  const topCustomers = Array.isArray(topOverdue?.customers) ? topOverdue.customers : Array.isArray(topOverdue) ? topOverdue : [];
  const latestDso = dsoData.length > 0 ? dsoData[dsoData.length - 1]?.dso : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">CFO Dashboard</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            DSO trends, cash flow forecasts, and credit exposure
          </p>
        </div>
        <Badge variant="info" dot>Live Data</Badge>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wide">Current DSO</p>
                <p className="text-2xl font-bold text-slate-900 mt-1">
                  {latestDso != null ? `${formatNumber(latestDso)} days` : "—"}
                </p>
              </div>
              <div className="rounded-xl bg-blue-50 p-2.5">
                <Clock className="h-5 w-5 text-blue-600" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wide">Cash Forecast (30d)</p>
                <p className="text-2xl font-bold text-emerald-600 mt-1">
                  {Array.isArray(cashFlowData) && cashFlowData.length > 0
                    ? formatCurrency(cashFlowData[0]?.predicted_amount || cashFlowData[0]?.amount)
                    : "—"}
                </p>
              </div>
              <div className="rounded-xl bg-emerald-50 p-2.5">
                <DollarSign className="h-5 w-5 text-emerald-600" />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wide">Top Overdue Customers</p>
                <p className="text-2xl font-bold text-red-600 mt-1">{topCustomers.length}</p>
              </div>
              <div className="rounded-xl bg-red-50 p-2.5">
                <AlertCircle className="h-5 w-5 text-red-600" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle>DSO Trend</CardTitle></CardHeader>
          <CardContent>
            <div className="h-64">
              {dsoData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={dsoData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="month" fontSize={11} />
                    <YAxis fontSize={11} />
                    <Tooltip />
                    <Line type="monotone" dataKey="dso" stroke="#6366f1" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-slate-400">
                  Import data or generate demo data to see DSO trends
                </div>
              )}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Overdue Amount Trend</CardTitle></CardHeader>
          <CardContent>
            <div className="h-64">
              {overdueData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={overdueData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="month" fontSize={11} />
                    <YAxis fontSize={11} tickFormatter={(v: number) => compactNumber(v)} />
                    <Tooltip formatter={(v: number) => [formatCurrency(v), "Overdue"]} />
                    <Area type="monotone" dataKey="overdue_amount" stroke="#ef4444" fill="#fef2f2" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-slate-400">
                  Import data or generate demo data to see overdue trends
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Top Overdue Customers */}
      <Card>
        <CardHeader>
          <CardTitle>Top Overdue Customers</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {topCustomers.length > 0 ? (
            <div className="divide-y divide-slate-100">
              {topCustomers.slice(0, 8).map((c: Record<string, unknown>, i: number) => (
                <div key={i} className="flex items-center justify-between px-6 py-3">
                  <div>
                    <p className="text-sm font-medium text-slate-900">
                      {(c.customer_name as string) || `Customer ${i + 1}`}
                    </p>
                    <p className="text-xs text-slate-500">{(c.territory as string) || "—"}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold text-red-600">
                      {formatCurrency(c.overdue_amount as number)}
                    </p>
                    <p className="text-xs text-slate-500">
                      {c.days_overdue ? `${c.days_overdue}d overdue` : "—"}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="px-6 py-8 text-center text-sm text-slate-400">No overdue customers</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
