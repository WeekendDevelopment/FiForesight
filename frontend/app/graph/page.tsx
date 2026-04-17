'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';

const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false });

// ── Node / Edge definitions ────────────────────────────────────────────────
type NodeGroup = 'page' | 'component' | 'api' | 'backend' | 'service' | 'external';

interface AppNode {
  id: string;
  label: string;
  group: NodeGroup;
  description?: string;
}

interface AppLink {
  source: string;
  target: string;
  label?: string;
}

const GROUP_COLORS: Record<NodeGroup, string> = {
  page:      '#60a5fa', // blue
  component: '#34d399', // green
  api:       '#f59e0b', // amber
  backend:   '#a78bfa', // purple
  service:   '#f472b6', // pink
  external:  '#94a3b8', // slate
};

const GROUP_LABELS: Record<NodeGroup, string> = {
  page:      'Pages',
  component: 'Components',
  api:       'API Routes',
  backend:   'Backend',
  service:   'Services',
  external:  'External APIs',
};

const NODES: AppNode[] = [
  // ── Pages ───────────────────────────────────────────────────────────────
  { id: 'page_main',      label: 'page.tsx',         group: 'page',      description: 'Main dashboard — ticker search, charts, jury' },
  { id: 'page_graph',     label: 'graph/page.tsx',   group: 'page',      description: 'This graph — app structure visualiser' },
  { id: 'layout',         label: 'layout.tsx',        group: 'page',      description: 'Root layout — New Relic injection, theme' },

  // ── Components ──────────────────────────────────────────────────────────
  { id: 'comp_advanced',  label: 'AdvancedChart',    group: 'component', description: 'TradingView Lightweight Charts (PRO mode)' },
  { id: 'comp_recharts',  label: 'Recharts Charts',  group: 'component', description: 'Classic candlestick / line chart (Recharts)' },
  { id: 'comp_jury',      label: 'AnalystJury',      group: 'component', description: '3-analyst verdict cards (Kimi K2 / Llama / Qwen)' },
  { id: 'comp_forecast',  label: 'ForecastPanel',    group: 'component', description: 'High / low / confidence forecast display' },
  { id: 'comp_news',      label: 'NewsPanel',        group: 'component', description: 'SerpAPI news + trending tickers' },
  { id: 'comp_metrics',   label: 'MetricsBar',       group: 'component', description: 'RSI, PE, market cap, sector, 52w range' },

  // ── Next.js API routes ───────────────────────────────────────────────────
  { id: 'api_predict',    label: '/api/predict',     group: 'api',       description: 'POST proxy → FastAPI /predict' },
  { id: 'api_compare',    label: '/api/compare',     group: 'api',       description: 'GET stub → FastAPI /compare (pending)' },

  // ── FastAPI backend ──────────────────────────────────────────────────────
  { id: 'be_predict',     label: 'POST /predict',    group: 'backend',   description: 'Main forecast endpoint — full pipeline' },
  { id: 'be_health',      label: 'GET /health',      group: 'backend',   description: 'Health check' },
  { id: 'be_debug',       label: 'GET /debug',       group: 'backend',   description: 'Debug / diagnostics' },

  // ── Backend services ─────────────────────────────────────────────────────
  { id: 'svc_yfinance',   label: 'yfinance',         group: 'service',   description: 'OHLCV history, live price, fundamentals' },
  { id: 'svc_influx',     label: 'InfluxDB',         group: 'service',   description: 'Time-series price cache (2Y OHLCV)' },
  { id: 'svc_ensemble',   label: 'Ensemble ML',      group: 'service',   description: 'Prophet + SARIMAX + RandomForest forecast' },
  { id: 'svc_indicators', label: 'Indicators',       group: 'service',   description: 'RSI, MACD, BB, SMA50/200, Support/Resistance' },
  { id: 'svc_rl',         label: 'RL Tracker',       group: 'service',   description: 'MAE tracking, weight blending, accuracy EMA' },

  // ── External APIs ────────────────────────────────────────────────────────
  { id: 'ext_groq',       label: 'Groq API',         group: 'external',  description: 'Llama 4 Scout + Llama 70B + Qwen3 32B' },
  { id: 'ext_serp',       label: 'SerpAPI',          group: 'external',  description: 'Google Finance news + trending tickers' },
  { id: 'ext_newrelic',   label: 'New Relic',        group: 'external',  description: 'APM + browser agent observability' },
];

const LINKS: AppLink[] = [
  // layout wraps pages
  { source: 'layout',        target: 'page_main',      label: 'wraps' },
  { source: 'layout',        target: 'page_graph',     label: 'wraps' },
  { source: 'layout',        target: 'ext_newrelic',   label: 'injects' },

  // main page renders components
  { source: 'page_main',     target: 'comp_advanced',  label: 'renders (PRO mode)' },
  { source: 'page_main',     target: 'comp_recharts',  label: 'renders (CLASSIC)' },
  { source: 'page_main',     target: 'comp_jury',      label: 'renders' },
  { source: 'page_main',     target: 'comp_forecast',  label: 'renders' },
  { source: 'page_main',     target: 'comp_news',      label: 'renders' },
  { source: 'page_main',     target: 'comp_metrics',   label: 'renders' },

  // main page calls api
  { source: 'page_main',     target: 'api_predict',    label: 'POST' },

  // api routes proxy to backend
  { source: 'api_predict',   target: 'be_predict',     label: 'proxies' },
  { source: 'api_compare',   target: 'be_predict',     label: 'stub' },

  // backend pipeline
  { source: 'be_predict',    target: 'svc_yfinance',   label: 'fetch OHLCV' },
  { source: 'be_predict',    target: 'svc_influx',     label: 'cache read/write' },
  { source: 'be_predict',    target: 'svc_ensemble',   label: 'forecast' },
  { source: 'be_predict',    target: 'svc_indicators', label: 'compute' },
  { source: 'be_predict',    target: 'svc_rl',         label: 'track accuracy' },
  { source: 'be_predict',    target: 'ext_groq',       label: 'LLM jury + note' },
  { source: 'be_predict',    target: 'ext_serp',       label: 'news + trending' },

  // yfinance feeds ensemble
  { source: 'svc_yfinance',  target: 'svc_ensemble',   label: 'prices' },
  { source: 'svc_influx',    target: 'svc_ensemble',   label: 'cached prices' },
  { source: 'svc_ensemble',  target: 'svc_rl',         label: 'predictions' },
];

// ── Graph data shape for react-force-graph-2d ────────────────────────────
const graphData = {
  nodes: NODES.map(n => ({ ...n, val: n.group === 'backend' || n.group === 'page' ? 3 : 1.5 })),
  links: LINKS,
};

export default function GraphPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims]             = useState({ w: 800, h: 600 });
  const [hovered, setHovered]       = useState<AppNode | null>(null);
  const [activeGroups, setActive]   = useState<Set<NodeGroup>>(new Set(Object.keys(GROUP_COLORS) as NodeGroup[]));

  useEffect(() => {
    const update = () => {
      if (containerRef.current) {
        setDims({ w: containerRef.current.offsetWidth, h: containerRef.current.offsetHeight });
      }
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  const filtered = {
    nodes: graphData.nodes.filter(n => activeGroups.has(n.group)),
    links: graphData.links.filter(l => {
      const src = graphData.nodes.find(n => n.id === ((l.source as any)?.id ?? l.source));
      const tgt = graphData.nodes.find(n => n.id === ((l.target as any)?.id ?? l.target));
      return src && tgt && activeGroups.has(src.group) && activeGroups.has(tgt.group);
    }),
  };

  const toggleGroup = (g: NodeGroup) => {
    setActive(prev => {
      const next = new Set(prev);
      if (next.has(g)) { if (next.size > 1) next.delete(g); }
      else next.add(g);
      return next;
    });
  };

  return (
    <div style={{ width: '100vw', height: '100vh', background: '#0d1117', display: 'flex', flexDirection: 'column', fontFamily: 'Inter, sans-serif' }}>

      {/* ── Header ── */}
      <div style={{ padding: '12px 20px', borderBottom: '1px solid #21262d', display: 'flex', alignItems: 'center', gap: 16, flexShrink: 0 }}>
        <Link href="/" style={{ color: '#60a5fa', fontSize: 13, textDecoration: 'none', opacity: 0.7 }}>← Dashboard</Link>
        <span style={{ color: '#e6edf3', fontWeight: 700, fontSize: 15, letterSpacing: 0.5 }}>FiForesight — App Graph</span>
        <span style={{ color: '#8b949e', fontSize: 12 }}>{NODES.length} nodes · {LINKS.length} edges</span>

        {/* ── Legend / filter toggles ── */}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {(Object.keys(GROUP_COLORS) as NodeGroup[]).map(g => (
            <button
              key={g}
              onClick={() => toggleGroup(g)}
              style={{
                padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600, cursor: 'pointer',
                border: `1px solid ${GROUP_COLORS[g]}`,
                background: activeGroups.has(g) ? GROUP_COLORS[g] + '22' : 'transparent',
                color: activeGroups.has(g) ? GROUP_COLORS[g] : '#8b949e',
                transition: 'all 0.15s',
              }}
            >
              {GROUP_LABELS[g]}
            </button>
          ))}
        </div>
      </div>

      {/* ── Graph canvas ── */}
      <div ref={containerRef} style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
        <ForceGraph2D
          graphData={filtered}
          width={dims.w}
          height={dims.h}
          backgroundColor="#0d1117"
          nodeLabel={() => ''}
          nodeVal={(n: any) => n.val}
          nodeColor={(n: any) => GROUP_COLORS[n.group as NodeGroup] ?? '#94a3b8'}
          nodeCanvasObject={(node: any, ctx, globalScale) => {
            const r     = Math.sqrt(node.val) * 5;
            const color = GROUP_COLORS[node.group as NodeGroup] ?? '#94a3b8';
            const isHov = hovered?.id === node.id;

            // glow
            if (isHov) {
              ctx.beginPath();
              ctx.arc(node.x, node.y, r + 6, 0, 2 * Math.PI);
              ctx.fillStyle = color + '33';
              ctx.fill();
            }

            // circle
            ctx.beginPath();
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
            ctx.fillStyle = isHov ? color : color + 'cc';
            ctx.fill();
            ctx.strokeStyle = isHov ? '#fff' : color;
            ctx.lineWidth   = isHov ? 1.5 : 0.5;
            ctx.stroke();

            // label
            const fontSize = Math.max(10 / globalScale, 4);
            ctx.font        = `${isHov ? 600 : 400} ${fontSize}px Inter, sans-serif`;
            ctx.fillStyle   = isHov ? '#fff' : '#c9d1d9';
            ctx.textAlign   = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(node.label, node.x, node.y + r + fontSize * 1.1);
          }}
          nodePointerAreaPaint={(node: any, color, ctx) => {
            const r = Math.sqrt(node.val) * 5 + 6;
            ctx.beginPath();
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
            ctx.fillStyle = color;
            ctx.fill();
          }}
          linkColor={() => '#30363d'}
          linkWidth={1}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
          linkDirectionalParticles={1}
          linkDirectionalParticleWidth={1.5}
          linkDirectionalParticleColor={(l: any) => {
            const src = graphData.nodes.find(n => n.id === ((l.source as any)?.id ?? l.source));
            return src ? GROUP_COLORS[src.group as NodeGroup] + '99' : '#60a5fa99';
          }}
          onNodeHover={(node: any) => setHovered(node ?? null)}
          cooldownTicks={120}
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.3}
        />

        {/* ── Hover tooltip ── */}
        {hovered && (
          <div style={{
            position: 'absolute', bottom: 24, left: 24,
            background: '#161b22', border: `1px solid ${GROUP_COLORS[hovered.group]}55`,
            borderRadius: 10, padding: '12px 16px', maxWidth: 280, pointerEvents: 'none',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span style={{ width: 10, height: 10, borderRadius: '50%', background: GROUP_COLORS[hovered.group], display: 'inline-block', flexShrink: 0 }} />
              <span style={{ color: '#e6edf3', fontWeight: 700, fontSize: 13 }}>{hovered.label}</span>
              <span style={{ color: GROUP_COLORS[hovered.group], fontSize: 10, fontWeight: 600, marginLeft: 'auto', textTransform: 'uppercase', letterSpacing: 1 }}>{hovered.group}</span>
            </div>
            {hovered.description && (
              <p style={{ color: '#8b949e', fontSize: 12, margin: 0, lineHeight: 1.5 }}>{hovered.description}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
