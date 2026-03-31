"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { disputeApi } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";
import { DataTable, Column } from "@/components/ui/data-table";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import {
  AlertTriangle,
  Search,
  ShieldAlert,
  Clock,
  CheckCircle,
  XCircle,
} from "lucide-react";

interface Dispute {
  id: string;
  dispute_number?: string;
  customer_name?: string;
  customer_id?: string;
  invoice_number?: string;
  invoice_id?: string;
  status: string;
  priority?: string;
  reason?: string;
  reason_detail?: string;
  amount?: number;
  disputed_amount?: number;
  currency?: string;
  sla_due_date?: string;
  sla_date?: string;
  sla_breached?: boolean;
  created_at?: string;
  resolved_at?: string;
  [key: string]: unknown;
}

export default function DisputesPage() {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const pageSize = 20;

  const { data, isLoading } = useQuery({
    queryKey: ["disputes", page, search, statusFilter],
    queryFn: () =>
      disputeApi
        .list({
          skip: (page - 1) * pageSize,
          limit: pageSize,
          search: search || undefined,
          status: statusFilter || undefined,
        })
        .then((r) => r.data),
  });

  const { data: overview } = useQuery({
    queryKey: ["disputes-overview"],
    queryFn: () => disputeApi.overview().then((r) => r.data),
    retry: false,
  });

  const disputes: Dispute[] = Array.isArray(data?.items)
    ? data.items
    : Array.isArray(data?.disputes)
    ? data.disputes
    : Array.isArray(data)
    ? data
    : [];
  const total = data?.total || disputes.length;

  const columns: Column<Dispute>[] = [
    {
      key: "dispute_number",
      header: "Dispute",
      render: (_: unknown, row: Dispute) => (
        <div>
          <p className="font-medium text-slate-900">
            {row.dispute_number || `DSP-${row.id?.slice(0, 8)}`}
          </p>
        </div>
      ),
    },
    {
      key: "invoice_number",
      header: "Invoice",
      render: (_: unknown, row: Dispute) => {
        const invNum = row.invoice_number;
        if (invNum) {
          return (
            <button
              className="text-sm text-blue-600 hover:text-blue-800 hover:underline"
              onClick={(e) => {
                e.stopPropagation();
                if (row.invoice_id) router.push(`/dashboard/invoices/${row.invoice_id}`);
              }}
            >
              {invNum}
            </button>
          );
        }
        return <span className="text-slate-400">—</span>;
      },
    },
    {
      key: "customer_name",
      header: "Customer",
      render: (_: unknown, row: Dispute) => {
        const name = row.customer_name;
        if (name) {
          return (
            <button
              className="text-sm text-blue-600 hover:text-blue-800 hover:underline text-left"
              onClick={(e) => {
                e.stopPropagation();
                if (row.customer_id) router.push(`/dashboard/customers/${row.customer_id}`);
              }}
            >
              {name}
            </button>
          );
        }
        return <span className="text-slate-400">—</span>;
      },
    },
    {
      key: "reason",
      header: "Reason",
      render: (val: unknown) => (
        <span className="text-sm text-slate-600 capitalize">
          {((val as string) || "—").replace("_", " ")}
        </span>
      ),
    },
    {
      key: "amount",
      header: "Amount",
      align: "right",
      render: (_: unknown, row: Dispute) => (
        <span className="font-semibold text-slate-900">
          {formatCurrency((row.amount ?? row.disputed_amount) as number)}
        </span>
      ),
    },
    {
      key: "priority",
      header: "Priority",
      render: (val: unknown) => {
        const p = (val as string) || "medium";
        const v: Record<string, "danger" | "warning" | "info" | "neutral"> = {
          high: "danger",
          medium: "warning",
          low: "info",
          critical: "danger",
        };
        return <Badge variant={v[p] || "neutral"}>{p}</Badge>;
      },
    },
    {
      key: "status",
      header: "Status",
      render: (val: unknown) => {
        const s = (val as string) || "open";
        const variants: Record<string, "success" | "danger" | "warning" | "info" | "neutral"> = {
          open: "info",
          in_review: "warning",
          escalated: "danger",
          resolved: "success",
          rejected: "neutral",
          credit_issued: "success",
        };
        return (
          <Badge variant={variants[s] || "neutral"}>
            {s.replace("_", " ")}
          </Badge>
        );
      },
    },
    {
      key: "sla_breached",
      header: "SLA",
      align: "center",
      render: (val: unknown, row: Dispute) =>
        val ? (
          <span className="text-xs font-medium text-red-600">Breached</span>
        ) : (row.sla_due_date || row.sla_date) ? (
          <span className="text-xs text-slate-500">
            Due {formatDate(row.sla_due_date || row.sla_date)}
          </span>
        ) : (
          <span className="text-slate-400">—</span>
        ),
    },
    {
      key: "created_at",
      header: "Opened",
      render: (val: unknown) => (
        <span className="text-xs text-slate-500">
          {formatDate(val as string)}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Disputes</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Manage dispute lifecycle, SLA tracking, and resolution workflow
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-orange-50 p-2">
              <AlertTriangle className="h-4 w-4 text-orange-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-slate-900">
                {overview?.total_disputes || overview?.total || total}
              </p>
              <p className="text-xs text-slate-500">Total Disputes</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-blue-50 p-2">
              <Clock className="h-4 w-4 text-blue-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-blue-600">
                {overview?.open_count || overview?.open || 0}
              </p>
              <p className="text-xs text-slate-500">Open</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-emerald-50 p-2">
              <CheckCircle className="h-4 w-4 text-emerald-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-emerald-600">
                {overview?.resolved_count || overview?.resolved || 0}
              </p>
              <p className="text-xs text-slate-500">Resolved</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-red-50 p-2">
              <ShieldAlert className="h-4 w-4 text-red-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-red-600">
                {overview?.sla_breached_count || overview?.sla_breached || 0}
              </p>
              <p className="text-xs text-slate-500">SLA Breached</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex-1 max-w-sm">
          <Input
            placeholder="Search disputes..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            icon={<Search className="h-4 w-4" />}
          />
        </div>
        <select
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All Statuses</option>
          <option value="open">Open</option>
          <option value="in_review">In Review</option>
          <option value="escalated">Escalated</option>
          <option value="resolved">Resolved</option>
          <option value="rejected">Rejected</option>
        </select>
      </div>

      {!isLoading && disputes.length === 0 && !search && !statusFilter ? (
        <EmptyState
          icon={AlertTriangle}
          title="No disputes"
          description="Disputes will appear here when invoices are contested by customers."
        />
      ) : (
        <DataTable
          columns={columns}
          data={disputes}
          loading={isLoading}
          emptyMessage="No disputes match your filters"
          onRowClick={(row) => router.push(`/dashboard/disputes/${row.id}`)}
          pagination={{ page, pageSize, total, onPageChange: setPage }}
        />
      )}
    </div>
  );
}
