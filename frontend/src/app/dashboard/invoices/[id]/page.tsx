"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { invoiceApi } from "@/lib/api";
import { formatCurrency, formatCurrencyFull, formatDate } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageLoader } from "@/components/ui/spinner";
import {
  ArrowLeft,
  FileText,
  Calendar,
  Clock,
  DollarSign,
  AlertTriangle,
  Banknote,
  Globe,
  Hash,
  User,
} from "lucide-react";

interface InvoiceDetail {
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
  description?: string;
  notes?: string;
  payment_terms?: string;
  line_items?: Array<{
    description?: string;
    quantity?: number;
    unit_price?: number;
    amount?: number;
  }>;
  [key: string]: unknown;
}

function getStatusBadgeVariant(
  status: string
): "success" | "danger" | "warning" | "info" | "neutral" {
  switch (status?.toLowerCase()) {
    case "paid":
      return "success";
    case "overdue":
      return "danger";
    case "disputed":
      return "warning";
    case "partial":
      return "warning";
    case "open":
      return "info";
    default:
      return "neutral";
  }
}

export default function InvoiceDetailPage() {
  const params = useParams();
  const router = useRouter();
  const invoiceId = params.id as string;

  const { data: invoice, isLoading } = useQuery({
    queryKey: ["invoice", invoiceId],
    queryFn: () =>
      invoiceApi.get(invoiceId).then((r) => r.data as InvoiceDetail),
  });

  if (isLoading) return <PageLoader />;

  if (!invoice) {
    return (
      <div className="text-center py-16">
        <p className="text-slate-500">Invoice not found</p>
        <Button
          variant="ghost"
          className="mt-4"
          onClick={() => router.push("/dashboard/invoices")}
        >
          Go back
        </Button>
      </div>
    );
  }

  const totalAmount = invoice.total_amount ?? invoice.amount ?? 0;
  const amountRemaining =
    invoice.amount_remaining ?? invoice.remaining_amount ?? 0;
  const amountPaid = invoice.amount_paid ?? totalAmount - amountRemaining;
  const daysOverdue = invoice.days_overdue ?? 0;
  const currency = invoice.currency ?? "AED";
  const lineItems = invoice.line_items ?? (invoice.items as InvoiceDetail["line_items"]) ?? [];
  const descriptionText = invoice.description ?? invoice.notes ?? null;

  return (
    <div className="space-y-6">
      {/* Header with back button */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/dashboard/invoices")}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 transition-colors"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-xl font-bold text-slate-900">
              {invoice.invoice_number}
            </h1>
            <p className="text-sm text-slate-500">
              {invoice.customer_name || "Invoice details"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={getStatusBadgeVariant(invoice.status)} dot>
            {invoice.status?.replace(/_/g, " ")}
          </Badge>
        </div>
      </div>

      {/* Key Metric Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 mb-1">Total Amount</p>
            <p className="text-xl font-bold text-slate-900">
              {formatCurrency(totalAmount, currency)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 mb-1">Amount Remaining</p>
            <p
              className={`text-xl font-bold ${
                amountRemaining > 0 ? "text-red-600" : "text-emerald-600"
              }`}
            >
              {formatCurrency(amountRemaining, currency)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 mb-1">Days Overdue</p>
            <p
              className={`text-xl font-bold ${
                daysOverdue > 0 ? "text-red-600" : "text-slate-900"
              }`}
            >
              {daysOverdue > 0 ? daysOverdue : "0"}
            </p>
            {invoice.aging_bucket && (
              <p className="text-[10px] text-slate-400 mt-0.5">
                {invoice.aging_bucket}
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 mb-1">Currency</p>
            <p className="text-xl font-bold text-slate-900">{currency}</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column - Invoice Details */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Invoice Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <InfoRow
                icon={Calendar}
                label="Invoice Date"
                value={formatDate(invoice.invoice_date)}
              />
              <InfoRow
                icon={Clock}
                label="Due Date"
                value={formatDate(invoice.due_date)}
              />
              {invoice.payment_terms && (
                <InfoRow
                  icon={FileText}
                  label="Payment Terms"
                  value={invoice.payment_terms}
                />
              )}
              {invoice.customer_name && (
                <div
                  className="flex items-center gap-3 cursor-pointer group"
                  onClick={() => {
                    if (invoice.customer_id) router.push(`/dashboard/customers/${invoice.customer_id}`);
                  }}
                >
                  <User className="h-4 w-4 text-slate-400 flex-shrink-0" />
                  <div className="min-w-0">
                    <p className="text-[10px] text-slate-400 uppercase tracking-wide">
                      Customer
                    </p>
                    <p className="text-sm text-blue-600 group-hover:text-blue-800 group-hover:underline truncate">
                      {invoice.customer_name}
                    </p>
                  </div>
                </div>
              )}
              {!invoice.customer_name && invoice.customer_id && (
                <div
                  className="flex items-center gap-3 cursor-pointer group"
                  onClick={() => router.push(`/dashboard/customers/${invoice.customer_id}`)}
                >
                  <User className="h-4 w-4 text-slate-400 flex-shrink-0" />
                  <div className="min-w-0">
                    <p className="text-[10px] text-slate-400 uppercase tracking-wide">
                      Customer
                    </p>
                    <p className="text-sm text-blue-600 group-hover:text-blue-800 group-hover:underline truncate">
                      View Customer
                    </p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Payment Summary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <InfoRow
                icon={DollarSign}
                label="Total Amount"
                value={formatCurrencyFull(totalAmount, currency)}
              />
              <InfoRow
                icon={Banknote}
                label="Amount Paid"
                value={formatCurrencyFull(amountPaid, currency)}
              />
              <InfoRow
                icon={AlertTriangle}
                label="Remaining"
                value={formatCurrencyFull(amountRemaining, currency)}
              />
              <InfoRow
                icon={Globe}
                label="Currency"
                value={currency}
              />
            </CardContent>
          </Card>
        </div>

        {/* Right column - Notes & Line Items */}
        <div className="lg:col-span-2 space-y-4">
          {/* Description / Notes */}
          {descriptionText && (
            <Card>
              <CardHeader>
                <CardTitle>Description / Notes</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">
                  {descriptionText}
                </p>
              </CardContent>
            </Card>
          )}

          {/* Line Items */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Line Items</CardTitle>
              <Badge variant="neutral">
                {lineItems.length} item{lineItems.length !== 1 ? "s" : ""}
              </Badge>
            </CardHeader>
            <CardContent className="p-0">
              {lineItems.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-100">
                        <th className="text-left px-6 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">
                          Description
                        </th>
                        <th className="text-right px-6 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">
                          Qty
                        </th>
                        <th className="text-right px-6 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">
                          Unit Price
                        </th>
                        <th className="text-right px-6 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">
                          Amount
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {lineItems.map((item, i) => (
                        <tr
                          key={i}
                          className="hover:bg-slate-50 transition-colors"
                        >
                          <td className="px-6 py-3 text-slate-700">
                            {item.description || `Item ${i + 1}`}
                          </td>
                          <td className="px-6 py-3 text-right text-slate-700">
                            {item.quantity != null ? item.quantity : "—"}
                          </td>
                          <td className="px-6 py-3 text-right text-slate-700">
                            {item.unit_price != null
                              ? formatCurrencyFull(item.unit_price, currency)
                              : "—"}
                          </td>
                          <td className="px-6 py-3 text-right font-medium text-slate-900">
                            {item.amount != null
                              ? formatCurrencyFull(item.amount, currency)
                              : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-t-2 border-slate-200">
                        <td
                          colSpan={3}
                          className="px-6 py-3 text-right text-sm font-semibold text-slate-700"
                        >
                          Total
                        </td>
                        <td className="px-6 py-3 text-right text-sm font-bold text-slate-900">
                          {formatCurrencyFull(totalAmount, currency)}
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              ) : (
                <p className="px-6 py-8 text-center text-sm text-slate-400">
                  No line items available for this invoice
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function InfoRow({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <Icon className="h-4 w-4 text-slate-400 flex-shrink-0" />
      <div className="min-w-0">
        <p className="text-[10px] text-slate-400 uppercase tracking-wide">
          {label}
        </p>
        <p className="text-sm text-slate-700 truncate">{value}</p>
      </div>
    </div>
  );
}
