"use client";

import { useEffect, useState } from "react";
import { useAppStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Layers, RotateCcw, ChevronRight, Eye, EyeOff, Check, X, AlertCircle, Sparkles, Clock } from "lucide-react";

export function NotesPanel() {
  const {
    activeNotebook,
    flashcards,
    activeCardIndex,
    showAnswer,
    fetchFlashcards,
    reviewFlashcard,
    nextCard,
    toggleAnswer,
  } = useAppStore();

  const [mode, setMode] = useState<"notes" | "flashcards">("notes");

  useEffect(() => {
    if (activeNotebook) {
      fetchFlashcards(activeNotebook.id);
    }
  }, [activeNotebook, fetchFlashcards]);

  const currentCard = flashcards[activeCardIndex];

  const ratingButtons = [
    { rating: 1, label: "Again", icon: X, color: "text-red-500 hover:bg-red-500/10" },
    { rating: 2, label: "Hard", icon: AlertCircle, color: "text-yellow-500 hover:bg-yellow-500/10" },
    { rating: 3, label: "Good", icon: Check, color: "text-green-500 hover:bg-green-500/10" },
    { rating: 4, label: "Easy", icon: Sparkles, color: "text-blue-500 hover:bg-blue-500/10" },
  ];

  return (
    <div className="flex-1 overflow-y-auto p-6">
      {/* Mode Toggle */}
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={() => setMode("notes")}
          className={cn(
            "text-sm font-medium px-3 py-1.5 rounded-lg transition-all",
            mode === "notes" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"
          )}
        >
          Notes
        </button>
        <button
          onClick={() => setMode("flashcards")}
          className={cn(
            "text-sm font-medium px-3 py-1.5 rounded-lg transition-all flex items-center gap-2",
            mode === "flashcards" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"
          )}
        >
          Flashcards
          {flashcards.length > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary/20 text-primary font-semibold">
              {flashcards.length}
            </span>
          )}
        </button>
      </div>

      {mode === "flashcards" ? (
        <div className="max-w-lg mx-auto">
          {currentCard ? (
            <div className="space-y-6">
              {/* Progress */}
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Card {activeCardIndex + 1} of {flashcards.length}</span>
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  Reviews: {currentCard.review_count}
                </span>
              </div>

              {/* Card */}
              <div
                className="glass-card p-8 min-h-[200px] flex flex-col items-center justify-center cursor-pointer group"
                onClick={toggleAnswer}
              >
                <p className="text-lg font-medium text-center leading-relaxed">
                  {showAnswer ? currentCard.back : currentCard.front}
                </p>
                {!showAnswer && (
                  <p className="text-xs text-muted-foreground mt-4 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Eye className="w-3 h-3" /> Click to reveal answer
                  </p>
                )}
                {showAnswer && (
                  <div className="mt-4 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium">
                    Answer
                  </div>
                )}
              </div>

              {/* Rating Buttons */}
              {showAnswer && (
                <div className="flex gap-2 animate-fade-in">
                  {ratingButtons.map(({ rating, label, icon: Icon, color }) => (
                    <button
                      key={rating}
                      onClick={() => reviewFlashcard(currentCard.id, rating)}
                      className={cn(
                        "flex-1 flex flex-col items-center gap-1 p-3 rounded-xl border border-border transition-all",
                        color
                      )}
                    >
                      <Icon className="w-4 h-4" />
                      <span className="text-xs font-medium">{label}</span>
                    </button>
                  ))}
                </div>
              )}

              {/* Tags */}
              {currentCard.tags?.length > 0 && (
                <div className="flex gap-1 flex-wrap">
                  {currentCard.tags.map((tag) => (
                    <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded-full bg-secondary text-muted-foreground">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-12">
              <Sparkles className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
              <h3 className="text-lg font-semibold mb-2">No cards due</h3>
              <p className="text-sm text-muted-foreground">
                All caught up! Generate flashcards from the Studio tab to start learning.
              </p>
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-12">
          <Layers className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
          <h3 className="text-lg font-semibold mb-2">Notes</h3>
          <p className="text-sm text-muted-foreground max-w-md mx-auto">
            Your personal notes and highlights will appear here.
            Save insights from chat or research to build your notes collection.
          </p>
        </div>
      )}
    </div>
  );
}
