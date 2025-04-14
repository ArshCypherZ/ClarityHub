"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { H1 } from "@/components/typography/h1";
import { H2 } from "@/components/typography/h2";
import { Para } from "@/components/typography/para";
import { Progress } from "@/components/ui/progress";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

interface Flashcard {
  id: string;
  question: string;
  hint: string;
  answer: string;
  isLearned: boolean;
}

interface FlashcardSet {
  id: string;
  topic: string;
  difficulty: string;
  createdAt: string;
  flashcards: Flashcard[];
}

export default function FlashcardViewClient({ params }: { params: { id: string } }) {
  const router = useRouter();
  const [flashcardSet, setFlashcardSet] = useState<FlashcardSet | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentCardIndex, setCurrentCardIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [showHint, setShowHint] = useState(false);

  useEffect(() => {
    const fetchFlashcardSet = async () => {
      try {
        const response = await fetch(`/api/flashcards/${params.id}`);
        if (!response.ok) throw new Error("Failed to fetch flashcard set");
        const data = await response.json();
        setFlashcardSet(data);
      } catch (err) {
        setError("Failed to load flashcards");
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchFlashcardSet();
  }, [params.id]);

  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return; // Don't handle keypresses when typing in form elements
      }
      
      switch (e.key.toLowerCase()) {
        case ' ':
        case 'enter':
          e.preventDefault();
          toggleFlip();
          break;
        case 'arrowright':
        case 'n':
          e.preventDefault();
          handleNext();
          break;
        case 'arrowleft':
        case 'p':
          e.preventDefault();
          handlePrevious();
          break;
        case 'h':
          e.preventDefault();
          !isFlipped && toggleHint();
          break;
        case 'l':
          e.preventDefault();
          markAsLearned();
          break;
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [isFlipped]); // Only include isFlipped in dependencies to prevent unnecessary recreations

  const handleNext = () => {
    if (!flashcardSet) return;
    setIsFlipped(false);
    setShowHint(false);
    setCurrentCardIndex((prev) => 
      prev < flashcardSet.flashcards.length - 1 ? prev + 1 : 0
    );
  };

  const handlePrevious = () => {
    if (!flashcardSet) return;
    setIsFlipped(false);
    setShowHint(false);
    setCurrentCardIndex((prev) => 
      prev > 0 ? prev - 1 : flashcardSet.flashcards.length - 1
    );
  };

  const toggleFlip = () => {
    setIsFlipped(!isFlipped);
    if (showHint) setShowHint(false);
  };

  const toggleHint = (e?: React.MouseEvent) => {
      e?.stopPropagation();
      setShowHint(!showHint);
    };

  const markAsLearned = async () => {
    if (!flashcardSet) return;
    const currentCard = flashcardSet.flashcards[currentCardIndex];
    
    try {
      const response = await fetch(`/api/flashcards/card/${currentCard.id}/toggle-learned`, {
        method: "POST",
      });

      if (response.ok) {
        const updatedFlashcards = [...flashcardSet.flashcards];
        updatedFlashcards[currentCardIndex] = {
          ...currentCard,
          isLearned: !currentCard.isLearned
        };
        
        setFlashcardSet({
          ...flashcardSet,
          flashcards: updatedFlashcards
        });
      }
    } catch (error) {
      console.error("Failed to mark card as learned:", error);
    }
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-gray-500" />
          <Para className="mt-4">Loading flashcards...</Para>
        </div>
      </div>
    );
  }

  if (error || !flashcardSet) {
    return (
      <div className="p-10 pl-32 text-center">
        <H2>Error</H2>
        <Para className="mt-4 text-red-500">{error || "Flashcard set not found"}</Para>
        <Button className="mt-6" onClick={() => router.push("/flashcards")}>
          Go Back
        </Button>
      </div>
    );
  }

  const currentCard = flashcardSet.flashcards[currentCardIndex];
  const progress = ((currentCardIndex + 1) / flashcardSet.flashcards.length) * 100;
  const learnedCount = flashcardSet.flashcards.filter(card => card.isLearned).length;
  const totalCards = flashcardSet.flashcards.length;
  const progressPercentage = Math.round((learnedCount / totalCards) * 100);

  return (
    <div className="p-10 pl-32">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <H1>{flashcardSet.topic}</H1>
          <Para className="text-gray-600">
            Difficulty: {flashcardSet.difficulty.charAt(0).toUpperCase() + flashcardSet.difficulty.slice(1)} · 
            Created: {new Date(flashcardSet.createdAt).toLocaleDateString()}
          </Para>
        </div>
        <Button 
          variant="outline" 
          onClick={() => router.push("/flashcards")}
        >
          Back to Flashcards
        </Button>
      </div>

      {/* Progress bar and stats */}
      <div className="mx-auto mb-8 max-w-2xl">
        <div className="mb-2 flex items-center justify-between">
          <Para className="text-gray-600">Card {currentCardIndex + 1} of {totalCards}</Para>
          <Para className="text-gray-600">{progressPercentage}% Learned</Para>
        </div>
        <Progress value={progress} className="h-2" />
      </div>

      {/* Flashcard */}
      <div className="mx-auto max-w-2xl">
        <div className={`flip-card mb-8 ${isFlipped ? 'flipped' : ''}`}>
          <div className="flip-card-inner h-64">
            <div className="flip-card-front flex h-full flex-col items-center justify-center rounded-xl bg-white p-8 shadow-lg">
              <H2 className="mb-4">Question</H2>
              <Para className="text-xl">{currentCard.question}</Para>
              {showHint && (
                <div className="mt-4 rounded-lg bg-gray-50 p-3">
                  <Para className="text-sm italic">Hint: {currentCard.hint}</Para>
                </div>
              )}
            </div>
            <div className="flip-card-back flex h-full flex-col items-center justify-center rounded-xl bg-white p-8 shadow-lg">
              <H2 className="mb-4">Answer</H2>
              <Para className="text-xl">{currentCard.answer}</Para>
            </div>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center justify-between">
          <Button variant="outline" onClick={handlePrevious}>
            Previous
          </Button>
          
          <div className="flex gap-2">
            {!isFlipped && (
              <Button
                variant="outline"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleHint();
                }}
              >
                {showHint ? "Hide Hint" : "Show Hint"}
              </Button>
            )}
            <Button
              variant={currentCard.isLearned ? "default" : "outline"}
              onClick={(e) => {
                e.stopPropagation();
                markAsLearned();
              }}
            >
              {currentCard.isLearned ? "Learned" : "Mark as Learned"}
            </Button>
            <Button
              variant="outline"
              onClick={(e) => {
                e.stopPropagation();
                toggleFlip();
              }}
            >
              {isFlipped ? "Show Question" : "Show Answer"}
            </Button>
          </div>
          
          <Button variant="outline" onClick={handleNext}>
            Next
          </Button>
        </div>
      </div>

      {/* Add keyboard shortcuts help */}
      <div className="mx-auto mt-8 max-w-2xl rounded-lg bg-gray-50 p-4">
        <H2 className="mb-2">Keyboard Shortcuts</H2>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Para><kbd className="px-2 py-1 bg-white rounded border">Space</kbd> or <kbd className="px-2 py-1 bg-white rounded border">Enter</kbd> Flip card</Para>
            <Para><kbd className="px-2 py-1 bg-white rounded border">→</kbd> or <kbd className="px-2 py-1 bg-white rounded border">N</kbd> Next card</Para>
            <Para><kbd className="px-2 py-1 bg-white rounded border">←</kbd> or <kbd className="px-2 py-1 bg-white rounded border">P</kbd> Previous card</Para>
          </div>
          <div>
            <Para><kbd className="px-2 py-1 bg-white rounded border">H</kbd> Toggle hint</Para>
            <Para><kbd className="px-2 py-1 bg-white rounded border">L</kbd> Toggle learned status</Para>
          </div>
        </div>
      </div>
    </div>
  );
}