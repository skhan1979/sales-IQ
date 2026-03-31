"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  X,
  ChevronRight,
  ChevronLeft,
  LayoutDashboard,
  Users,
  FileText,
  MessageSquare,
  BarChart3,
  Sparkles,
} from "lucide-react";

interface TourStep {
  target?: string; // CSS selector
  title: string;
  description: string;
  route?: string; // navigate to this route for the step
  position?: "top" | "bottom" | "left" | "right" | "center";
  icon?: React.ElementType;
}

const TOUR_STEPS: TourStep[] = [
  {
    title: "Welcome to SalesIQ",
    description:
      "SalesIQ is an AI-powered Accounts Receivable Intelligence platform built for GCC mid-market enterprises. Let's take a quick tour of the key features.",
    position: "center",
    icon: Sparkles,
  },
  {
    title: "Executive Dashboard",
    description:
      "Your command center. See total receivables (AED 12.9M), overdue amounts, DSO, collection rates, and aging distribution at a glance. All data updates in real-time.",
    route: "/dashboard",
    position: "center",
    icon: LayoutDashboard,
  },
  {
    title: "Customer 360",
    description:
      "Deep-dive into any customer with a full credit profile, risk score, payment history, and AI-predicted behavior. Manage 22 customers across the GCC region.",
    route: "/dashboard/customers",
    position: "center",
    icon: Users,
  },
  {
    title: "Invoice Management",
    description:
      "Track all 40 invoices with aging buckets, auto-calculated days overdue, and AI-predicted payment dates. Export data as CSV or JSON with one click.",
    route: "/dashboard/invoices",
    position: "center",
    icon: FileText,
  },
  {
    title: "AI Chat Assistant",
    description:
      'Ask questions in natural language — "What is our current DSO?" or "Which customers are high risk?" — and get instant, data-backed answers with streaming responses.',
    route: "/dashboard/chat",
    position: "center",
    icon: MessageSquare,
  },
  {
    title: "CFO Dashboard",
    description:
      "Purpose-built for the CFO: DSO trends over 12 months, overdue concentration by customer, and cash flow projections. Also includes a Sales dashboard and Analytics.",
    route: "/dashboard/cfo",
    position: "center",
    icon: BarChart3,
  },
  {
    title: "Collections Copilot",
    description:
      "AI drafts collection messages for you, tracks promises-to-pay, and prioritizes follow-ups. 49 collection activities tracked with PTP fulfillment monitoring.",
    route: "/dashboard/copilot",
    position: "center",
    icon: Sparkles,
  },
  {
    title: "You're All Set!",
    description:
      "Explore the full platform: 23 pages, 183+ API routes, 7 AI agents, real-time WebSocket notifications, and CSV/JSON export. Press Ctrl+K anytime for quick search.",
    position: "center",
    icon: Sparkles,
  },
];

const TOUR_STORAGE_KEY = "salesiq_tour_completed";

export function DemoTour() {
  const [isActive, setIsActive] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [showPrompt, setShowPrompt] = useState(false);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    // Show prompt on first visit to dashboard
    if (pathname === "/dashboard") {
      const completed = sessionStorage.getItem(TOUR_STORAGE_KEY);
      if (!completed) {
        const timer = setTimeout(() => setShowPrompt(true), 1500);
        return () => clearTimeout(timer);
      }
    }
  }, [pathname]);

  const startTour = useCallback(() => {
    setShowPrompt(false);
    setIsActive(true);
    setCurrentStep(0);
  }, []);

  const endTour = useCallback(() => {
    setIsActive(false);
    setCurrentStep(0);
    sessionStorage.setItem(TOUR_STORAGE_KEY, "true");
  }, []);

  const goNext = useCallback(() => {
    const nextStep = currentStep + 1;
    if (nextStep >= TOUR_STEPS.length) {
      endTour();
      return;
    }
    const step = TOUR_STEPS[nextStep];
    if (step.route) {
      router.push(step.route);
    }
    setCurrentStep(nextStep);
  }, [currentStep, router, endTour]);

  const goPrev = useCallback(() => {
    const prevStep = currentStep - 1;
    if (prevStep < 0) return;
    const step = TOUR_STEPS[prevStep];
    if (step.route) {
      router.push(step.route);
    }
    setCurrentStep(prevStep);
  }, [currentStep, router]);

  // Tour prompt
  if (showPrompt && !isActive) {
    return (
      <div className="fixed bottom-6 right-6 z-50 animate-in slide-in-from-bottom-4 duration-500">
        <div className="rounded-2xl bg-white shadow-2xl border border-slate-200 p-5 max-w-sm">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 p-2.5 flex-shrink-0">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-slate-900">
                First time here?
              </h3>
              <p className="text-xs text-slate-500 mt-0.5 mb-3">
                Take a quick guided tour to discover SalesIQ's key features.
              </p>
              <div className="flex items-center gap-2">
                <Button size="sm" onClick={startTour}>
                  Start Tour
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setShowPrompt(false);
                    sessionStorage.setItem(TOUR_STORAGE_KEY, "true");
                  }}
                >
                  Skip
                </Button>
              </div>
            </div>
            <button
              onClick={() => setShowPrompt(false)}
              className="text-slate-400 hover:text-slate-600"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!isActive) return null;

  const step = TOUR_STEPS[currentStep];
  const Icon = step.icon || Sparkles;
  const progress = ((currentStep + 1) / TOUR_STEPS.length) * 100;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-sm" />

      {/* Tour card */}
      <div className="fixed inset-0 z-[61] flex items-center justify-center p-6">
        <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full overflow-hidden animate-in zoom-in-95 duration-200">
          {/* Progress bar */}
          <div className="h-1 bg-slate-100">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>

          <div className="p-6">
            {/* Icon + step counter */}
            <div className="flex items-center justify-between mb-4">
              <div className="rounded-xl bg-gradient-to-br from-blue-50 to-indigo-50 p-3">
                <Icon className="h-6 w-6 text-blue-600" />
              </div>
              <span className="text-xs font-medium text-slate-400">
                {currentStep + 1} / {TOUR_STEPS.length}
              </span>
            </div>

            {/* Content */}
            <h3 className="text-lg font-bold text-slate-900 mb-2">
              {step.title}
            </h3>
            <p className="text-sm text-slate-600 leading-relaxed mb-6">
              {step.description}
            </p>

            {/* Navigation */}
            <div className="flex items-center justify-between">
              <button
                onClick={endTour}
                className="text-xs text-slate-400 hover:text-slate-600 transition-colors"
              >
                Skip tour
              </button>
              <div className="flex items-center gap-2">
                {currentStep > 0 && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={goPrev}
                    icon={<ChevronLeft className="h-3.5 w-3.5" />}
                  >
                    Back
                  </Button>
                )}
                <Button
                  size="sm"
                  onClick={goNext}
                  icon={
                    currentStep < TOUR_STEPS.length - 1 ? (
                      <ChevronRight className="h-3.5 w-3.5" />
                    ) : undefined
                  }
                >
                  {currentStep < TOUR_STEPS.length - 1
                    ? "Next"
                    : "Finish Tour"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
