"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { creditLimitApi } from "@/lib/api-extra";
import { formatCurrency, formatDate } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataTable, Column } from "@/components/ui/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";
import {
  CreditCard,
  Plus,
  CheckCircle,
  XCircle,
  Clock,
  TrendingUp,
  Shield,
} from "lucide-react";

interface CreditRequest {
  id: string;
  customer_name?: string;
  customer_id?: string;
  current_limit?: number | string;
  requested_limit?: number | string;
  approval_status?: string;
  status: string;
  risk_assessment?: string;
  ai_risk_assessment?: Record<string, unknown>;
  ai_recommended_limit?: number | string;
  recommended_limit?: number | string;
  created_at?: string;
  decided_at?: string;
  decided_by_name?: string;
  [key: string]: unknown;
}

export default function CreditLimitsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const { data, isLoading } = useQuery({
    queryKey: ["credit-limits", page],
    queryFn: () =>
      creditLimitApi.list({ skip: (page - 1) * pageSize, limit: pageSize }).then((r) => r.data),
  });

  const decideMutation = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: string }) =>
      creditLimitApi.decide(id, decision).then((r) => r.data),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ["credit-limits"] });
      toast.success(`Request ${vars.decision}d`);
    },
    onError: () => toast.error("Decision failed"),
  });

  const requests: CreditRequest[] = Array.isArray(data?.items)
    ? data.items
    : Array.isArray(data?.requests)
    ? data.requests
    : Array.isArray(data)
    ? data
    : [];
  const total = data?.total || requests.length;

  const pendingCount = requests.filter((r) => (r.approval_status || r.status) === "pending").length;
  const approvedCount = requests.filter((r) => (r.approval_status || r.status) === "approved").length;

  const columns: Column<CreditRequest>[] = [
    {
      key: "customer_name",
      header: "Customer",
      render: (_: unknown, row: CreditRequest) => {
        const name = row.customer_name;
        if (name) {
          return (
            <button
              className="font-medium text-blue-600 hover:text-blue-800 hover:underline text-left"
              onClick={(e) => {
                e.stopPropagation();
                if (row.customer_id) router.push(`/dashboard/customers/${row.customer_id}`);
              }}
            >
              {name}
            </button>
          );
        }
        return (
          <p className="font-medium text-slate-500">
            {row.customer_id ? `Customer ${row.customer_id.slice(0, 8)}` : "Unknown"}
          </p>
        );
      },
    },
    {
      key: "current_limit",
      header: "Current Limit",
      align: "right",
      render: (val: unknown) => (
        <span className="text-slate-600">{formatCurrency(typeof val === "string" ? parseFloat(val) : val as number)}</span>
      ),
    },
    {
      key: "requested_limit",
      header: "Requested",
      align: "right",
      render: (val: unknown) => (
        <span className="font-semibold text-slate-900">{formatCurrency(typeof val === "string" ? parseFloat(val) : val as number)}</span>
      ),
    },
    {
      key: "ai_recommended_limit",
      header: "AI Recommended",
      align: "right",
      render: (_: unknown, row: CreditRequest) => {
        const v = row.ai_recommended_limit ?? row.recommended_limit;
        return v ? (
          <span className="font-medium text-indigo-600">{formatCurrency(typeof v === "string" ? parseFloat(v) : v as number)}</span>
        ) : (
          <span className="text-slate-400">—</span>
        );
      },
    },
    {
      key: "ai_risk_assessment",
      header: "Risk",
      render: (_: unknown, row: CreditRequest) => {
        const assessment = row.ai_risk_assessment;
        const riskScore = assessment?.risk_score as number | undefined;
        if (riskScore != null) {
          const level = riskScore > 70 ? "high" : riskScore > 40 ? "medium" : "low";
          const v: Record<string, "success" | "warning" | "danger"> = { low: "success", medium: "warning", high: "danger" };
          return <Badge variant={v[level]}>{level} ({Math.round(riskScore)})</Badge>;
        }
        const risk = (row.risk_assessment as string) || "unknown";
        const v: Record<string, "success" | "warning" | "danger" | "neutral"> = { low: "success", medium: "warning", high: "danger" };
        return <Badge variant={v[risk] || "neutral"}>{risk}</Badge>;
      },
    },
    {
      key: "approval_status",
      header: "Status",
      render: (_: unknown, row: CreditRequest) => {
        const s = (row.approval_status || row.status) || "pending";
        const v: Record<string, "success" | "warning" | "danger" | "info" | "neutral"> = {
          approved: "success", rejected: "danger", pending: "warning",
        };
        return <Badge variant={v[s] || "neutral"} dot>{s}</Badge>;
      },
    },
    {
      key: "id",
      header: "Actions",
      align: "center",
      render: (_: unknown, row: CreditRequest) =>
        (row.approval_status || row.status) === "pending" ? (
          <div className="flex items-center gap-1 justify-center">
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                decideMutation.mutate({ id: row.id, decision: "approve" });
              }}
              icon={<CheckCircle className="h-3.5 w-3.5 text-emerald-600" />}
            >
              Approve
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                decideMutation.mutate({ id: row.id, decision: "reject" });
              }}
              icon={<XCircle className="h-3.5 w-3.5 text-red-600" />}
            >
              Reject
            </Button>
          </div>
        ) : (
          <span className="text-xs text-slate-400">{formatDate(row.decided_at)}</span>
        ),
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Credit Limits</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Review credit limit requests with AI risk assessments
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-amber-50 p-2"><Clock className="h-4 w-4 text-amber-600" /></div>
            <div>
              <p className="text-lg font-bold text-amber-600">{pendingCount}</p>
              <p className="text-xs text-slate-500">Pending Review</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-emerald-50 p-2"><CheckCircle className="h-4 w-4 text-emerald-600" /></div>
            <div>
              <p className="text-lg font-bold text-emerald-600">{approvedCount}</p>
              <p className="text-xs text-slate-500">Approved</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-blue-50 p-2"><Shield className="h-4 w-4 text-blue-600" /></div>
            <div>
              <p className="text-lg font-bold text-blue-600">{total}</p>
              <p className="text-xs text-slate-500">Total Requests</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {!isLoading && requests.length === 0 ? (
        <EmptyState
          icon={CreditCard}
          title="No credit limit requests"
          description="Credit limit requests will appear here when customers need limit adjustments."
        />
      ) : (
        <DataTable
          columns={columns}
          data={requests}
          loading={isLoading}
          emptyMessage="No credit limit requests"
          onRowClick={(row) => {
            if (row.customer_id) router.push(`/dashboard/customers/${row.customer_id}`);
          }}
          pagination={{ page, pageSize, total, onPageChange: setPage }}
        />
      )}
    </div>
  );
}
