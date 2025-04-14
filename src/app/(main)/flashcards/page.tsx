"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { BookOpen, Loader2 } from "lucide-react";
import { H2 } from "@/components/typography/h2";
import { Para } from "@/components/typography/para";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

export const dynamic = 'force-dynamic'; // Ensures the page is always dynamically rendered

interface FlashcardSet {
  id: string;
  topic: string;
  difficulty: string;
  createdAt: string;
  flashcards: {
    id: string;
    isLearned: boolean;
  }[];
}

export default function FlashcardsIndex() {
  const router = useRouter();
  const [flashcardSets, setFlashcardSets] = useState<FlashcardSet[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingSet, setDeletingSet] = useState<string | null>(null);

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to delete this flashcard set?")) {
      return;
    }
    
    try {
      setDeletingSet(id);
      const response = await fetch(`/api/flashcards/${id}`, {
        method: "DELETE",
      });

      if (response.ok) {
        setFlashcardSets(sets => sets.filter(set => set.id !== id));
      } else {
        const data = await response.json();
        setError(data.error || "Failed to delete flashcard set");
      }
    } catch (err) {
      setError("Failed to delete flashcard set");
      console.error(err);
    } finally {
      setDeletingSet(null);
    }
  };

  useEffect(() => {
    const fetchFlashcardSets = async () => {
      try {
        const response = await fetch("/api/flashcards");
        if (!response.ok) throw new Error("Failed to fetch flashcard sets");
        const data = await response.json();
        setFlashcardSets(data);
      } catch (err) {
        setError("Failed to load flashcard sets");
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchFlashcardSets();
  }, []);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-gray-500" />
          <Para className="mt-4">Loading flashcard sets...</Para>
        </div>
      </div>
    );
  }

  return (
    <div className="p-10 pl-32">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <H2 className="flex items-center gap-2">
            <BookOpen className="h-6 w-6" />
            Your Flashcards
          </H2>
          <Para>
            Review and study with your personalized flashcard sets
          </Para>
        </div>
        <Button 
          onClick={() => router.push("/flashcards/create")}
          className="rounded-none text-lg"
        >
          CREATE NEW FLASHCARDS
        </Button>
      </div>

      {error && (
        <div className="mb-6 rounded-lg bg-red-50 p-4 text-red-700">
          <Para>{error}</Para>
        </div>
      )}

      {flashcardSets.length === 0 ? (
        <div className="mt-8 text-center">
          <Para className="mb-6 text-gray-500">
            You haven&apos;t created any flashcard sets yet
          </Para>
          <Button 
            onClick={() => router.push("/flashcards/create")}
            className="rounded-none text-lg"
          >
            CREATE YOUR FIRST FLASHCARDS
          </Button>
        </div>
      ) : (
        <div className="grid gap-6">
          {flashcardSets.map((set) => {
            const learnedCount = set.flashcards.filter(card => card.isLearned).length;
            const totalCards = set.flashcards.length;
            const progressPercentage = totalCards > 0 
              ? Math.round((learnedCount / totalCards) * 100) 
              : 0;
            
            return (
              <div
                key={set.id}
                className="flex items-center justify-between rounded-xl bg-white p-6"
              >
                <div>
                  <h3 className="mb-2 text-xl font-semibold">{set.topic}</h3>
                  <p className="text-gray-600">
                    {set.difficulty.charAt(0).toUpperCase() + set.difficulty.slice(1)} · 
                    {totalCards} cards
                  </p>
                  <p className="mt-2 text-sm text-gray-500">
                    Created on {new Date(set.createdAt).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <span className="text-brand-logo-text text-2xl font-bold">
                      {progressPercentage}%
                    </span>
                    <p className="text-sm text-gray-500">Learned</p>
                  </div>
                  <div className="flex gap-2">
                    <Link href={`/flashcards/${set.id}`}>
                      <Button variant="outline">Study</Button>
                    </Link>
                    <Button 
                      variant="outline" 
                      onClick={() => handleDelete(set.id)}
                      disabled={deletingSet === set.id}
                    >
                      {deletingSet === set.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        "Delete"
                      )}
                    </Button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
