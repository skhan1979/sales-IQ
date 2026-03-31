"use client";

import React from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { disputeApi } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";
import { PageLoader } from "@/components/ui/spinner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";

interface DisputeDetail {
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
  resolution_notes?: string;
  notes?: string;
  [key: string]: unknown;
}

const statusVariants: Record<
  string,
  "info" | "warning" | "danger" | "success" | "neutral"
> = {
  open: "info",
  in_review: "warning",
  escalated: "danger",
  resolved: "success",
  rejected: "neutral",
  credit_issued: "success",
};

const priorityVariants: Record<
  string,
  "danger" | "warning" | "info"
> = {
  high: "danger",
  medium: "warning",
  low: "info",
  critical: "danger",
};

export default function DisputeDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const { data: dispute, isLoading } = useQuery<DisputeDetail>({
    queryKey: ["dispute", id],
    queryFn: () => disputeApi.get(id).then((r) => r.data),
    enabled: !!id,
  });

  if (isLoading) {
    return <PageLoader />;
  }

  if (!dispute) {
    return (
      <div className="space-y-6">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push("/dashboard/disputes")}
          icon={<ArrowLeft className="h-4 w-4" />}
        >
          Back to Disputes
        </Button>
        <div className="flex h-[400px] items-center justify-center">
          <div className="text-center space-y-2">
            <p className="text-lg font-semibold text-slate-900">
              Dispute Not Found
            </p>
            <p className="text-sm text-slate-500">
              The dispute you are looking for does not exist or has been removed.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const displayNumber =
    dispute.dispute_number || `DSP-${dispute.id?.slice(0, 8)}`;
  const displayAmount =
    dispute.amount ?? dispute.disputed_amount;
  const slaDueDate = dispute.sla_due_date || dispute.sla_date;

  return (
    <div className="space-y-6">
      {/* Back navigation */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.push("/dashboard/disputes")}
        icon={<ArrowLeft className="h-4 w-4" />}
      >
        Back to Disputes
      </Button>

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900">{displayNumber}</h1>
          {dispute.customer_name && (
            <p className="text-sm text-slate-500 mt-0.5">
              {dispute.customer_name}
              {dispute.customer_id && (
                <span className="text-slate-400">
                  {" "}
                  &middot; {dispute.customer_id}
                </span>
              )}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Badge
            variant={statusVariants[dispute.status] || "neutral"}
            dot
          >
            {dispute.status.replace(/_/g, " ")}
          </Badge>
          {dispute.priority && (
            <Badge
              variant={priorityVariants[dispute.priority] || "neutral"}
            >
              {dispute.priority}
            </Badge>
          )}
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
              Amount
            </p>
            <p className="mt-1 text-lg font-bold text-slate-900">
              {formatCurrency(displayAmount as number, dispute.currency || undefined)}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
              SLA Status
            </p>
            {dispute.sla_breached ? (
              <p className="mt-1 text-lg font-bold text-red-600">Breached</p>
            ) : slaDueDate ? (
              <p className="mt-1 text-lg font-bold text-slate-900">
                Due {formatDate(slaDueDate)}
              </p>
            ) : (
              <p className="mt-1 text-lg font-bold text-slate-400">&mdash;</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
              Created
            </p>
            <p className="mt-1 text-lg font-bold text-slate-900">
              {formatDate(dispute.created_at)}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
              Resolved
            </p>
            <p className="mt-1 text-lg font-bold text-slate-900">
              {dispute.resolved_at ? formatDate(dispute.resolved_at) : "\u2014"}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Dispute Details */}
      <Card>
        <CardHeader>
          <CardTitle>Dispute Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4">
            <DetailRow label="Reason" value={dispute.reason} capitalize />
            <DetailRow label="Invoice" value={dispute.invoice_number} />
            <DetailRow
              label="Disputed Amount"
              value={
                dispute.disputed_amount != null
                  ? formatCurrency(dispute.disputed_amount, dispute.currency || undefined)
                  : undefined
              }
            />
            <DetailRow
              label="Currency"
              value={dispute.currency}
            />
          </div>

          {dispute.reason_detail && (
            <div className="pt-3 border-t border-slate-100">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
                Reason Detail
              </p>
              <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
                {dispute.reason_detail}
              </p>
            </div>
          )}

          {dispute.notes && (
            <div className="pt-3 border-t border-slate-100">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
                Notes
              </p>
              <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
                {dispute.notes}
              </p>
            </div>
          )}

          {dispute.resolution_notes && (
            <div className="pt-3 border-t border-slate-100">
              <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">
                Resolution Notes
              </p>
              <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
                {dispute.resolution_notes}
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function DetailRow({
  label,
  value,
  capitalize = false,
}: {
  label: string;
  value?: string | null;
  capitalize?: boolean;
}) {
  return (
    <div>
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
        {label}
      </p>
      <p
        className={`mt-0.5 text-sm font-medium text-slate-900 ${
          capitalize ? "capitalize" : ""
        }`}
      >
        {value ? value.replace(/_/g, " ") : "\u2014"}
      </p>
    </div>
  );
}
