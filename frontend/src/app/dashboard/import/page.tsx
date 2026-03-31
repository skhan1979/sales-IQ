"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import api, { getAccessToken } from "@/lib/api";
import { dataQualityApi } from "@/lib/api-extra";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/toast";
import {
  Upload,
  FileSpreadsheet,
  ArrowRight,
  CheckCircle,
  AlertCircle,
  AlertTriangle,
  Columns,
  Play,
  Shield,
  Zap,
  Eye,
  SkipForward,
  RefreshCw,
  Download,
  Info,
  XCircle,
} from "lucide-react";

type Step = "upload" | "mapping" | "preview" | "executing" | "data_quality" | "complete";

interface MappingResult {
  headers: string[];
  auto_mapping: Record<string, string>;
  available_fields: string[];
  required_fields: string[];
  unmapped_headers: string[];
  sample_rows: Record<string, unknown>[];
  total_rows: number;
  csv_content: string;
  filename: string;
}

interface PreviewResult {
  total_rows: number;
  preview_rows: { row_number: number; parsed: Record<string, unknown>; errors: string[] }[];
  missing_required_fields: string[];
  mapped_fields: string[];
  unmapped_headers: string[];
  errors: string[];
  warnings: string[];
  can_import: boolean;
}

interface DQIssue {
  entity_id: string;
  stage: string;
  severity: string;
  field: string;
  message: string;
}

interface DQChange {
  entity_id: string;
  stage: string;
  field: string;
  old_value: string | null;
  new_value: string | null;
}

interface DQResult {
  run_id: string;
  status: string;
  entity_type: string;
  records_processed: number;
  records_succeeded: number;
  records_failed: number;
  total_issues: number;
  quarantined_count: number;
  average_quality_score: number;
  stage_timings: Record<string, number>;
  duration_ms: number;
  error: string | null;
  entity_results?: {
    entity_id: string;
    quality_score: number;
    issues: DQIssue[];
    changes: DQChange[];
    is_quarantined: boolean;
  }[];
  normalization_changes?: DQChange[];
  anomalies?: Record<string, unknown>[];
  enrichments?: Record<string, unknown>[];
}

interface ImportResult {
  entity_type: string;
  total_rows: number;
  created: number;
  updated?: number;
  skipped: number;
  errors: string[];
}

/* ─── Helper: Aggregate issues by severity+field ─── */
function aggregateIssues(dq: DQResult) {
  const map: Record<string, { severity: string; field: string; message: string; count: number }> = {};
  for (const er of dq.entity_results || []) {
    for (const issue of er.issues) {
      const key = `${issue.severity}::${issue.field}::${issue.message}`;
      if (!map[key]) {
        map[key] = { severity: issue.severity, field: issue.field, message: issue.message, count: 0 };
      }
      map[key].count++;
    }
  }
  return Object.values(map).sort((a, b) => {
    const sevOrder: Record<string, number> = { critical: 0, warning: 1, info: 2 };
    return (sevOrder[a.severity] ?? 3) - (sevOrder[b.severity] ?? 3) || b.count - a.count;
  });
}

function severityColor(sev: string) {
  switch (sev) {
    case "critical": return { bg: "bg-red-100", text: "text-red-700", dot: "bg-red-500" };
    case "warning": return { bg: "bg-amber-100", text: "text-amber-700", dot: "bg-amber-500" };
    default: return { bg: "bg-blue-100", text: "text-blue-700", dot: "bg-blue-500" };
  }
}

function scoreColor(score: number) {
  if (score >= 90) return "text-emerald-600";
  if (score >= 70) return "text-amber-600";
  return "text-red-600";
}

export default function CSVImportPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);

  const [step, setStep] = useState<Step>("upload");
  const [entityType, setEntityType] = useState("customers");
  const [file, setFile] = useState<File | null>(null);
  const [mappingResult, setMappingResult] = useState<MappingResult | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [csvContent, setCsvContent] = useState<string>("");
  const [availableFields, setAvailableFields] = useState<string[]>([]);
  const [requiredFields, setRequiredFields] = useState<string[]>([]);
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [dqResult, setDqResult] = useState<DQResult | null>(null);
  const [dqLoading, setDqLoading] = useState(false);
  const [fixesApplied, setFixesApplied] = useState(false);

  /* ─── Upload Mutation ─── */
  const uploadMutation = useMutation({
    mutationFn: async (f: File) => {
      const form = new FormData();
      form.append("file", f);
      form.append("entity_type", entityType);
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const token = getAccessToken();
      return axios
        .post(`${baseUrl}/api/v1/import/upload-and-map`, form, {
          headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        })
        .then((r) => r.data);
    },
    onSuccess: (data: MappingResult) => {
      setMappingResult(data);
      setMapping(data.auto_mapping || {});
      setCsvContent(data.csv_content || "");
      setAvailableFields(data.available_fields || []);
      setRequiredFields(data.required_fields || []);
      setStep("mapping");
      const mappedCount = Object.keys(data.auto_mapping || {}).length;
      const totalHeaders = (data.headers || []).length;
      toast.success(
        "File uploaded",
        `${data.total_rows} rows detected, ${mappedCount}/${totalHeaders} columns auto-mapped`
      );
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Could not process the file. Ensure it is a valid CSV or Excel file.";
      toast.error("Upload failed", msg);
    },
  });

  /* ─── Preview Mutation ─── */
  const previewMutation = useMutation({
    mutationFn: () =>
      api
        .post("/import/preview", { entity_type: entityType, mapping, csv_content: csvContent })
        .then((r) => r.data),
    onSuccess: (data: PreviewResult) => {
      setPreview(data);
      setStep("preview");
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Preview failed";
      toast.error("Preview failed", msg);
    },
  });

  /* ─── Execute Import Mutation ─── */
  const executeMutation = useMutation({
    mutationFn: () =>
      api
        .post("/import/execute", { entity_type: entityType, mapping, csv_content: csvContent })
        .then((r) => r.data),
    onSuccess: (data: ImportResult) => {
      setImportResult(data);
      queryClient.invalidateQueries();
      toast.success("Import complete", `${data.created || 0} records created`);
      // Automatically trigger Data Quality scan
      triggerDQScan();
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Import failed";
      toast.error("Import failed", msg);
      setStep("preview"); // Go back to preview on failure
    },
  });

  /* ─── DQ Scan ─── */
  const triggerDQScan = useCallback(async () => {
    setStep("data_quality");
    setDqLoading(true);
    try {
      // Map import entity types to DQ entity types (DQ only supports customers/invoices/payments)
      const dqEntityMap: Record<string, string> = {
        customers: "customers",
        invoices: "invoices",
        payments: "payments",
      };
      const dqEntity = dqEntityMap[entityType];
      if (!dqEntity) {
        // Entity type not supported by DQ — skip to complete
        setDqLoading(false);
        setStep("complete");
        return;
      }
      const { data } = await dataQualityApi.scanDetailed({ entity_type: dqEntity });
      setDqResult(data);
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Data quality scan encountered an error";
      toast.error("DQ Scan issue", msg);
      // Still show results page even if DQ failed
      setDqResult(null);
    } finally {
      setDqLoading(false);
    }
  }, [entityType, toast]);

  /* ─── Auto-fix Mutation ─── */
  const autoFixMutation = useMutation({
    mutationFn: async () => {
      if (!dqResult?.normalization_changes?.length && !dqResult?.enrichments?.length) {
        return { applied: 0, total: 0 };
      }
      const fixes: Record<string, unknown>[] = [];
      // Collect normalization changes
      for (const change of dqResult?.normalization_changes || []) {
        if (change.new_value) {
          fixes.push({
            entity_id: change.entity_id,
            entity_type: entityType,
            field: change.field,
            new_value: change.new_value,
          });
        }
      }
      // Collect enrichments
      for (const enrichment of dqResult?.enrichments || []) {
        if (enrichment.value && enrichment.entity_id) {
          fixes.push({
            entity_id: enrichment.entity_id as string,
            entity_type: entityType,
            field: enrichment.field as string,
            new_value: enrichment.value as string,
          });
        }
      }
      if (fixes.length === 0) return { applied: 0, total: 0 };
      const { data } = await dataQualityApi.applyFixBulk({ fixes });
      return data;
    },
    onSuccess: (data) => {
      setFixesApplied(true);
      const applied = (data as { applied?: number })?.applied || 0;
      toast.success("Fixes applied", `${applied} corrections applied successfully`);
      queryClient.invalidateQueries();
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "Failed to apply fixes";
      toast.error("Auto-fix failed", msg);
    },
  });

  /* ─── File Select ─── */
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      setFile(f);
      uploadMutation.mutate(f);
    }
  };

  /* ─── Reset ─── */
  const resetAll = () => {
    setStep("upload");
    setFile(null);
    setMappingResult(null);
    setMapping({});
    setCsvContent("");
    setAvailableFields([]);
    setRequiredFields([]);
    setPreview(null);
    setImportResult(null);
    setDqResult(null);
    setDqLoading(false);
    setFixesApplied(false);
  };

  /* ─── Mapping helpers ─── */
  const mappedCount = Object.values(mapping).filter(Boolean).length;
  const totalHeaders = mappingResult?.headers.length || 0;
  const unmappedRequired = requiredFields.filter((f) => !Object.values(mapping).includes(f));

  /* ─── Step bar config ─── */
  const steps: { key: Step; label: string }[] = [
    { key: "upload", label: "Upload" },
    { key: "mapping", label: "Map Fields" },
    { key: "preview", label: "Preview" },
    { key: "data_quality", label: "Data Quality" },
    { key: "complete", label: "Complete" },
  ];
  const stepIndex = steps.findIndex((s) => s.key === step || (step === "executing" && s.key === "data_quality"));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900">Data Import</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Upload D365, SAP, or CSV files — auto-map fields, preview, import, and run data quality checks
        </p>
      </div>

      {/* ── Progress Steps ── */}
      <div className="flex items-center gap-2">
        {steps.map((s, i) => (
          <React.Fragment key={s.key}>
            <div
              className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium ${
                i <= stepIndex ? "bg-blue-100 text-blue-700" : "bg-slate-100 text-slate-400"
              }`}
            >
              <span
                className={`h-5 w-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                  i < stepIndex
                    ? "bg-blue-600 text-white"
                    : i === stepIndex
                    ? "bg-blue-600 text-white"
                    : "bg-slate-300 text-white"
                }`}
              >
                {i < stepIndex ? "✓" : i + 1}
              </span>
              {s.label}
            </div>
            {i < steps.length - 1 && <ArrowRight className="h-3 w-3 text-slate-300" />}
          </React.Fragment>
        ))}
      </div>

      {/* ══════════════════════════════════════════════════════════════
          Step 1: UPLOAD
         ══════════════════════════════════════════════════════════════ */}
      {step === "upload" && (
        <Card>
          <CardContent className="p-8">
            <div className="mb-6">
              <label className="block text-sm font-medium text-slate-700 mb-2">Entity Type</label>
              <select
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm w-48"
                value={entityType}
                onChange={(e) => setEntityType(e.target.value)}
              >
                <option value="customers">Customers</option>
                <option value="invoices">Invoices</option>
                <option value="payments">Payments</option>
                <option value="collections">Collections</option>
                <option value="disputes">Disputes</option>
                <option value="credit_limits">Credit Limits</option>
              </select>
            </div>
            <div
              onClick={() => fileRef.current?.click()}
              className="border-2 border-dashed border-slate-300 rounded-xl p-12 text-center cursor-pointer hover:border-blue-400 hover:bg-blue-50/30 transition-colors"
            >
              <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={handleFileSelect} />
              <Upload className="h-10 w-10 text-slate-300 mx-auto mb-4" />
              <p className="text-sm font-medium text-slate-700">
                {file ? file.name : "Click to upload an Excel or CSV file"}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Supports D365 F&O, SAP B1, and generic .xlsx / .xls / .csv formats (max 10 MB)
              </p>
            </div>
            {uploadMutation.isPending && (
              <div className="flex items-center justify-center gap-2 mt-4">
                <RefreshCw className="h-4 w-4 text-blue-600 animate-spin" />
                <p className="text-sm text-blue-600">Parsing file and auto-mapping columns...</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ══════════════════════════════════════════════════════════════
          Step 2: FIELD MAPPING
         ══════════════════════════════════════════════════════════════ */}
      {step === "mapping" && mappingResult && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Field Mapping</CardTitle>
              <div className="flex items-center gap-3">
                <Badge variant={mappedCount === totalHeaders ? "success" : "neutral"}>
                  {mappedCount}/{totalHeaders} mapped
                </Badge>
                {unmappedRequired.length > 0 && (
                  <Badge variant="danger">
                    {unmappedRequired.length} required unmapped
                  </Badge>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-500 mb-4">
              {mappingResult.total_rows} rows from <span className="font-medium">{mappingResult.filename}</span>.
              Verify auto-detected mappings below. Required fields are marked with *.
            </p>

            {/* Unmapped required warning */}
            {unmappedRequired.length > 0 && (
              <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 flex items-start gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-xs font-medium text-amber-800">Required fields not yet mapped:</p>
                  <p className="text-xs text-amber-700 mt-0.5">{unmappedRequired.join(", ")}</p>
                </div>
              </div>
            )}

            <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
              {mappingResult.headers.map((header) => {
                const target = mapping[header] || "";
                const isRequired = requiredFields.includes(target);
                const isMapped = !!target;
                return (
                  <div key={header} className="flex items-center gap-3 py-1.5">
                    {/* Source column name */}
                    <div className="w-[38%]">
                      <span className="text-sm font-mono text-slate-700 bg-slate-100 px-2.5 py-1 rounded inline-block max-w-full truncate">
                        {header}
                      </span>
                    </div>

                    <ArrowRight className="h-4 w-4 text-slate-300 flex-shrink-0" />

                    {/* Target field dropdown */}
                    <div className="w-[38%]">
                      <select
                        className={`w-full rounded-lg border px-3 py-1.5 text-sm ${
                          isMapped
                            ? "border-emerald-300 bg-emerald-50 text-emerald-800"
                            : "border-slate-300 bg-white text-slate-500"
                        }`}
                        value={target}
                        onChange={(e) => setMapping((m) => ({ ...m, [header]: e.target.value }))}
                      >
                        <option value="">— Skip —</option>
                        {availableFields.map((field) => (
                          <option key={field} value={field}>
                            {requiredFields.includes(field) ? `${field} *` : field}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Status badge */}
                    <div className="w-[12%]">
                      <Badge variant={isMapped ? "success" : "neutral"} className="text-[10px]">
                        {isMapped ? (isRequired ? "Required ✓" : "Mapped") : "Skip"}
                      </Badge>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="flex gap-2 mt-6 pt-4 border-t border-slate-100">
              <Button variant="outline" onClick={() => { setStep("upload"); setFile(null); setMappingResult(null); }}>
                Back
              </Button>
              <Button
                onClick={() => previewMutation.mutate()}
                loading={previewMutation.isPending}
                disabled={mappedCount === 0}
                icon={<Columns className="h-4 w-4" />}
              >
                Preview Import
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ══════════════════════════════════════════════════════════════
          Step 3: PREVIEW
         ══════════════════════════════════════════════════════════════ */}
      {step === "preview" && preview && (
        <Card>
          <CardHeader>
            <CardTitle>Import Preview</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="rounded-lg bg-emerald-50 p-4 text-center">
                <CheckCircle className="h-5 w-5 text-emerald-600 mx-auto mb-1" />
                <p className="text-lg font-bold text-emerald-700">
                  {preview.total_rows - preview.errors.length}
                </p>
                <p className="text-xs text-emerald-600">Valid rows</p>
              </div>
              <div className="rounded-lg bg-red-50 p-4 text-center">
                <AlertCircle className="h-5 w-5 text-red-600 mx-auto mb-1" />
                <p className="text-lg font-bold text-red-700">{preview.errors.length}</p>
                <p className="text-xs text-red-600">Errors</p>
              </div>
              <div className="rounded-lg bg-amber-50 p-4 text-center">
                <AlertTriangle className="h-5 w-5 text-amber-600 mx-auto mb-1" />
                <p className="text-lg font-bold text-amber-700">{preview.warnings.length}</p>
                <p className="text-xs text-amber-600">Warnings</p>
              </div>
            </div>

            {/* Missing required fields */}
            {preview.missing_required_fields.length > 0 && (
              <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 flex items-start gap-2">
                <XCircle className="h-4 w-4 text-red-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-xs font-medium text-red-800">Missing required field mappings (import blocked):</p>
                  <p className="text-xs text-red-700 mt-0.5">{preview.missing_required_fields.join(", ")}</p>
                </div>
              </div>
            )}

            {/* Sample errors */}
            {preview.errors.length > 0 && (
              <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3">
                <p className="text-xs font-medium text-red-700 mb-2">Sample Errors:</p>
                {preview.errors.slice(0, 5).map((err, i) => (
                  <p key={i} className="text-xs text-red-600">{err}</p>
                ))}
                {preview.errors.length > 5 && (
                  <p className="text-xs text-red-500 mt-1">... and {preview.errors.length - 5} more</p>
                )}
              </div>
            )}

            {/* Unmapped columns info */}
            {preview.unmapped_headers.length > 0 && (
              <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-3 flex items-start gap-2">
                <Info className="h-4 w-4 text-slate-500 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-xs font-medium text-slate-700">Skipped columns (not mapped):</p>
                  <p className="text-xs text-slate-500 mt-0.5">{preview.unmapped_headers.join(", ")}</p>
                </div>
              </div>
            )}

            <div className="flex gap-2 mt-4">
              <Button variant="outline" onClick={() => setStep("mapping")}>
                Back to Mapping
              </Button>
              <Button
                onClick={() => {
                  setStep("executing");
                  executeMutation.mutate();
                }}
                loading={executeMutation.isPending}
                disabled={!preview.can_import}
                icon={<Play className="h-4 w-4" />}
              >
                Import {preview.total_rows - preview.errors.length} rows & Run Data Quality
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ══════════════════════════════════════════════════════════════
          Step 3.5: EXECUTING (brief loading state)
         ══════════════════════════════════════════════════════════════ */}
      {step === "executing" && (
        <Card>
          <CardContent className="p-12 text-center">
            <RefreshCw className="h-10 w-10 text-blue-500 mx-auto mb-4 animate-spin" />
            <h2 className="text-lg font-bold text-slate-900 mb-2">Importing Data...</h2>
            <p className="text-sm text-slate-500">
              Creating records and preparing data quality analysis
            </p>
          </CardContent>
        </Card>
      )}

      {/* ══════════════════════════════════════════════════════════════
          Step 4: DATA QUALITY RESULTS
         ══════════════════════════════════════════════════════════════ */}
      {step === "data_quality" && (
        <div className="space-y-4">
          {/* Import summary bar */}
          {importResult && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 flex items-center gap-3">
              <CheckCircle className="h-5 w-5 text-emerald-600 flex-shrink-0" />
              <p className="text-sm text-emerald-800">
                <span className="font-semibold">{importResult.created}</span> {entityType} imported
                {importResult.updated ? `, ${importResult.updated} updated` : ""}
                {importResult.skipped ? `, ${importResult.skipped} skipped` : ""}
              </p>
            </div>
          )}

          {/* DQ Loading */}
          {dqLoading && (
            <Card>
              <CardContent className="p-12 text-center">
                <Shield className="h-10 w-10 text-indigo-500 mx-auto mb-4 animate-pulse" />
                <h2 className="text-lg font-bold text-slate-900 mb-2">Running Data Quality Scan...</h2>
                <p className="text-sm text-slate-500">
                  Validating, deduplicating, normalizing, detecting anomalies, and enriching your data
                </p>
              </CardContent>
            </Card>
          )}

          {/* DQ Results */}
          {!dqLoading && dqResult && (
            <>
              {/* Score + Summary Cards */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <Card>
                  <CardContent className="p-4 text-center">
                    <Shield className="h-5 w-5 text-indigo-500 mx-auto mb-1" />
                    <p className={`text-2xl font-bold ${scoreColor(dqResult.average_quality_score)}`}>
                      {dqResult.average_quality_score.toFixed(1)}
                    </p>
                    <p className="text-[10px] text-slate-500 mt-0.5">Quality Score</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4 text-center">
                    <FileSpreadsheet className="h-5 w-5 text-blue-500 mx-auto mb-1" />
                    <p className="text-2xl font-bold text-slate-900">{dqResult.records_processed}</p>
                    <p className="text-[10px] text-slate-500 mt-0.5">Records Scanned</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4 text-center">
                    <AlertTriangle className="h-5 w-5 text-amber-500 mx-auto mb-1" />
                    <p className="text-2xl font-bold text-amber-700">{dqResult.total_issues}</p>
                    <p className="text-[10px] text-slate-500 mt-0.5">Issues Found</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4 text-center">
                    <XCircle className="h-5 w-5 text-red-500 mx-auto mb-1" />
                    <p className="text-2xl font-bold text-red-700">{dqResult.quarantined_count}</p>
                    <p className="text-[10px] text-slate-500 mt-0.5">Quarantined</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="p-4 text-center">
                    <Zap className="h-5 w-5 text-emerald-500 mx-auto mb-1" />
                    <p className="text-2xl font-bold text-emerald-700">
                      {(dqResult.normalization_changes?.length || 0) + (dqResult.enrichments?.length || 0)}
                    </p>
                    <p className="text-[10px] text-slate-500 mt-0.5">Auto-fixable</p>
                  </CardContent>
                </Card>
              </div>

              {/* Issues Table */}
              {dqResult.total_issues > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">Issues & Recommendations</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-slate-200">
                            <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">Severity</th>
                            <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">Field</th>
                            <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">Issue</th>
                            <th className="text-right py-2 px-3 text-xs font-medium text-slate-500">Count</th>
                          </tr>
                        </thead>
                        <tbody>
                          {aggregateIssues(dqResult).slice(0, 20).map((issue, i) => {
                            const c = severityColor(issue.severity);
                            return (
                              <tr key={i} className="border-b border-slate-100 last:border-0">
                                <td className="py-2 px-3">
                                  <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full ${c.bg} ${c.text}`}>
                                    <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
                                    {issue.severity}
                                  </span>
                                </td>
                                <td className="py-2 px-3 text-xs font-mono text-slate-700">{issue.field}</td>
                                <td className="py-2 px-3 text-xs text-slate-600">{issue.message}</td>
                                <td className="py-2 px-3 text-right text-xs font-semibold text-slate-700">
                                  {issue.count}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Normalization Changes Preview */}
              {(dqResult.normalization_changes?.length || 0) > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">Suggested Corrections</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto max-h-48 overflow-y-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-slate-200">
                            <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">Field</th>
                            <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">Current Value</th>
                            <th className="text-left py-2 px-3 text-xs font-medium text-slate-500">Suggested Value</th>
                          </tr>
                        </thead>
                        <tbody>
                          {dqResult.normalization_changes!.slice(0, 10).map((change, i) => (
                            <tr key={i} className="border-b border-slate-100 last:border-0">
                              <td className="py-2 px-3 text-xs font-mono text-slate-700">{change.field}</td>
                              <td className="py-2 px-3 text-xs text-red-600 line-through">{change.old_value || "—"}</td>
                              <td className="py-2 px-3 text-xs text-emerald-700 font-medium">{change.new_value || "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {(dqResult.normalization_changes?.length || 0) > 10 && (
                      <p className="text-xs text-slate-400 mt-2">
                        Showing 10 of {dqResult.normalization_changes!.length} corrections
                      </p>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Action Buttons */}
              <Card>
                <CardContent className="p-5">
                  <h3 className="text-sm font-semibold text-slate-900 mb-3">Actions</h3>
                  <div className="flex flex-wrap gap-3">
                    {/* Auto-fix with AI */}
                    {((dqResult.normalization_changes?.length || 0) + (dqResult.enrichments?.length || 0)) > 0 && !fixesApplied && (
                      <Button
                        onClick={() => autoFixMutation.mutate()}
                        loading={autoFixMutation.isPending}
                        icon={<Zap className="h-4 w-4" />}
                      >
                        Auto-fix with AI ({(dqResult.normalization_changes?.length || 0) + (dqResult.enrichments?.length || 0)} corrections)
                      </Button>
                    )}

                    {fixesApplied && (
                      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-200">
                        <CheckCircle className="h-4 w-4 text-emerald-600" />
                        <span className="text-sm text-emerald-700 font-medium">Fixes Applied</span>
                      </div>
                    )}

                    {/* Re-scan after fixes */}
                    {fixesApplied && (
                      <Button
                        variant="outline"
                        onClick={() => {
                          setFixesApplied(false);
                          setDqResult(null);
                          triggerDQScan();
                        }}
                        icon={<RefreshCw className="h-4 w-4" />}
                      >
                        Re-scan Data Quality
                      </Button>
                    )}

                    {/* Accept & Continue */}
                    <Button
                      variant={fixesApplied || dqResult.total_issues === 0 ? "primary" : "outline"}
                      onClick={() => setStep("complete")}
                      icon={<SkipForward className="h-4 w-4" />}
                    >
                      {dqResult.total_issues === 0 ? "Continue — Data is Clean" : "Accept & Continue"}
                    </Button>
                  </div>

                  {dqResult.quarantined_count > 0 && (
                    <p className="text-xs text-red-600 mt-3 flex items-center gap-1">
                      <AlertCircle className="h-3 w-3" />
                      {dqResult.quarantined_count} records quarantined due to critical issues — review recommended before continuing
                    </p>
                  )}
                </CardContent>
              </Card>
            </>
          )}

          {/* DQ not available for this entity */}
          {!dqLoading && !dqResult && (
            <Card>
              <CardContent className="p-8 text-center">
                <Info className="h-8 w-8 text-slate-400 mx-auto mb-3" />
                <p className="text-sm text-slate-500 mb-4">
                  Data Quality scanning is not available for {entityType} entity type, or an error occurred.
                </p>
                <Button onClick={() => setStep("complete")} icon={<SkipForward className="h-4 w-4" />}>
                  Continue to Summary
                </Button>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════
          Step 5: COMPLETE
         ══════════════════════════════════════════════════════════════ */}
      {step === "complete" && (
        <Card>
          <CardContent className="p-8 text-center">
            <CheckCircle className="h-12 w-12 text-emerald-500 mx-auto mb-4" />
            <h2 className="text-lg font-bold text-slate-900 mb-2">Import Complete</h2>

            {importResult && (
              <div className="text-sm text-slate-600 mb-4 space-y-1">
                <p>
                  <span className="font-semibold">{importResult.created}</span> {entityType} created
                  {importResult.updated ? `, ${importResult.updated} updated` : ""}
                  {importResult.skipped ? `, ${importResult.skipped} skipped` : ""}
                </p>
                {dqResult && (
                  <p>
                    Data Quality Score:{" "}
                    <span className={`font-bold ${scoreColor(dqResult.average_quality_score)}`}>
                      {dqResult.average_quality_score.toFixed(1)}%
                    </span>
                    {fixesApplied && <span className="text-emerald-600 ml-2">(AI corrections applied)</span>}
                  </p>
                )}
              </div>
            )}

            {importResult?.errors && importResult.errors.length > 0 && (
              <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-left max-w-lg mx-auto">
                <p className="text-xs font-medium text-red-700 mb-1">Import Errors ({importResult.errors.length}):</p>
                {importResult.errors.slice(0, 3).map((err, i) => (
                  <p key={i} className="text-xs text-red-600">{err}</p>
                ))}
                {importResult.errors.length > 3 && (
                  <p className="text-xs text-red-500 mt-1">... and {importResult.errors.length - 3} more</p>
                )}
              </div>
            )}

            <Button onClick={resetAll} className="mt-2">Import Another File</Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
