"use client";

import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { dataQualityApi } from "@/lib/api-extra";
import { formatNumber, formatDate, formatPercent } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageLoader } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import {
  ShieldCheck,
  Play,
  Activity,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

export default function DataQualityPage() {
  const queryClient = useQueryClient();
  const toast = useToast();

  const { data: overview, isLoading } = useQuery({
    queryKey: ["dq-overview"],
    queryFn: () => dataQualityApi.overview().then((r) => r.data),
  });

  const { data: history } = useQuery({
    queryKey: ["dq-history"],
    queryFn: () => dataQualityApi.history({ limit: 10 }).then((r) => r.data),
    retry: false,
  });

  const scanMutation = useMutation({
    mutationFn: () => dataQualityApi.scan().then((r) => r.data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["dq-overview"] });
      queryClient.invalidateQueries({ queryKey: ["dq-history"] });
      toast.success(
        "Scan complete",
        `Health score: ${data.overall_score || data.health_score || "calculated"}`
      );
    },
    onError: () => {
      toast.error("Scan failed", "Could not run data quality scan");
    },
  });

  if (isLoading) return <PageLoader />;

  const healthScore = overview?.health_score || overview?.overall_score || 0;
  const entityCounts = overview?.entity_counts || overview?.entities || {};
  const scanHistory = Array.isArray(history?.scans)
    ? history.scans
    : Array.isArray(history)
    ? history
    : [];

  const scoreColor =
    healthScore >= 80
      ? "text-emerald-600"
      : healthScore >= 60
      ? "text-amber-600"
      : "text-red-600";

  const entityChartData = Object.entries(entityCounts).map(([key, val]) => ({
    name: key.replace(/_/g, " "),
    count: (val as Record<string, number>)?.total || (val as number) || 0,
    issues: (val as Record<string, number>)?.issues || 0,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Data Quality</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Monitor and improve data health across your portfolio
          </p>
        </div>
        <Button
          onClick={() => scanMutation.mutate()}
          loading={scanMutation.isPending}
          icon={<Play className="h-4 w-4" />}
        >
          Run Scan
        </Button>
      </div>

      {/* Score + stats */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <Card className="sm:col-span-1">
          <CardContent className="p-5 flex flex-col items-center justify-center text-center">
            <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">
              Health Score
            </p>
            <p className={`text-4xl font-bold ${scoreColor}`}>
              {formatNumber(healthScore)}
            </p>
            <p className="text-xs text-slate-400 mt-1">/ 100</p>
            <Badge
              variant={
                healthScore >= 80
                  ? "success"
                  : healthScore >= 60
                  ? "warning"
                  : "danger"
              }
              className="mt-2"
            >
              {healthScore >= 80
                ? "Healthy"
                : healthScore >= 60
                ? "Needs Attention"
                : "Critical"}
            </Badge>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-emerald-50 p-2">
              <CheckCircle className="h-4 w-4 text-emerald-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-emerald-600">
                {overview?.valid_records || overview?.clean || 0}
              </p>
              <p className="text-xs text-slate-500">Clean Records</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-amber-50 p-2">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-amber-600">
                {overview?.issues_found || overview?.warnings || 0}
              </p>
              <p className="text-xs text-slate-500">Issues Found</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-blue-50 p-2">
              <Activity className="h-4 w-4 text-blue-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-blue-600">
                {scanHistory.length}
              </p>
              <p className="text-xs text-slate-500">Scans Run</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Entity breakdown */}
        <Card>
          <CardHeader>
            <CardTitle>Entity Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-56">
              {entityChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={entityChartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" fontSize={11} />
                    <YAxis fontSize={11} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} name="Total" />
                    <Bar dataKey="issues" fill="#f59e0b" radius={[4, 4, 0, 0]} name="Issues" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-slate-400">
                  Run a scan to see entity breakdown
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Scan history */}
        <Card>
          <CardHeader>
            <CardTitle>Scan History</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {scanHistory.length > 0 ? (
              <div className="divide-y divide-slate-100">
                {scanHistory.slice(0, 8).map(
                  (
                    scan: {
                      id?: string;
                      score?: number;
                      health_score?: number;
                      created_at?: string;
                      issues_found?: number;
                      entities_scanned?: number;
                    },
                    i: number
                  ) => (
                    <div
                      key={scan.id || i}
                      className="flex items-center justify-between px-6 py-3"
                    >
                      <div>
                        <p className="text-sm font-medium text-slate-900">
                          Scan #{scanHistory.length - i}
                        </p>
                        <p className="text-xs text-slate-500">
                          {formatDate(scan.created_at)}
                        </p>
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge
                          variant={
                            (scan.score || scan.health_score || 0) >= 80
                              ? "success"
                              : (scan.score || scan.health_score || 0) >= 60
                              ? "warning"
                              : "danger"
                          }
                        >
                          {scan.score || scan.health_score || 0}%
                        </Badge>
                      </div>
                    </div>
                  )
                )}
              </div>
            ) : (
              <p className="px-6 py-8 text-center text-sm text-slate-400">
                No scans run yet
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
