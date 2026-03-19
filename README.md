# Clash AI

*Where AI minds clash to give you a sharper answer.*

## Introduction

Clash AI is a multi-agent AI system built to generate better, deeper, and more refined responses in the AI era.

Today, most AI tools still work in a one-model, one-response format. You ask a question, one model answers, and the interaction ends there. That works for speed, but it often misses something important: stronger answers usually come from challenge, refinement, and synthesis.

Clash AI explores a different direction. Instead of relying on a single response, it makes multiple AI models interact, question each other, defend their reasoning, and move toward a stronger conclusion. The goal is not just to answer quickly, but to produce responses that are more thoughtful, balanced, and useful.

This is not just a chatbot. It is a multi-agent reasoning experience designed to show how AI can evolve from direct answering into discussion, refinement, and synthesis.

## Project Overview

Clash AI creates a structured debate between local AI models. A user submits a prompt, one agent responds, another agent critiques or refines that response, and the exchange continues for multiple turns. Once the debate reaches a stopping point, a judge model synthesizes the interaction into a final verdict.

This architecture is designed to push beyond one-shot generation. By allowing disagreement and refinement inside the system, Clash AI aims to produce answers that feel more considered and more reliable.

## Why Clash AI?

In today’s AI era, most tools still give users a response from one model only. That creates a familiar limitation: the answer may be fast, but it is often unchallenged. A single-model response can miss nuance, overlook counterarguments, or settle too quickly on one perspective.

Clash AI is built around the idea that better answers can emerge when models debate, critique, and synthesize. Instead of treating AI as a single voice, this project treats it as a reasoning system with multiple perspectives.

Why that matters:

- Single-model answers can be direct but shallow.
- Multiple interacting models can expose blind spots.
- Debate creates pressure for stronger reasoning.
- Synthesis turns disagreement into a more refined final answer.
- The result is an AI experience focused on thought quality, not just answer speed.

## How It Works

### Flow

```text
User asks a question
        |
        v
Agent A gives an opinion
        |
        v
Agent B critiques or refines it
        |
        v
Agents continue interacting
        |
        v
Judge model produces the refined verdict
```

### Step-by-step

1. The user enters a question in the chat interface.
2. Agent A generates an initial opinion.
3. Agent B reads that opinion and critiques, challenges, or refines it.
4. The agents continue interacting for multiple turns.
5. The system preserves the transcript of the internal debate.
6. A final judge or synthesis model reads the full interaction.
7. The user receives a refined verdict built from discussion rather than a one-shot reply.

## Features

- Multi-agent debate between local AI models
- Better answer refinement through critique and synthesis
- Chat-style interface inspired by modern AI products
- Ongoing conversation across multiple user turns
- Final synthesized verdict after internal reasoning
- Local model support through Ollama
- Stop control for interrupting live debate
- Persistent chat history with LocalStorage

## Tech Stack

- React
- Node.js
- Express
- TailwindCSS
- Framer Motion
- Ollama
- llama3.2
- mistral

## Current Architecture

Clash AI currently runs with a full-stack architecture:

- Frontend: React + Vite for the chat interface
- Backend: Node.js + Express for debate orchestration
- Styling: TailwindCSS with a ChatGPT-style dark UI
- Animation: Framer Motion for message transitions and status states
- Local inference: Ollama for running local models
- Models: `llama3.2` and `mistral` as debating agents, with a judge model for synthesis

## Future Vision

Clash AI is an exploration of how AI systems can generate richer and more reliable answers by using disagreement, discussion, and synthesis instead of only one-shot responses.

The broader vision is to move beyond the idea of AI as a single responder and toward AI systems that reason more like teams: challenging assumptions, refining arguments, and producing conclusions with greater depth. As this project evolves, it can grow into a more advanced multi-agent reasoning platform for learning, decision support, research, and problem solving.

## Getting Started

### Environment

```env
PORT=5000
FRONTEND_URL=http://localhost:5173
OLLAMA_URL=http://localhost:11434
OLLAMA_DEBATER_ONE=llama3.2
OLLAMA_DEBATER_TWO=mistral
OLLAMA_JUDGE=gpt-oss:20b
```

If the preferred judge model is not installed locally, point `OLLAMA_JUDGE` at another available model such as `mistral`.

### Run the backend

```bash
cd backend
npm run dev
```

### Run the frontend

```bash
cd frontend
npm install
npm run dev
```
