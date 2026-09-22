// Derive display facts from REAL artifacts only: the model card markdown returned
// by /about and the /races list. Never asserts a metric the artifacts do not
// support: if a claim cannot be parsed, it is simply omitted.

export function raceCount(races, season) {
  if (!Array.isArray(races)) return null;
  return races.filter((r) => r.season === season).length || null;
}

export function parseModelCardFacts(cardText) {
  const out = { trained: null, heldOut: null, beats2026: null };
  if (!cardText || typeof cardText !== "string") return out;

  const trained = cardText.match(/Trained on:\s*\[([^\]]+)\]/);
  if (trained) {
    const yrs = trained[1].split(",").map((s) => s.trim());
    if (yrs.length) out.trained = `${yrs[0]} to ${yrs[yrs.length - 1]}`;
  }
  const held = cardText.match(/Evaluated \(held out\) on:\s*\[([^\]]+)\]/);
  if (held) out.heldOut = held[1].split(",").map((s) => s.trim()).join(", ");

  // Only the completed-2026 walk-forward pre-qualifying verdict, which is the
  // fair comparison for predictions published before qualifying.
  const m = cardText.match(
    /completed \[2026\][\s\S]*?Beats pre-qualifying baselines:\s*(YES|NOT YET)\**\s*\(pipeline spearman\s*([\d.]+)\s*vs strongest baseline[^)]*?([\d.]+)\)/
  );
  const races2026 = cardText.match(
    /completed \[2026\][\s\S]*?Full pipeline \(predicted grid\)\s*\|\s*(\d+)\s*\|/
  );
  if (m) {
    out.beats2026 = {
      verdict: m[1],
      pipeline: m[2],
      baseline: m[3],
      races: races2026 ? Number(races2026[1]) : null,
    };
  }
  return out;
}
