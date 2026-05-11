/**
 * Build a single "RunStats" object that <RunSummaryCard> understands.
 * Combines server-side aggregates (avg/quality/deltas — already computed
 * with one SQL GROUP BY) with client-side per-question stats (min/max,
 * by-category breakdown) derived from the results array.
 */
export function computeRunStats(run, results) {
  if (!run || !results) return null

  const scored = results.filter(r => r.top_score !== null && r.top_score !== undefined)
  const scores = scored.map(r => r.top_score)
  const min = scores.length ? Math.min(...scores) : null
  const max = scores.length ? Math.max(...scores) : null

  const byCategory = {}
  for (const r of results) {
    if (!byCategory[r.category]) {
      byCategory[r.category] = { total: 0, scored: 0, sum: 0 }
    }
    byCategory[r.category].total++
    if (r.top_score !== null && r.top_score !== undefined) {
      byCategory[r.category].scored++
      byCategory[r.category].sum += r.top_score
    }
  }

  return {
    quality: run.quality_score,
    avg: run.avg_score,
    typeAcc: run.type_accuracy,
    errorCount: run.error_count ?? 0,
    avgLatency: run.avg_latency_ms,
    deltaQuality: run.delta_quality,
    deltaAvg: run.delta_avg_score,
    deltaTypeAcc: run.delta_type_accuracy,
    previousRunId: run.previous_run_id,
    min,
    max,
    count: scored.length,
    total: results.length,
    byCategory,
  }
}
