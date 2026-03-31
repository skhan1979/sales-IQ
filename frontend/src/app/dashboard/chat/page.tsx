"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import api, { intelligenceApi, getAccessToken } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import {
  MessageSquare,
  Send,
  Bot,
  User,
  Trash2,
  Sparkles,
  Copy,
  Check,
} from "lucide-react";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  isStreaming?: boolean;
}

interface Conversation {
  id: string;
  title?: string;
  created_at?: string;
}

export default function ChatPage() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [isStreaming, setIsStreaming] = useState(false);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Conversation history
  const { data: convData } = useQuery({
    queryKey: ["chat-conversations"],
    queryFn: () => intelligenceApi.chat("", undefined).then((r) => r.data).catch(() => null),
    enabled: false, // manual only
  });

  const handleSend = useCallback(async () => {
    const msg = input.trim();
    if (!msg || isStreaming) return;

    // Add user message
    const userMsg: ChatMessage = {
      role: "user",
      content: msg,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsStreaming(true);

    // Add placeholder for assistant
    const assistantMsg: ChatMessage = {
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
      isStreaming: true,
    };
    setMessages((prev) => [...prev, assistantMsg]);

    try {
      // Try SSE streaming first
      const token = getAccessToken();
      const response = await fetch(
        `${api.defaults.baseURL}/intelligence/chat`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
            Accept: "text/event-stream",
          },
          body: JSON.stringify({
            message: msg,
            conversation_id: conversationId,
            stream: true,
          }),
        }
      );

      // Check if we got a streaming response
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("text/event-stream") && response.body) {
        // SSE stream
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let accumulated = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split("\n");

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const data = line.slice(6);
              if (data === "[DONE]") break;
              try {
                const parsed = JSON.parse(data);
                const token = parsed.token || parsed.content || parsed.delta || "";
                accumulated += token;
                setMessages((prev) => {
                  const updated = [...prev];
                  updated[updated.length - 1] = {
                    ...updated[updated.length - 1],
                    content: accumulated,
                  };
                  return updated;
                });
              } catch {
                // plain text token
                accumulated += data;
                setMessages((prev) => {
                  const updated = [...prev];
                  updated[updated.length - 1] = {
                    ...updated[updated.length - 1],
                    content: accumulated,
                  };
                  return updated;
                });
              }
            }
          }
        }

        // Finalize
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            isStreaming: false,
          };
          return updated;
        });
      } else {
        // Regular JSON response — simulate typing
        const data = await response.json();
        const fullText =
          data.response || data.message || data.answer || data.content ||
          (data.error?.message) || "I received your message.";

        if (data.conversation_id) setConversationId(data.conversation_id);

        // Simulate streaming with word-by-word reveal
        const words = fullText.split(" ");
        let current = "";
        for (let i = 0; i < words.length; i++) {
          current += (i > 0 ? " " : "") + words[i];
          const snapshot = current;
          await new Promise((r) => setTimeout(r, 20 + Math.random() * 30));
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              ...updated[updated.length - 1],
              content: snapshot,
            };
            return updated;
          });
        }
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            isStreaming: false,
          };
          return updated;
        });
      }
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          content:
            "I apologize, but I encountered an issue processing your request. Please ensure demo data is generated and try again.",
          timestamp: new Date().toISOString(),
          isStreaming: false,
        };
        return updated;
      });
    } finally {
      setIsStreaming(false);
      inputRef.current?.focus();
    }
  }, [input, isStreaming, conversationId]);

  const handleCopy = (text: string, idx: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const handleClear = () => {
    setMessages([]);
    setConversationId(undefined);
  };

  const suggestions = [
    "What is our current DSO?",
    "Which customers are high risk?",
    "Show me overdue aging summary",
    "What is our collection rate trend?",
    "List top 5 overdue invoices",
    "Summarize our AR position",
  ];

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">AI Chat</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Ask questions about your accounts receivable data in natural language
          </p>
        </div>
        {messages.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleClear}
            icon={<Trash2 className="h-3.5 w-3.5" />}
          >
            Clear
          </Button>
        )}
      </div>

      <Card className="flex-1 flex flex-col overflow-hidden">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center animate-in fade-in duration-500">
              <div className="rounded-full bg-gradient-to-br from-blue-50 to-indigo-50 p-5 mb-4">
                <Bot className="h-10 w-10 text-blue-600" />
              </div>
              <h3 className="text-base font-semibold text-slate-700 mb-1">
                SalesIQ AI Assistant
              </h3>
              <p className="text-sm text-slate-500 max-w-sm mb-6">
                Ask me anything about your receivables, customers, aging, or
                collections performance.
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-w-lg">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    onClick={() => setInput(s)}
                    className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600 hover:bg-blue-50 hover:border-blue-200 hover:text-blue-700 transition-all duration-150 text-left"
                  >
                    <Sparkles className="h-3 w-3 text-blue-400 mb-1" />
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg, i) => (
              <div
                key={i}
                className={`flex gap-3 animate-in slide-in-from-bottom-2 duration-200 ${
                  msg.role === "user" ? "justify-end" : ""
                }`}
              >
                {msg.role === "assistant" && (
                  <div className="flex-shrink-0 h-8 w-8 rounded-full bg-gradient-to-br from-blue-100 to-indigo-100 flex items-center justify-center">
                    <Bot className="h-4 w-4 text-blue-600" />
                  </div>
                )}
                <div className="max-w-[70%] group relative">
                  <div
                    className={`rounded-2xl px-4 py-2.5 text-sm ${
                      msg.role === "user"
                        ? "bg-blue-600 text-white"
                        : "bg-slate-100 text-slate-800"
                    }`}
                  >
                    <p className="whitespace-pre-wrap leading-relaxed">
                      {msg.content}
                      {msg.isStreaming && (
                        <span className="inline-block w-1.5 h-4 bg-blue-500 ml-0.5 animate-pulse rounded-sm" />
                      )}
                    </p>
                  </div>
                  {msg.role === "assistant" && !msg.isStreaming && msg.content && (
                    <button
                      onClick={() => handleCopy(msg.content, i)}
                      className="absolute -bottom-5 left-2 opacity-0 group-hover:opacity-100 transition-opacity text-xs text-slate-400 hover:text-slate-600 flex items-center gap-1"
                    >
                      {copiedIdx === i ? (
                        <><Check className="h-3 w-3 text-emerald-500" /> Copied</>
                      ) : (
                        <><Copy className="h-3 w-3" /> Copy</>
                      )}
                    </button>
                  )}
                </div>
                {msg.role === "user" && (
                  <div className="flex-shrink-0 h-8 w-8 rounded-full bg-slate-200 flex items-center justify-center">
                    <User className="h-4 w-4 text-slate-600" />
                  </div>
                )}
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="border-t border-slate-100 p-4 bg-white">
          <div className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
              placeholder="Ask about your receivables..."
              className="flex-1 rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-all"
              disabled={isStreaming}
            />
            <Button
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
              icon={isStreaming ? undefined : <Send className="h-4 w-4" />}
            >
              {isStreaming ? <Spinner size="sm" /> : "Send"}
            </Button>
          </div>
          <p className="text-[10px] text-slate-400 mt-2 text-center">
            SalesIQ AI can make mistakes. Verify important data with reports.
          </p>
        </div>
      </Card>
    </div>
  );
}
