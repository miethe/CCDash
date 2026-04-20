// Feature detail drawer v2. Sections:
//  1. Lineage strip
//  2. Spec & PRD Open Questions / SPIKEs (collapsible, always-visible when data present)
//  3. Execution Tasks — Phases → Batches → Tasks (linked to Plan box)
//  4. Dependency DAG (second view) — phases/batches/tasks dependency graph
//  5. Agent activity

function FeatureDetail({ feature, onClose, onOpenArtifact, focusKind, onExec }) {
  const [viewMode, setViewMode] = React.useState('batches'); // 'batches' | 'dag'
  const [openSections, setOpenSections] = React.useState({
    spec: true, prd: true, tasks: true, dag: false,
  });
  const [oqAnswers, setOqAnswers] = React.useState({}); // local overrides
  const onAnswerOQ = (id, answer) => setOqAnswers(s => ({ ...s, [id]: answer }));
  const toggle = (k) => setOpenSections(s => ({ ...s, [k]: !s[k] }));

  // Scroll to a section when opened via a lineage click (use container-scoped scrollTop, not scrollIntoView)
  const bodyRef = React.useRef();
  const tasksRef = React.useRef();
  const specRef = React.useRef();
  const prdRef = React.useRef();
  React.useEffect(() => {
    if (!focusKind) return;
    const map = { plan: tasksRef, prog: tasksRef, spec: specRef, spike: specRef, prd: prdRef };
    const r = map[focusKind]?.current;
    const body = bodyRef.current;
    if (r && body) {
      const top = r.offsetTop - 16;
      body.scrollTo({ top, behavior: 'smooth' });
    }
    if (focusKind === 'plan' || focusKind === 'prog') setOpenSections(s => ({ ...s, tasks: true }));
    if (focusKind === 'spec' || focusKind === 'spike') setOpenSections(s => ({ ...s, spec: true }));
    if (focusKind === 'prd') setOpenSections(s => ({ ...s, prd: true }));
  }, [focusKind]);

  if (!feature) return null;
  const f = feature;
  const { ARTIFACTS } = window.APP_DATA;

  const specOQs = (f.openQuestions || []).filter(q => ['spec','shaping'].includes(q.scope || 'spec') || true);
  // For this prototype, put all OQs under Spec section; we may split by scope in real data.

  return (
    <div style={{
      position: 'fixed', top: 0, right: 0, bottom: 0,
      width: 'min(920px, 64vw)',
      background: 'var(--bg-1)',
      borderLeft: '1px solid var(--line-2)',
      boxShadow: '-20px 0 60px rgba(0,0,0,0.4)',
      zIndex: 50,
      display: 'flex', flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, padding: '18px 22px', borderBottom: '1px solid var(--line-1)' }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <span className="caps" style={{ fontSize: 10, color: 'var(--ink-3)' }}>{f.category}</span>
            <span style={{ color: 'var(--ink-4)' }}>·</span>
            <span className="mono" style={{ fontSize: 11, color: 'var(--ink-2)' }}>{f.slug}</span>
            {f.mismatch && (
              <span className="pill" style={{
                background: 'color-mix(in oklab, var(--mag) 18%, transparent)',
                color: 'var(--mag)', border: '1px solid color-mix(in oklab, var(--mag) 35%, transparent)',
              }}>mismatch · {f.mismatch.kind}</span>
            )}
          </div>
          <h1 className="serif" style={{ margin: 0, fontSize: 26, letterSpacing: '-0.01em', fontWeight: 500 }}>{f.title}</h1>
          <div style={{ display: 'flex', gap: 10, marginTop: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            <StatusPill status={f.raw} />
            {f.raw !== f.effective && (
              <>
                <span style={{ color: 'var(--ink-3)' }}>{Icons.arrow}</span>
                <StatusPill status={f.effective} />
              </>
            )}
            <span className="chip mono" style={{ fontSize: 10 }}>{f.complexity}</span>
            {f.tags.map(t => <span key={t} className="chip" style={{ fontSize: 10.5 }}>{t}</span>)}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button className="btn" onClick={() => onExec?.({ kind: 'feature', feature: f })}>{Icons.play} Execute phase</button>
          <button className="btn btn-ghost" onClick={onClose}>{Icons.x}</button>
        </div>
      </div>

      {/* Body */}
      <div ref={bodyRef} style={{ flex: 1, overflow: 'auto', padding: '18px 22px', display: 'flex', flexDirection: 'column', gap: 18 }}>
        {/* Lineage strip */}
        <LineageStrip feature={f} onOpenArtifact={onOpenArtifact} />

        {/* SPEC section — SPIKEs + Open Questions */}
        <CollapsibleSection
          innerRef={specRef}
          open={openSections.spec}
          onToggle={() => toggle('spec')}
          color="var(--spec)"
          eyebrow="Design Spec lineage"
          title="SPIKEs & Open Questions"
          count={(f.spikes?.length || 0) + (f.openQuestions?.length || 0)}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <div>
              <SubHeader label="SPIKEs" color="var(--spk)" count={(f.spikes || []).length} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
                {(f.spikes || []).length === 0 && <Muted>No SPIKEs on record.</Muted>}
                {(f.spikes || []).map(s => (
                  <div key={s.id} className="tile spike-row" style={{ padding: 10, display: 'flex', alignItems: 'center', gap: 10, borderLeft: '3px solid var(--spk)', position: 'relative' }}>
                    <span className="mono caps" style={{ fontSize: 10, color: 'var(--spk)' }}>{s.id}</span>
                    <span style={{ fontSize: 12, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.title}</span>
                    <StatusPill status={s.status} />
                    <div className="spike-exec" style={{ opacity: 0, transition: 'opacity 140ms' }}>
                      <ExecBtn onClick={() => onExec?.({ kind: 'spike', spike: s, feature: f })} compact label="run" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <SubHeader label="Open questions" color="var(--spec)" count={(f.openQuestions || []).length} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
                {(f.openQuestions || []).length === 0 && <Muted>No open questions.</Muted>}
                {(f.openQuestions || []).map(q => {
                  const a = oqAnswers[q.id];
                  const merged = a ? { ...q, answer: a, status: 'resolved' } : q;
                  return <OpenQuestionRow key={q.id} q={merged} onAnswer={onAnswerOQ} />;
                })}
              </div>
            </div>
          </div>
        </CollapsibleSection>

        {/* PRD section — in a future pass this will list PRD-scope decisions; for now reuse OQ summary */}
        {(f.artifacts?.prds || []).length > 1 && (
          <CollapsibleSection
            innerRef={prdRef}
            open={openSections.prd}
            onToggle={() => toggle('prd')}
            color="var(--prd)"
            eyebrow="PRD lineage"
            title={`${f.artifacts.prds.length} PRDs linked`}
            count={f.artifacts.prds.length}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {f.artifacts.prds.map(d => (
                <div key={d.id} className="tile" style={{ padding: 10, display: 'grid', gridTemplateColumns: '110px 1fr auto auto', gap: 10, alignItems: 'center', borderLeft: '3px solid var(--prd)' }}>
                  <span className="mono caps" style={{ fontSize: 10, color: 'var(--prd)' }}>{d.id.toUpperCase()}</span>
                  <span style={{ fontSize: 12 }}>{d.title}</span>
                  <span className="mono" style={{ fontSize: 10, color: 'var(--ink-3)' }}>{d.updated}</span>
                  <StatusPill status={d.status} />
                </div>
              ))}
            </div>
          </CollapsibleSection>
        )}

        {/* EXECUTION TASKS — linked to Plan */}
        {f.phases && f.phases.length > 0 && (
          <CollapsibleSection
            innerRef={tasksRef}
            open={openSections.tasks}
            onToggle={() => toggle('tasks')}
            color="var(--plan)"
            eyebrow="Linked to Plan"
            title="Execution tasks"
            count={f.phases.reduce((n, p) => n + (p.tasks?.length || 0), 0)}
            right={
              <div style={{ display: 'flex', gap: 4, background: 'var(--bg-0)', border: '1px solid var(--line-1)', borderRadius: 6, padding: 2 }}>
                <SegBtn active={viewMode === 'batches'} onClick={() => setViewMode('batches')}>Batches</SegBtn>
                <SegBtn active={viewMode === 'dag'}     onClick={() => setViewMode('dag')}>Dependency DAG</SegBtn>
              </div>
            }>
            {viewMode === 'batches'
              ? <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <ModelLegend feature={f} />
                  {f.phases.map(p => <PhaseCard key={p.n} phase={p} agents={window.APP_DATA.AGENTS} onExec={onExec} />)}
                </div>
              : <DependencyDAG phases={f.phases} />
            }
          </CollapsibleSection>
        )}

        {/* Agent activity */}
        <section>
          <div className="caps" style={{ fontSize: 10, color: 'var(--ink-3)', marginBottom: 10 }}>Agent activity for this feature</div>
          <div className="tile" style={{ padding: 10 }}>
            {window.APP_DATA.LIVE_AGENTS.slice(0, 3).map((l, i) => (
              <div key={i} className="mono" style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 11, color: 'var(--ink-2)', padding: '4px 0' }}>
                <span style={{ color: l.state === 'running' ? 'var(--ok)' : l.state === 'thinking' ? 'var(--info)' : 'var(--ink-3)' }}>
                  {l.state === 'running' ? '●' : l.state === 'thinking' ? '◐' : '○'}
                </span>
                <span style={{ color: 'var(--ink-0)', minWidth: 200 }}>{l.agent}</span>
                <span style={{ color: 'var(--ink-3)' }}>{l.state}</span>
                <span style={{ color: 'var(--ink-2)', flex: 1, textAlign: 'right' }}>{l.task}</span>
                <span style={{ color: 'var(--ink-3)', width: 50, textAlign: 'right' }}>{l.since}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function LineageStrip({ feature, onOpenArtifact }) {
  const f = feature;
  const { reprStatus, ARTIFACTS } = window.APP_DATA;
  const items = [
    { kind: 'spec',  label: 'SPEC',  color: 'var(--spec)', count: (f.artifacts?.specs || []).length, rep: reprStatus(f.artifacts?.specs) },
    { kind: 'spike', label: 'SPIKE', color: 'var(--spk)',  count: (f.spikes || []).length,           rep: reprStatus(f.spikes) },
    { kind: 'prd',   label: 'PRD',   color: 'var(--prd)',  count: (f.artifacts?.prds || []).length,  rep: reprStatus(f.artifacts?.prds) },
    { kind: 'plan',  label: 'PLAN',  color: 'var(--plan)', count: (f.artifacts?.plans || []).length, rep: reprStatus(f.artifacts?.plans) },
    { kind: 'prog',  label: 'PHASE', color: 'var(--prog)', count: (f.phases || []).length,           rep: null, special: 'prog' },
    { kind: 'ctx',   label: 'CTX',   color: 'var(--ctx)',  count: (f.artifacts?.ctxs || []).length,  rep: reprStatus(f.artifacts?.ctxs) },
    { kind: 'rep',   label: 'REPORT',color: 'var(--rep)',  count: (f.artifacts?.reports || []).length, rep: reprStatus(f.artifacts?.reports) },
  ];
  return (
    <section>
      <div className="caps" style={{ fontSize: 10, color: 'var(--ink-3)', marginBottom: 10 }}>Lineage · click to expand below</div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {items.map(it => {
          const muted = it.count === 0;
          return (
            <button key={it.kind}
              onClick={() => !muted && onOpenArtifact?.(it.kind)}
              className="tile" style={{
                padding: 10, minWidth: 120, display: 'flex', flexDirection: 'column', gap: 6, cursor: muted ? 'default' : 'pointer',
                borderColor: `color-mix(in oklab, ${it.color} 30%, var(--line-1))`,
                background: `linear-gradient(180deg, color-mix(in oklab, ${it.color} ${muted ? 4 : 10}%, var(--bg-2)), var(--bg-2))`,
                opacity: muted ? 0.4 : 1, textAlign: 'left', fontFamily: 'inherit',
              }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <span className="mono caps" style={{ fontSize: 10, color: it.color }}>{it.label}</span>
                <span className="mono tnum" style={{ fontSize: 10, color: 'var(--ink-2)', padding: '0 5px', background: 'var(--bg-0)', borderRadius: 4, border: '1px solid var(--line-1)' }}>
                  ×{it.count}
                </span>
              </div>
              {it.special === 'prog' && it.count > 0 && (
                <div style={{ display: 'flex', gap: 3 }}>
                  {(f.phases || []).map(p => <PhaseDot key={p.n} phase={p} />)}
                </div>
              )}
              {it.rep && <StatusPill status={it.rep.status} />}
              {!it.rep && it.special !== 'prog' && <span style={{ fontSize: 10, color: 'var(--ink-3)' }}>—</span>}
            </button>
          );
        })}
      </div>
    </section>
  );
}

function CollapsibleSection({ innerRef, open, onToggle, color, eyebrow, title, count, right, children }) {
  return (
    <section ref={innerRef} className="panel" style={{ overflow: 'hidden', borderLeft: `3px solid ${color}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', borderBottom: open ? '1px solid var(--line-1)' : 'none' }}>
        <button onClick={onToggle} style={{ background: 'none', border: 'none', color: 'var(--ink-2)', cursor: 'pointer', padding: 2, display: 'flex' }}>
          <span style={{ display: 'inline-block', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .15s' }}>{Icons.chevron}</span>
        </button>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="caps" style={{ fontSize: 9.5, color, letterSpacing: 0.12 + 'em' }}>{eyebrow}</div>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink-0)' }}>
            {title}
            {typeof count === 'number' && <span className="mono tnum" style={{ marginLeft: 8, fontSize: 11, color: 'var(--ink-3)' }}>({count})</span>}
          </div>
        </div>
        {right}
      </div>
      {open && <div style={{ padding: 14 }}>{children}</div>}
    </section>
  );
}

function SubHeader({ label, color, count }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ width: 6, height: 6, background: color, borderRadius: 1 }} />
      <span className="caps" style={{ fontSize: 10, color: 'var(--ink-2)' }}>{label}</span>
      <span className="mono tnum" style={{ fontSize: 10, color: 'var(--ink-3)' }}>×{count}</span>
    </div>
  );
}

function Muted({ children }) {
  return <div style={{ fontSize: 11.5, color: 'var(--ink-3)', padding: '6px 2px', fontStyle: 'italic' }}>{children}</div>;
}

function OpenQuestionRow({ q, onAnswer }) {
  const sev = { high: 'var(--err)', medium: 'var(--warn)', low: 'var(--info)' }[q.severity] || 'var(--ink-3)';
  const [editing, setEditing] = React.useState(false);
  const [val, setVal] = React.useState(q.answer || '');
  const [localAnswer, setLocalAnswer] = React.useState(q.answer || null);
  const resolved = q.status === 'resolved' || !!localAnswer;
  const save = () => {
    if (val.trim()) { setLocalAnswer(val.trim()); onAnswer?.(q.id, val.trim()); }
    setEditing(false);
  };
  return (
    <div className="tile" style={{
      padding: 10, display: 'flex', alignItems: 'flex-start', gap: 10,
      borderLeft: `3px solid ${resolved ? 'var(--ok)' : sev}`,
      opacity: resolved && !editing ? 0.75 : 1,
      transition: 'opacity 160ms',
    }}>
      <span className="mono caps" style={{ fontSize: 10, color: resolved ? 'var(--ok)' : sev, marginTop: 1 }}>{q.id}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, color: 'var(--ink-0)' }}>{q.text}</div>
        {/* Existing/new answer display or editor */}
        {editing ? (
          <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
            <textarea
              autoFocus value={val}
              onChange={(e) => setVal(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) save();
                if (e.key === 'Escape') { setEditing(false); setVal(localAnswer || ''); }
              }}
              placeholder="Write the answer / decision…"
              style={{
                fontFamily: 'inherit', fontSize: 12, lineHeight: 1.45,
                padding: '8px 10px', background: 'var(--bg-0)', color: 'var(--ink-0)',
                border: '1px solid color-mix(in oklab, var(--brand) 40%, var(--line-1))',
                borderRadius: 5, outline: 'none', resize: 'vertical', minHeight: 64,
              }} />
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 10 }}>
              <button onClick={save} className="mono"
                style={{
                  padding: '3px 10px', background: 'var(--brand)', color: 'var(--bg-0)',
                  border: 'none', borderRadius: 3, cursor: 'pointer', fontSize: 10.5, fontWeight: 600,
                }}>resolve ⌘↵</button>
              <button onClick={() => { setEditing(false); setVal(localAnswer || ''); }} className="mono"
                style={{
                  padding: '3px 10px', background: 'transparent', color: 'var(--ink-3)',
                  border: '1px solid var(--line-1)', borderRadius: 3, cursor: 'pointer', fontSize: 10.5,
                }}>esc</button>
              <span style={{ color: 'var(--ink-4)', marginLeft: 'auto' }}>frontmatter · answer + status</span>
            </div>
          </div>
        ) : localAnswer ? (
          <div onClick={() => setEditing(true)}
            style={{
              marginTop: 6, padding: '6px 9px', fontSize: 11.5, lineHeight: 1.45,
              background: 'color-mix(in oklab, var(--ok) 8%, transparent)',
              borderLeft: '2px solid var(--ok)', borderRadius: '0 3px 3px 0',
              color: 'var(--ink-1)', cursor: 'text',
            }}>
            <span className="caps mono" style={{ fontSize: 9.5, color: 'var(--ok)', marginRight: 6 }}>answer</span>
            {localAnswer}
          </div>
        ) : (
          <button onClick={() => setEditing(true)}
            style={{
              marginTop: 6, padding: '3px 0', fontSize: 10.5,
              background: 'transparent', color: 'var(--brand)', border: 'none',
              cursor: 'pointer', fontFamily: 'var(--mono)',
            }}>
            + answer…
          </button>
        )}
        <div style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 4 }}>
          <span className="mono">@{q.owner}</span> · {q.severity} · {resolved ? 'resolved' : q.status}
        </div>
      </div>
    </div>
  );
}

function SegBtn({ active, onClick, children }) {
  return (
    <button onClick={onClick} style={{
      padding: '4px 10px', fontSize: 11, fontWeight: 500,
      background: active ? 'var(--bg-3)' : 'transparent',
      color: active ? 'var(--ink-0)' : 'var(--ink-2)',
      border: 'none', borderRadius: 4, cursor: 'pointer', fontFamily: 'inherit',
    }}>
      {children}
    </button>
  );
}

function PhaseCard({ phase, agents, onExec }) {
  const { MODELS, rollupFeature, tokenEstimate } = window.APP_DATA;
  const batches = {};
  (phase.tasks || []).forEach(t => { const b = t.batch || 1; if (!batches[b]) batches[b] = []; batches[b].push(t); });
  const batchKeys = Object.keys(batches).sort((a, b) => +a - +b);
  const c = (STATUS_TOKENS[phase.status] || {}).color || 'var(--ink-2)';
  // Phase totals
  const phaseTokensByModel = { opus: 0, sonnet: 0, haiku: 0 };
  let phasePts = 0, phaseTokens = 0;
  (phase.tasks || []).forEach(t => {
    phasePts += (t.points || 0);
    const m = (agents[t.agent] || { model: 'sonnet' }).model;
    if (t.status === 'completed' || t.status === 'in-progress') {
      const est = tokenEstimate(t, m);
      phaseTokensByModel[m] = (phaseTokensByModel[m] || 0) + est;
      phaseTokens += est;
    }
  });
  const fmt = (n) => n >= 1000 ? `${(n/1000).toFixed(n<10000?1:0)}k` : String(n);
  return (
    <div className="tile" style={{ padding: 14, borderLeft: `3px solid ${c}` }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span className="mono" style={{ fontSize: 10.5, color: 'var(--ink-3)' }}>PHASE {String(phase.n).padStart(2, '0')}</span>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>{phase.name}</h3>
          <StatusPill status={phase.status} />
          <ExecBtn onClick={() => onExec?.({ kind: 'phase', phase })} label="run phase" />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="mono tnum" style={{ fontSize: 10.5, color: 'var(--ink-3)' }}>{phasePts} pts · {fmt(phaseTokens)} tok</span>
          <div className="mono tnum" style={{ fontSize: 11, color: 'var(--ink-2)' }}>{phase.progress}%</div>
          <div style={{ width: 120, height: 4, background: 'var(--bg-3)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{ width: `${phase.progress}%`, height: '100%', background: c }} />
          </div>
        </div>
      </div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'stretch' }}>
        {batchKeys.map(k => {
          const bTasks = batches[k];
          const bTokens = bTasks.reduce((acc, t) => {
            const m = (agents[t.agent] || { model: 'sonnet' }).model;
            return acc + ((t.status === 'completed' || t.status === 'in-progress') ? tokenEstimate(t, m) : 0);
          }, 0);
          return (
            <div key={k} className="batch-col" style={{ flex: 1, minWidth: 0, background: 'var(--bg-1)', border: '1px solid var(--line-1)', borderRadius: 6, padding: 10, position: 'relative' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, gap: 6 }}>
                <span className="caps" style={{ fontSize: 9.5, color: 'var(--ink-3)' }}>batch {k}</span>
                <span className="mono" style={{ fontSize: 10, color: 'var(--ink-3)' }}>{bTasks.length} · parallel{bTokens ? ` · ${fmt(bTokens)}` : ''}</span>
                <ExecBtn onClick={() => onExec?.({ kind: 'batch', phase, batch: k })} compact />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {bTasks.map(t => <TaskRow key={t.id} task={t} agents={agents} onExec={onExec} />)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ExecBtn({ onClick, label, compact }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      className="exec-btn"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={(e) => { e.stopPropagation(); onClick?.(); }}
      title={label || 'Execute'}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        padding: compact ? '1px 5px' : '2px 7px',
        background: hover ? 'color-mix(in oklab, var(--brand) 22%, transparent)' : 'color-mix(in oklab, var(--brand) 8%, transparent)',
        color: 'var(--brand)',
        border: '1px solid color-mix(in oklab, var(--brand) 35%, transparent)',
        borderRadius: 3, fontSize: compact ? 10 : 10.5, fontFamily: 'var(--mono)', cursor: 'pointer',
        lineHeight: 1.3, transition: 'background 120ms',
      }}>
      <span style={{ fontSize: compact ? 9 : 10 }}>▶</span>{!compact && label && <span>{label}</span>}
    </button>
  );
}

function TaskRow({ task, agents, onExec }) {
  const { MODELS, tokenEstimate } = window.APP_DATA;
  const tok = STATUS_TOKENS[task.status] || { color: 'var(--ink-2)', label: task.status };
  const agent = agents[task.agent] || { short: task.agent, model: 'sonnet' };
  const model = MODELS[agent.model] || MODELS.sonnet;
  const tokens = (task.status === 'completed' || task.status === 'in-progress') ? tokenEstimate(task, agent.model) : 0;
  const tokDisp = tokens >= 1000 ? `${(tokens/1000).toFixed(tokens<10000?1:0)}k` : (tokens ? String(tokens) : '—');
  const [hover, setHover] = React.useState(false);
  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'grid', gridTemplateColumns: '66px 1fr auto auto auto 22px', alignItems: 'center', gap: 8,
        padding: '5px 8px', borderRadius: 4,
        borderLeft: `2px solid ${model.color}`,
        background: task.status === 'blocked' ? 'color-mix(in oklab, var(--err) 10%, var(--bg-2))'
                   : task.status === 'in-progress' ? 'color-mix(in oklab, var(--plan) 8%, var(--bg-2))'
                   : hover ? 'var(--bg-2)' : 'transparent',
        transition: 'background 80ms',
      }}>
      <span className="mono" style={{ fontSize: 10.5, color: 'var(--ink-3)' }}>{task.id}</span>
      <span style={{ fontSize: 12, color: 'var(--ink-0)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{task.title}</span>
      <span className="mono" title={`${agent.short} · ${model.label}`} style={{
        fontSize: 9.5, color: model.color, padding: '1px 6px',
        border: `1px solid color-mix(in oklab, ${model.color} 40%, transparent)`,
        background: `color-mix(in oklab, ${model.color} 10%, transparent)`,
        borderRadius: 3,
      }}>
        {agent.short}
        <span style={{ opacity: 0.65, marginLeft: 4 }}>{model.label}</span>
      </span>
      <span className="mono tnum" title={`${tokens.toLocaleString()} tokens`} style={{ fontSize: 10, color: tokens ? 'var(--ink-2)' : 'var(--ink-4)', minWidth: 32, textAlign: 'right' }}>
        {tokDisp}
      </span>
      <span className="pill" style={{
        background: `color-mix(in oklab, ${tok.color} 14%, transparent)`,
        color: tok.color, border: `1px solid color-mix(in oklab, ${tok.color} 26%, transparent)`,
      }}>{tok.label}</span>
      <span style={{ opacity: hover ? 1 : 0, transition: 'opacity 120ms' }}>
        <ExecBtn onClick={() => onExec?.({ kind: 'task', task })} compact />
      </span>
    </div>
  );
}

// ============ Dependency DAG ============
// Layout: columns = batches (per phase), stacked top→bottom by phase.
// Edges: task.deps → task. Highlights parallelizable sets clearly.

function DependencyDAG({ phases }) {
  // Flatten tasks, assign (phase, batch) coords
  const allTasks = phases.flatMap(p => (p.tasks || []).map(t => ({ ...t, phase: p.n, phaseName: p.name })));
  const taskMap = Object.fromEntries(allTasks.map(t => [t.id, t]));

  // Column = batch within phase. Compute per-phase layout.
  const PHASE_GAP = 26;
  const NODE_W = 170;
  const NODE_H = 44;
  const COL_GAP = 42;
  const ROW_GAP = 12;
  const PAD = 16;

  const phaseBlocks = phases.map(p => {
    const tasks = p.tasks || [];
    const byBatch = {};
    tasks.forEach(t => { const b = t.batch || 1; (byBatch[b] ||= []).push(t); });
    const batchKeys = Object.keys(byBatch).sort((a, b) => +a - +b);
    const rows = Math.max(1, ...batchKeys.map(k => byBatch[k].length));
    const blockHeight = PAD * 2 + 22 /* header */ + rows * NODE_H + (rows - 1) * ROW_GAP;
    const blockWidth  = PAD * 2 + batchKeys.length * NODE_W + (batchKeys.length - 1) * COL_GAP;
    return { p, byBatch, batchKeys, rows, blockHeight, blockWidth };
  });

  const totalWidth = Math.max(600, ...phaseBlocks.map(b => b.blockWidth));
  let yCursor = 0;
  const blockTops = phaseBlocks.map(b => { const t = yCursor; yCursor += b.blockHeight + PHASE_GAP; return t; });
  const totalHeight = yCursor;

  // Compute absolute positions for each task
  const positions = {};
  phaseBlocks.forEach((block, bi) => {
    const yStart = blockTops[bi] + PAD + 22;
    block.batchKeys.forEach((k, ci) => {
      block.byBatch[k].forEach((t, ri) => {
        const x = PAD + ci * (NODE_W + COL_GAP);
        const y = yStart + ri * (NODE_H + ROW_GAP);
        positions[t.id] = { x, y, w: NODE_W, h: NODE_H };
      });
    });
  });

  // Edges: deps → task. Only draw if both endpoints exist in this feature.
  const edges = [];
  allTasks.forEach(t => {
    (t.deps || []).forEach(d => {
      if (positions[d] && positions[t.id]) {
        edges.push({ from: positions[d], to: positions[t.id], status: t.status, dStatus: taskMap[d].status });
      }
    });
  });

  return (
    <div style={{ overflow: 'auto', border: '1px solid var(--line-1)', borderRadius: 6, background: 'var(--bg-0)', maxHeight: 560 }}>
      <div style={{ position: 'relative', width: totalWidth, height: totalHeight }}>
        {/* Phase block frames */}
        {phaseBlocks.map((block, bi) => (
          <div key={block.p.n} style={{
            position: 'absolute', left: 0, top: blockTops[bi],
            width: totalWidth, height: block.blockHeight,
            borderBottom: bi < phaseBlocks.length - 1 ? '1px dashed var(--line-1)' : 'none',
          }}>
            <div style={{ position: 'absolute', left: PAD, top: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="mono caps" style={{ fontSize: 10, color: 'var(--prog)' }}>PHASE {String(block.p.n).padStart(2, '0')}</span>
              <span style={{ fontSize: 12, color: 'var(--ink-1)', fontWeight: 500 }}>{block.p.name}</span>
              <StatusPill status={block.p.status} />
            </div>
            {/* Batch column headers */}
            {block.batchKeys.map((k, ci) => (
              <div key={k} className="caps" style={{
                position: 'absolute', left: PAD + ci * (NODE_W + COL_GAP), top: 32,
                width: NODE_W, fontSize: 9.5, color: 'var(--ink-4)', letterSpacing: 0.12 + 'em',
              }}>
                BATCH {k} · parallel
              </div>
            ))}
          </div>
        ))}

        {/* SVG edge layer */}
        <svg width={totalWidth} height={totalHeight} style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
          <defs>
            <marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">
              <path d="M0 0 L10 5 L0 10 z" fill="currentColor" />
            </marker>
          </defs>
          {edges.map((e, i) => {
            const x1 = e.from.x + e.from.w;
            const y1 = e.from.y + e.from.h / 2;
            const x2 = e.to.x;
            const y2 = e.to.y + e.to.h / 2;
            const mx = (x1 + x2) / 2;
            const color = e.status === 'blocked' ? 'var(--err)'
                        : e.status === 'in-progress' ? 'var(--plan)'
                        : e.dStatus === 'completed' && e.status !== 'completed' ? 'var(--ok)'
                        : 'var(--line-2)';
            return (
              <g key={i} style={{ color }}>
                <path d={`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2 - 6} ${y2}`}
                  fill="none" stroke={color} strokeWidth="1.3" markerEnd="url(#arr)"
                  className={e.status === 'in-progress' ? 'flow' : ''} />
              </g>
            );
          })}
        </svg>

        {/* Nodes */}
        {allTasks.map(t => {
          const p = positions[t.id];
          if (!p) return null;
          const tok = STATUS_TOKENS[t.status] || { color: 'var(--ink-2)', label: t.status };
          return (
            <div key={t.id} style={{
              position: 'absolute', left: p.x, top: p.y, width: p.w, height: p.h,
              background: 'var(--bg-2)',
              border: `1px solid ${t.status === 'blocked' ? 'color-mix(in oklab, var(--err) 45%, var(--line-1))' : 'var(--line-1)'}`,
              borderLeft: `3px solid ${tok.color}`,
              borderRadius: 5,
              padding: '6px 9px',
              display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}>
                <span className="mono" style={{ fontSize: 10, color: 'var(--ink-3)' }}>{t.id}</span>
                <span className="dot" style={{ background: tok.color }} />
              </div>
              <div style={{ fontSize: 11, color: 'var(--ink-0)', lineHeight: 1.2,
                overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                {t.title}
              </div>
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 14, padding: '8px 14px', borderTop: '1px solid var(--line-1)', fontSize: 10.5, color: 'var(--ink-3)', background: 'var(--bg-1)' }}>
        <span className="caps" style={{ fontSize: 9.5 }}>deps</span>
        <span><span style={{ display: 'inline-block', width: 22, height: 2, background: 'var(--ok)', verticalAlign: 'middle', marginRight: 4 }} />unblocked & ready</span>
        <span><span style={{ display: 'inline-block', width: 22, height: 2, background: 'var(--plan)', verticalAlign: 'middle', marginRight: 4 }} />active</span>
        <span><span style={{ display: 'inline-block', width: 22, height: 2, background: 'var(--err)', verticalAlign: 'middle', marginRight: 4 }} />blocked</span>
        <span style={{ marginLeft: 'auto' }}>same-column nodes can run in parallel</span>
      </div>
    </div>
  );
}

function ModelLegend({ feature }) {
  const { MODELS, rollupFeature } = window.APP_DATA;
  const r = rollupFeature(feature);
  const fmt = (n) => n >= 1000 ? `${(n/1000).toFixed(n<10000?1:0)}k` : String(n);
  const rows = ['opus', 'sonnet', 'haiku'];
  const total = r.tokens || 1;
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 14, padding: '8px 12px',
      background: 'var(--bg-2)', border: '1px solid var(--line-1)', borderRadius: 6,
      fontSize: 10.5, color: 'var(--ink-2)',
    }}>
      <span className="caps" style={{ fontSize: 9.5, color: 'var(--ink-4)' }}>models</span>
      {rows.map(k => {
        const pct = r.tokens ? Math.round((r.tokensByModel[k] / total) * 100) : 0;
        return (
          <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span className="dot" style={{ background: MODELS[k].color }} />
            <span className="mono" style={{ color: MODELS[k].color, fontSize: 10.5 }}>{MODELS[k].label}</span>
            <span className="mono tnum" style={{ color: 'var(--ink-3)', fontSize: 10 }}>
              {fmt(r.tokensByModel[k])} · {pct}%
            </span>
          </span>
        );
      })}
      <span style={{ marginLeft: 'auto' }} className="mono tnum">
        <span style={{ color: 'var(--ink-3)' }}>Σ&nbsp;</span>
        <span style={{ color: 'var(--ink-0)' }}>{r.points}&nbsp;pts</span>
        <span style={{ color: 'var(--ink-3)' }}> · {fmt(r.tokens)} tokens</span>
      </span>
    </div>
  );
}

Object.assign(window, { FeatureDetail });
