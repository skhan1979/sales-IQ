"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { collectionsApi } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";
import { DataTable, Column } from "@/components/ui/data-table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import {
  PhoneCall,
  Search,
  Mail,
  MessageSquare,
  AlertTriangle,
  CheckCircle,
  Clock,
  TrendingUp,
} from "lucide-react";

interface CollectionActivity {
  id: string;
  customer_name?: string;
  customer_id?: string;
  invoice_number?: string;
  invoice_id?: string;
  action_type?: string;
  action_date?: string;
  outcome?: string;
  notes?: string;
  follow_up_date?: string;
  ptp_date?: string;
  ptp_amount?: number;
  ptp_fulfilled?: boolean;
  created_at?: string;
  created_by_name?: string;
  collector_id?: string;
  ai_suggested?: boolean;
  is_ai_suggested?: boolean;
  ai_priority_score?: number;
  [key: string]: unknown;
}

const actionIcons: Record<string, React.ElementType> = {
  call: PhoneCall,
  email: Mail,
  sms: MessageSquare,
  escalation: AlertTriangle,
};

export default function CollectionsPage() {
  const router = useRouter();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const pageSize = 20;

  const { data, isLoading } = useQuery({
    queryKey: ["collections", page, search],
    queryFn: () =>
      collectionsApi
        .list({
          skip: (page - 1) * pageSize,
          limit: pageSize,
          search: search || undefined,
        })
        .then((r) => r.data),
  });

  const { data: summary } = useQuery({
    queryKey: ["collections-summary"],
    queryFn: () => collectionsApi.summary().then((r) => r.data),
    retry: false,
  });

  const activities: CollectionActivity[] = Array.isArray(data?.items)
    ? data.items
    : Array.isArray(data?.activities)
    ? data.activities
    : Array.isArray(data)
    ? data
    : [];
  const total = data?.total || activities.length;

  const columns: Column<CollectionActivity>[] = [
    {
      key: "customer_name",
      header: "Customer",
      render: (_: unknown, row: CollectionActivity) => {
        const name = row.customer_name;
        return (
          <div>
            {name ? (
              <button
                className="font-medium text-blue-600 hover:text-blue-800 hover:underline text-left"
                onClick={(e) => {
                  e.stopPropagation();
                  if (row.customer_id) router.push(`/dashboard/customers/${row.customer_id}`);
                }}
              >
                {name}
              </button>
            ) : (
              <p className="font-medium text-slate-500">
                {row.customer_id ? `ID: ${row.customer_id.slice(0, 8)}` : "—"}
              </p>
            )}
            {row.invoice_number && (
              <p className="text-xs text-slate-500">Inv: {row.invoice_number}</p>
            )}
          </div>
        );
      },
    },
    {
      key: "action_type",
      header: "Action",
      render: (val: unknown, row: CollectionActivity) => {
        const action = (val as string) || "call";
        const Icon = actionIcons[action] || PhoneCall;
        return (
          <div className="flex items-center gap-2">
            <Icon className="h-4 w-4 text-slate-400" />
            <span className="text-sm capitalize">{action}</span>
            {(row.ai_suggested || row.is_ai_suggested) && (
              <Badge variant="info">AI</Badge>
            )}
          </div>
        );
      },
    },
    {
      key: "outcome",
      header: "Outcome",
      render: (val: unknown) => {
        const outcome = (val as string) || "";
        if (!outcome) return <span className="text-slate-400">Pending</span>;
        const color: Record<string, string> = {
          promise_to_pay: "text-emerald-600",
          ptp: "text-emerald-600",
          paid: "text-emerald-700 font-medium",
          no_answer: "text-amber-600",
          callback: "text-blue-600",
          refused: "text-red-600",
          escalated: "text-red-600",
        };
        return (
          <span className={`text-sm capitalize ${color[outcome] || "text-slate-600"}`}>
            {outcome.replace(/_/g, " ")}
          </span>
        );
      },
    },
    {
      key: "ptp_amount",
      header: "PTP Amount",
      align: "right",
      render: (val: unknown, row: CollectionActivity) =>
        val ? (
          <div className="text-right">
            <p className="text-sm font-medium text-slate-900">
              {formatCurrency(val as number)}
            </p>
            {row.ptp_fulfilled != null && (
              <Badge
                variant={row.ptp_fulfilled ? "success" : "warning"}
              >
                {row.ptp_fulfilled ? "Fulfilled" : "Pending"}
              </Badge>
            )}
          </div>
        ) : (
          <span className="text-slate-400">—</span>
        ),
    },
    {
      key: "action_date",
      header: "Follow Up",
      render: (_: unknown, row: CollectionActivity) => (
        <span className="text-sm text-slate-600">
          {formatDate((row.follow_up_date || row.action_date) as string)}
        </span>
      ),
    },
    {
      key: "created_at",
      header: "Date",
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
        <h1 className="text-xl font-bold text-slate-900">Collections</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Track collection activities, promises-to-pay, and follow-ups
        </p>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-blue-50 p-2">
              <PhoneCall className="h-4 w-4 text-blue-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-slate-900">
                {summary?.total_activities || summary?.total || total}
              </p>
              <p className="text-xs text-slate-500">Total Activities</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-indigo-50 p-2">
              <Clock className="h-4 w-4 text-indigo-600" />
            </div>
            <div>
              <p className="text-lg font-bold text-indigo-600">
                {summary?.this_month || 0}
              </p>
              <p className="text-xs text-slate-500">This Month</p>
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
                {summary?.ptp_fulfilled || 0}
              </p>
              <p className="text-xs text-slate-500">PTP Fulfilled</p>
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
                {summary?.ptp_broken || 0}
              </p>
              <p className="text-xs text-slate-500">PTP Broken</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Search */}
      <div className="flex items-center gap-3">
        <div className="flex-1 max-w-sm">
          <Input
            placeholder="Search activities..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            icon={<Search className="h-4 w-4" />}
          />
        </div>
      </div>

      {!isLoading && activities.length === 0 && !search ? (
        <EmptyState
          icon={PhoneCall}
          title="No collection activities"
          description="Collection activities will appear here once you start tracking calls, emails, and follow-ups."
        />
      ) : (
        <DataTable
          columns={columns}
          data={activities}
          loading={isLoading}
          emptyMessage="No activities match your search"
          onRowClick={(row) => {
            if (row.customer_id) router.push(`/dashboard/customers/${row.customer_id}`);
          }}
          pagination={{ page, pageSize, total, onPageChange: setPage }}
        />
      )}
    </div>
  );
}
