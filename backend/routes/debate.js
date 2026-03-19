import express from 'express';

const router = express.Router();
const MAX_DEBATE_TURNS = 6;
const AGREEMENT_MARKER = 'FINAL AGREEMENT';
const REPETITION_THRESHOLD = 0.78;

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
  if (item.role === 'judge') return 'Judge Verdict';
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
    return 'No debate history yet.';
  }

  return transcript
    .map((entry, index) => `${index + 1}. Agent ${entry.agent}: ${entry.message}`)
    .join('\n\n');
}

function buildAgentMessages({ prompt, conversationHistory, transcript, selfAgent, selfModel, otherAgent, stage }) {
  const latestOpponentMessage = [...transcript].reverse().find((entry) => entry.agent === otherAgent);
  const instructions =
    stage === 'opening'
      ? [
          `You are Agent ${selfAgent} using ${selfModel}.`,
          'Give a short opening opinion for the user in exactly 4 to 5 short lines.',
          'Each line should be one clear point, not a paragraph.',
          `Do not say ${AGREEMENT_MARKER} unless you truly want to end the debate.`,
        ]
      : [
          `You are Agent ${selfAgent} using ${selfModel}.`,
          `Read the latest message from Agent ${otherAgent}, respond directly, defend your reasoning, challenge weak points, and refine your stance if needed.`,
          `Reply in exactly 4 to 5 short lines. If you are genuinely convinced enough to converge, include the exact phrase ${AGREEMENT_MARKER}.`,
          'Avoid repeating yourself and keep every line concrete.',
        ];

  const userPrompt = [
    `Current user message: ${prompt}`,
    '',
    `Earlier conversation context:\n${formatConversationHistory(conversationHistory)}`,
    '',
    `Current debate transcript:\n${formatTranscript(transcript)}`,
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
  return [
    {
      role: 'system',
      content: [
        `You are the judge model ${judgeModel}.`,
        'Read the earlier conversation and the current debate transcript.',
        'Produce exactly four sections in this order:',
        'Key Agreements',
        'Key Disagreements',
        'Final Verdict',
        'Concise Answer',
        'Keep each section tight and practical. The Concise Answer must be one paragraph for the chat history summary.',
      ].join('\n'),
    },
    {
      role: 'user',
      content: [
        `Current user message: ${prompt}`,
        '',
        `Earlier conversation context:\n${formatConversationHistory(conversationHistory)}`,
        '',
        `Current debate transcript:\n${formatTranscript(transcript)}`,
      ].join('\n'),
    },
  ];
}

function extractConciseAnswer(verdict) {
  const match = verdict.match(/Concise Answer\s*[:\n]+([\s\S]*)/i);
  if (!match) {
    return verdict.trim();
  }

  return match[1].trim();
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

    const verdict = await callOllama(
      config.judge,
      buildJudgeMessages(prompt, conversationHistory, transcript, config.judge),
      controller.signal,
      0.4
    );

    writeEvent(res, {
      type: 'done',
      debate: transcript,
      verdict,
      conciseAnswer: extractConciseAnswer(verdict),
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
