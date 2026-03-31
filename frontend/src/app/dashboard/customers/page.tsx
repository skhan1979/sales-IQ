"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { customerApi } from "@/lib/api";
import {
  formatCurrency,
  formatDate,
  getStatusColor,
  getRiskColor,
  getRiskLabel,
} from "@/lib/utils";
import { DataTable, Column } from "@/components/ui/data-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import { CreateCustomerModal } from "@/components/forms/create-customer";
import {
  Users,
  Search,
  Plus,
  Building2,
  AlertTriangle,
  ShieldCheck,
  Filter,
} from "lucide-react";

interface Customer {
  id: string;
  name: string;
  external_id?: string;
  industry?: string;
  territory?: string;
  segment?: string;
  status: string;
  credit_limit?: number;
  outstanding_balance?: number;
  credit_utilization?: number;
  risk_score?: number;
  data_quality_score?: number;
  overdue_amount?: number;
  created_at?: string;
  [key: string]: unknown;
}

export default function CustomersPage() {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const pageSize = 20;

  const { data, isLoading } = useQuery({
    queryKey: ["customers", page, search, statusFilter],
    queryFn: () =>
      customerApi
        .list({
          skip: (page - 1) * pageSize,
          limit: pageSize,
          search: search || undefined,
          status: statusFilter || undefined,
        })
        .then((r) => r.data),
  });

  const customers: Customer[] = Array.isArray(data?.items)
    ? data.items
    : Array.isArray(data?.customers)
    ? data.customers
    : Array.isArray(data)
    ? data
    : [];
  const total = data?.total || customers.length;

  const columns: Column<Customer>[] = [
    {
      key: "name",
      header: "Customer",
      render: (_: unknown, row: Customer) => (
        <div>
          <p className="font-medium text-slate-900">{row.name}</p>
          <p className="text-xs text-slate-500">
            {row.external_id || row.industry || "—"}
          </p>
        </div>
      ),
    },
    {
      key: "territory",
      header: "Territory",
      render: (val: unknown) => (
        <span className="text-slate-600">{(val as string) || "—"}</span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (val: unknown) => {
        const status = (val as string) || "unknown";
        return (
          <Badge
            variant={
              status === "active"
                ? "success"
                : status === "credit_hold"
                ? "danger"
                : "neutral"
            }
          >
            {status.replace("_", " ")}
          </Badge>
        );
      },
    },
    {
      key: "outstanding_balance",
      header: "Outstanding",
      align: "right",
      render: (val: unknown) => (
        <span className="font-medium text-slate-900">
          {formatCurrency(val as number)}
        </span>
      ),
    },
    {
      key: "credit_utilization",
      header: "Credit Usage",
      align: "right",
      render: (_: unknown, row: Customer) => {
        const utilization = Number(row.credit_utilization) || 0;
        const limit = Number(row.credit_limit) || 0;
        const pct = limit > 0 ? (utilization / limit) * 100 : 0;
        return (
          <div className="flex items-center justify-end gap-2">
            <div className="h-1.5 w-16 rounded-full bg-slate-100">
              <div
                className={`h-full rounded-full ${
                  pct > 90
                    ? "bg-red-500"
                    : pct > 70
                    ? "bg-amber-500"
                    : "bg-emerald-500"
                }`}
                style={{ width: `${Math.min(pct, 100)}%` }}
              />
            </div>
            <span className="text-xs text-slate-600 w-10 text-right">
              {pct.toFixed(0)}%
            </span>
          </div>
        );
      },
    },
    {
      key: "risk_score",
      header: "Risk",
      align: "center",
      render: (val: unknown) => {
        const score = val as number;
        return (
          <span className={`text-xs font-semibold ${getRiskColor(score)}`}>
            {getRiskLabel(score)}
          </span>
        );
      },
    },
    {
      key: "overdue_amount",
      header: "Overdue",
      align: "right",
      render: (val: unknown) => {
        const amt = (val as number) || 0;
        return (
          <span
            className={amt > 0 ? "font-medium text-red-600" : "text-slate-400"}
          >
            {amt > 0 ? formatCurrency(amt) : "—"}
          </span>
        );
      },
    },
  ];

  // Summary stats
  const totalOutstanding = customers.reduce(
    (s, c) => s + (c.outstanding_balance || 0),
    0
  );
  const totalOverdue = customers.reduce(
    (s, c) => s + (c.overdue_amount || 0),
    0
  );
  const creditHoldCount = customers.filter(
    (c) => c.status === "credit_hold"
  ).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Customers</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Manage your customer portfolio and monitor credit risk
          </p>
        </div>
        <Button icon={<Plus className="h-4 w-4" />} onClick={() => setShowCreate(true)}>Add Customer</Button>
      </div>

      <CreateCustomerModal open={showCreate} onClose={() => setShowCreate(false)} />

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-blue-50 p-2">
              <Users className="h-4 w-4 text-blue-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-slate-900">{total}</p>
              <p className="text-xs text-slate-500">Total Customers</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-indigo-50 p-2">
              <Building2 className="h-4 w-4 text-indigo-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-slate-900">
                {formatCurrency(totalOutstanding)}
              </p>
              <p className="text-xs text-slate-500">Total Outstanding</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-red-50 p-2">
              <AlertTriangle className="h-4 w-4 text-red-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-red-600">
                {formatCurrency(totalOverdue)}
              </p>
              <p className="text-xs text-slate-500">Total Overdue</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-amber-50 p-2">
              <ShieldCheck className="h-4 w-4 text-amber-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-amber-600">
                {creditHoldCount}
              </p>
              <p className="text-xs text-slate-500">Credit Hold</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="flex-1 max-w-sm">
          <Input
            placeholder="Search customers..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            icon={<Search className="h-4 w-4" />}
          />
        </div>
        <select
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All Statuses</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
          <option value="credit_hold">Credit Hold</option>
          <option value="on_hold">On Hold</option>
        </select>
      </div>

      {/* Table */}
      {!isLoading && customers.length === 0 && !search && !statusFilter ? (
        <EmptyState
          icon={Users}
          title="No customers yet"
          description="Add your first customer or generate demo data from the Admin panel to get started."
          action={
            <Button icon={<Plus className="h-4 w-4" />} onClick={() => setShowCreate(true)}>Add Customer</Button>
          }
        />
      ) : (
        <DataTable
          columns={columns}
          data={customers}
          loading={isLoading}
          emptyMessage="No customers match your search"
          exportFilename="salesiq-customers"
          onRowClick={(row) =>
            router.push(`/dashboard/customers/${row.id}`)
          }
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
