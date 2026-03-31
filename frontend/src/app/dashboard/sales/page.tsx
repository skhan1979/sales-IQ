"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { salesApi } from "@/lib/api";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PageLoader } from "@/components/ui/spinner";
import { ShoppingBag, TrendingUp, AlertCircle, Zap, Users } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";

const PIE_COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"];

export default function SalesDashboardPage() {
  const { data: summary, isLoading, isError } = useQuery({
    queryKey: ["sales-summary"],
    queryFn: () => salesApi.summary().then((r) => r.data),
    retry: false,
  });

  const { data: churnWatchlist } = useQuery({
    queryKey: ["churn-watchlist"],
    queryFn: () => salesApi.churnWatchlist().then((r) => r.data),
    retry: false,
  });

  const { data: growthOps } = useQuery({
    queryKey: ["growth-opportunities"],
    queryFn: () => salesApi.growthOpportunities().then((r) => r.data),
    retry: false,
  });

  const { data: reorderAlerts } = useQuery({
    queryKey: ["reorder-alerts"],
    queryFn: () => salesApi.reorderAlerts().then((r) => r.data),
    retry: false,
  });

  if (isLoading) return <PageLoader />;

  const churnList = Array.isArray(churnWatchlist?.customers) ? churnWatchlist.customers : Array.isArray(churnWatchlist) ? churnWatchlist : [];
  const opportunities = Array.isArray(growthOps?.opportunities) ? growthOps.opportunities : Array.isArray(growthOps) ? growthOps : [];
  const reorders = Array.isArray(reorderAlerts?.customers) ? reorderAlerts.customers : Array.isArray(reorderAlerts) ? reorderAlerts : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Sales Dashboard</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Churn watchlist, growth opportunities, and reorder intelligence
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-red-50 p-2"><AlertCircle className="h-4 w-4 text-red-600" /></div>
            <div>
              <p className="text-lg font-bold text-red-600">{churnList.length}</p>
              <p className="text-xs text-slate-500">Churn Risk</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-emerald-50 p-2"><TrendingUp className="h-4 w-4 text-emerald-600" /></div>
            <div>
              <p className="text-lg font-bold text-emerald-600">{opportunities.length}</p>
              <p className="text-xs text-slate-500">Growth Opportunities</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-blue-50 p-2"><ShoppingBag className="h-4 w-4 text-blue-600" /></div>
            <div>
              <p className="text-lg font-bold text-blue-600">{reorders.length}</p>
              <p className="text-xs text-slate-500">Reorder Alerts</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-indigo-50 p-2"><Zap className="h-4 w-4 text-indigo-600" /></div>
            <div>
              <p className="text-lg font-bold text-indigo-600">
                {formatCurrency(summary?.total_revenue_ytd)}
              </p>
              <p className="text-xs text-slate-500">Revenue YTD</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Churn Watchlist */}
        <Card>
          <CardHeader>
            <CardTitle>Churn Watchlist</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {churnList.length > 0 ? (
              <div className="divide-y divide-slate-100">
                {churnList.slice(0, 8).map((c: Record<string, unknown>, i: number) => (
                  <div key={i} className="flex items-center justify-between px-6 py-3">
                    <div>
                      <p className="text-sm font-medium text-slate-900">{(c.customer_name as string) || "Customer"}</p>
                      <p className="text-xs text-slate-500">{(c.reason as string) || "Declining activity"}</p>
                    </div>
                    <Badge variant="danger">
                      {c.churn_probability ? `${formatPercent(c.churn_probability as number)} risk` : "High"}
                    </Badge>
                  </div>
                ))}
              </div>
            ) : (
              <p className="px-6 py-8 text-center text-sm text-slate-400">No churn risks detected</p>
            )}
          </CardContent>
        </Card>

        {/* Growth Opportunities */}
        <Card>
          <CardHeader>
            <CardTitle>Growth Opportunities</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {opportunities.length > 0 ? (
              <div className="divide-y divide-slate-100">
                {opportunities.slice(0, 8).map((op: Record<string, unknown>, i: number) => (
                  <div key={i} className="flex items-center justify-between px-6 py-3">
                    <div>
                      <p className="text-sm font-medium text-slate-900">{(op.customer_name as string) || "Customer"}</p>
                      <p className="text-xs text-slate-500 capitalize">{((op.type as string) || "expansion").replace("_", " ")}</p>
                    </div>
                    <span className="text-sm font-medium text-emerald-600">
                      {formatCurrency(op.potential_value as number)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="px-6 py-8 text-center text-sm text-slate-400">Import data or generate demo data to see opportunities</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
