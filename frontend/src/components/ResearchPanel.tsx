"use client";

import { useState, useCallback, useRef } from "react";
import { useAppStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import {
  Search,
  Loader2,
  BookOpen,
  ChevronRight,
  Copy,
  ExternalLink,
  RotateCcw,
  Sparkles,
} from "lucide-react";

export function ResearchPanel() {
  const {
    researchAnswer,
    researchLoading,
    researchSessions,
    sendResearchQuery,
  } = useAppStore();
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async () => {
    if (!query.trim() || researchLoading) return;
    await sendResearchQuery(query);
    setQuery("");
  };

  const handleFollowUp = (q: string) => {
    setQuery(q);
    inputRef.current?.focus();
  };

  const copyAnswer = useCallback(() => {
    if (researchAnswer?.answer) {
      navigator.clipboard.writeText(researchAnswer.answer);
    }
  }, [researchAnswer]);

  return (
    <div className="flex-1 flex flex-col">
      {/* Heading */}
      <div className="px-6 pt-6 pb-2">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-primary" />
          Deep Research
        </h2>
        <p className="text-sm text-muted-foreground">
          Multi-turn, source-grounded research mode with citations
        </p>
      </div>

      {/* Result Area */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {researchAnswer ? (
          <div className="space-y-6 max-w-3xl mx-auto animate-fade-in">
            {/* Answer Card */}
            <div className="glass-card p-6">
              <div className="flex items-center justify-between mb-4">
                <span className="text-xs font-semibold text-primary tracking-wider uppercase">
                  Research Answer · Turn {researchAnswer.turn_number}
                </span>
                <div className="flex gap-1">
                  <button
                    onClick={copyAnswer}
                    className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-all"
                    title="Copy"
                  >
                    <Copy className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
              <div className="text-sm leading-relaxed whitespace-pre-wrap">
                {researchAnswer.answer}
              </div>

              {/* Citations */}
              {researchAnswer.citations?.length > 0 && (
                <div className="mt-4 pt-4 border-t border-border/50">
                  <p className="text-xs font-semibold text-muted-foreground mb-2">
                    Sources ({researchAnswer.citations.length})
                  </p>
                  <div className="space-y-2">
                    {researchAnswer.citations.map((c, i) => (
                      <div
                        key={i}
                        className="text-xs p-2 rounded-md bg-primary/5 border border-primary/10"
                      >
                        <span className="text-primary font-semibold">
                          [{i + 1}]
                        </span>{" "}
                        <span className="font-medium">{c.source_title}</span>
                        <p className="text-muted-foreground mt-1 italic">
                          &ldquo;{c.cited_text}&rdquo;
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Follow-up Questions */}
            {researchAnswer.follow_up_questions?.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wider">
                  Suggested Follow-ups
                </p>
                <div className="flex flex-wrap gap-2">
                  {researchAnswer.follow_up_questions.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => handleFollowUp(q)}
                      className="text-xs px-3 py-1.5 rounded-full border border-border hover:bg-primary/10 hover:border-primary/30 hover:text-primary transition-all flex items-center gap-1.5"
                    >
                      <ChevronRight className="w-3 h-3" />
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Meta */}
            <div className="flex items-center gap-4 text-[10px] text-muted-foreground">
              <span>Model: {researchAnswer.model_used}</span>
              <span>Latency: {researchAnswer.latency_ms}ms</span>
              <span>Turns: {researchAnswer.total_turns}</span>
            </div>
          </div>
        ) : (
          <div className="h-full flex items-center justify-center">
            <div className="text-center max-w-md">
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary/20 to-purple-500/20 flex items-center justify-center mx-auto mb-4">
                <Sparkles className="w-8 h-8 text-primary" />
              </div>
              <h3 className="text-xl font-semibold mb-2">Deep Research Mode</h3>
              <p className="text-sm text-muted-foreground mb-6">
                Ask complex, multi-part research questions. Nexus will analyze
                your sources in depth with full citations and follow-up
                suggestions.
              </p>
              <div className="flex flex-wrap gap-2 justify-center">
                {[
                  "What are the key limitations discussed?",
                  "Compare the methodologies used",
                  "Synthesize the main findings",
                ].map((q) => (
                  <button
                    key={q}
                    onClick={() => setQuery(q)}
                    className="text-xs px-3 py-1.5 rounded-full border border-border hover:bg-primary/10 hover:border-primary/30 hover:text-primary transition-all"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="p-4 border-t border-border">
        <div className="max-w-3xl mx-auto flex gap-2">
          <div className="flex-1 relative">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              ref={inputRef}
              type="text"
              placeholder="Ask a research question..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
              className="w-full h-11 pl-10 pr-4 rounded-xl bg-secondary/50 border border-border text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 transition-all"
            />
          </div>
          <button
            onClick={handleSubmit}
            disabled={!query.trim() || researchLoading}
            className={cn(
              "px-5 h-11 rounded-xl flex items-center gap-2 text-sm font-medium transition-all",
              query.trim()
                ? "bg-primary text-primary-foreground shadow-lg shadow-primary/25 hover:bg-primary/90"
                : "bg-secondary text-muted-foreground"
            )}
          >
            {researchLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <>
                <Search className="w-4 h-4" />
                Research
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
