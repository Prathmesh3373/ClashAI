function DebateCard({ title, accentClass, time, content, delay = '' }) {
  return (
    <article
      className={`glass-panel min-h-[280px] rounded-3xl border border-white/10 p-6 shadow-glow opacity-0 ${delay} ${accentClass}`}
    >
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-xl font-semibold text-arena-text">{title}</h3>
          {time ? <p className="mt-2 text-sm text-arena-muted">Response time: {time}</p> : null}
        </div>
      </div>
      <p className="whitespace-pre-wrap leading-7 text-slate-200">{content}</p>
    </article>
  );
}

export default DebateCard;
