// Formatting functions for Eval scores and metrics

export function fmtScore(s) {
  if (s === null || s === undefined) return '—'
  return s.toFixed(3)
}

export function fmtDelta(d) {
  if (d === null || d === undefined) return '—'
  return (d >= 0 ? '+' : '') + d.toFixed(3)
}

export function fmtQuality(q) {
  if (q === null || q === undefined) return '—'
  return q.toFixed(1)
}

export function fmtDeltaQuality(d) {
  if (d === null || d === undefined) return ''
  return (d >= 0 ? '+' : '') + d.toFixed(1)
}

export function fmtPct(p) {
  if (p === null || p === undefined) return '—'
  return (p * 100).toFixed(0) + '%'
}

export function scoreColor(score) {
  if (score === null || score === undefined) return ''
  if (score >= 0.85) return 'score-green'
  if (score >= 0.80) return 'score-yellow'
  return 'score-red'
}

export function deltaColor(delta) {
  if (delta === null || delta === undefined) return ''
  if (delta > 0.001) return 'score-green'
  if (delta < -0.001) return 'score-red'
  return 'score-muted'
}

export function qualityColor(q) {
  if (q === null || q === undefined) return 'score-muted'
  if (q >= 70) return 'score-green'
  if (q >= 55) return 'score-yellow'
  return 'score-red'
}

export function deltaQualityColor(d) {
  if (d === null || d === undefined) return ''
  if (d > 0.5) return 'score-green'
  if (d < -0.5) return 'score-red'
  return 'score-muted'
}