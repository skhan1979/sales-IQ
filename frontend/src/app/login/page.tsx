"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Brain, Eye, EyeOff } from "lucide-react";

const DEMO_ACCOUNTS = [
  { label: "Admin", email: "admin@salesiq.ai", password: "Admin@2024", role: "Tenant Admin" },
  { label: "CFO", email: "cfo@salesiq.ai", password: "Cfo@2024!", role: "CFO" },
  { label: "Collector", email: "collector@salesiq.ai", password: "Collect@2024", role: "Collector" },
  { label: "Sales Rep", email: "sales@salesiq.ai", password: "Sales@2024!", role: "Sales Rep" },
];

export default function LoginPage() {
  const router = useRouter();
  const { login, isLoading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const [submitting, setSubmitting] = useState(false);

  const validateForm = (): boolean => {
    const errs: { email?: string; password?: string } = {};
    if (!email.trim()) {
      errs.email = "Email is required";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      errs.email = "Enter a valid email address";
    }
    if (!password) {
      errs.password = "Password is required";
    } else if (password.length < 6) {
      errs.password = "Password must be at least 6 characters";
    }
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!validateForm()) return;

    setSubmitting(true);
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { error?: { message?: string }; detail?: string } } };
      setError(
        axiosErr?.response?.data?.error?.message ||
        axiosErr?.response?.data?.detail ||
        "Invalid credentials. Please try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const fillDemo = (account: typeof DEMO_ACCOUNTS[number]) => {
    setEmail(account.email);
    setPassword(account.password);
    setFieldErrors({});
    setError("");
  };

  return (
    <div className="min-h-screen flex">
      {/* Left Panel - Brand */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-blue-600 via-blue-700 to-indigo-800 relative overflow-hidden">
        <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHZpZXdCb3g9IjAgMCA2MCA2MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48ZyBmaWxsPSJub25lIiBmaWxsLXJ1bGU9ImV2ZW5vZGQiPjxnIGZpbGw9IiNmZmYiIGZpbGwtb3BhY2l0eT0iMC4wNSI+PHBhdGggZD0iTTM2IDM0djItSDI0di0yaDEyem0wLTRWMjhIMjR2MmgxMnptLTgtMTBoMnYyaC0ydi0yem0tNCAwaDJ2MmgtMnYtMnoiLz48L2c+PC9nPjwvc3ZnPg==')] opacity-50" />
        <div className="relative z-10 flex flex-col justify-center px-16">
          <div className="flex items-center gap-3 mb-8">
            <div className="h-12 w-12 rounded-xl bg-white/20 backdrop-blur flex items-center justify-center">
              <Brain className="h-7 w-7 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">SalesIQ</h1>
              <p className="text-blue-200 text-sm">Revenue Intelligence</p>
            </div>
          </div>
          <h2 className="text-4xl font-bold text-white leading-tight mb-4">
            Agentic AR<br />Intelligence Platform
          </h2>
          <p className="text-blue-100 text-lg max-w-md leading-relaxed">
            Unified customer data, explainable AI predictions, and autonomous
            collection agents — purpose-built for GCC mid-market enterprises.
          </p>
          <div className="mt-12 grid grid-cols-3 gap-6">
            <div className="text-center">
              <div className="text-3xl font-bold text-white">7</div>
              <div className="text-blue-200 text-xs mt-1">AI Agents</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-white">183+</div>
              <div className="text-blue-200 text-xs mt-1">API Routes</div>
            </div>
            <div className="text-center">
              <div className="text-3xl font-bold text-white">100%</div>
              <div className="text-blue-200 text-xs mt-1">Demo Ready</div>
            </div>
          </div>
        </div>
      </div>

      {/* Right Panel - Login Form */}
      <div className="flex-1 flex items-center justify-center px-8 bg-slate-50">
        <div className="w-full max-w-sm">
          {/* Mobile brand */}
          <div className="lg:hidden flex items-center gap-2 mb-8 justify-center">
            <div className="h-10 w-10 rounded-xl bg-blue-600 flex items-center justify-center">
              <Brain className="h-6 w-6 text-white" />
            </div>
            <span className="text-xl font-bold text-slate-900">SalesIQ</span>
          </div>

          <div className="mb-8">
            <h2 className="text-2xl font-bold text-slate-900">Welcome back</h2>
            <p className="text-slate-500 mt-1">
              Sign in to your account to continue
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700 animate-in slide-in-from-top-1 duration-200">
                {error}
              </div>
            )}

            <Input
              label="Email address"
              type="email"
              placeholder="admin@salesiq.ai"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setFieldErrors((p) => ({ ...p, email: undefined })); }}
              error={fieldErrors.email}
              autoFocus
              autoComplete="email"
            />

            <div className="relative">
              <Input
                label="Password"
                type={showPassword ? "text" : "password"}
                placeholder="Enter your password"
                value={password}
                onChange={(e) => { setPassword(e.target.value); setFieldErrors((p) => ({ ...p, password: undefined })); }}
                error={fieldErrors.password}
                autoComplete="current-password"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-[34px] text-slate-400 hover:text-slate-600 transition-colors"
                tabIndex={-1}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>

            <Button
              type="submit"
              className="w-full"
              size="lg"
              loading={submitting || isLoading}
            >
              {submitting ? "Signing in..." : "Sign in"}
            </Button>
          </form>

          {/* Demo accounts */}
          <div className="mt-8 rounded-lg bg-blue-50 border border-blue-100 px-4 py-3">
            <p className="text-xs font-medium text-blue-800 mb-2">
              Quick Login — Demo Accounts
            </p>
            <div className="grid grid-cols-2 gap-2">
              {DEMO_ACCOUNTS.map((acc) => (
                <button
                  key={acc.email}
                  onClick={() => fillDemo(acc)}
                  className="text-left rounded-md border border-blue-200 bg-white px-3 py-2 text-xs hover:bg-blue-50 transition-colors group"
                >
                  <span className="font-medium text-blue-800 group-hover:text-blue-900">
                    {acc.label}
                  </span>
                  <span className="block text-blue-500 text-[10px]">{acc.role}</span>
                </button>
              ))}
            </div>
          </div>

          <p className="text-center text-xs text-slate-400 mt-8">
            SalesIQ v0.1.0 — Phase 3
          </p>
        </div>
      </div>
    </div>
  );
}
