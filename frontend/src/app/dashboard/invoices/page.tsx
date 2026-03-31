"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { invoiceApi } from "@/lib/api";
import {
  formatCurrency,
  formatDate,
  getAgingColor,
} from "@/lib/utils";
import { DataTable, Column } from "@/components/ui/data-table";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import {
  FileText,
  Search,
  DollarSign,
  Clock,
  AlertCircle,
  CheckCircle,
} from "lucide-react";

interface Invoice {
  id: string;
  invoice_number: string;
  customer_name?: string;
  customer_id?: string;
  amount?: number;
  total_amount?: number;
  amount_remaining?: number;
  remaining_amount?: number;
  amount_paid?: number;
  status: string;
  invoice_date?: string;
  due_date?: string;
  days_overdue?: number;
  aging_bucket?: string;
  currency?: string;
  [key: string]: unknown;
}

export default function InvoicesPage() {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [agingFilter, setAgingFilter] = useState("");
  const pageSize = 20;

  const { data, isLoading } = useQuery({
    queryKey: ["invoices", page, search, statusFilter, agingFilter],
    queryFn: () =>
      invoiceApi
        .list({
          skip: (page - 1) * pageSize,
          limit: pageSize,
          search: search || undefined,
          status: statusFilter || undefined,
          aging_bucket: agingFilter || undefined,
        })
        .then((r) => r.data),
  });

  const invoices: Invoice[] = Array.isArray(data?.items)
    ? data.items
    : Array.isArray(data?.invoices)
    ? data.invoices
    : Array.isArray(data)
    ? data
    : [];
  const total = data?.total || invoices.length;

  const columns: Column<Invoice>[] = [
    {
      key: "invoice_number",
      header: "Invoice",
      render: (_: unknown, row: Invoice) => (
        <div>
          <p className="font-medium text-slate-900">
            {row.invoice_number}
          </p>
        </div>
      ),
    },
    {
      key: "customer_name",
      header: "Customer",
      render: (_: unknown, row: Invoice) => {
        const name = row.customer_name;
        if (name) {
          return (
            <button
              className="text-sm text-blue-600 hover:text-blue-800 hover:underline text-left truncate max-w-[150px]"
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
      key: "invoice_date",
      header: "Date",
      render: (val: unknown) => (
        <span className="text-slate-600">{formatDate(val as string)}</span>
      ),
    },
    {
      key: "due_date",
      header: "Due Date",
      render: (val: unknown) => (
        <span className="text-slate-600">{formatDate(val as string)}</span>
      ),
    },
    {
      key: "amount",
      header: "Amount",
      align: "right",
      render: (_: unknown, row: Invoice) => (
        <span className="font-semibold text-slate-900">
          {formatCurrency((row.amount ?? row.total_amount) as number)}
        </span>
      ),
    },
    {
      key: "amount_remaining",
      header: "Remaining",
      align: "right",
      render: (_: unknown, row: Invoice) => {
        const rem = (row.amount_remaining ?? row.remaining_amount) || 0;
        return (
          <span
            className={rem > 0 ? "font-medium text-orange-600" : "text-emerald-600"}
          >
            {formatCurrency(rem)}
          </span>
        );
      },
    },
    {
      key: "status",
      header: "Status",
      render: (val: unknown) => {
        const status = (val as string) || "open";
        const variants: Record<string, "success" | "danger" | "warning" | "info" | "neutral"> = {
          paid: "success",
          overdue: "danger",
          disputed: "warning",
          partial: "warning",
          open: "info",
          cancelled: "neutral",
        };
        return (
          <Badge variant={variants[status] || "neutral"}>
            {status}
          </Badge>
        );
      },
    },
    {
      key: "aging_bucket",
      header: "Aging",
      render: (val: unknown) => {
        const bucket = (val as string) || "current";
        return (
          <span
            className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${getAgingColor(bucket)}`}
          >
            {bucket === "current" ? "Current" : `${bucket} days`}
          </span>
        );
      },
    },
    {
      key: "days_overdue",
      header: "Days Late",
      align: "right",
      render: (val: unknown) => {
        const days = (val as number) || 0;
        return days > 0 ? (
          <span className="text-sm font-medium text-red-600">{days}d</span>
        ) : (
          <span className="text-slate-400">—</span>
        );
      },
    },
  ];

  // Quick stats
  const totalAmount = invoices.reduce((s, i) => s + (i.total_amount || 0), 0);
  const totalRemaining = invoices.reduce(
    (s, i) => s + (i.remaining_amount || 0),
    0
  );
  const overdueCount = invoices.filter((i) => i.status === "overdue").length;
  const paidCount = invoices.filter((i) => i.status === "paid").length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Invoices</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Track invoice lifecycle, aging, and payment status
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-blue-50 p-2">
              <FileText className="h-4 w-4 text-blue-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-slate-900">{total}</p>
              <p className="text-xs text-slate-500">Total Invoices</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-indigo-50 p-2">
              <DollarSign className="h-4 w-4 text-indigo-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-slate-900">
                {formatCurrency(totalAmount)}
              </p>
              <p className="text-xs text-slate-500">Total Value</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-red-50 p-2">
              <AlertCircle className="h-4 w-4 text-red-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-red-600">{overdueCount}</p>
              <p className="text-xs text-slate-500">Overdue</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-emerald-50 p-2">
              <CheckCircle className="h-4 w-4 text-emerald-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-emerald-600">{paidCount}</p>
              <p className="text-xs text-slate-500">Paid</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex-1 min-w-[200px] max-w-sm">
          <Input
            placeholder="Search invoices..."
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
          <option value="overdue">Overdue</option>
          <option value="partial">Partial</option>
          <option value="paid">Paid</option>
          <option value="disputed">Disputed</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <select
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
          value={agingFilter}
          onChange={(e) => {
            setAgingFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All Aging</option>
          <option value="current">Current</option>
          <option value="1-30">1-30 days</option>
          <option value="31-60">31-60 days</option>
          <option value="61-90">61-90 days</option>
          <option value="90+">90+ days</option>
        </select>
      </div>

      {/* Table */}
      {!isLoading && invoices.length === 0 && !search && !statusFilter ? (
        <EmptyState
          icon={FileText}
          title="No invoices yet"
          description="Invoices will appear here once you import data or generate demo records."
        />
      ) : (
        <DataTable
          columns={columns}
          data={invoices}
          loading={isLoading}
          emptyMessage="No invoices match your filters"
          onRowClick={(row) => router.push(`/dashboard/invoices/${row.id}`)}
          pagination={{
            page,
            pageSize,
            total,
            onPageChange: setPage,
          }}
        />
      )}
    </div>
  );
}
