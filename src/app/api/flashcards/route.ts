import { NextRequest, NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";
import { prisma } from "@/lib/db";

export const dynamic = 'force-dynamic'; // Force dynamic rendering, prevent static analysis

export async function GET(req: NextRequest) {
  try {
    const { userId } = await auth();
    if (!userId) {
      return NextResponse.json(
        { error: "Unauthorized" },
        { status: 401 }
      );
    }

    const flashcardSets = await prisma.flashcardSet.findMany({
      where: {
        userId,
      },
      include: {
        flashcards: {
          select: {
            id: true,
            isLearned: true,
          },
        },
      },
      orderBy: {
        createdAt: "desc",
      },
    });

    return NextResponse.json(flashcardSets);
  } catch (error) {
    console.error("Error fetching flashcard sets:", error);
    return NextResponse.json(
      { error: "Failed to fetch flashcard sets" },
      { status: 500 }
    );
  }
}
