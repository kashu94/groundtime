// Sign-in backdrop: a departure lounge at dusk. Tall windows onto the apron, an aircraft at
// the gate, a departures board with one flight running late, and the seats people wait in.
// Plain SVG and CSS; animation stops under prefers-reduced-motion.

/** The departures board: flight, destination, time, status. Fixed, so the server and the
 * browser draw the same. */
const BOARD = [
  ["KS434", "BENGALURU", "14:20", "DELAYED 18:20"],
  ["DX211", "MUMBAI", "14:45", "BOARDING"],
  ["NG508", "CHENNAI", "15:10", "ON TIME"],
  ["DX318", "NEW DELHI", "15:35", "ON TIME"],
  ["KS612", "KOCHI", "16:05", "ON TIME"],
] as const;

const MULLIONS = [0, 1, 2, 3, 4, 5, 6];
const PANE = 100;

/** Rows of lounge seats, back to front: y, seat count, scale. */
const SEATS = [
  [662, 9, 0.8],
  [712, 8, 1],
] as const;

export function TerminalAtDusk() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <svg viewBox="0 0 600 800" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full">
        <defs>
          <linearGradient id="dusk" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#0b1b3a" />
            <stop offset="0.45" stopColor="#3b3a6b" />
            <stop offset="0.72" stopColor="#c0627a" />
            <stop offset="0.9" stopColor="#f2a65a" />
            <stop offset="1" stopColor="#f7c77e" />
          </linearGradient>
          <radialGradient id="sun" cx="0.72" cy="0.95" r="0.45">
            <stop offset="0" stopColor="#ffd8a0" stopOpacity="0.85" />
            <stop offset="1" stopColor="#ffd8a0" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="hall" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#070d1c" />
            <stop offset="1" stopColor="#0d1629" />
          </linearGradient>
          <linearGradient id="floor" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#1a2238" />
            <stop offset="1" stopColor="#05080f" />
          </linearGradient>
          <linearGradient id="reflection" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#f2a65a" stopOpacity="0.28" />
            <stop offset="1" stopColor="#f2a65a" stopOpacity="0" />
          </linearGradient>
          <filter id="soft" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2" />
          </filter>
        </defs>

        {/* The hall, and the sky through its windows. */}
        <rect width="600" height="800" fill="url(#hall)" />
        <rect x="0" y="250" width="600" height="380" fill="url(#dusk)" />
        <rect x="0" y="250" width="600" height="380" fill="url(#sun)" className="dusk-glow" />

        {/* Far side of the apron: the horizon, a control tower, runway lights. */}
        <rect x="0" y="560" width="600" height="70" fill="#1b2140" opacity="0.85" />
        <g fill="#141a33">
          <rect x="96" y="500" width="10" height="60" />
          <rect x="86" y="488" width="30" height="16" rx="3" />
          <rect x="92" y="482" width="18" height="7" />
        </g>
        <circle cx="101" cy="480" r="1.6" fill="#ff6b6b" className="board-delayed" />
        {Array.from({ length: 22 }, (_, i) => (
          <circle key={i} cx={20 + i * 27} cy={566} r={1.1} fill="#ffe2a8" opacity={0.75} />
        ))}

        {/* A flight climbing out in the distance. */}
        <g className="takeoff" opacity="0">
          <path d="M120 470 l26 -4 l6 -6 l3 1 l-3 5 l12 -2 l3 2 l-14 4 l-3 7 l-3 0 l1 -6 l-24 3 z" fill="#1d2444" />
          <circle cx="120" cy="470" r="1.4" fill="#fff4cc" />
        </g>

        {/* The aircraft at the gate, and the jet bridge reaching it. */}
        <g>
          <path
            d="M250 585 C 250 566, 270 556, 300 556 L 560 556 C 585 556, 600 566, 600 580 L 600 600 L 270 600 C 258 600, 250 594, 250 585 Z"
            fill="#e9edf5"
          />
          <path d="M250 585 C 250 574, 258 566, 270 563 L 282 563 L 282 584 Z" fill="#26324d" opacity="0.85" />
          <rect x="300" y="568" width="300" height="3" fill="#ea580c" opacity="0.9" />
          {Array.from({ length: 16 }, (_, i) => (
            <rect key={i} x={312 + i * 17} y={575} width={7} height={6} rx={2} fill="#3b4a6b" />
          ))}
          <path d="M380 600 L 470 640 L 500 640 L 450 600 Z" fill="#cfd6e3" />
          <ellipse cx="440" cy="612" rx="22" ry="9" fill="#b8c1d1" />
          <rect x="296" y="600" width="4" height="22" fill="#2a3045" />
          <rect x="520" y="600" width="5" height="22" fill="#2a3045" />
          <circle cx="298" cy="624" r="5" fill="#0d111c" />
          <circle cx="522" cy="624" r="6" fill="#0d111c" />
        </g>
        <path d="M0 540 L 212 552 L 212 590 L 0 600 Z" fill="#2a3552" />
        <path d="M212 552 L 252 556 L 252 588 L 212 590 Z" fill="#334063" />
        {[30, 70, 110, 150, 190].map((x) => (
          <rect key={x} x={x} y={556} width={10} height={6} rx={1.5} fill="#ffd9a0" opacity={0.7} />
        ))}
        <rect x="150" y="598" width="8" height="32" fill="#1c2438" />

        {/* Window frame: tall panes, a transom, and the glare on the glass. */}
        <g fill="#0a1222">
          {MULLIONS.map((i) => (
            <rect key={i} x={i * PANE - 4} y="250" width="8" height="380" />
          ))}
          <rect x="0" y="246" width="600" height="10" />
          <rect x="0" y="408" width="600" height="5" opacity="0.8" />
          <rect x="0" y="626" width="600" height="8" />
        </g>
        <path d="M120 256 L 170 256 L 90 630 L 40 630 Z" fill="#ffffff" opacity="0.04" />
        <path d="M340 256 L 360 256 L 300 630 L 280 630 Z" fill="#ffffff" opacity="0.035" />

        {/* Ceiling and its lights. */}
        <path d="M0 0 L 600 0 L 600 246 L 0 246 Z" fill="#070c19" />
        {[60, 180, 300, 420, 540].map((x) => (
          <g key={x}>
            <rect x={x - 22} y={34} width={44} height={4} rx={2} fill="#fff1d6" opacity={0.85} />
            <ellipse cx={x} cy={44} rx={60} ry={14} fill="#fff1d6" opacity={0.05} filter="url(#soft)" />
          </g>
        ))}

        {/* The departures board, hanging right of centre so the words on the left stay clear. */}
        <g transform="translate(262 82)">
          <rect x="146" y="-30" width="3" height="30" fill="#1f2a40" />
          <rect x="0" y="0" width="300" height="150" rx="6" fill="#05070d" stroke="#1f2a40" strokeWidth="2" />
          <text x="14" y="22" fill="#ffd166" fontSize="11" fontWeight="700" letterSpacing="2" fontFamily="ui-monospace, monospace">
            DEPARTURES
          </text>
          {BOARD.map(([flight, to, time, status], i) => (
            <g key={flight} transform={`translate(14 ${44 + i * 22})`} fontFamily="ui-monospace, monospace" fontSize="10">
              <rect x="-6" y="-12" width="284" height="18" rx="2" fill="#0d1220" />
              <text x="0" y="0" fill="#e6edf7">
                {flight}
              </text>
              <text x="48" y="0" fill="#e6edf7">
                {to}
              </text>
              <text x="130" y="0" fill="#9fb0c8">
                {time}
              </text>
              <text
                x="170"
                y="0"
                fill={status.startsWith("DELAYED") ? "#ffb020" : status === "BOARDING" ? "#5ee0a0" : "#7dd3fc"}
                className={status.startsWith("DELAYED") ? "board-delayed" : undefined}
              >
                {status}
              </text>
            </g>
          ))}
        </g>

        {/* The floor, with the dusk reflected in it. */}
        <rect x="0" y="634" width="600" height="166" fill="url(#floor)" />
        <rect x="0" y="634" width="600" height="110" fill="url(#reflection)" />

        {/* Lounge seats in silhouette. */}
        {SEATS.map(([y, count, s]) => (
          <g key={y} fill="#03060c">
            {Array.from({ length: count }, (_, i) => {
              const x = 18 + i * 70 * s;
              return (
                <g key={i}>
                  <rect x={x} y={y - 26 * s} width={52 * s} height={22 * s} rx={5 * s} />
                  <rect x={x - 2 * s} y={y - 6 * s} width={56 * s} height={9 * s} rx={3 * s} />
                  <rect x={x + 24 * s} y={y + 3 * s} width={4 * s} height={14 * s} />
                </g>
              );
            })}
            <rect x="0" y={y + 16 * s} width="600" height={4 * s} opacity={0.6} />
          </g>
        ))}
      </svg>

      {/* Legibility: darker where the text sits, and a soft vignette. */}
      <div className="absolute inset-0 bg-[linear-gradient(100deg,rgba(3,8,20,0.82)_0%,rgba(3,8,20,0.5)_42%,rgba(3,8,20,0.08)_100%)]" />
      <div className="absolute inset-x-0 bottom-0 h-1/2 bg-[linear-gradient(0deg,rgba(3,8,20,0.75),transparent)]" />
      <div className="absolute inset-0 shadow-[inset_0_0_160px_rgba(0,0,0,0.55)]" />
    </div>
  );
}
