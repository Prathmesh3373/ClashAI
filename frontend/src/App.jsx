import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useMemo, useRef, useState } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000';
const STORAGE_KEY = 'debate-arena-conversations-v2';
const SIDEBAR_WIDTH = 280;
const APP_NAME = 'Clash AI';
const APP_TAGLINE = 'Where AI minds clash to give you a sharper answer.';

const examplePrompts = [
  'Should I drop college for a startup?',
  'AI vs DSA for engineers',
  'India vs USA for tech careers',
  'Startup vs Job',
  'Should students learn AI first?',
];

function createConversation(title = 'New chat') {
  return {
    id: crypto.randomUUID(),
    title,
    messages: [],
    updatedAt: Date.now(),
  };
}

function loadConversations() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function buildThinkingMessage(phase) {
  if (phase === 'agentA') return 'Agent A is thinking...';
  if (phase === 'agentB') return 'Agent B is analyzing...';
  if (phase === 'judge') return 'Judge is synthesizing the debate...';
  return '';
}

function ChevronIcon({ direction = 'right', className = '' }) {
  const rotation = direction === 'right' ? 'rotate-0' : direction === 'left' ? 'rotate-180' : 'rotate-90';

  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`h-4 w-4 ${rotation} ${className}`}
      aria-hidden="true"
    >
      <path d="m9 18 6-6-6-6" />
    </svg>
  );
}

function renderFormattedText(text, paragraphClassName = '') {
  return text.split(/\n\n+/).map((paragraph, paragraphIndex) => {
    const parts = paragraph.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);

    return (
      <p key={`${paragraphIndex}-${paragraph.slice(0, 12)}`} className={paragraphClassName}>
        {parts.map((part, partIndex) => {
          const isBold = part.startsWith('**') && part.endsWith('**');
          const content = isBold ? part.slice(2, -2) : part;

          return isBold ? (
            <strong key={partIndex} className="font-semibold text-[#ECECF1]">
              {content}
            </strong>
          ) : (
            <span key={partIndex}>{content}</span>
          );
        })}
      </p>
    );
  });
}

function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const isStatus = message.role === 'status';
  const rowClass = isUser ? 'justify-end' : 'justify-start';
  const bubbleClass = isUser
    ? 'max-w-3xl rounded-[1.75rem] border border-white/10 bg-[#343541] px-5 py-4'
    : 'w-full rounded-2xl bg-[#444654] px-5 py-4 sm:px-6';
  const iconText = message.role === 'user' ? 'U' : isStatus ? '...' : message.label === 'Judge Verdict' ? 'J' : 'AI';

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className={`flex w-full ${rowClass}`}
    >
      <div className={bubbleClass}>
        <div className="mb-2 flex items-center gap-3 text-xs uppercase tracking-[0.16em] text-[#ECECF1]">
          <span className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-white/10 bg-white/5 text-[10px] font-semibold text-[#ECECF1]">
            {iconText}
          </span>
          <span>{message.label}</span>
        </div>
        {isStatus ? (
          <div className="flex items-center gap-3 text-[#ECECF1]">
            <motion.div
              animate={{ opacity: [0.35, 1, 0.35] }}
              transition={{ duration: 1.4, repeat: Infinity, ease: 'easeInOut' }}
              className="h-2.5 w-2.5 rounded-full bg-white/85 shadow-[0_0_14px_rgba(255,255,255,0.35)]"
            />
            <p className="text-sm text-[#ECECF1]">{message.content}</p>
            <div className="flex items-center gap-1">
              {[0, 1, 2].map((dot) => (
                <motion.span
                  key={dot}
                  animate={{ opacity: [0.25, 1, 0.25] }}
                  transition={{ duration: 1, repeat: Infinity, delay: dot * 0.12 }}
                  className="h-1.5 w-1.5 rounded-full bg-white/85"
                />
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-3 text-[#ECECF1]">{renderFormattedText(message.content, 'leading-7 text-[#ECECF1]')}</div>
        )}
      </div>
    </motion.article>
  );
}

function EdgeToggle({ isOpen, onClick, mobile = false }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`fixed z-50 inline-flex h-10 w-10 items-center justify-center rounded-r-full border border-white/10 border-l-0 bg-[#202123] text-[#ECECF1] transition hover:bg-[#2A2B32] ${
        mobile ? 'left-0 top-20 md:hidden' : 'left-0 top-1/2 hidden -translate-y-1/2 md:inline-flex'
      }`}
      aria-label={isOpen ? 'Close sidebar' : 'Open sidebar'}
    >
      <motion.div animate={{ rotate: isOpen ? 180 : 0 }} transition={{ duration: 0.2 }}>
        <ChevronIcon direction="right" />
      </motion.div>
    </button>
  );
}

function App() {
  const [conversations, setConversations] = useState(() => loadConversations());
  const [currentConversationId, setCurrentConversationId] = useState(() => loadConversations()[0]?.id || null);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState('');
  const [error, setError] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const scrollRef = useRef(null);
  const abortControllerRef = useRef(null);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
  }, [conversations]);

  useEffect(() => {
    if (!currentConversationId && conversations.length) {
      setCurrentConversationId(conversations[0].id);
    }
  }, [conversations, currentConversationId]);

  useEffect(() => {
    if (!scrollRef.current) {
      return;
    }

    scrollRef.current.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [conversations, phase]);

  useEffect(() => () => abortControllerRef.current?.abort(), []);

  const currentConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === currentConversationId) || null,
    [conversations, currentConversationId]
  );

  const activeMessages = currentConversation?.messages || [];
  const visibleMessages = loading
    ? activeMessages
    : activeMessages.filter((message) => message.role === 'user' || message.role === 'judge' || message.role === 'status');
  const thinkingMessage = loading ? buildThinkingMessage(phase) : '';

  function createNewChat() {
    const conversation = createConversation();
    setConversations((current) => [conversation, ...current]);
    setCurrentConversationId(conversation.id);
    setInput('');
    setError('');
    setSidebarOpen(false);
  }

  function updateConversation(conversationId, updater) {
    setConversations((current) =>
      current
        .map((conversation) => {
          if (conversation.id !== conversationId) {
            return conversation;
          }

          const updated = updater(conversation);
          return {
            ...updated,
            updatedAt: Date.now(),
          };
        })
        .sort((a, b) => b.updatedAt - a.updatedAt)
    );
  }

  function stopDebate() {
    if (!loading) {
      return;
    }

    abortControllerRef.current?.abort();
    setLoading(false);
    setPhase('');

    if (currentConversationId) {
      updateConversation(currentConversationId, (conversation) => ({
        ...conversation,
        messages: [
          ...conversation.messages,
          {
            id: crypto.randomUUID(),
            role: 'status',
            label: 'System',
            content: 'Debate stopped by user.',
          },
        ],
      }));
    }
  }

  async function submitMessage(nextPrompt) {
    const value = nextPrompt.trim();
    if (!value || loading) {
      return;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    const existingConversation = currentConversation || createConversation(value);
    const conversationId = existingConversation.id;
    const hadConversation = Boolean(currentConversation);
    const priorMessages = existingConversation.messages || [];
    const userMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      label: 'You',
      content: value,
    };

    if (!hadConversation) {
      setConversations((current) => [existingConversation, ...current]);
      setCurrentConversationId(conversationId);
    }

    updateConversation(conversationId, (conversation) => ({
      ...conversation,
      title: conversation.messages.length ? conversation.title : value,
      messages: [...conversation.messages, userMessage],
    }));

    setInput('');
    setError('');
    setLoading(true);
    setPhase('agentA');
    setSidebarOpen(false);

    try {
      const response = await fetch(`${API_BASE_URL}/api/debate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        signal: controller.signal,
        body: JSON.stringify({
          prompt: value,
          history: priorMessages,
        }),
      });

      if (!response.ok || !response.body) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || 'Failed to start debate.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let streamDone = false;

      while (!streamDone) {
        const { value: chunk, done } = await reader.read();
        streamDone = done;
        buffer += decoder.decode(chunk || new Uint8Array(), { stream: !done });

        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) {
            continue;
          }

          const event = JSON.parse(line);

          if (event.type === 'message') {
            const mappedMessage = {
              id: crypto.randomUUID(),
              role: event.entry.agent === 'A' ? 'agentA' : 'agentB',
              label: event.entry.agent === 'A' ? 'Agent A' : 'Agent B',
              content: event.entry.message,
              meta: event.entry.model,
            };

            updateConversation(conversationId, (conversation) => ({
              ...conversation,
              messages: [...conversation.messages, mappedMessage],
            }));
            setPhase(event.entry.agent === 'A' ? 'agentB' : 'agentA');
          }

          if (event.type === 'status') {
            if (event.stopReason === 'stopped_by_user') {
              setPhase('');
            } else {
              setPhase('judge');
            }
          }

          if (event.type === 'done') {
            if (event.verdict || event.conciseAnswer) {
              const judgeMessage = {
                id: crypto.randomUUID(),
                role: 'judge',
                label: 'Judge Verdict',
                content: event.conciseAnswer || event.verdict,
                meta: event.judgeName,
              };

              updateConversation(conversationId, (conversation) => ({
                ...conversation,
                messages: [...conversation.messages, judgeMessage],
                conciseAnswer: event.conciseAnswer,
                verdict: event.verdict,
              }));
            }
            setPhase('');
          }

          if (event.type === 'error') {
            throw new Error(event.error || 'Debate failed.');
          }
        }
      }
    } catch (requestError) {
      if (requestError.name !== 'AbortError') {
        setError(requestError.message || 'Something went wrong.');
      }
      setPhase('');
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
      setLoading(false);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    submitMessage(input);
  }

  function handleInputKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submitMessage(input);
    }
  }

  const desktopLeftOffset = sidebarOpen ? `${SIDEBAR_WIDTH}px` : '0px';

  return (
    <main className="chat-shell flex min-h-screen bg-[#343541] font-[Inter] text-[#ECECF1]">
      <AnimatePresence>
        {sidebarOpen ? (
          <motion.button
            type="button"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setSidebarOpen(false)}
            className="fixed inset-0 z-30 bg-black/45 md:hidden"
          />
        ) : null}
      </AnimatePresence>

      <EdgeToggle isOpen={sidebarOpen} onClick={() => setSidebarOpen((value) => !value)} mobile />
      {!sidebarOpen ? <EdgeToggle isOpen={sidebarOpen} onClick={() => setSidebarOpen(true)} /> : null}

      <motion.aside
        initial={false}
        animate={{ x: sidebarOpen ? 0 : -SIDEBAR_WIDTH }}
        transition={{ duration: 0.22, ease: 'easeOut' }}
        className="fixed inset-y-0 left-0 z-40 flex w-[280px] flex-col border-r border-white/10 bg-[#202123] md:z-30"
      >
        <div className="flex items-center justify-between p-3">
          <button
            type="button"
            onClick={createNewChat}
            className="flex-1 rounded-lg border border-white/10 bg-transparent px-4 py-3 text-left text-sm font-medium text-[#ECECF1] transition hover:bg-[#2A2B32]"
          >
            + New Chat
          </button>
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            className="ml-2 inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/5 text-[#ECECF1] transition hover:bg-[#2A2B32]"
            aria-label="Close sidebar"
          >
            <ChevronIcon direction="left" />
          </button>
        </div>
        <div className="chat-scroll flex-1 space-y-2 overflow-y-auto px-3 pb-4 pt-1">
          {conversations.map((conversation) => (
            <button
              key={conversation.id}
              type="button"
              onClick={() => {
                setCurrentConversationId(conversation.id);
                setError('');
                setSidebarOpen(false);
              }}
              className={`w-full rounded-lg px-4 py-3 text-left text-sm text-[#ECECF1] transition ${
                conversation.id === currentConversationId ? 'bg-[#2A2B32]' : 'hover:bg-[#2A2B32]'
              }`}
            >
              <p className="truncate">{conversation.title}</p>
            </button>
          ))}
        </div>
      </motion.aside>

      <section className="flex min-h-screen min-w-0 flex-1 flex-col bg-[#343541] transition-[margin] duration-200" style={{ marginLeft: desktopLeftOffset }}>
        <header className="border-b border-white/10 bg-[#343541] px-4 py-4 sm:px-6">
          <div className="flex items-center justify-between gap-3">
            <h1 className="text-base font-semibold tracking-[0.02em]">{APP_NAME}</h1>
            <button
              type="button"
              onClick={createNewChat}
              className="rounded-full border border-white/10 px-3 py-1.5 text-sm text-[#ECECF1] transition hover:bg-[#2A2B32] md:hidden"
            >
              New Chat
            </button>
          </div>
        </header>

        <div ref={scrollRef} className="chat-scroll flex-1 overflow-y-auto bg-[#343541] px-3 py-6 pb-40 sm:px-6">
          <div className="mx-auto max-w-4xl space-y-6">
            {!activeMessages.length ? (
              <div className="flex min-h-[60vh] flex-col items-center justify-center px-2 text-center">
                <h2 className="text-4xl font-semibold tracking-tight sm:text-5xl">{APP_NAME}</h2>
                <p className="mt-4 max-w-2xl text-base text-[#ECECF1] sm:text-lg">{APP_TAGLINE}</p>
                <div className="mt-8 flex max-w-3xl flex-wrap justify-center gap-3">
                  {examplePrompts.map((example) => (
                    <button
                      key={example}
                      type="button"
                      onClick={() => submitMessage(example)}
                      className="rounded-full border border-white/10 bg-[#40414F] px-4 py-2 text-sm text-[#ECECF1] transition hover:bg-[#4a4b59]"
                    >
                      {example}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            <AnimatePresence initial={false}>
              {visibleMessages.map((message) => (
                <MessageBubble key={message.id} message={message} />
              ))}
              {thinkingMessage ? (
                <MessageBubble
                  key="thinking-indicator"
                  message={{
                    id: 'thinking-indicator',
                    role: 'status',
                    label: 'Internal Debate',
                    content: thinkingMessage,
                  }}
                />
              ) : null}
            </AnimatePresence>
          </div>
        </div>

        <div className="fixed bottom-0 right-0 border-t border-white/10 bg-[#343541] px-3 py-3 sm:px-6 sm:py-4 transition-[left] duration-200" style={{ left: desktopLeftOffset }}>
          <form onSubmit={handleSubmit} className="mx-auto max-w-4xl">
            <div className="rounded-lg border border-white/10 bg-[#40414F] p-3 shadow-[0_12px_40px_rgba(0,0,0,0.22)]">
              <div className="flex items-end gap-3">
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={handleInputKeyDown}
                  placeholder="Ask anything..."
                  rows={2}
                  className="min-h-[56px] flex-1 resize-none border-0 bg-transparent px-3 py-3 font-[Inter] text-base text-[#ECECF1] outline-none placeholder:text-[#8E8EA0]"
                />
                <button
                  type={loading ? 'button' : 'submit'}
                  onClick={loading ? stopDebate : undefined}
                  className="mb-1 rounded-full border border-white/10 bg-[#ECECF1] px-4 py-2 text-sm font-semibold text-[#202123] transition hover:bg-white sm:px-5"
                >
                  {loading ? 'Stop' : 'Send'}
                </button>
              </div>
              <p className="px-3 pb-1 pt-2 text-[11px] text-[#8E8EA0]">Press Enter to send. Shift+Enter for a new line.</p>
            </div>
          </form>
          {error ? (
            <div className="mx-auto mt-3 max-w-4xl rounded-lg bg-[#444654] px-4 py-3 text-sm text-[#ECECF1]">
              {error}
            </div>
          ) : null}
        </div>
      </section>
    </main>
  );
}

export default App;
