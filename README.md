# ClarityHub - AI-Powered Learning Platform

An intelligent learning platform that leverages AI to generate personalized study roadmaps, interactive quizzes, and comprehensive study materials. This platform aims to revolutionize the way students approach their academic journey.

## 🌟 Features

### 1. AI-Generated Study Roadmaps

- Personalized learning paths based on your subject and topic
- Customizable difficulty levels and timelines
- Progress tracking for each subtopic
- Adaptive to your prior knowledge level

### 2. Interactive Quizzes

- AI-generated questions to test your understanding
- Real-time feedback and explanations
- Progress tracking and performance analytics
- Personalized question difficulty based on your performance

### 3. Study Materials

- Comprehensive topic explanations
- Curated learning resources
- YouTube video recommendations
- Personalized content based on your learning style

### 4. AI Tutor

- Engage in interactive video lecture (with animated texts, graph, equations and flowcharts)
- Get explanations and clarifications on demand with AI
- Track generated videos history

### 5. AI-Generated Flashcards

- Create flashcard decks based on your study topics
- AI generates questions and answers for effective memorization
- Track your learning progress for each card
- Review cards you haven't mastered yet

## 🚀 Tech Stack

- **Frontend**: Next.js 15.1.4, React 19.0.0
- **Styling**: TailwindCSS 4.0.8
- **Authentication**: Clerk
- **Database**: Prisma with PostgreSQL
- **AI Integration**: Custom AI API for content generation

## 🛠️ Getting Started

### Prerequisites

- Node.js (LTS version)
- pnpm package manager
- PostgreSQL database
- Clerk account for authentication
- Environment variables setup

### Installation

1. Clone the repository

```bash
git clone <repository-url>
cd reponame
```

2. Install dependencies

```bash
pnpm install
```

3. Set up environment variables
   Create a `.env` file in the root directory and add the following:

```env
DATABASE_URL="your-postgresql-url"
CLERK_SECRET_KEY="your-clerk-secret-key"
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="your-clerk-publishable-key"
SIGNING_SECRET="your-webhook-secret"
DATA_API="your-ai-api-endpoint"
ROADMAP_API="your-ai-api-endpoint"
QUIZ_API="your-ai-api-endpoint"
AITUTOR_API_BASE_URL="your-ai-tutor-api-base-url"
FLASHCARD_API="your-ai-api-endpoint
```

4. Run database migrations

```bash
pnpm dlx prisma generate
pnpm dlx prisma db push
```

5. Start the development server

```bash
pnpm dev
```

For production

```bash
pnpm build
pnpm start
```

Troubleshooting with migration:

```bash
pnpm dlx prisma migrate resolve --applied 20250413195948_add_flashcards
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the application.

## 🎯 Usage

1. **Create a Study Roadmap**

   - Enter your study topic/syllabus
   - Specify subject, course level, and exam
   - Choose difficulty level and timeline
   - Get a personalized learning path

2. **Access Study Materials**

   - Click on any subtopic in your roadmap
   - View comprehensive explanations
   - Access curated resources and videos

3. **Take Quizzes**
   - Generate topic-specific quizzes
   - Answer questions and get instant feedback
   - Track your progress

4. **Use the AI Tutor**
   - Navigate to the AI Tutor section
   - Generate a video based on your learning topic with customization like language and accent of the speaker.
   - Get past generated videos and their download links

5. **Create and Use Flashcards**
   - Navigate to the Flashcards section
   - Generate a new deck based on your topic
   - Review flashcards, marking them as learned
   - Focus on cards needing more review

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.
---

Built with ❤️
