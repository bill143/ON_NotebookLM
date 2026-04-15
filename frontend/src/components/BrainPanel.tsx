"use client";

import { useCallback, useEffect, useState } from "react";
import { useAppStore } from "@/lib/store";
import { api, type FlashCard } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  Brain,
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff,
  Loader2,
  Plus,
  RotateCcw,
  Sparkles,
  Trophy,
} from "lucide-react";

interface ProgressStats {
  total_cards: number;
  cards_due: number;
  cards_learned: number;
  cards_new: number;
  average_difficulty: number;
  retention_rate: number;
  streak_days: number;
}

export function BrainPanel() {
  const { activeNotebook, flashcards } = useAppStore();
  const [dueCards, setDueCards] = useState<FlashCard[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [showAnswer, setShowAnswer] = useState(false);
  const [loading, setLoading] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [progress, setProgress] = useState<ProgressStats | null>(null);
  const [mode, setMode] = useState<"overview" | "review">("overview");

  const loadDueCards = useCallback(async () => {
    setLoading(true);
    try {
      const cards = await api.getDueFlashcards(activeNotebook?.id);
      setDueCards(cards);
      setCurrentIndex(0);
      setShowAnswer(false);
    } catch (error) {
      console.error("Failed to load due cards:", error);
    } finally {
      setLoading(false);
    }
  }, [activeNotebook?.id]);

  useEffect(() => {
    loadDueCards();
  }, [loadDueCards]);

  const currentCard = dueCards[currentIndex];

  const handleReview = async (rating: number) => {
    if (!currentCard) return;
    setReviewing(true);
    try {
      await api.reviewFlashcard(currentCard.id, rating);
      if (currentIndex < dueCards.length - 1) {
        setCurrentIndex(currentIndex + 1);
        setShowAnswer(false);
      } else {
        setMode("overview");
        await loadDueCards();
      }
    } catch (error) {
      console.error("Review failed:", error);
    } finally {
      setReviewing(false);
    }
  };

  if (mode === "review" && currentCard) {
    return (
      <div className="flex-1 overflow-y-auto p-6 flex flex-col items-center justify-center">
        {/* Progress bar */}
        <div className="w-full max-w-lg mb-6">
          <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
            <span>{currentIndex + 1} / {dueCards.length}</span>
            <span>{Math.round(((currentIndex + 1) / dueCards.length) * 100)}%</span>
          </div>
          <div className="h-1.5 bg-secondary rounded-full">
            <div
              className="h-full bg-primary rounded-full transition-all duration-300"
              style={{ width: `${((currentIndex + 1) / dueCards.length) * 100}%` }}
            />
          </div>
        </div>

        {/* Card */}
        <div className="w-full max-w-lg">
          <div
            className={cn(
              "glass-card p-8 min-h-[240px] flex flex-col items-center justify-center text-center cursor-pointer transition-all",
              showAnswer ? "border-primary/30" : "hover:border-primary/20"
            )}
            onClick={() => setShowAnswer(!showAnswer)}
          >
            <div className="text-xs text-muted-foreground mb-4 uppercase tracking-wider">
              {showAnswer ? "Answer" : "Question"}
            </div>
            <p className="text-lg font-medium">
              {showAnswer ? currentCard.back : currentCard.front}
            </p>
            <div className="mt-4 text-xs text-muted-foreground flex items-center gap-1">
              {showAnswer ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
              {showAnswer ? "Click to hide" : "Click to reveal answer"}
            </div>
          </div>

          {/* Rating buttons */}
          {showAnswer && (
            <div className="grid grid-cols-4 gap-2 mt-4">
              {[
                { rating: 1, label: "Again", color: "text-red-500 border-red-500/30 hover:bg-red-500/10" },
                { rating: 2, label: "Hard", color: "text-orange-500 border-orange-500/30 hover:bg-orange-500/10" },
                { rating: 3, label: "Good", color: "text-green-500 border-green-500/30 hover:bg-green-500/10" },
                { rating: 4, label: "Easy", color: "text-blue-500 border-blue-500/30 hover:bg-blue-500/10" },
              ].map(({ rating, label, color }) => (
                <button
                  key={rating}
                  disabled={reviewing}
                  onClick={() => handleReview(rating)}
                  className={cn(
                    "py-3 rounded-lg border text-sm font-semibold transition-all",
                    color,
                    reviewing && "opacity-50 cursor-not-allowed"
                  )}
                >
                  {reviewing ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : label}
                </button>
              ))}
            </div>
          )}

          {/* Navigation */}
          <div className="flex items-center justify-between mt-4">
            <button
              onClick={() => {
                setCurrentIndex(Math.max(0, currentIndex - 1));
                setShowAnswer(false);
              }}
              disabled={currentIndex === 0}
              className="p-2 rounded-lg hover:bg-accent disabled:opacity-30 transition-all"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => { setMode("overview"); }}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Exit Review
            </button>
            <button
              onClick={() => {
                setCurrentIndex(Math.min(dueCards.length - 1, currentIndex + 1));
                setShowAnswer(false);
              }}
              disabled={currentIndex >= dueCards.length - 1}
              className="p-2 rounded-lg hover:bg-accent disabled:opacity-30 transition-all"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Overview mode
  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Brain className="w-5 h-5 text-primary" />
            Learning Brain
          </h2>
          <p className="text-sm text-muted-foreground">
            Spaced repetition flashcards from your sources
          </p>
        </div>
        <button
          onClick={loadDueCards}
          disabled={loading}
          className="p-2 rounded-lg hover:bg-accent transition-all"
          title="Refresh"
        >
          <RotateCcw className={cn("w-4 h-4", loading && "animate-spin")} />
        </button>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        <div className="glass-card p-4 text-center">
          <div className="text-2xl font-bold text-primary">{dueCards.length}</div>
          <div className="text-xs text-muted-foreground">Due Today</div>
        </div>
        <div className="glass-card p-4 text-center">
          <div className="text-2xl font-bold text-green-500">{flashcards.length}</div>
          <div className="text-xs text-muted-foreground">Total Cards</div>
        </div>
        <div className="glass-card p-4 text-center">
          <div className="text-2xl font-bold text-yellow-500">
            <Trophy className="w-6 h-6 inline" />
          </div>
          <div className="text-xs text-muted-foreground">Streak</div>
        </div>
      </div>

      {/* Start Review button */}
      {dueCards.length > 0 && (
        <button
          onClick={() => {
            setMode("review");
            setCurrentIndex(0);
            setShowAnswer(false);
          }}
          className="w-full glass-card p-5 text-center group hover:border-primary/30 transition-all mb-6"
        >
          <Sparkles className="w-8 h-8 text-primary mx-auto mb-2 group-hover:scale-110 transition-transform" />
          <h3 className="text-sm font-semibold">
            Start Review ({dueCards.length} cards due)
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Review your flashcards using spaced repetition
          </p>
        </button>
      )}

      {dueCards.length === 0 && !loading && (
        <div className="glass-card p-8 text-center">
          <Trophy className="w-10 h-10 text-green-500 mx-auto mb-3" />
          <h3 className="text-sm font-semibold">All caught up!</h3>
          <p className="text-xs text-muted-foreground mt-1">
            No cards due for review. Great job!
          </p>
        </div>
      )}

      {/* Card list */}
      {flashcards.length > 0 && (
        <div className="mt-6">
          <h3 className="text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
            All Flashcards
          </h3>
          <div className="space-y-2">
            {flashcards.slice(0, 20).map((card) => (
              <div key={card.id} className="glass-card p-3 flex items-center gap-3">
                <div className={cn(
                  "w-2 h-2 rounded-full shrink-0",
                  card.review_count === 0 ? "bg-blue-500" :
                  card.state === 2 ? "bg-green-500" : "bg-yellow-500"
                )} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm truncate">{card.front}</p>
                  <p className="text-xs text-muted-foreground">
                    Reviews: {card.review_count} · D: {card.difficulty.toFixed(1)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
