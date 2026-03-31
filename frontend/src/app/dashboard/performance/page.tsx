"use client";

import React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { performanceApi } from "@/lib/api-extra";
import { formatNumber } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageLoader } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import {
  Activity,
  Zap,
  Database,
  HardDrive,
  Trash2,
  Clock,
  AlertTriangle,
  CheckCircle,
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
} from "recharts";

export default function PerformancePage() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const { data: summary, isLoading } = useQuery({
    queryKey: ["perf-summary"],
    queryFn: () => performanceApi.summary().then((r) => r.data),
  });

  const { data: dbStats } = useQuery({
    queryKey: ["perf-db"],
    queryFn: () => performanceApi.db().then((r) => r.data),
    retry: false,
  });

  const { data: cacheStats } = useQuery({
    queryKey: ["perf-cache"],
    queryFn: () => performanceApi.cache().then((r) => r.data),
    retry: false,
  });

  const { data: indexStats } = useQuery({
    queryKey: ["perf-indexes"],
    queryFn: () => performanceApi.indexes().then((r) => r.data),
    retry: false,
  });

  const clearCacheMutation = useMutation({
    mutationFn: () => performanceApi.clearCache().then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["perf-cache"] });
      toast.success("Cache cleared");
    },
  });

  if (isLoading) return <PageLoader />;

  const metrics = summary || {};
  const slowEndpoints = Array.isArray(metrics.slow_endpoints)
    ? metrics.slow_endpoints
    : [];
  const db = dbStats || {};
  const cache = cacheStats || {};
  const indexes = indexStats || {};

  const endpointChartData = slowEndpoints.slice(0, 10).map((ep: Record<string, unknown>) => ({
    name: ((ep.path as string) || "").replace("/api/v1/", "").slice(0, 25),
    avg: (ep.avg_ms as number) || (ep.avg_response_time as number) || 0,
    p95: (ep.p95_ms as number) || (ep.p95 as number) || 0,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Performance</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            API response times, database health, and cache statistics
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => clearCacheMutation.mutate()}
          loading={clearCacheMutation.isPending}
          icon={<Trash2 className="h-3.5 w-3.5" />}
        >
          Clear Cache
        </Button>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-blue-50 p-2"><Zap className="h-4 w-4 text-blue-600" /></div>
            <div>
              <p className="text-lg font-bold text-blue-600">
                {metrics.avg_response_ms || metrics.avg_response_time || "—"}ms
              </p>
              <p className="text-xs text-slate-500">Avg Response</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-emerald-50 p-2"><Activity className="h-4 w-4 text-emerald-600" /></div>
            <div>
              <p className="text-lg font-bold text-emerald-600">
                {metrics.total_requests || metrics.request_count || 0}
              </p>
              <p className="text-xs text-slate-500">Total Requests</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-red-50 p-2"><AlertTriangle className="h-4 w-4 text-red-600" /></div>
            <div>
              <p className="text-lg font-bold text-red-600">
                {metrics.error_rate != null ? `${metrics.error_rate}%` : "0%"}
              </p>
              <p className="text-xs text-slate-500">Error Rate</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-indigo-50 p-2"><Database className="h-4 w-4 text-indigo-600" /></div>
            <div>
              <p className="text-lg font-bold text-indigo-600">
                {db.cache_hit_ratio != null ? `${db.cache_hit_ratio}%` : "—"}
              </p>
              <p className="text-xs text-slate-500">DB Cache Hit</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Slow Endpoints */}
        <Card>
          <CardHeader><CardTitle>Endpoint Response Times</CardTitle></CardHeader>
          <CardContent>
            <div className="h-64">
              {endpointChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={endpointChartData} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" fontSize={11} unit="ms" />
                    <YAxis type="category" dataKey="name" width={140} fontSize={10} />
                    <Tooltip />
                    <Bar dataKey="avg" fill="#6366f1" radius={[0, 4, 4, 0]} name="Avg (ms)" />
                    <Bar dataKey="p95" fill="#f59e0b" radius={[0, 4, 4, 0]} name="P95 (ms)" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-slate-400">
                  Make some API requests to see performance data
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Database Stats */}
        <Card>
          <CardHeader><CardTitle>Database</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <StatRow label="Database Size" value={db.database_size || db.size || "—"} />
            <StatRow label="Active Connections" value={db.active_connections || "—"} />
            <StatRow label="Cache Hit Ratio" value={db.cache_hit_ratio != null ? `${db.cache_hit_ratio}%` : "—"} />
            <StatRow label="Total Tables" value={db.table_count || db.tables || "—"} />
            <StatRow label="Total Indexes" value={indexes.total || indexes.total_indexes || "—"} />
            <StatRow label="Used Indexes" value={indexes.used || indexes.used_indexes || "—"} />
            <StatRow label="Unused Indexes" value={indexes.unused || indexes.unused_indexes || "—"} />
          </CardContent>
        </Card>
      </div>

      {/* Cache Stats */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Application Cache</CardTitle>
          <Badge variant="info" dot>Active</Badge>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {["dashboard_cache", "kpi_cache", "query_cache"].map((name) => {
              const c = (cache as Record<string, Record<string, unknown>>)?.[name] || cache?.[name.replace("_cache", "")] || {};
              return (
                <div key={name} className="rounded-lg border border-slate-200 p-4">
                  <p className="text-sm font-medium text-slate-900 capitalize mb-2">
                    {name.replace("_", " ")}
                  </p>
                  <div className="space-y-1">
                    <StatRow label="Entries" value={c.entries || c.size || 0} />
                    <StatRow label="Hit Rate" value={c.hit_rate != null ? `${c.hit_rate}%` : "—"} />
                    <StatRow label="TTL" value={c.ttl ? `${c.ttl}s` : "—"} />
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs text-slate-500">{label}</span>
      <span className="text-xs font-medium text-slate-900">{String(value)}</span>
    </div>
  );
}
