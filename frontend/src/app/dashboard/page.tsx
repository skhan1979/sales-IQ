"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/lib/auth";
import { dashboardApi, executiveApi } from "@/lib/api";
import {
  formatCurrency,
  formatNumber,
  formatPercent,
  compactNumber,
} from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PageLoader } from "@/components/ui/spinner";
import {
  DollarSign,
  Clock,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  Users,
  FileText,
  BarChart3,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
} from "recharts";

interface KPICardProps {
  title: string;
  value: string;
  subtitle?: string;
  change?: number;
  icon: React.ElementType;
  color: string;
}

function KPICard({ title, value, subtitle, change, icon: Icon, color }: KPICardProps) {
  const isPositive = change != null && change >= 0;
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
              {title}
            </p>
            <p className="text-2xl font-bold text-slate-900">{value}</p>
            {subtitle && (
              <p className="text-xs text-slate-500">{subtitle}</p>
            )}
          </div>
          <div className={`rounded-xl p-2.5 ${color}`}>
            <Icon className="h-5 w-5" />
          </div>
        </div>
        {change != null && (
          <div className="mt-3 flex items-center gap-1">
            {isPositive ? (
              <TrendingUp className="h-3.5 w-3.5 text-emerald-600" />
            ) : (
              <TrendingDown className="h-3.5 w-3.5 text-red-600" />
            )}
            <span
              className={`text-xs font-medium ${
                isPositive ? "text-emerald-600" : "text-red-600"
              }`}
            >
              {isPositive ? "+" : ""}
              {formatPercent(change)} vs last month
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const AGING_COLORS = ["#10b981", "#f59e0b", "#f97316", "#ef4444", "#991b1b"];

export default function DashboardPage() {
  const { user } = useAuth();

  const { data: arSummary, isLoading: arLoading } = useQuery({
    queryKey: ["ar-summary"],
    queryFn: () => dashboardApi.arSummary().then((r) => r.data),
  });

  const { data: topOverdue, isLoading: overdueLoading } = useQuery({
    queryKey: ["top-overdue"],
    queryFn: () => dashboardApi.topOverdue(8).then((r) => r.data),
  });

  const { data: collectionEff, isLoading: effLoading } = useQuery({
    queryKey: ["collection-effectiveness"],
    queryFn: () => dashboardApi.collectionEffectiveness(12).then((r) => r.data),
  });

  const { data: execDashboard } = useQuery({
    queryKey: ["executive-dashboard"],
    queryFn: () => executiveApi.dashboard().then((r) => r.data),
    retry: false,
  });

  const isLoading = arLoading;

  if (isLoading) return <PageLoader />;

  const summary = arSummary || {};
  const agingData = Array.isArray(summary.aging_buckets)
    ? summary.aging_buckets.map(
        (b: { bucket: string; amount: string | number; count: number }, i: number) => ({
          name: b.bucket === "current" ? "Current" : b.bucket,
          amount: typeof b.amount === "string" ? parseFloat(b.amount) : b.amount,
          fill: AGING_COLORS[i] || "#64748b",
        })
      )
    : typeof summary.aging_buckets === "object" && summary.aging_buckets
    ? Object.entries(summary.aging_buckets).map(([name, value], i) => ({
        name: name === "current" ? "Current" : name,
        amount: typeof value === "string" ? parseFloat(value as string) : (value as number),
        fill: AGING_COLORS[i] || "#64748b",
      }))
    : [
        { name: "Current", amount: 0, fill: AGING_COLORS[0] },
        { name: "1-30", amount: 0, fill: AGING_COLORS[1] },
        { name: "31-60", amount: 0, fill: AGING_COLORS[2] },
        { name: "61-90", amount: 0, fill: AGING_COLORS[3] },
        { name: "90+", amount: 0, fill: AGING_COLORS[4] },
      ];

  // Parse string amounts from API
  const totalReceivables = typeof summary.total_receivables === "string"
    ? parseFloat(summary.total_receivables) : summary.total_receivables;
  const totalOverdue = typeof summary.total_overdue === "string"
    ? parseFloat(summary.total_overdue) : summary.total_overdue;

  const collectionData = Array.isArray(collectionEff?.months)
    ? collectionEff.months
    : Array.isArray(collectionEff)
    ? collectionEff
    : [];

  const overdueList = Array.isArray(topOverdue?.invoices)
    ? topOverdue.invoices
    : Array.isArray(topOverdue)
    ? topOverdue
    : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-slate-900">
          Good {new Date().getHours() < 12 ? "morning" : new Date().getHours() < 17 ? "afternoon" : "evening"},{" "}
          {user?.full_name?.split(" ")[0] || "there"}
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Here&apos;s your accounts receivable overview
        </p>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title="Total Receivables"
          value={formatCurrency(totalReceivables)}
          subtitle={`${formatNumber(summary.total_customers || 0)} customers`}
          icon={DollarSign}
          color="bg-blue-50 text-blue-600"
        />
        <KPICard
          title="Total Overdue"
          value={formatCurrency(totalOverdue)}
          subtitle={`${formatNumber(summary.customers_on_credit_hold || 0)} on credit hold`}
          change={summary.overdue_change}
          icon={AlertCircle}
          color="bg-red-50 text-red-600"
        />
        <KPICard
          title="Days Sales Outstanding"
          value={`${formatNumber(summary.average_dso || summary.dso || 0)} days`}
          subtitle="Weighted average"
          change={summary.dso_change}
          icon={Clock}
          color="bg-amber-50 text-amber-600"
        />
        <KPICard
          title="Collection Rate"
          value={formatPercent(summary.collection_rate)}
          subtitle="Last 30 days"
          change={summary.collection_rate_change}
          icon={TrendingUp}
          color="bg-emerald-50 text-emerald-600"
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Aging Distribution */}
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle>Aging Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={agingData} layout="vertical" margin={{ left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis
                    type="number"
                    tickFormatter={(v: number) => compactNumber(v)}
                    fontSize={11}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={60}
                    fontSize={11}
                  />
                  <Tooltip
                    formatter={(value: number) => [
                      formatCurrency(value),
                      "Amount",
                    ]}
                  />
                  <Bar dataKey="amount" radius={[0, 4, 4, 0]}>
                    {agingData.map((entry: { fill?: string }, index: number) => (
                      <Cell key={index} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Collection Effectiveness Trend */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Collection Effectiveness</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-64">
              {collectionData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={collectionData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="month" fontSize={11} />
                    <YAxis fontSize={11} tickFormatter={(v: number) => compactNumber(v)} />
                    <Tooltip
                      formatter={(value: number, name: string) => [
                        formatCurrency(value),
                        name === "invoiced" ? "Invoiced" : "Collected",
                      ]}
                    />
                    <Line
                      type="monotone"
                      dataKey="invoiced"
                      stroke="#6366f1"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="collected"
                      stroke="#10b981"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-slate-400">
                  No collection data available yet. Generate demo data to see trends.
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Bottom Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Top Overdue */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Top Overdue Invoices</CardTitle>
            <Badge variant="danger" dot>
              {overdueList.length || 0} overdue
            </Badge>
          </CardHeader>
          <CardContent className="p-0">
            {overdueList.length > 0 ? (
              <div className="divide-y divide-slate-100">
                {overdueList.slice(0, 6).map(
                  (
                    inv: {
                      id: string;
                      invoice_number?: string;
                      customer_name?: string;
                      customer_id?: string;
                      total_amount?: number;
                      amount?: number | string;
                      amount_remaining?: number | string;
                      days_overdue?: number;
                    },
                    i: number
                  ) => (
                    <div
                      key={inv.id || i}
                      className="flex items-center justify-between px-6 py-3"
                    >
                      <div>
                        <p className="text-sm font-medium text-slate-900">
                          {inv.invoice_number || `INV-${i + 1}`}
                        </p>
                        <p className="text-xs text-slate-500">
                          {inv.customer_name || (inv.customer_id ? `Customer ${inv.customer_id.slice(0, 8)}` : "Unknown Customer")}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-semibold text-slate-900">
                          {formatCurrency(typeof inv.amount === "string" ? parseFloat(inv.amount) : (inv.amount ?? inv.total_amount))}
                        </p>
                        <p className="text-xs text-red-600">
                          {inv.days_overdue || 0} days overdue
                        </p>
                      </div>
                    </div>
                  )
                )}
              </div>
            ) : (
              <div className="px-6 py-8 text-center text-sm text-slate-400">
                No overdue invoices found
              </div>
            )}
          </CardContent>
        </Card>

        {/* AI Summary */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>AI Executive Summary</CardTitle>
            <Badge variant="info" dot>
              Auto-generated
            </Badge>
          </CardHeader>
          <CardContent>
            {execDashboard?.ai_summary ? (
              <div className="space-y-3">
                <p className="text-sm text-slate-700 leading-relaxed">
                  {execDashboard.ai_summary}
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-start gap-3 rounded-lg bg-blue-50 p-4">
                  <BarChart3 className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-blue-800">
                      Platform Ready
                    </p>
                    <p className="text-xs text-blue-600 mt-1">
                      Your SalesIQ instance is operational. Generate demo data
                      from Admin to see AI-powered insights, aging analysis,
                      and predictive forecasts.
                    </p>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="rounded-lg border border-slate-200 p-3 text-center">
                    <Users className="h-4 w-4 text-slate-400 mx-auto mb-1" />
                    <p className="text-lg font-bold text-slate-900">
                      {formatNumber(summary.total_customers || 0)}
                    </p>
                    <p className="text-[10px] text-slate-500">Customers</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 p-3 text-center">
                    <FileText className="h-4 w-4 text-slate-400 mx-auto mb-1" />
                    <p className="text-lg font-bold text-slate-900">
                      {formatNumber(summary.total_invoices || 0)}
                    </p>
                    <p className="text-[10px] text-slate-500">Invoices</p>
                  </div>
                  <div className="rounded-lg border border-slate-200 p-3 text-center">
                    <DollarSign className="h-4 w-4 text-slate-400 mx-auto mb-1" />
                    <p className="text-lg font-bold text-slate-900">
                      {compactNumber(summary.total_receivables || 0)}
                    </p>
                    <p className="text-[10px] text-slate-500">Total AR</p>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
