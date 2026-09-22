import { useEffect, useRef, useState } from "react";

const reduce = () =>
  typeof window !== "undefined" &&
  window.matchMedia &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Animate a number from 0 to `target` with requestAnimationFrame. Respects
// prefers-reduced-motion (jumps straight to the value). No external library.
export function useCountUp(target, { duration = 900, decimals = 1 } = {}) {
  const [val, setVal] = useState(reduce() ? target : 0);
  const raf = useRef(0);
  useEffect(() => {
    if (reduce()) { setVal(target); return; }
    const start = performance.now();
    const from = 0;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
      setVal(from + (target - from) * eased);
      if (t < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [target, duration]);
  return Number(val).toFixed(decimals);
}
