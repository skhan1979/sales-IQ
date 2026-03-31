"use client";

import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { invoiceApi, customerApi } from "@/lib/api";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";

interface CreateInvoiceModalProps {
  open: boolean;
  onClose: () => void;
  customerId?: string;
}

export function CreateInvoiceModal({
  open,
  onClose,
  customerId,
}: CreateInvoiceModalProps) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState({
    customer_id: customerId || "",
    invoice_number: "",
    total_amount: "",
    currency: "AED",
    invoice_date: new Date().toISOString().slice(0, 10),
    due_date: "",
    description: "",
  });

  const { data: customerData } = useQuery({
    queryKey: ["customers-select"],
    queryFn: () => customerApi.list({ limit: 100 }).then((r) => r.data),
    enabled: open && !customerId,
  });

  const customers = Array.isArray(customerData?.customers)
    ? customerData.customers
    : Array.isArray(customerData)
    ? customerData
    : [];

  const mutation = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      invoiceApi.create(data).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      queryClient.invalidateQueries({ queryKey: ["ar-summary"] });
      toast.success("Invoice created", `${form.invoice_number} has been added`);
      onClose();
      resetForm();
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail || "Failed to create invoice";
      toast.error("Creation failed", msg);
    },
  });

  const resetForm = () =>
    setForm({
      customer_id: customerId || "",
      invoice_number: "",
      total_amount: "",
      currency: "AED",
      invoice_date: new Date().toISOString().slice(0, 10),
      due_date: "",
      description: "",
    });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate({
      customer_id: form.customer_id,
      invoice_number: form.invoice_number,
      total_amount: parseFloat(form.total_amount),
      currency: form.currency,
      invoice_date: form.invoice_date,
      due_date: form.due_date || undefined,
      description: form.description || undefined,
    });
  };

  const update = (key: string, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Create Invoice"
      description="Add a new invoice to your receivables"
      size="md"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            loading={mutation.isPending}
            disabled={!form.customer_id || !form.invoice_number || !form.total_amount}
          >
            Create Invoice
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {!customerId && (
          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-slate-700">
              Customer *
            </label>
            <select
              className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              value={form.customer_id}
              onChange={(e) => update("customer_id", e.target.value)}
              required
            >
              <option value="">Select a customer...</option>
              {customers.map(
                (c: { id: string; customer_name: string }) => (
                  <option key={c.id} value={c.id}>
                    {c.customer_name}
                  </option>
                )
              )}
            </select>
          </div>
        )}
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Invoice Number *"
            placeholder="e.g. INV-2024-0001"
            value={form.invoice_number}
            onChange={(e) => update("invoice_number", e.target.value)}
            required
          />
          <Input
            label="Amount *"
            type="number"
            placeholder="50000"
            value={form.total_amount}
            onChange={(e) => update("total_amount", e.target.value)}
            required
          />
        </div>
        <div className="grid grid-cols-3 gap-4">
          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-slate-700">
              Currency
            </label>
            <select
              className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              value={form.currency}
              onChange={(e) => update("currency", e.target.value)}
            >
              <option value="AED">AED</option>
              <option value="SAR">SAR</option>
              <option value="QAR">QAR</option>
              <option value="KWD">KWD</option>
              <option value="BHD">BHD</option>
              <option value="OMR">OMR</option>
              <option value="USD">USD</option>
            </select>
          </div>
          <Input
            label="Invoice Date *"
            type="date"
            value={form.invoice_date}
            onChange={(e) => update("invoice_date", e.target.value)}
            required
          />
          <Input
            label="Due Date"
            type="date"
            value={form.due_date}
            onChange={(e) => update("due_date", e.target.value)}
          />
        </div>
        <Input
          label="Description"
          placeholder="Invoice description or PO reference"
          value={form.description}
          onChange={(e) => update("description", e.target.value)}
        />
      </form>
    </Modal>
  );
}
