"use client";

import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { customerApi, intelligenceApi, invoiceApi } from "@/lib/api";
import {
  formatCurrency,
  formatDate,
  formatPercent,
  getRiskColor,
  getRiskLabel,
  getStatusColor,
} from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageLoader } from "@/components/ui/spinner";
import {
  ArrowLeft,
  Building2,
  Mail,
  Phone,
  MapPin,
  TrendingUp,
  AlertCircle,
  CreditCard,
  FileText,
  Globe,
  Shield,
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

interface CustomerDetail {
  id: string;
  customer_name: string;
  name?: string;
  external_id?: string;
  industry?: string;
  segment?: string;
  territory?: string;
  status: string;
  email?: string;
  phone?: string;
  address?: string;
  city?: string;
  country?: string;
  tax_id?: string;
  credit_limit?: number;
  outstanding_balance?: number;
  credit_utilization?: number;
  overdue_amount?: number;
  risk_score?: number;
  data_quality_score?: number;
  payment_terms_days?: number;
  avg_days_to_pay?: number;
  total_revenue_ytd?: number;
  created_at?: string;
  [key: string]: unknown;
}

export default function CustomerDetailPage() {
  const params = useParams();
  const router = useRouter();
  const customerId = params.id as string;

  const { data: customer, isLoading } = useQuery({
    queryKey: ["customer", customerId],
    queryFn: () => customerApi.get(customerId).then((r) => r.data as CustomerDetail),
  });

  const { data: healthScore } = useQuery({
    queryKey: ["health-score", customerId],
    queryFn: () => intelligenceApi.healthScore(customerId).then((r) => r.data),
    retry: false,
    enabled: !!customerId,
  });

  const { data: invoices } = useQuery({
    queryKey: ["customer-invoices", customerId],
    queryFn: () =>
      invoiceApi.list({ customer_id: customerId, limit: 10 }).then((r) => r.data),
    retry: false,
    enabled: !!customerId,
  });

  if (isLoading) return <PageLoader />;
  if (!customer) {
    return (
      <div className="text-center py-16">
        <p className="text-slate-500">Customer not found</p>
        <Button variant="ghost" className="mt-4" onClick={() => router.back()}>
          Go back
        </Button>
      </div>
    );
  }

  const invoiceList = Array.isArray(invoices?.items)
    ? invoices.items
    : Array.isArray(invoices?.invoices)
    ? invoices.invoices
    : Array.isArray(invoices)
    ? invoices
    : [];

  const creditLimit = Number(customer.credit_limit) || 0;
  const creditUtil = Number(customer.credit_utilization) || 0;
  const creditPct = creditLimit > 0 ? (creditUtil / creditLimit) * 100 : 0;
  const score = healthScore?.score || healthScore?.overall_score;
  const breakdown = healthScore?.breakdown || healthScore?.components || {};

  return (
    <div className="space-y-6">
      {/* Breadcrumb + actions */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/dashboard/customers")}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 transition-colors"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-xl font-bold text-slate-900">
              {customer.name || customer.customer_name}
            </h1>
            <p className="text-sm text-slate-500">
              {customer.external_id || customer.industry || "Customer details"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge
            variant={
              customer.status === "active"
                ? "success"
                : customer.status === "credit_hold"
                ? "danger"
                : "neutral"
            }
            dot
          >
            {customer.status?.replace("_", " ")}
          </Badge>
        </div>
      </div>

      {/* Top Row - Key Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 mb-1">Outstanding</p>
            <p className="text-xl font-bold text-slate-900">
              {formatCurrency(customer.outstanding_balance)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 mb-1">Overdue</p>
            <p className="text-xl font-bold text-red-600">
              {formatCurrency(customer.overdue_amount)}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 mb-1">Credit Usage</p>
            <div className="flex items-center gap-2">
              <p className="text-xl font-bold text-slate-900">
                {formatPercent(creditPct)}
              </p>
              <div className="flex-1 h-2 rounded-full bg-slate-100">
                <div
                  className={`h-full rounded-full ${
                    creditPct > 90
                      ? "bg-red-500"
                      : creditPct > 70
                      ? "bg-amber-500"
                      : "bg-emerald-500"
                  }`}
                  style={{ width: `${Math.min(creditPct, 100)}%` }}
                />
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-slate-500 mb-1">Health Score</p>
            <p className={`text-xl font-bold ${getRiskColor(score)}`}>
              {score != null ? `${score}/100` : "—"}
            </p>
            <p className="text-[10px] text-slate-400">{getRiskLabel(score)}</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column - Info */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Company Info</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {customer.industry && (
                <InfoRow icon={Building2} label="Industry" value={customer.industry} />
              )}
              {customer.segment && (
                <InfoRow icon={Shield} label="Segment" value={customer.segment} />
              )}
              {customer.territory && (
                <InfoRow icon={MapPin} label="Territory" value={customer.territory} />
              )}
              {customer.email && (
                <InfoRow icon={Mail} label="Email" value={customer.email} />
              )}
              {customer.phone && (
                <InfoRow icon={Phone} label="Phone" value={customer.phone} />
              )}
              {customer.country && (
                <InfoRow icon={Globe} label="Country" value={customer.country} />
              )}
              {customer.tax_id && (
                <InfoRow icon={FileText} label="Tax ID" value={customer.tax_id} />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Credit & Terms</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <InfoRow
                icon={CreditCard}
                label="Credit Limit"
                value={formatCurrency(customer.credit_limit)}
              />
              <InfoRow
                icon={FileText}
                label="Payment Terms"
                value={
                  customer.payment_terms_days
                    ? `Net ${customer.payment_terms_days}`
                    : "—"
                }
              />
              <InfoRow
                icon={TrendingUp}
                label="Avg Days to Pay"
                value={
                  customer.avg_days_to_pay
                    ? `${customer.avg_days_to_pay} days`
                    : "—"
                }
              />
              <InfoRow
                icon={AlertCircle}
                label="Data Quality"
                value={
                  customer.data_quality_score
                    ? `${customer.data_quality_score}%`
                    : "—"
                }
              />
            </CardContent>
          </Card>
        </div>

        {/* Center/Right - Health + Invoices */}
        <div className="lg:col-span-2 space-y-4">
          {/* Health breakdown */}
          {Object.keys(breakdown).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Health Score Breakdown</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={Object.entries(breakdown).map(([k, v]) => ({
                        name: k.replace(/_/g, " "),
                        score: v as number,
                      }))}
                      layout="vertical"
                    >
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                      <XAxis type="number" domain={[0, 100]} fontSize={11} />
                      <YAxis type="category" dataKey="name" width={100} fontSize={11} />
                      <Tooltip />
                      <Bar dataKey="score" fill="#6366f1" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Recent invoices */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Recent Invoices</CardTitle>
              <Badge variant="neutral">{invoiceList.length} shown</Badge>
            </CardHeader>
            <CardContent className="p-0">
              {invoiceList.length > 0 ? (
                <div className="divide-y divide-slate-100">
                  {invoiceList.map(
                    (
                      inv: {
                        id: string;
                        invoice_number?: string;
                        total_amount?: number;
                        amount?: number;
                        remaining_amount?: number;
                        amount_remaining?: number;
                        status?: string;
                        invoice_date?: string;
                        days_overdue?: number;
                      },
                      i: number
                    ) => (
                      <div
                        key={inv.id || i}
                        className="flex items-center justify-between px-6 py-3 hover:bg-slate-50 cursor-pointer"
                        onClick={() =>
                          router.push(`/dashboard/invoices/${inv.id}`)
                        }
                      >
                        <div>
                          <p className="text-sm font-medium text-slate-900">
                            {inv.invoice_number || `INV-${i + 1}`}
                          </p>
                          <p className="text-xs text-slate-500">
                            {formatDate(inv.invoice_date)}
                          </p>
                        </div>
                        <div className="flex items-center gap-3">
                          <Badge
                            variant={
                              inv.status === "paid"
                                ? "success"
                                : inv.status === "overdue"
                                ? "danger"
                                : inv.status === "disputed"
                                ? "warning"
                                : "info"
                            }
                          >
                            {inv.status || "open"}
                          </Badge>
                          <span className="text-sm font-medium text-slate-900 w-24 text-right">
                            {formatCurrency(inv.total_amount ?? inv.amount)}
                          </span>
                        </div>
                      </div>
                    )
                  )}
                </div>
              ) : (
                <p className="px-6 py-8 text-center text-sm text-slate-400">
                  No invoices found for this customer
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
