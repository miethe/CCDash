// Small reusable components: icons, status pills, artifact chips, tiles.

const Icon = ({ d, size = 14, stroke = 1.6, className = '', style = {} }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round"
    className={className} style={style} aria-hidden="true">
    {d}
  </svg>
);

// Tiny lucide-style icons inlined so we don't depend on a library
const Icons = {
  graph:    <Icon d={<><circle cx="6" cy="6" r="2.2"/><circle cx="18" cy="6" r="2.2"/><circle cx="12" cy="18" r="2.2"/><path d="M7.6 7.4l3 9"/><path d="M16.4 7.4l-3 9"/></>} />,
  inbox:    <Icon d={<><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></>} />,
  search:   <Icon d={<><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></>} />,
  settings: <Icon d={<><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></>} />,
  layers:   <Icon d={<><path d="M12 2 2 7l10 5 10-5-10-5z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/></>} />,
  spark:    <Icon d={<><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></>} />,
  play:     <Icon d={<><polygon points="6 3 20 12 6 21 6 3"/></>} />,
  pause:    <Icon d={<><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></>} />,
  chevron:  <Icon d={<><polyline points="9 18 15 12 9 6"/></>} />,
  down:     <Icon d={<><polyline points="6 9 12 15 18 9"/></>} />,
  up:       <Icon d={<><polyline points="18 15 12 9 6 15"/></>} />,
  x:        <Icon d={<><path d="M18 6 6 18M6 6l12 12"/></>} />,
  check:    <Icon d={<><polyline points="20 6 9 17 4 12"/></>} />,
  dot:      <Icon d={<><circle cx="12" cy="12" r="4" fill="currentColor"/></>} />,
  git:      <Icon d={<><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M6 21V9a9 9 0 0 0 9 9"/></>} />,
  alert:    <Icon d={<><path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4M12 17h0"/></>} />,
  clock:    <Icon d={<><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></>} />,
  file:     <Icon d={<><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></>} />,
  flow:     <Icon d={<><path d="M3 6h18M3 12h18M3 18h18"/></>} />,
  bolt:     <Icon d={<><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></>} />,
  brain:    <Icon d={<><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24A2.5 2.5 0 0 1 6.5 4 2.5 2.5 0 0 1 9.5 2Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24A2.5 2.5 0 0 0 17.5 4 2.5 2.5 0 0 0 14.5 2Z"/></>} />,
  zap:      <Icon d={<><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></>} />,
  plus:     <Icon d={<><path d="M12 5v14M5 12h14"/></>} />,
  filter:   <Icon d={<><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></>} />,
  arrow:    <Icon d={<><path d="M5 12h14M13 5l7 7-7 7"/></>} />,
  refresh:  <Icon d={<><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/></>} />,
};

// Status → token. Raw status system.
const STATUS_TOKENS = {
  idea:        { color: 'var(--ink-2)', label: 'idea' },
  shaping:     { color: 'var(--info)',  label: 'shaping' },
  ready:       { color: 'var(--spec)',  label: 'ready' },
  draft:       { color: 'var(--ink-2)', label: 'draft' },
  approved:    { color: 'var(--prd)',   label: 'approved' },
  'in-progress': { color: 'var(--plan)', label: 'in-progress' },
  in_progress: { color: 'var(--plan)',  label: 'in-progress' },
  blocked:     { color: 'var(--err)',   label: 'blocked' },
  completed:   { color: 'var(--ok)',    label: 'completed' },
  superseded:  { color: 'var(--ink-3)', label: 'superseded' },
  future:      { color: 'var(--ink-3)', label: 'future' },
  deprecated:  { color: 'var(--ink-3)', label: 'deprecated' },
};

function StatusPill({ status, size = 'sm' }) {
  const t = STATUS_TOKENS[status] || { color: 'var(--ink-2)', label: status };
  const pad = size === 'md' ? '3px 8px' : '2px 6px';
  return (
    <span className="pill tnum" style={{
      background: `color-mix(in oklab, ${t.color} 15%, transparent)`,
      color: t.color,
      border: `1px solid color-mix(in oklab, ${t.color} 30%, transparent)`,
      padding: pad,
    }}>
      <span className="dot" style={{ background: t.color }} />
      {t.label}
    </span>
  );
}

function ArtifactChip({ kind, size = 'sm', onClick, active }) {
  const a = window.APP_DATA.ARTIFACTS[kind];
  if (!a) return null;
  const s = size === 'md' ? { padding: '4px 10px', fontSize: 11.5 } : { padding: '2px 8px', fontSize: 10.5 };
  return (
    <button
      className="chip mono"
      onClick={onClick}
      style={{
        ...s,
        background: active ? `color-mix(in oklab, ${a.color} 22%, var(--bg-2))` : `color-mix(in oklab, ${a.color} 10%, var(--bg-2))`,
        borderColor: `color-mix(in oklab, ${a.color} 35%, var(--line-1))`,
        color: `color-mix(in oklab, ${a.color} 90%, white)`,
        cursor: onClick ? 'pointer' : 'default',
      }}>
      <span style={{ color: a.color, fontSize: 10 }}>{a.glyph}</span>
      {a.short}
    </button>
  );
}

function MetricTile({ label, value, sub, accent, big }) {
  const color = accent || 'var(--ink-0)';
  return (
    <div className="tile" style={{ padding: big ? '18px 20px' : '12px 14px', display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div className="caps" style={{ fontSize: 10, color: 'var(--ink-3)' }}>{label}</div>
      <div className="tnum" style={{
        fontFamily: 'var(--sans)',
        fontWeight: 600,
        fontSize: big ? 34 : 22,
        letterSpacing: '-0.02em',
        lineHeight: 1,
        color,
      }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 11, color: 'var(--ink-3)' }}>{sub}</div>}
    </div>
  );
}

function SectionHeader({ eyebrow, title, children, glyph }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, marginBottom: 14 }}>
      <div>
        {eyebrow && <div className="caps" style={{ fontSize: 10, color: 'var(--ink-3)', marginBottom: 6 }}>{eyebrow}</div>}
        <h2 className="serif" style={{ margin: 0, fontSize: 22, letterSpacing: '-0.01em', fontWeight: 500, color: 'var(--ink-0)' }}>
          {glyph && <span style={{ marginRight: 8, color: 'var(--brand)' }}>{glyph}</span>}
          {title}
        </h2>
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>{children}</div>
    </div>
  );
}

function Spark({ data, color = 'var(--brand)', w = 80, h = 22 }) {
  const max = Math.max(...data, 1);
  const stepX = w / (data.length - 1);
  const pts = data.map((v, i) => `${(i * stepX).toFixed(1)},${(h - (v / max) * (h - 2) - 1).toFixed(1)}`).join(' ');
  return (
    <svg width={w} height={h}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

Object.assign(window, { Icon, Icons, StatusPill, ArtifactChip, MetricTile, SectionHeader, Spark });
