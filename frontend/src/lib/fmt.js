export const usd = (v, digits = 0) =>
  `$${Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;

export const ethFmt = (v, digits = 4) =>
  `${Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })} ETH`;

export const ethExact = (v) =>
  `${Number(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 8 })} ETH`;

export const dt = (iso) => (iso ? new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) : "—");

export const short = (s, n = 8) => (s ? `${s.slice(0, n + 2)}…${s.slice(-n)}` : "—");

export const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, " ") : "");
