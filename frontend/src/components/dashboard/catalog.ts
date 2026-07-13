import { z } from 'zod';

/**
 * Synod Dashboard Catalog
 * Defines the strict, Zod-validated vocabulary of components that the
 * backend (or an LLM) can emit via json-render.
 *
 * PRD §11.3 enumerates exactly 6 allowed widget types:
 *   MetricCard, RankBar, LatencyChart, CostGauge, TokenTable, SourceList.
 * No color prop is exposed in any schema — all styling is B&W only.
 * This catalog is the frontend mirror of the Pydantic models in
 * dashboard_builder_node.py (_PROP_MODELS dict).
 */

// ─── Component Schemas ───────────────────────────────────────────────────

export const MetricCardSchema = z.object({
  label: z.string(),
  value: z.union([z.string(), z.number()]),
  unit: z.string().optional(),
  description: z.string().optional(),
});

export const RankBarSchema = z.object({
  label: z.string(),
  score: z.number(),
  maxScore: z.number(),
});

export const TokenTableSchema = z.object({
  members: z.array(
    z.object({
      label: z.string(),
      tokensIn: z.number(),
      tokensOut: z.number(),
      costUsd: z.number(),
    })
  ),
});

export const SourceListSchema = z.object({
  sources: z.array(
    z.object({
      url: z.string().optional(),
      title: z.string(),
      snippet: z.string().optional(),
    })
  ),
});

/**
 * LatencyChart — horizontal bar chart showing per-member latency.
 * PRD §11.3 named widget type. Renders as a ranked list of bars (greyscale).
 * No color prop — fill is always --grey-0.
 */
export const LatencyChartSchema = z.object({
  members: z.array(
    z.object({
      label: z.string(),
      latencyMs: z.number(),
    })
  ),
  unit: z.string().optional(), // defaults to "ms"
});

/**
 * CostGauge — a single-value gauge showing cumulative session cost.
 * PRD §11.3 named widget type. Renders as a MetricCard-style display
 * with an optional budget ceiling fill bar (greyscale only).
 * No color prop — threshold is communicated via border weight.
 */
export const CostGaugeSchema = z.object({
  label: z.string(),
  costUsd: z.number(),
  budgetUsd: z.number().optional(), // if set, renders a capacity bar
  description: z.string().optional(),
});

// ─── Catalog Definition ──────────────────────────────────────────────────

export const catalog = {
  MetricCard:    MetricCardSchema,
  RankBar:       RankBarSchema,
  LatencyChart:  LatencyChartSchema,
  CostGauge:     CostGaugeSchema,
  TokenTable:    TokenTableSchema,
  SourceList:    SourceListSchema,
};
