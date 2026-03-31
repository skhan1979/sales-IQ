"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { paymentApi } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";
import { DataTable, Column } from "@/components/ui/data-table";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import {
  CreditCard,
  Search,
  DollarSign,
  CheckCircle2,
  XCircle,
  ArrowRightLeft,
} from "lucide-react";

interface Payment {
  id: string;
  payment_number?: string;
  reference_number?: string;
  customer_name?: string;
  customer_id?: string;
  invoice_number?: string;
  invoice_id?: string;
  amount?: number;
  currency?: string;
  payment_date?: string;
  payment_method?: string;
  reference?: string;
  is_matched?: boolean;
  matched_invoice_id?: string;
  bank_reference?: string;
  match_confidence?: number;
  [key: string]: unknown;
}

export default function PaymentsPage() {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [matchedFilter, setMatchedFilter] = useState("");
  const pageSize = 20;

  const { data, isLoading } = useQuery({
    queryKey: ["payments", page, search, matchedFilter],
    queryFn: () =>
      paymentApi
        .list({
          skip: (page - 1) * pageSize,
          limit: pageSize,
          search: search || undefined,
          is_matched:
            matchedFilter === "matched"
              ? true
              : matchedFilter === "unmatched"
              ? false
              : undefined,
        })
        .then((r) => r.data),
  });

  const payments: Payment[] = Array.isArray(data?.items)
    ? data.items
    : Array.isArray(data?.payments)
    ? data.payments
    : Array.isArray(data)
    ? data
    : [];
  const total = data?.total || payments.length;

  const columns: Column<Payment>[] = [
    {
      key: "payment_number",
      header: "Payment",
      render: (_: unknown, row: Payment) => (
        <div>
          <p className="font-medium text-slate-900">
            {row.payment_number || row.reference_number || row.reference || `PAY-${row.id?.slice(0, 8)}`}
          </p>
        </div>
      ),
    },
    {
      key: "customer_name",
      header: "Customer",
      render: (_: unknown, row: Payment) => {
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
      key: "payment_date",
      header: "Date",
      render: (val: unknown) => (
        <span className="text-slate-600">{formatDate(val as string)}</span>
      ),
    },
    {
      key: "amount",
      header: "Amount",
      align: "right",
      render: (val: unknown) => (
        <span className="font-semibold text-emerald-700">
          {formatCurrency(val as number)}
        </span>
      ),
    },
    {
      key: "payment_method",
      header: "Method",
      render: (val: unknown) => (
        <span className="text-sm text-slate-600 capitalize">
          {((val as string) || "—").replace("_", " ")}
        </span>
      ),
    },
    {
      key: "is_matched",
      header: "Match Status",
      align: "center",
      render: (val: unknown) =>
        val ? (
          <Badge variant="success" dot>
            Matched
          </Badge>
        ) : (
          <Badge variant="warning" dot>
            Unmatched
          </Badge>
        ),
    },
    {
      key: "invoice_number",
      header: "Invoice",
      render: (val: unknown, row: Payment) => {
        const invoiceNum = (val as string) || "";
        const invoiceId = row.invoice_id || row.matched_invoice_id;
        if (invoiceNum || invoiceId) {
          return (
            <button
              className="text-sm text-blue-600 hover:text-blue-800 hover:underline"
              onClick={(e) => {
                e.stopPropagation();
                if (invoiceId) router.push(`/dashboard/invoices/${invoiceId}`);
              }}
            >
              {invoiceNum || "Linked Invoice"}
            </button>
          );
        }
        return <span className="text-sm text-slate-400">—</span>;
      },
    },
    {
      key: "bank_reference",
      header: "Bank Ref",
      render: (val: unknown) => (
        <span className="text-xs text-slate-500 font-mono">
          {(val as string) || "—"}
        </span>
      ),
    },
  ];

  const totalAmount = payments.reduce((s, p) => s + (p.amount || 0), 0);
  const matchedCount = payments.filter((p) => p.is_matched).length;
  const unmatchedCount = payments.filter((p) => !p.is_matched).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Payments</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          View payment records and invoice matching status
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-blue-50 p-2">
              <CreditCard className="h-4 w-4 text-blue-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-slate-900">{total}</p>
              <p className="text-xs text-slate-500">Total Payments</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-emerald-50 p-2">
              <DollarSign className="h-4 w-4 text-emerald-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-emerald-600">
                {formatCurrency(totalAmount)}
              </p>
              <p className="text-xs text-slate-500">Total Collected</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-green-50 p-2">
              <CheckCircle2 className="h-4 w-4 text-green-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-green-600">{matchedCount}</p>
              <p className="text-xs text-slate-500">Matched</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-amber-50 p-2">
              <ArrowRightLeft className="h-4 w-4 text-amber-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-amber-600">
                {unmatchedCount}
              </p>
              <p className="text-xs text-slate-500">Unmatched</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex-1 max-w-sm">
          <Input
            placeholder="Search payments..."
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
          value={matchedFilter}
          onChange={(e) => {
            setMatchedFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All</option>
          <option value="matched">Matched</option>
          <option value="unmatched">Unmatched</option>
        </select>
      </div>

      {!isLoading && payments.length === 0 && !search ? (
        <EmptyState
          icon={CreditCard}
          title="No payments recorded"
          description="Payments will appear here once you import data or generate demo records."
        />
      ) : (
        <DataTable
          columns={columns}
          data={payments}
          loading={isLoading}
          emptyMessage="No payments match your search"
          onRowClick={(row) => router.push(`/dashboard/payments/${row.id}`)}
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
