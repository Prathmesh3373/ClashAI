import express from 'express';

const router = express.Router();
const MAX_DEBATE_TURNS = 6;
const AGREEMENT_MARKER = 'FINAL AGREEMENT';
const REPETITION_THRESHOLD = 0.78;
const FOLLOW_UP_START_PATTERN = /^(what about|what if|how about|and\b|so\b|then\b|but\b|also\b|now\b|okay\b|ok\b|in that case|if so|if not)/i;
const FOLLOW_UP_REFERENCE_PATTERN = /\b(this|that|it|they|them|those|these|he|she|him|her|its|their|there|here|same|above|earlier|previous|startup|situation|case)\b/i;
const GREETING_PATTERN = /^(hi|hello|hey|hii|yo|sup|hola|namaste|good morning|good afternoon|good evening)\b[!. ]*$/i;

function normalizeModelName(value, fallback) {
  return (value || fallback).trim().replace(/\s+/g, '');
}

function getOllamaConfig() {
  const debaterOne = normalizeModelName(process.env.OLLAMA_DEBATER_ONE, 'llama3.2');
  const debaterTwo = normalizeModelName(process.env.OLLAMA_DEBATER_TWO, 'mistral');

  return {
    url: (process.env.OLLAMA_URL || 'http://localhost:11434').trim(),
    debaterOne,
    debaterTwo,
    judge: normalizeModelName(process.env.OLLAMA_JUDGE, 'gpt-oss:20b'),
  };
}

async function callOllama(model, messages, signal, temperature = 0.7) {
  const { url } = getOllamaConfig();
  if (signal?.aborted) {
    throw new Error('REQUEST_ABORTED');
  }

  const response = await fetch(`${url}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    signal,
    body: JSON.stringify({
      model,
      stream: false,
      options: { temperature },
      messages,
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Ollama API error: ${response.status} ${errorText}`);
  }

  const data = await response.json();
  return data?.message?.content?.trim() || `${model} returned an empty response.`;
}

function labelForHistoryItem(item) {
  if (item.role === 'user') return 'User';
  if (item.role === 'agentA') return 'Agent A';
  if (item.role === 'agentB') return 'Agent B';
  if (item.role === 'judge') return 'Answer';
  if (item.role === 'system') return 'System';
  return item.label || 'Message';
}

function formatConversationHistory(history) {
  if (!history?.length) {
    return 'No prior conversation.';
  }

  return history
    .map((item, index) => `${index + 1}. ${labelForHistoryItem(item)}: ${item.content}`)
    .join('\n\n');
}

function formatTranscript(transcript) {
  if (!transcript.length) {
    return 'No agent conversation yet.';
  }

  return transcript
    .map((entry, index) => `${index + 1}. Agent ${entry.agent}: ${entry.message}`)
    .join('\n\n');
}

function isLikelyFollowUpPrompt(prompt) {
  const normalized = prompt.trim();
  const wordCount = normalized.split(/\s+/).filter(Boolean).length;

  if (FOLLOW_UP_START_PATTERN.test(normalized)) {
    return true;
  }

  return wordCount <= 18 && FOLLOW_UP_REFERENCE_PATTERN.test(normalized);
}

function buildConversationContext(prompt, conversationHistory) {
  if (!conversationHistory?.length) {
    return 'No prior conversation. Treat this as a standalone question.';
  }

  if (!isLikelyFollowUpPrompt(prompt)) {
    return [
      'There is earlier chat history, but the current prompt should be treated as a fresh standalone question unless the user explicitly refers back to earlier context.',
      'Do not anchor the answer to earlier topics by default.',
    ].join('\n');
  }

  const recentHistory = conversationHistory.slice(-8);
  return [
    'This prompt looks like a follow-up, so use the recent conversation only where it is clearly relevant.',
    formatConversationHistory(recentHistory),
  ].join('\n\n');
}

function buildAgentMessages({ prompt, conversationHistory, transcript, selfAgent, selfModel, otherAgent, stage }) {
  const latestOpponentMessage = [...transcript].reverse().find((entry) => entry.agent === otherAgent);
  const instructions =
    stage === 'opening'
      ? [
          `You are Agent ${selfAgent} using ${selfModel}.`,
          'Treat the current user message as its own question unless it explicitly depends on earlier chat context.',
          'Speak like a thoughtful assistant helping the user, not like a report generator.',
          'Give a short opening opinion in exactly 4 to 5 short conversational lines.',
          'Each line should be one clear point, not a paragraph.',
          `Do not say ${AGREEMENT_MARKER} unless you truly want to end the debate.`,
        ]
      : [
          `You are Agent ${selfAgent} using ${selfModel}.`,
          'Treat the current user message as its own question unless it explicitly depends on earlier chat context.',
          'Speak like a thoughtful assistant helping the user, not like a report generator.',
          `Read the latest message from Agent ${otherAgent}, respond directly, defend your reasoning, challenge weak points, and refine your stance if needed.`,
          `Reply in exactly 4 to 5 short conversational lines. If you are genuinely convinced enough to converge, include the exact phrase ${AGREEMENT_MARKER}.`,
          'Avoid repeating yourself and keep every line concrete.',
        ];

  const userPrompt = [
    `Current user message: ${prompt}`,
    '',
    `Conversation context policy:\n${buildConversationContext(prompt, conversationHistory)}`,
    '',
    `Current agent conversation:\n${formatTranscript(transcript)}`,
    '',
    latestOpponentMessage
      ? `Latest message from Agent ${otherAgent}: ${latestOpponentMessage.message}`
      : `No message from Agent ${otherAgent} yet.`,
  ].join('\n');

  return [
    { role: 'system', content: instructions.join('\n') },
    { role: 'user', content: userPrompt },
  ];
}

function buildJudgeMessages(prompt, conversationHistory, transcript, judgeModel) {
  const isGreeting = GREETING_PATTERN.test(prompt.trim());

  return [
    {
      role: 'system',
      content: [
        `You are the final assistant model ${judgeModel}.`,
        'Reply directly to the user in a natural, conversational tone.',
        'Treat the current user message as a standalone question unless it explicitly depends on earlier chat context.',
        'Use earlier conversation only if it is clearly relevant to this prompt.',
        'Read the conversation context guidance and the current agent conversation before answering.',
        isGreeting
          ? 'The user is greeting you. Respond warmly, naturally, and briefly, then offer help.'
          : 'Give one refined final answer based on the agent conversation. Do not output headings, bullet labels, report sections, or meta commentary.',
        'Your output must be only the final answer text that should appear in chat.',
      ].join('\n'),
    },
    {
      role: 'user',
      content: [
        `Current user message: ${prompt}`,
        '',
        `Conversation context policy:\n${buildConversationContext(prompt, conversationHistory)}`,
        '',
        `Current agent conversation:\n${formatTranscript(transcript)}`,
      ].join('\n'),
    },
  ];
}

function extractConciseAnswer(verdict) {
  return verdict.trim();
}

function normalizeText(value) {
  return value.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
}

function calculateSimilarity(a, b) {
  const aWords = new Set(normalizeText(a).split(' ').filter(Boolean));
  const bWords = new Set(normalizeText(b).split(' ').filter(Boolean));

  if (!aWords.size || !bWords.size) {
    return 0;
  }

  let intersection = 0;
  for (const word of aWords) {
    if (bWords.has(word)) {
      intersection += 1;
    }
  }

  return intersection / Math.min(aWords.size, bWords.size);
}

function isRepeatingArgument(transcript, agent, message) {
  const previousByAgent = [...transcript].reverse().find((entry) => entry.agent === agent);
  if (!previousByAgent) {
    return false;
  }

  return calculateSimilarity(previousByAgent.message, message) >= REPETITION_THRESHOLD;
}

function writeEvent(res, payload) {
  if (!res.writableEnded && !res.destroyed) {
    res.write(`${JSON.stringify(payload)}\n`);
  }
}

function assertNotAborted(signal) {
  if (signal.aborted) {
    throw new Error('REQUEST_ABORTED');
  }
}

router.post('/', async (req, res) => {
  const config = getOllamaConfig();
  const prompt = req.body?.prompt?.trim();
  const conversationHistory = Array.isArray(req.body?.history) ? req.body.history : [];

  if (!prompt) {
    return res.status(400).json({ error: 'Prompt is required.' });
  }

  const controller = new AbortController();
  const abortRequest = () => controller.abort();
  req.on('aborted', abortRequest);

  res.setHeader('Content-Type', 'application/x-ndjson; charset=utf-8');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  const transcript = [];

  try {
    writeEvent(res, {
      type: 'meta',
      debaterOneName: config.debaterOne,
      debaterTwoName: config.debaterTwo,
      judgeName: config.judge,
      maxTurns: MAX_DEBATE_TURNS,
    });

    assertNotAborted(controller.signal);
    const openingA = await callOllama(
      config.debaterOne,
      buildAgentMessages({
        prompt,
        conversationHistory,
        transcript,
        selfAgent: 'A',
        selfModel: config.debaterOne,
        otherAgent: 'B',
        stage: 'opening',
      }),
      controller.signal
    );
    transcript.push({ agent: 'A', model: config.debaterOne, message: openingA });
    writeEvent(res, { type: 'message', entry: transcript.at(-1) });

    assertNotAborted(controller.signal);
    const openingB = await callOllama(
      config.debaterTwo,
      buildAgentMessages({
        prompt,
        conversationHistory,
        transcript,
        selfAgent: 'B',
        selfModel: config.debaterTwo,
        otherAgent: 'A',
        stage: 'reply',
      }),
      controller.signal
    );
    transcript.push({ agent: 'B', model: config.debaterTwo, message: openingB });
    writeEvent(res, { type: 'message', entry: transcript.at(-1) });

    let stopReason = openingA.includes(AGREEMENT_MARKER) || openingB.includes(AGREEMENT_MARKER)
      ? 'final_agreement'
      : '';

    let turnCount = 0;
    while (!stopReason && turnCount < MAX_DEBATE_TURNS) {
      assertNotAborted(controller.signal);
      const responseA = await callOllama(
        config.debaterOne,
        buildAgentMessages({
          prompt,
          conversationHistory,
          transcript,
          selfAgent: 'A',
          selfModel: config.debaterOne,
          otherAgent: 'B',
          stage: 'reply',
        }),
        controller.signal
      );
      const repeatA = isRepeatingArgument(transcript, 'A', responseA);
      transcript.push({ agent: 'A', model: config.debaterOne, message: responseA });
      writeEvent(res, { type: 'message', entry: transcript.at(-1) });
      turnCount += 1;

      if (responseA.includes(AGREEMENT_MARKER)) {
        stopReason = 'final_agreement';
        break;
      }
      if (repeatA) {
        stopReason = 'repetition';
        break;
      }
      if (turnCount >= MAX_DEBATE_TURNS) {
        stopReason = 'max_turns';
        break;
      }

      assertNotAborted(controller.signal);
      const responseB = await callOllama(
        config.debaterTwo,
        buildAgentMessages({
          prompt,
          conversationHistory,
          transcript,
          selfAgent: 'B',
          selfModel: config.debaterTwo,
          otherAgent: 'A',
          stage: 'reply',
        }),
        controller.signal
      );
      const repeatB = isRepeatingArgument(transcript, 'B', responseB);
      transcript.push({ agent: 'B', model: config.debaterTwo, message: responseB });
      writeEvent(res, { type: 'message', entry: transcript.at(-1) });
      turnCount += 1;

      if (responseB.includes(AGREEMENT_MARKER)) {
        stopReason = 'final_agreement';
        break;
      }
      if (repeatB) {
        stopReason = 'repetition';
        break;
      }
    }

    if (!stopReason) {
      stopReason = 'max_turns';
    }

    assertNotAborted(controller.signal);
    writeEvent(res, { type: 'status', stopReason });

    const answer = await callOllama(
      config.judge,
      buildJudgeMessages(prompt, conversationHistory, transcript, config.judge),
      controller.signal,
      0.4
    );

    const conciseAnswer = extractConciseAnswer(answer);

    writeEvent(res, {
      type: 'done',
      debate: transcript,
      verdict: conciseAnswer,
      conciseAnswer,
      stopReason,
      debaterOneName: config.debaterOne,
      debaterTwoName: config.debaterTwo,
      judgeName: config.judge,
    });
    res.end();
  } catch (error) {
    if (error.name === 'AbortError' || error.message === 'REQUEST_ABORTED') {
      writeEvent(res, {
        type: 'done',
        debate: transcript,
        verdict: '',
        conciseAnswer: '',
        stopReason: 'stopped_by_user',
        debaterOneName: config.debaterOne,
        debaterTwoName: config.debaterTwo,
        judgeName: config.judge,
      });
      res.end();
      return;
    }

    writeEvent(res, { type: 'error', error: error.message || 'Debate failed.' });
    res.end();
  } finally {
    req.off('aborted', abortRequest);
  }
});

export default router;
