// Planning Graph — rewritten for v2.
// - Leftmost: sticky Feature column with name, status, category.
// - Lanes: SPEC · SPIKE · PRD · PLAN · PROGRESS · CTX/REPORT.
// - Each lane cell can hold MULTIPLE stacked doc chips (when a feature has >1 spec/prd/plan/etc.).
// - Row heights auto-expand to accommodate the tallest lane in the row.

function PlanningGraph({ features, onSelectFeature, onSelectNode, selectedFeatureId }) {
  const { ARTIFACTS } = window.APP_DATA;

  const LANES = [
    { key: 'specs',   label: 'Design Spec',   color: 'var(--spec)', glyph: ARTIFACTS.spec.glyph },
    { key: 'spikes',  label: 'SPIKE',         color: 'var(--spk)',  glyph: ARTIFACTS.spk.glyph  },
    { key: 'prds',    label: 'PRD',           color: 'var(--prd)',  glyph: ARTIFACTS.prd.glyph  },
    { key: 'plans',   label: 'Impl Plan',     color: 'var(--plan)', glyph: ARTIFACTS.plan.glyph },
    { key: 'prog',    label: 'Progress',      color: 'var(--prog)', glyph: ARTIFACTS.prog.glyph },
    { key: 'ctxrep',  label: 'Context / Report', color: 'var(--ctx)',  glyph: ARTIFACTS.ctx.glyph },
    { key: 'totals',  label: 'Effort · Tokens', color: 'var(--ink-2)', glyph: '∑' },
  ];

  const FEATURE_COL_W = 240;
  const LANE_W = 200;
  const PADX = 16;
  const PADY = 14;
  const SUBROW_H = 28;
  const SUBROW_GAP = 6;
  const MIN_ROW_H = 54;

  // Compute per-feature row model: how many sub-rows each lane wants
  const rowsModel = features.map(f => {
    const spkCount = (f.spikes || []).length;
    const specCount = (f.artifacts?.specs || []).length;
    const prdCount = (f.artifacts?.prds || []).length;
    const planCount = (f.artifacts?.plans || []).length;
    const ctxCount = (f.artifacts?.ctxs || []).length + (f.artifacts?.reports || []).length;
    const progCount = (f.phases && f.phases.length) ? 1 : 0;

    const maxSub = Math.max(1, specCount, spkCount, prdCount, planCount, progCount, ctxCount);
    const rowH = Math.max(MIN_ROW_H, PADY * 2 + maxSub * SUBROW_H + (maxSub - 1) * SUBROW_GAP);
    return { f, rowH, maxSub };
  });

  // Cumulative y positions for each row (for SVG edges)
  let yAccum = 0;
  const rowTops = rowsModel.map(r => { const t = yAccum; yAccum += r.rowH; return t; });
  const totalHeight = yAccum;
  const totalWidth = FEATURE_COL_W + LANES.length * LANE_W;

  return (
    <div className="panel" style={{ overflow: 'hidden', padding: 0 }}>
      {/* Header row */}
      <div style={{ display: 'grid', gridTemplateColumns: `${FEATURE_COL_W}px repeat(${LANES.length}, ${LANE_W}px)`, borderBottom: '1px solid var(--line-1)', background: 'var(--bg-1)', position: 'sticky', top: 0, zIndex: 2 }}>
        <div style={{ padding: '14px 16px', borderRight: '1px solid var(--line-1)' }}>
          <div className="caps" style={{ fontSize: 10, color: 'var(--ink-3)' }}>Feature</div>
        </div>
        {LANES.map(lane => (
          <div key={lane.key} style={{ padding: '14px 14px', borderRight: '1px solid var(--line-1)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: lane.color, boxShadow: `0 0 10px color-mix(in oklab, ${lane.color} 55%, transparent)` }} />
            <span className="caps" style={{ fontSize: 10, color: 'var(--ink-2)' }}>{lane.label}</span>
          </div>
        ))}
      </div>

      {/* Body with horizontal scroll */}
      <div style={{ overflow: 'auto', maxHeight: '72vh' }}>
        <div style={{ position: 'relative', width: totalWidth, minWidth: '100%' }}>
          {/* Edge layer */}
          <svg width={totalWidth} height={totalHeight} style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
            {rowsModel.map(({ f }, rowIdx) => {
              const y = rowTops[rowIdx] + rowsModel[rowIdx].rowH / 2;
              const laneCenters = LANES.map((_, i) => FEATURE_COL_W + i * LANE_W + LANE_W / 2);
              const laneHas = {
                specs: (f.artifacts?.specs?.length || 0) > 0,
                spikes: (f.spikes?.length || 0) > 0,
                prds: (f.artifacts?.prds?.length || 0) > 0,
                plans: (f.artifacts?.plans?.length || 0) > 0,
                prog: (f.phases?.length || 0) > 0,
                ctxrep: (f.artifacts?.ctxs?.length || 0) + (f.artifacts?.reports?.length || 0) > 0,
              };
              const chain = LANES.map(l => l.key).filter(k => laneHas[k]);
              const active = f.effective === 'in-progress';
              return chain.slice(0, -1).map((k, i) => {
                const iFrom = LANES.findIndex(l => l.key === k);
                const iTo = LANES.findIndex(l => l.key === chain[i + 1]);
                const x1 = laneCenters[iFrom] + 80;
                const x2 = laneCenters[iTo] - 80;
                const mx = (x1 + x2) / 2;
                return (
                  <path key={`${rowIdx}-${i}`} d={`M ${x1} ${y} C ${mx} ${y}, ${mx} ${y}, ${x2} ${y}`}
                    fill="none" stroke={active ? 'color-mix(in oklab, var(--brand) 80%, transparent)' : 'var(--line-2)'}
                    strokeWidth="1.2" className={active ? 'flow' : ''} />
                );
              });
            })}
            {/* Column separators */}
            <line x1={FEATURE_COL_W} x2={FEATURE_COL_W} y1={0} y2={totalHeight} stroke="var(--line-1)" />
            {LANES.map((_, i) => (
              <line key={i} x1={FEATURE_COL_W + (i + 1) * LANE_W} x2={FEATURE_COL_W + (i + 1) * LANE_W} y1={0} y2={totalHeight}
                stroke="color-mix(in oklab, var(--line-1) 60%, transparent)" strokeDasharray="2 6" />
            ))}
          </svg>

          {/* Rows */}
          {rowsModel.map(({ f, rowH }, rowIdx) => (
            <div key={f.id}
              onClick={() => onSelectFeature?.(f.id)}
              style={{
                display: 'grid',
                gridTemplateColumns: `${FEATURE_COL_W}px repeat(${LANES.length}, ${LANE_W}px)`,
                borderBottom: '1px solid var(--line-1)',
                background: selectedFeatureId === f.id ? 'color-mix(in oklab, var(--brand) 6%, transparent)' : 'transparent',
                cursor: 'pointer',
                position: 'relative',
                minHeight: rowH,
              }}>
              {/* Feature cell */}
              <FeatureCell f={f} selected={selectedFeatureId === f.id} />

              {/* Spec */}
              <LaneCell color="var(--spec)">
                {(f.artifacts?.specs || []).map(d => (
                  <DocChip key={d.id} doc={d} color="var(--spec)" label="SPEC" onOpen={(e) => { e.stopPropagation(); onSelectNode?.({ feature: f, kind: 'spec', doc: d }); }} />
                ))}
                {(f.artifacts?.specs || []).length === 0 && <EmptyDash />}
              </LaneCell>

              {/* Spikes */}
              <LaneCell color="var(--spk)">
                {(f.spikes || []).map(s => (
                  <DocChip key={s.id} doc={s} color="var(--spk)" label={s.id} title={s.title}
                    onOpen={(e) => { e.stopPropagation(); onSelectNode?.({ feature: f, kind: 'spike', doc: s }); }} />
                ))}
                {(f.spikes || []).length === 0 && <EmptyDash />}
              </LaneCell>

              {/* PRDs */}
              <LaneCell color="var(--prd)">
                {(f.artifacts?.prds || []).map(d => (
                  <DocChip key={d.id} doc={d} color="var(--prd)" label="PRD" onOpen={(e) => { e.stopPropagation(); onSelectNode?.({ feature: f, kind: 'prd', doc: d }); }} />
                ))}
                {(f.artifacts?.prds || []).length === 0 && <EmptyDash />}
              </LaneCell>

              {/* Plans */}
              <LaneCell color="var(--plan)">
                {(f.artifacts?.plans || []).map(d => (
                  <DocChip key={d.id} doc={d} color="var(--plan)" label="PLAN"
                    onOpen={(e) => { e.stopPropagation(); onSelectNode?.({ feature: f, kind: 'plan', doc: d }); }} />
                ))}
                {(f.artifacts?.plans || []).length === 0 && <EmptyDash />}
              </LaneCell>

              {/* Progress */}
              <LaneCell color="var(--prog)">
                {(f.phases && f.phases.length > 0) ? (
                  <PhaseStackInline phases={f.phases}
                    onOpen={(e) => { e.stopPropagation(); onSelectNode?.({ feature: f, kind: 'prog' }); }} />
                ) : <EmptyDash />}
              </LaneCell>

              {/* Context / Reports */}
              <LaneCell color="var(--ctx)">
                {(f.artifacts?.ctxs || []).map(d => (
                  <DocChip key={d.id} doc={d} color="var(--ctx)" label="CTX"
                    onOpen={(e) => { e.stopPropagation(); onSelectNode?.({ feature: f, kind: 'ctx', doc: d }); }} />
                ))}
                {(f.artifacts?.reports || []).map(d => (
                  <DocChip key={d.id} doc={d} color="var(--rep)" label="REP"
                    onOpen={(e) => { e.stopPropagation(); onSelectNode?.({ feature: f, kind: 'rep', doc: d }); }} />
                ))}
                {((f.artifacts?.ctxs || []).length + (f.artifacts?.reports || []).length) === 0 && <EmptyDash />}
              </LaneCell>

              {/* Effort + Tokens totals */}
              <LaneCell color="var(--ink-2)">
                <TotalsCell feature={f} />
              </LaneCell>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function FeatureCell({ f, selected }) {
  const categoryColors = {
    features: 'var(--brand)', refactors: 'var(--info)',
    enhancements: 'var(--plan)', spikes: 'var(--spk)',
  };
  const cat = categoryColors[f.category] || 'var(--ink-3)';
  return (
    <div style={{
      padding: '12px 14px',
      borderRight: '1px solid var(--line-1)',
      borderLeft: selected ? `3px solid var(--brand)` : `3px solid transparent`,
      paddingLeft: selected ? 11 : 14,
      background: 'var(--bg-1)',
      display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span className="caps mono" style={{ fontSize: 9, color: cat, letterSpacing: 0.1 + 'em' }}>{f.category}</span>
        <span className="mono" style={{ fontSize: 10, color: 'var(--ink-4)' }}>·</span>
        <span className="mono" style={{ fontSize: 10, color: 'var(--ink-3)' }}>{f.complexity}</span>
        {f.mismatch && <span style={{ marginLeft: 'auto', color: 'var(--mag)', fontSize: 10 }} title="frontmatter mismatch">⚑</span>}
        {f.stale && <span style={{ marginLeft: 'auto', color: 'var(--warn)', fontSize: 10 }} title="stale">◷</span>}
      </div>
      <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--ink-0)', lineHeight: 1.25,
        overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
        {f.title}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <StatusPill status={f.effective} />
        <span className="mono" style={{ fontSize: 10, color: 'var(--ink-3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{f.slug}</span>
      </div>
    </div>
  );
}

function LaneCell({ children, color }) {
  return (
    <div style={{
      padding: '10px 10px',
      borderRight: '1px solid var(--line-1)',
      display: 'flex', flexDirection: 'column', gap: 6,
      justifyContent: 'center',
      minWidth: 0,
    }}>
      {children}
    </div>
  );
}

function DocChip({ doc, color, label, title, onOpen }) {
  const tok = STATUS_TOKENS[doc.status] || { color: 'var(--ink-2)', label: doc.status };
  const mutedBg = doc.status === 'completed' || doc.status === 'superseded';
  const displayTitle = title || doc.title || (doc.path || '').split('/').pop();
  return (
    <button
      onClick={onOpen}
      title={doc.path}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '5px 9px',
        borderRadius: 5,
        background: mutedBg
          ? `color-mix(in oklab, ${color} 6%, var(--bg-2))`
          : `linear-gradient(180deg, color-mix(in oklab, ${color} 18%, var(--bg-2)), color-mix(in oklab, ${color} 10%, var(--bg-2)))`,
        border: `1px solid color-mix(in oklab, ${color} 35%, var(--line-1))`,
        color: 'var(--ink-0)',
        cursor: 'pointer',
        fontFamily: 'inherit',
        textAlign: 'left',
        minWidth: 0,
        opacity: doc.status === 'superseded' ? 0.5 : 1,
      }}>
      <span className="mono caps" style={{ fontSize: 9, color, letterSpacing: 0.08 + 'em', flexShrink: 0 }}>{label}</span>
      <span style={{ fontSize: 11, color: 'var(--ink-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1, minWidth: 0 }}>
        {displayTitle}
      </span>
      <span className="dot" style={{ background: tok.color, flexShrink: 0 }} />
    </button>
  );
}

function EmptyDash() {
  return <span style={{ fontSize: 14, color: 'var(--ink-4)', textAlign: 'center', letterSpacing: 4 }}>—</span>;
}

function PhaseStackInline({ phases, onOpen }) {
  return (
    <button onClick={onOpen} style={{
      display: 'flex', alignItems: 'center', gap: 4,
      padding: '5px 8px',
      background: 'var(--bg-2)',
      border: '1px solid color-mix(in oklab, var(--prog) 35%, var(--line-1))',
      borderRadius: 5,
      cursor: 'pointer',
      fontFamily: 'inherit',
    }}>
      {phases.map(p => <PhaseDot key={p.n} phase={p} />)}
      <span className="mono" style={{ fontSize: 9.5, color: 'var(--ink-3)', marginLeft: 4 }}>
        {phases.filter(p => p.status === 'completed').length}/{phases.length}
      </span>
    </button>
  );
}

function PhaseDot({ phase }) {
  const status = phase.status;
  const color = (STATUS_TOKENS[status] || {}).color || 'var(--ink-3)';
  const filled = status === 'completed';
  const bordered = status === 'in-progress';
  const blocked = status === 'blocked';
  return (
    <div title={`Phase ${phase.n}: ${phase.name} (${phase.progress}%)`} style={{
      width: 14, height: 14, borderRadius: 3,
      background: filled ? color : 'transparent',
      border: `1.5px solid ${color}`,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 8.5, fontFamily: 'var(--mono)',
      color: filled ? 'var(--bg-0)' : color,
      position: 'relative',
    }}>
      {filled ? '✓' : blocked ? '!' : phase.n}
      {bordered && (
        <span style={{
          position: 'absolute', inset: -3,
          borderRadius: 5,
          border: `1.5px solid color-mix(in oklab, ${color} 50%, transparent)`,
          animation: 'pulse-ring 1.8s infinite',
        }} />
      )}
    </div>
  );
}

function TotalsCell({ feature }) {
  const { rollupFeature, MODELS } = window.APP_DATA;
  const r = rollupFeature(feature);
  if (r.taskCount === 0) return <EmptyDash />;
  const fmt = (n) => n >= 1000 ? `${(n / 1000).toFixed(n < 10000 ? 1 : 0)}k` : String(n);
  const total = r.tokens;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5, padding: '2px 4px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span className="mono tnum" style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink-0)' }}>{r.points}</span>
        <span className="caps" style={{ fontSize: 9, color: 'var(--ink-3)' }}>pts</span>
        <span className="mono tnum" title={`${total.toLocaleString()} tokens`}
              style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--ink-1)' }}>
          {fmt(total)}
        </span>
      </div>
      {/* Stacked model bar */}
      {total > 0 && (
        <div style={{ display: 'flex', height: 6, borderRadius: 2, overflow: 'hidden', background: 'var(--bg-3)' }}>
          {['opus', 'sonnet', 'haiku'].map(m => {
            const pct = total > 0 ? (r.tokensByModel[m] / total) * 100 : 0;
            if (pct === 0) return null;
            return <div key={m} title={`${MODELS[m].label}: ${r.tokensByModel[m].toLocaleString()}`}
              style={{ width: `${pct}%`, background: MODELS[m].color }} />;
          })}
        </div>
      )}
      <div style={{ display: 'flex', gap: 4 }}>
        {['opus', 'sonnet', 'haiku'].map(m => r.tokensByModel[m] > 0 && (
          <span key={m} className="mono" style={{ fontSize: 9, color: MODELS[m].color }}>
            <span className="dot" style={{ background: MODELS[m].color, marginRight: 3 }} />
            {fmt(r.tokensByModel[m])}
          </span>
        ))}
      </div>
    </div>
  );
}

Object.assign(window, { PlanningGraph, PhaseDot, TotalsCell });
