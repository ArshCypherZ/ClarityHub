"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { BookOpen, Loader2 } from "lucide-react";
import { H2 } from "@/components/typography/h2";
import { Para } from "@/components/typography/para";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export default function FlashcardsPage() {
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [topic, setTopic] = useState("");
  const [difficulty, setDifficulty] = useState("intermediate");
  const [numFlashcards, setNumFlashcards] = useState(10);
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setLoading(true);
      if (!topic) {
        setError("Please enter a topic");
        return;
      }
      setError("");
      const response = await fetch("/api/flashcards/generate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          topic,
          difficulty,
          num_flashcards: numFlashcards,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        router.push(`/flashcards/${data.id}`);
      } else {
        const errorData = await response.json();
        setError(errorData.error || "Failed to generate flashcards");
      }
    } catch (error) {
      console.error("Error generating flashcards:", error);
      setError("An error occurred while generating the flashcards");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-10 pl-32">
      <div>
        <H2 className="flex items-center gap-2">
          <BookOpen className="h-6 w-6" />
          Generate Flashcards
        </H2>
        <Para>
          Create AI-generated flashcards to help you study and memorize key concepts
        </Para>
      </div>

      <form
        onSubmit={handleSubmit}
        className="mt-10 flex max-w-2xl flex-col gap-6"
      >
        <div className="flex flex-col gap-2">
          <label htmlFor="topic" className="text-lg font-medium">
            Enter your flashcards topic
          </label>
          <Input
            id="topic"
            placeholder="Ex: Photosynthesis Process"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            className="rounded-lg bg-white p-4"
          />
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="difficulty" className="text-lg font-medium">
            Select Difficulty
          </label>
          <Select
            value={difficulty}
            onValueChange={setDifficulty}
          >
            <SelectTrigger id="difficulty" className="rounded-lg bg-white p-4">
              <SelectValue placeholder="Select Difficulty" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="beginner">Beginner</SelectItem>
              <SelectItem value="intermediate">Intermediate</SelectItem>
              <SelectItem value="advanced">Advanced</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="numFlashcards" className="text-lg font-medium">
            Number of Flashcards
          </label>
          <Input
            id="numFlashcards"
            type="number"
            min={1}
            max={30}
            value={numFlashcards}
            onChange={(e) => setNumFlashcards(parseInt(e.target.value))}
            className="rounded-lg bg-white p-4"
          />
        </div>

        <Button
          type="submit"
          disabled={loading}
          className="w-fit rounded-none text-lg"
        >
          {loading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              GENERATING...
            </>
          ) : (
            "GENERATE FLASHCARDS"
          )}
        </Button>

        {error && (
          <div className="rounded-lg bg-red-50 p-4 text-red-700">
            {error}
          </div>
        )}
      </form>
    </div>
  );
}