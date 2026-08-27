# KrishiMitra Design System — Kisan-first

This is the binding design contract for every screen in KrishiMitra.
It exists because of who uses the app and where:

- **Indian farmers, often first-time smartphone users.** Nothing may depend
  on learned UI conventions. Controls look like what they do; icons are
  literal shapes (a water drop, a bug, a tractor).
- **Outdoors, in direct sunlight, on low-end Android phones.** Contrast and
  size beat subtlety every time. No thin gray text, no small tap targets,
  no heavy animation on weak GPUs.
- **Frequently in Hindi (and 10 other Indian languages).** One font family
  must cover Latin and Devanagari so mixed-language screens do not render in
  mismatched fallbacks.

This is a decision-support tool, not a SaaS dashboard. Every page answers a
question a farmer actually has: What should I grow? When do I water? How much
fertilizer? What is my crop worth at the mandi?

## Hard rules

1. **Zero emoji anywhere.** UI text, icons, labels — none. Icons come only
   from `components/ui/Icons.tsx` (inline SVG, stroke, `currentColor`).
2. **No gradients. No backdrop-filter. No entrance/keyframe animations.**
   Transitions only on hover/focus/active, 150ms or less.
3. **Sunlight contrast.** Body text `#1a1c1a` on white/near-white. Meaningful
   text is never lighter than `#4a4f4a`. Essential numbers and labels are
   never in "muted" gray (`--ink-tertiary` is for metadata only).
4. **Touch.** Interactive elements: min-height 48px. Primary action buttons:
   56px and full-width on mobile. Form inputs: min-height 52px, 17px+ text.
5. **Type scale.** Base font-size 17px. Page titles 26–30px bold. Section
   titles 19–20px semibold. Line-height 1.5+.
6. **Language.** Task-first plain words. Say what the farmer GETS.

## Tokens (`app/globals.css` `:root`)

```css
--bg: #f4f5f1;            /* warm paper, not cool slate */
--bg-surface: #ffffff;
--bg-subtle: #eceee8;
--ink: #1a1c1a;
--ink-secondary: #4a4f4a;
--ink-tertiary: #6b716b;   /* metadata only, never essential info */
--brand: #1a6b3c;          /* agricultural green, AA on white at 18px+ */
--brand-dark: #14522e;
--brand-subtle: #e3f0e8;
--accent: #b45309;         /* earth amber for warnings/secondary accents */
--accent-subtle: #fdf2e3;
--danger: #b91c1c;  --danger-subtle: #fdecec;
--info: #1d4ed8;    --info-subtle: #e8eefc;
--line: #d9ddd4;    --line-strong: #b9bfb2;
--radius: 12px;  --radius-sm: 8px;  --radius-lg: 16px;
--shadow: 0 1px 3px rgba(26,28,26,0.08);
--shadow-raised: 0 4px 12px rgba(26,28,26,0.10);
```

**Font:** `"Noto Sans", "Noto Sans Devanagari", system-ui, sans-serif` for
every element, weights 400/600/700, loaded from Google Fonts in
`app/layout.tsx`. Never introduce a second family or a serif display font.

Compatibility aliases (`--muted`, `--brand-light`, `--radius-md`,
`--shadow-sm`, ...) map old variable names onto the new tokens so legacy
inline styles keep working. New code uses the canonical names above.

## Shared class API

Pages use ONLY these shared classes plus their own page-scoped classes.

| Class | Use |
| --- | --- |
| `.page-title` / `.page-subtitle` | Page heading (28px bold) and its one-line explanation |
| `.section-title` | 20px semibold section heading |
| `.surface-card` | White card: content grouping |
| `.surface-card-interactive` | Card that is entirely tappable |
| `.btn-primary` / `.btn-secondary` / `.btn-danger` | 48px+ buttons, bold labels; primary is 56px full-width on mobile |
| `.field-label` / `.field-input` / `.field-select` / `.field-help` | Big forms: 52px inputs, 17px+ text |
| `.stat-item` > `.stat-label` + `.stat-value` | A number a farmer cares about, labeled |
| `.result-card` (+ `-success` / `-warning` / `-danger`) | The answer a farmer came for: thick left border, tinted background |
| `.badge` (+ `-success` / `-warning` / `-danger` / `-info`) | Small status labels |
| `.empty-state` | Nothing to show yet |
| `.list-row` | One row in a list, 48px min |
| `.divider` | Horizontal rule |
| `.action-grid` > `.action-card` | Task-first home cards: icon + big label + one-line outcome; the whole card is the tap target |

### Usage examples

```tsx
<h2 className="page-title">{t("soil.title")}</h2>
<p className="page-subtitle">{t("soil.subtitle")}</p>

<label className="field-label" htmlFor="ph">{t("common.soilPh")}</label>
<input id="ph" className="field-input" inputMode="decimal" />
<p className="field-help">6.0 – 7.5 suits most crops</p>

<button type="submit" className="btn-primary">{t("common.predict")}</button>

<div className="result-card result-card-success">
  <span className="stat-label">{t("common.bestMatch")}</span>
  <span className="stat-value">Wheat</span>
</div>

<a className="action-card" href="/dashboard/irrigation-planner">
  <span className="action-card-icon"><Icon name="water" size={26} /></span>
  <span>
    <span className="action-card-label">{t("nav.irrigation")}</span>
    <span className="action-card-outcome">{t("dashboard.irrigationDesc")}</span>
  </span>
</a>
```

## Icons (`components/ui/Icons.tsx`)

```tsx
import { Icon } from "@/components/ui/Icons";
<Icon name="water" size={22} />
```

Inline SVG, `viewBox 24`, stroke `currentColor`, strokeWidth 1.8, fill none,
round caps. Available names:

`home, plant, soil, water, fertilizer, pest, weather, market, scheme, tools,
book, news, chart, farmer, search, language, alert, check, info, arrow-right,
phone, location, calendar, rupee, upload, history, leaf`

Need a new icon? Add it to `Icons.tsx` in the same style. Never inline an SVG
in a page and never use an emoji as an icon.

## Copy rules — no AI-speak

Farmer-facing copy says what the farmer gets, in the farmer's own words.
Banned words and their replacements:

| Banned | Say instead |
| --- | --- |
| ML-powered, AI, intelligence | (drop it) "Find the best crop for your soil" |
| platform | app, tool, helper |
| workflow | steps, work |
| insights | what your numbers mean, results |
| analyzer, analysis engine | check ("Soil Check") |
| module | tool, page |
| dashboard (as a farmer word) | home |
| leverage, optimize, seamless | use, improve, easy |

Titles name the task, not the technology: "What to Grow", "When to Water",
"Fertilizer Dose", "Mandi Prices", "How Predictions Work".

## Navigation labels (EN | HI)

| Key | EN | HI |
| --- | --- | --- |
| nav.dashboard | Home | होम |
| nav.crop | What to Grow | क्या उगाएं |
| nav.soil | Soil Check | मिट्टी की जांच |
| nav.irrigation | When to Water | सिंचाई कब करें |
| nav.fertilizer | Fertilizer Dose | खाद की मात्रा |
| nav.pest | Crop Problems | फसल की समस्या |
| nav.weather | Weather | मौसम |
| nav.market | Mandi Prices | मंडी भाव |
| nav.schemes | Govt Schemes | सरकारी योजनाएं |
| nav.rental | Rent Tools | औजार किराए पर |
| nav.knowledge | Farming Tips | खेती की जानकारी |
| nav.news | News | समाचार |
| nav.models | How Predictions Work | अनुमान कैसे बनते हैं |
| nav.history | My Records | मेरा रिकॉर्ड |

## Translation status

Only the **English and Hindi** blocks in `lib/i18n.ts` carry the new
kisan-first wording. The other nine language blocks (bn, te, ta, mr, gu, kn,
ml, pa, or) keep their older wording — several of their nav/shell strings are
still the old English values — until a proper translation pass is done. Do
not machine-edit those blocks casually; farmers read them.

## Accessibility notes

- `:focus-visible` shows a 3px brand outline everywhere — never remove it.
- The language picker is a native `<select>`: the OS renders it full-screen
  with large rows, which is the most familiar control on low-end Android.
- Loading/error/empty states (`components/ui/AsyncState.tsx`) always render
  text, not just an icon, and errors always offer a retry button.
