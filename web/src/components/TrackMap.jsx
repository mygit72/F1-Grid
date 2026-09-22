import { useRef, useState, useLayoutEffect } from "react";
import { motion } from "framer-motion";

// A generic, invented circuit outline - NOT a real F1 track's geometry. This
// is deliberate: tracing an actual circuit (Silverstone, Monza, etc.) would
// edge toward reproducing licensed broadcast/track IP. The shape just needs
// to *read* as "a circuit" so dots moving around it feel like a race.
const TRACK_PATH =
  "M 60 220 C 60 120 140 60 260 60 C 360 60 380 110 360 150 " +
  "C 345 180 300 175 290 200 C 280 230 330 240 380 230 " +
  "C 460 215 480 150 540 150 C 600 150 620 200 600 240 " +
  "C 580 280 500 270 460 290 C 400 320 380 360 300 360 " +
  "C 180 360 60 320 60 220 Z";

const TEAM_COLORS = {
  RBR: "#3671C6", FER: "#F91536", MER: "#27F4D2", MCL: "#FF8000",
  AST: "#229971", ALP: "#2293D1", WIL: "#37BEDD", HAA: "#B6BABD",
  SAU: "#52E252", RB: "#6692FF",
};
const teamColor = (team) => TEAM_COLORS[team] ?? "#7C8794";

/**
 * Renders driver dots spaced around a generic loop in finishing-order, with
 * the leader furthest along - a stylized "where they'd be on track" cue, not
 * a literal lap simulation. Dots animate to new spots when predictions change.
 */
export default function TrackMap({ predictions, highlightDriver }) {
  const pathRef = useRef(null);
  const [pathLen, setPathLen] = useState(0);

  useLayoutEffect(() => {
    if (pathRef.current) setPathLen(pathRef.current.getTotalLength());
  }, []);

  const sorted = [...predictions].sort(
    (a, b) => a.predicted_position - b.predicted_position
  );
  const n = sorted.length || 1;

  const pointAtFraction = (t) => {
    if (!pathRef.current || !pathLen) return null;
    const pt = pathRef.current.getPointAtLength(pathLen * t);
    return { x: pt.x, y: pt.y };
  };

  return (
    <div className="panel" style={{ padding: 16 }}>
      <svg viewBox="0 0 660 400" style={{ display: "block", width: "100%", height: "auto" }}>
        {/* engineering-tool backdrop: faint gridlines + axis ticks with mono labels */}
        <g aria-hidden="true">
          {[0, 132, 264, 396, 528, 660].map((x) => (
            <line key={`v${x}`} className="gridline" x1={x} y1={16} x2={x} y2={384} />
          ))}
          {[16, 108, 200, 292, 384].map((y) => (
            <line key={`h${y}`} className="gridline" x1={8} y1={y} x2={652} y2={y} />
          ))}
          {[0, 132, 264, 396, 528, 660].map((x) => (
            <text key={`vt${x}`} className="axis-label" x={x + 2} y={397}>{x}</text>
          ))}
          {[108, 200, 292].map((y) => (
            <text key={`ht${y}`} className="axis-label" x={2} y={y - 3}>{400 - y}</text>
          ))}
          <text className="axis-label" x={594} y={12}>X / Y (px)</text>
        </g>
        <path
          ref={pathRef}
          d={TRACK_PATH}
          fill="none"
          stroke="var(--line)"
          strokeWidth={14}
          strokeLinecap="round"
        />
        <path
          d={TRACK_PATH}
          fill="none"
          stroke="#000"
          strokeOpacity={0.25}
          strokeWidth={2}
          strokeDasharray="6 10"
        />
        {pathLen > 0 &&
          sorted.map((p, i) => {
            const t = 1 - i / n;
            const point = pointAtFraction(t);
            if (!point) return null;
            const isHi = highlightDriver === p.driver;
            return (
              <g key={p.driver}>
                <motion.circle
                  cx={point.x}
                  cy={point.y}
                  initial={{ cx: point.x, cy: point.y }}
                  animate={{ cx: point.x, cy: point.y }}
                  transition={{ type: "spring", stiffness: 120, damping: 20 }}
                  r={isHi ? 9 : 6}
                  fill={teamColor(p.team)}
                  stroke={isHi ? "var(--telemetry)" : "#05070a"}
                  strokeWidth={isHi ? 2.5 : 1.5}
                />
                {(i === 0 || isHi) && (
                  <motion.text
                    x={point.x}
                    y={point.y - 12}
                    initial={{ x: point.x, y: point.y - 12 }}
                    animate={{ x: point.x, y: point.y - 12 }}
                    transition={{ type: "spring", stiffness: 120, damping: 20 }}
                    textAnchor="middle"
                    className="mono"
                    fontSize="10"
                    fill="var(--text)"
                  >
                    {p.driver}
                  </motion.text>
                )}
              </g>
            );
          })}
      </svg>
      <p style={{ color: "var(--muted)", fontSize: "0.72rem", marginTop: 6 }}>
        Stylized generic circuit - relative spacing reflects predicted order, not
        a real lap simulation or any specific track's geometry.
      </p>
    </div>
  );
}
