"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { paymentApi } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageLoader } from "@/components/ui/spinner";
import {
  ArrowLeft,
  DollarSign,
  CalendarDays,
  CreditCard,
  Target,
  Hash,
  FileText,
  Landmark,
  Link2,
  StickyNote,
  User,
} from "lucide-react";

interface PaymentDetail {
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
  notes?: string;
  [key: string]: unknown;
}

export default function PaymentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const paymentId = params.id as string;

  const { data: payment, isLoading } = useQuery({
    queryKey: ["payment", paymentId],
    queryFn: () =>
      paymentApi.get(paymentId).then((r) => r.data as PaymentDetail),
  });

  if (isLoading) return <PageLoader />;

  if (!payment) {
    return (
      <div className="text-center py-16">
        <p className="text-slate-500">Payment not found</p>
        <Button variant="ghost" className="mt-4" onClick={() => router.back()}>
          Go back
        </Button>
      </div>
    );
  }

  const displayNumber =
    payment.payment_number || payment.reference_number || payment.id;

  const confidencePct =
    payment.match_confidence != null
      ? Math.round(payment.match_confidence * (payment.match_confidence <= 1 ? 100 : 1))
      : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/dashboard/payments")}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 transition-colors"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-xl font-bold text-slate-900">
              {displayNumber}
            </h1>
            {payment.customer_name && (
              <p className="text-sm text-slate-500">
                {payment.customer_name}
              </p>
            )}
          </div>
        </div>
        <Badge
          variant={payment.is_matched ? "success" : "warning"}
          dot
        >
          {payment.is_matched ? "Matched" : "Unmatched"}
        </Badge>
      </div>

      {/* Key Metric Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-1">
              <DollarSign className="h-4 w-4 text-slate-400" />
              <p className="text-xs text-slate-500">Amount</p>
            </div>
            <p className="text-xl font-bold text-slate-900">
              {formatCurrency(payment.amount, payment.currency || undefined)}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-1">
              <CalendarDays className="h-4 w-4 text-slate-400" />
              <p className="text-xs text-slate-500">Payment Date</p>
            </div>
            <p className="text-xl font-bold text-slate-900">
              {formatDate(payment.payment_date)}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-1">
              <CreditCard className="h-4 w-4 text-slate-400" />
              <p className="text-xs text-slate-500">Payment Method</p>
            </div>
            <p className="text-xl font-bold text-slate-900 capitalize">
              {payment.payment_method?.replace(/_/g, " ") || "\u2014"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-1">
              <Target className="h-4 w-4 text-slate-400" />
              <p className="text-xs text-slate-500">Match Confidence</p>
            </div>
            {confidencePct != null ? (
              <div>
                <p
                  className={`text-xl font-bold ${
                    confidencePct >= 80
                      ? "text-emerald-600"
                      : confidencePct >= 50
                      ? "text-amber-600"
                      : "text-red-600"
                  }`}
                >
                  {confidencePct}%
                </p>
                <div className="mt-1 h-1.5 w-full rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full ${
                      confidencePct >= 80
                        ? "bg-emerald-500"
                        : confidencePct >= 50
                        ? "bg-amber-500"
                        : "bg-red-500"
                    }`}
                    style={{ width: `${Math.min(confidencePct, 100)}%` }}
                  />
                </div>
              </div>
            ) : (
              <p className="text-xl font-bold text-slate-400">&mdash;</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Payment Details */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Payment Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {payment.bank_reference && (
              <DetailRow
                icon={Landmark}
                label="Bank Reference"
                value={payment.bank_reference}
              />
            )}
            {payment.reference && (
              <DetailRow
                icon={Hash}
                label="Reference"
                value={payment.reference}
              />
            )}
            {payment.payment_number && (
              <DetailRow
                icon={FileText}
                label="Payment Number"
                value={payment.payment_number}
              />
            )}
            {payment.reference_number && (
              <DetailRow
                icon={FileText}
                label="Reference Number"
                value={payment.reference_number}
              />
            )}
            {payment.customer_name ? (
              <div
                className="flex items-start gap-3 cursor-pointer group"
                onClick={() => {
                  if (payment.customer_id) router.push(`/dashboard/customers/${payment.customer_id}`);
                }}
              >
                <User className="h-4 w-4 text-slate-400 mt-0.5 flex-shrink-0" />
                <div className="min-w-0">
                  <p className="text-[10px] text-slate-400 uppercase tracking-wide">
                    Customer
                  </p>
                  <p className="text-sm text-blue-600 group-hover:text-blue-800 group-hover:underline truncate">
                    {payment.customer_name}
                  </p>
                </div>
              </div>
            ) : payment.customer_id ? (
              <div
                className="flex items-start gap-3 cursor-pointer group"
                onClick={() => router.push(`/dashboard/customers/${payment.customer_id}`)}
              >
                <User className="h-4 w-4 text-slate-400 mt-0.5 flex-shrink-0" />
                <div className="min-w-0">
                  <p className="text-[10px] text-slate-400 uppercase tracking-wide">
                    Customer
                  </p>
                  <p className="text-sm text-blue-600 group-hover:text-blue-800 group-hover:underline truncate">
                    View Customer
                  </p>
                </div>
              </div>
            ) : null}
            {payment.currency && (
              <DetailRow
                icon={DollarSign}
                label="Currency"
                value={payment.currency}
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Invoice Matching</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {payment.matched_invoice_id ? (
              <div className="space-y-4">
                <DetailRow
                  icon={Link2}
                  label="Matched Invoice"
                  value={payment.invoice_number || payment.matched_invoice_id}
                  href={`/dashboard/invoices/${payment.matched_invoice_id}`}
                />
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
                  <p className="text-sm font-medium text-emerald-700">
                    This payment has been matched to an invoice.
                  </p>
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
                <p className="text-sm font-medium text-amber-700">
                  No invoice has been matched to this payment yet.
                </p>
              </div>
            )}

            {payment.notes && (
              <DetailRow
                icon={StickyNote}
                label="Notes"
                value={payment.notes}
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function DetailRow({
  icon: Icon,
  label,
  value,
  href,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  href?: string;
}) {
  const router = useRouter();

  return (
    <div className="flex items-start gap-3">
      <Icon className="h-4 w-4 text-slate-400 mt-0.5 flex-shrink-0" />
      <div className="min-w-0">
        <p className="text-[10px] text-slate-400 uppercase tracking-wide">
          {label}
        </p>
        {href ? (
          <button
            onClick={() => router.push(href)}
            className="text-sm text-blue-600 hover:text-blue-800 hover:underline truncate block"
          >
            {value}
          </button>
        ) : (
          <p className="text-sm text-slate-700 break-words">{value}</p>
        )}
      </div>
    </div>
  );
}
