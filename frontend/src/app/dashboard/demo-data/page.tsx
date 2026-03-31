"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { demoDataApi } from "@/lib/api-extra";
import { formatNumber } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import {
  Database,
  Play,
  Trash2,
  RefreshCw,
  Users,
  FileText,
  CreditCard,
  AlertTriangle,
  PhoneCall,
  CheckCircle,
  Loader2,
  ShieldAlert,
} from "lucide-react";

export default function DemoDataPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [generating, setGenerating] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteInput, setDeleteInput] = useState("");

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["demo-stats"],
    queryFn: () => demoDataApi.stats().then((r) => r.data),
  });

  const generateMutation = useMutation({
    mutationFn: (opts: { erp_profile?: string; size?: string }) =>
      demoDataApi.generate(opts).then((r) => r.data),
    onSuccess: (data) => {
      queryClient.invalidateQueries();
      toast.success(
        "Demo data generated",
        `Created ${data.summary || "records"} successfully`
      );
      setGenerating(false);
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail || "Failed to generate demo data";
      toast.error("Generation failed", msg);
      setGenerating(false);
    },
  });

  const clearMutation = useMutation({
    mutationFn: () => demoDataApi.clear().then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries();
      toast.success("Demo data cleared", "All demo records have been removed");
      setShowDeleteConfirm(false);
      setDeleteInput("");
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail || "Could not remove demo data";
      toast.error("Clear failed", msg);
    },
  });

  const statCards = [
    { key: "customers", label: "Customers", icon: Users, color: "text-blue-600 bg-blue-50" },
    { key: "invoices", label: "Invoices", icon: FileText, color: "text-indigo-600 bg-indigo-50" },
    { key: "payments", label: "Payments", icon: CreditCard, color: "text-emerald-600 bg-emerald-50" },
    { key: "disputes", label: "Disputes", icon: AlertTriangle, color: "text-orange-600 bg-orange-50" },
    { key: "collection_activities", label: "Collections", icon: PhoneCall, color: "text-purple-600 bg-purple-50" },
  ];

  const presets = [
    {
      id: "d365_fo",
      name: "D365 Finance & Ops",
      description: "Dynamics 365 F&O profile with GCC customers, AED/SAR invoices, and realistic aging",
      size: "medium",
    },
    {
      id: "sap_b1",
      name: "SAP Business One",
      description: "SAP B1 profile with manufacturing customers, long payment terms, and large invoices",
      size: "medium",
    },
    {
      id: "generic",
      name: "Generic ERP Import",
      description: "Generic CSV import profile with multi-entity trading group and diverse data",
      size: "large",
    },
  ];

  const demoCount = statCards.reduce((sum, sc) => sum + (stats?.[sc.key]?.demo || 0), 0);
  const totalCount = statCards.reduce((sum, sc) => sum + (stats?.[sc.key]?.total || 0), 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Demo Data</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Generate realistic GCC demo data to explore all platform features
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="danger"
            size="sm"
            onClick={() => setShowDeleteConfirm(true)}
            disabled={totalCount === 0}
            icon={<Trash2 className="h-3.5 w-3.5" />}
          >
            Clear Demo Data
          </Button>
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      {showDeleteConfirm && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="p-5">
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-red-100 p-2 flex-shrink-0">
                <ShieldAlert className="h-5 w-5 text-red-600" />
              </div>
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-red-900 mb-1">
                  Confirm Demo Data Deletion
                </h3>
                <p className="text-xs text-red-700 mb-3">
                  This will permanently remove all {totalCount} demo/test records
                  (customers, invoices, payments, disputes, collections).
                  Only records tagged as demo or untagged records will be removed.
                  Production-imported data (with a source_system tag) will NOT be affected.
                </p>
                <p className="text-xs font-medium text-red-800 mb-2">
                  Type <span className="font-mono font-bold">DELETE</span> to confirm:
                </p>
                <div className="flex items-center gap-3">
                  <input
                    type="text"
                    value={deleteInput}
                    onChange={(e) => setDeleteInput(e.target.value)}
                    placeholder="Type DELETE"
                    className="rounded-lg border border-red-300 bg-white px-3 py-1.5 text-sm w-40 focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-500/20"
                    autoFocus
                  />
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={() => clearMutation.mutate()}
                    loading={clearMutation.isPending}
                    disabled={deleteInput !== "DELETE"}
                    icon={<Trash2 className="h-3.5 w-3.5" />}
                  >
                    Delete All Demo Data
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => { setShowDeleteConfirm(false); setDeleteInput(""); }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Current Data Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {statCards.map((sc) => {
          const d = stats?.[sc.key] || { total: 0, demo: 0, real: 0 };
          return (
            <Card key={sc.key}>
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <div className={`rounded-lg p-1.5 ${sc.color}`}>
                    <sc.icon className="h-3.5 w-3.5" />
                  </div>
                  <span className="text-xs font-medium text-slate-500">{sc.label}</span>
                </div>
                <p className="text-xl font-bold text-slate-900">{formatNumber(d.total)}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-[10px] text-blue-600">{d.demo} demo</span>
                  <span className="text-[10px] text-slate-400">|</span>
                  <span className="text-[10px] text-slate-500">{d.real} real</span>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Generation Presets */}
      <div>
        <h2 className="text-sm font-semibold text-slate-900 mb-3">Data Presets</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {presets.map((preset) => (
            <Card key={preset.id} className="relative overflow-hidden">
              <CardContent className="p-5">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-900">
                      {preset.name}
                    </h3>
                    <Badge variant="neutral" className="mt-1">
                      {preset.size}
                    </Badge>
                  </div>
                  <div className="rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 p-2">
                    <Database className="h-4 w-4 text-white" />
                  </div>
                </div>
                <p className="text-xs text-slate-500 mb-4 leading-relaxed">
                  {preset.description}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full"
                  loading={generating && generateMutation.isPending}
                  onClick={() => {
                    setGenerating(true);
                    generateMutation.mutate({
                      erp_profile: preset.id,
                      size: preset.size,
                    });
                  }}
                  icon={<Play className="h-3.5 w-3.5" />}
                >
                  Generate
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Quick Generate */}
      <Card>
        <CardHeader>
          <CardTitle>Quick Generate</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-500 mb-4">
            Generate a standard dataset with realistic GCC business data including
            customers with Arabic/English names, invoices with AED/SAR amounts,
            varied payment patterns, and overdue aging.
          </p>
          <Button
            loading={generateMutation.isPending}
            onClick={() => {
              setGenerating(true);
              generateMutation.mutate({});
            }}
            icon={<Play className="h-4 w-4" />}
          >
            Generate Default Dataset
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
