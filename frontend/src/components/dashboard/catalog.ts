import { z } from 'zod';

/**
 * Synod Dashboard Catalog
 * Defines the strict, Zod-validated vocabulary of components that the
 * backend (or an LLM) can emit via json-render.
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

// ─── Catalog Definition ──────────────────────────────────────────────────

export const catalog = {
  MetricCard: MetricCardSchema,
  RankBar: RankBarSchema,
  TokenTable: TokenTableSchema,
  SourceList: SourceListSchema,
};
