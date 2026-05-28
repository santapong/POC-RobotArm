/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Inter Tight"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 1px)",
        sm: "calc(var(--radius) - 1px)",
      },
      colors: {
        // shadcn tokens (HSL vars)
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        popover: { DEFAULT: "hsl(var(--popover))", foreground: "hsl(var(--popover-foreground))" },
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        destructive: { DEFAULT: "hsl(var(--destructive))", foreground: "hsl(var(--destructive-foreground))" },
        // shadcn border/input/ring share the ARC palette (raw vars, not hsl-wrapped)
        border: "var(--border)",
        input: "var(--border-2)",
        ring: "var(--ok)",
        // ARC·OPS mission-control tokens
        bg: "var(--bg)",
        "bg-1": "var(--bg-1)",
        "bg-2": "var(--bg-2)",
        panel: "var(--panel)",
        "panel-2": "var(--panel-2)",
        fg: "var(--fg)",
        "fg-mute": "var(--fg-mute)",
        dim: "var(--dim)",
        off: "var(--off)",
        "border-2": "var(--border-2)",
        track: "var(--track)",
        ok: "var(--ok)",
        info: "var(--info)",
        warn: "var(--warn)",
        err: "var(--err)",
        magenta: "var(--magenta)",
      },
    },
  },
  plugins: [],
};
