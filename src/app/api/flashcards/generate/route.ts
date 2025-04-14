import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/db";

interface Flashcard {
  question: string;
  hint: string;
  answer: string;
}

export async function POST(req: NextRequest) {
  const FLASHCARD_API_URL = process.env.FLASHCARD_API;
  if (!FLASHCARD_API_URL) {
    console.error("Error: FLASHCARD_API environment variable is not set.");
    return NextResponse.json(
      { error: "Server configuration error." },
      { status: 500 }
    );
  }

  try {
    const { userId } = await auth();
    if (!userId) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      );
    }

    const { topic, difficulty, num_flashcards } = await req.json();

    // Enhanced input validation
    if (!topic) {
      return NextResponse.json(
        { error: "Topic is required" },
        { status: 400 }
      );
    }

    if (!difficulty || !["beginner", "intermediate", "advanced"].includes(difficulty)) {
      return NextResponse.json(
        { error: "Invalid difficulty level" },
        { status: 400 }
      );
    }

    if (!num_flashcards || num_flashcards < 1 || num_flashcards > 30) {
      return NextResponse.json(
        { error: "Number of flashcards must be between 1 and 30" },
        { status: 400 }
      );
    }

    // Call the external API with timeout and retry logic
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout

    try {
      const response = await fetch(FLASHCARD_API_URL, { // Use environment variable
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          topic,
          difficulty,
          num_flashcards,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorData = await response.json();
        console.error("External API error:", errorData);
        return NextResponse.json(
          { error: "Failed to generate flashcards. Please try again." },
          { status: response.status }
        );
      }

      const data = await response.json();

      // Validate response data
      if (!data.flashcards || !Array.isArray(data.flashcards) || data.flashcards.length === 0) {
        throw new Error("Invalid response from flashcard generation service");
      }

      // Create a new flashcard set in the database
      const flashcardSet = await prisma.flashcardSet.create({
        data: {
          userId,
          topic,
          difficulty,
          createdAt: new Date(),
        },
      });

      // Create individual flashcards with error handling for each
      const flashcardPromises = data.flashcards.map((card: Flashcard) =>
        prisma.flashcard.create({
          data: {
            setId: flashcardSet.id,
            question: card.question || "Question unavailable",
            hint: card.hint || "No hint available",
            answer: card.answer || "Answer unavailable",
            createdAt: new Date(),
          },
        }).catch(error => {
          console.error("Error creating flashcard:", error);
          return null;
        })
      );

      const createdCards = await Promise.all(flashcardPromises);
      
      // If no cards were created successfully, rollback and return error
      if (createdCards.every(card => card === null)) {
        await prisma.flashcardSet.delete({
          where: { id: flashcardSet.id }
        });
        throw new Error("Failed to create any flashcards");
      }

      return NextResponse.json({ id: flashcardSet.id });

    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        return NextResponse.json(
          { error: "Request timed out. Please try again." },
          { status: 504 }
        );
      }
      throw error; // Re-throw to be caught by outer catch block
    }

  } catch (error) {
    console.error("Error generating flashcards:", error);
    return NextResponse.json(
      { error: "Failed to generate flashcards. Please try again later." },
      { status: 500 }
    );
  }
}
