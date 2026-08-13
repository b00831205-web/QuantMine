/**
 * Effect size as colour, so "significant" stops reading as "good".
 *
 * Significance and magnitude answer different questions. With ~2900 daily IC
 * observations the standard error is tiny, so a mean IC of 0.9% still lands
 * 4.4 standard errors from zero -- reliably non-zero, and reliably too small to
 * trade. A binary chip collapses both into one word, and in practice readers
 * take that word as a verdict on the factor.
 *
 * The chip therefore keeps saying "significant" -- that is what was tested and
 * it is true -- but its colour carries the size: neutral grey at an IC of zero,
 * full accent blue at ``STRONG_IC`` and above. A weak-but-significant factor
 * looks weak at a glance, without anyone having to read a second column.
 */

/**
 * Mean |IC| treated as a strong factor, the point where the ramp saturates.
 *
 * 0.05 is the conventional bar in equity factor research rather than anything
 * derived from this dataset; it is surfaced in the table header so the rule is
 * visible instead of hidden in a colour.
 */
export const STRONG_IC = 0.05;

/**
 * Blend between neutral and accent by |IC| / STRONG_IC.
 *
 * Mixed in CSS rather than computed as hex so both endpoints stay design tokens
 * and follow the active theme. oklab keeps the midpoints perceptually even; a
 * plain sRGB mix passes through a muddy band that reads as a third category.
 */
export const effectSizeColor = (icMean: number | null | undefined): string => {
  if (icMean === null || icMean === undefined || Number.isNaN(icMean)) {
    return 'var(--text-muted)';
  }
  const strength = Math.min(Math.abs(icMean) / STRONG_IC, 1);
  return `color-mix(in oklab, var(--accent) ${Math.round(strength * 100)}%, var(--text-muted))`;
};
