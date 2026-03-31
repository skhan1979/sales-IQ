"use client";

import React, { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { customerApi } from "@/lib/api";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";

interface CreateCustomerModalProps {
  open: boolean;
  onClose: () => void;
}

const INITIAL = {
  name: "",
  external_id: "",
  email: "",
  phone: "",
  industry: "",
  segment: "mid_market",
  territory: "UAE-Dubai",
  country: "AE",
  credit_limit: "500000",
  payment_terms_days: "30",
};

export function CreateCustomerModal({ open, onClose }: CreateCustomerModalProps) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState({ ...INITIAL });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  const mutation = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      customerApi.create(data).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      toast.success("Customer created", `${form.name} has been added`);
      handleClose();
    },
    onError: (err: unknown) => {
      const axiosErr = err as { response?: { data?: { error?: { message?: string }; detail?: string } } };
      const msg = axiosErr?.response?.data?.error?.message || axiosErr?.response?.data?.detail || "Failed to create customer";
      toast.error("Creation failed", msg);
    },
  });

  const validate = (): boolean => {
    const errs: Record<string, string> = {};
    if (!form.name.trim()) errs.name = "Customer name is required";
    else if (form.name.trim().length < 2) errs.name = "Name must be at least 2 characters";
    if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errs.email = "Invalid email";
    if (form.phone && !/^[+\d\s()-]{7,20}$/.test(form.phone)) errs.phone = "Invalid phone number";
    const cl = parseFloat(form.credit_limit);
    if (isNaN(cl) || cl < 0) errs.credit_limit = "Must be a positive number";
    else if (cl > 100_000_000) errs.credit_limit = "Exceeds maximum (100M)";
    setErrors(errs);
    // Mark all as touched
    const allTouched: Record<string, boolean> = {};
    Object.keys(form).forEach((k) => (allTouched[k] = true));
    setTouched(allTouched);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    mutation.mutate({
      name: form.name.trim(),
      external_id: form.external_id || undefined,
      email: form.email || undefined,
      phone: form.phone || undefined,
      industry: form.industry || undefined,
      segment: form.segment,
      territory: form.territory,
      country: form.country,
      currency: "AED",
      credit_limit: parseFloat(form.credit_limit) || 500000,
      payment_terms_days: parseInt(form.payment_terms_days) || 30,
    });
  };

  const handleClose = () => {
    setForm({ ...INITIAL });
    setErrors({});
    setTouched({});
    onClose();
  };

  const update = (key: string, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    if (touched[key]) {
      // Re-validate this field on change
      setErrors((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  };

  const touch = (key: string) => setTouched((prev) => ({ ...prev, [key]: true }));

  const fieldError = (key: string) => (touched[key] ? errors[key] : undefined);

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Add Customer"
      description="Create a new customer record in your portfolio"
      size="lg"
      footer={
        <>
          <Button variant="outline" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            loading={mutation.isPending}
            disabled={mutation.isPending}
          >
            Create Customer
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Customer Name *"
            placeholder="e.g. Al Futtaim Group"
            value={form.name}
            onChange={(e) => update("name", e.target.value)}
            onBlur={() => touch("name")}
            error={fieldError("name")}
            autoFocus
          />
          <Input
            label="External ID"
            placeholder="e.g. CUST-001"
            value={form.external_id}
            onChange={(e) => update("external_id", e.target.value)}
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Email"
            type="email"
            placeholder="finance@company.com"
            value={form.email}
            onChange={(e) => update("email", e.target.value)}
            onBlur={() => touch("email")}
            error={fieldError("email")}
          />
          <Input
            label="Phone"
            placeholder="+971 4 XXX XXXX"
            value={form.phone}
            onChange={(e) => update("phone", e.target.value)}
            onBlur={() => touch("phone")}
            error={fieldError("phone")}
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Industry"
            placeholder="e.g. FMCG, Construction"
            value={form.industry}
            onChange={(e) => update("industry", e.target.value)}
          />
          <Select
            label="Segment"
            value={form.segment}
            onChange={(e) => update("segment", e.target.value)}
            options={[
              { value: "enterprise", label: "Enterprise" },
              { value: "mid_market", label: "Mid-Market" },
              { value: "sme", label: "SME" },
              { value: "micro", label: "Micro" },
            ]}
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Select
            label="Territory"
            value={form.territory}
            onChange={(e) => update("territory", e.target.value)}
            options={[
              { value: "UAE-Dubai", label: "UAE - Dubai" },
              { value: "UAE-AbuDhabi", label: "UAE - Abu Dhabi" },
              { value: "KSA-Riyadh", label: "KSA - Riyadh" },
              { value: "KSA-Jeddah", label: "KSA - Jeddah" },
              { value: "QAT-Doha", label: "Qatar - Doha" },
              { value: "KWT-Kuwait", label: "Kuwait" },
              { value: "BHR-Manama", label: "Bahrain" },
              { value: "OMN-Muscat", label: "Oman - Muscat" },
            ]}
          />
          <Select
            label="Country"
            value={form.country}
            onChange={(e) => update("country", e.target.value)}
            options={[
              { value: "AE", label: "United Arab Emirates" },
              { value: "SA", label: "Saudi Arabia" },
              { value: "QA", label: "Qatar" },
              { value: "KW", label: "Kuwait" },
              { value: "BH", label: "Bahrain" },
              { value: "OM", label: "Oman" },
            ]}
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Credit Limit (AED)"
            type="number"
            placeholder="500000"
            value={form.credit_limit}
            onChange={(e) => update("credit_limit", e.target.value)}
            onBlur={() => touch("credit_limit")}
            error={fieldError("credit_limit")}
          />
          <Select
            label="Payment Terms"
            value={form.payment_terms_days}
            onChange={(e) => update("payment_terms_days", e.target.value)}
            options={[
              { value: "15", label: "Net 15" },
              { value: "30", label: "Net 30" },
              { value: "45", label: "Net 45" },
              { value: "60", label: "Net 60" },
              { value: "90", label: "Net 90" },
            ]}
          />
        </div>
      </form>
    </Modal>
  );
}
