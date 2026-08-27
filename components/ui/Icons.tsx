import type { ReactNode } from "react";

/**
 * The ONLY icon source for the whole app. Inline stroke SVGs so they render
 * crisply at any size, inherit currentColor, and never depend on an emoji
 * font. Shapes are literal (a water drop, a bug, a tractor) so a first-time
 * smartphone user can recognise them at 20px.
 */
export type IconName =
  | "home"
  | "plant"
  | "soil"
  | "water"
  | "fertilizer"
  | "pest"
  | "weather"
  | "market"
  | "scheme"
  | "tools"
  | "book"
  | "news"
  | "chart"
  | "farmer"
  | "search"
  | "language"
  | "alert"
  | "check"
  | "info"
  | "arrow-right"
  | "phone"
  | "location"
  | "calendar"
  | "rupee"
  | "upload"
  | "history"
  | "leaf";

const ICON_PATHS: Record<IconName, ReactNode> = {
  // A house: roof, walls, door.
  home: (
    <>
      <path d="M3 11.2 12 3.8l9 7.4" />
      <path d="M5.3 9.8V20h13.4V9.8" />
      <path d="M10 20v-5.4h4V20" />
    </>
  ),
  // A young plant: stem with two leaves growing from the ground line.
  plant: (
    <>
      <path d="M12 21v-8.4" />
      <path d="M12 12.6C12 8.8 9.2 6.2 5 6c0 4.2 2.8 6.8 7 6.6Z" />
      <path d="M12 10.4c0-3.2 2.4-5.4 6-5.6 0 3.6-2.4 5.8-6 5.6Z" />
      <path d="M4 21h16" />
    </>
  ),
  // Soil layers with a sprout coming out of the ground.
  soil: (
    <>
      <path d="M12 13.5V9.8" />
      <path d="M12 9.8C12 7.6 10.4 6.2 8 6c0 2.4 1.6 3.9 4 3.8Z" />
      <path d="M3 13.5h18" />
      <path d="M3 17h3.2m3.2 0h3.2m3.2 0H19" />
      <path d="M5 20.5h3.2m3.2 0h3.2m3.2 0H19" />
    </>
  ),
  // A single water drop.
  water: (
    <>
      <path d="M12 3.2c3.8 4.4 6.4 7.9 6.4 11a6.4 6.4 0 0 1-12.8 0c0-3.1 2.6-6.6 6.4-11Z" />
      <path d="M9.2 14.5a2.9 2.9 0 0 0 2 2.6" />
    </>
  ),
  // A fertilizer sack with granules.
  fertilizer: (
    <>
      <path d="M9 7.5V5.6c0-1 .7-1.8 1.6-1.8h2.8c.9 0 1.6.8 1.6 1.8v1.9" />
      <path d="M6.8 7.5h10.4l1.3 11c.1 .9-.6 1.7-1.5 1.7H7c-.9 0-1.6-.8-1.5-1.7l1.3-11Z" />
      <path d="M9.5 12.6h.01M12 15.4h.01M14.5 12.6h.01M12 11h.01M9.7 16.6h.01M14.3 16.6h.01" />
    </>
  ),
  // A bug: round body, head, antennae, legs.
  pest: (
    <>
      <circle cx="12" cy="14" r="4.6" />
      <path d="M12 9.4v9.2" />
      <path d="M9.8 7.4 8.2 4.6M14.2 7.4l1.6-2.8" />
      <path d="M7.4 12.2H3.8M7.4 16.2l-3 1.6M16.6 12.2h3.6M16.6 16.2l3 1.6" />
    </>
  ),
  // Sun and cloud.
  weather: (
    <>
      <circle cx="8.4" cy="8.2" r="3" />
      <path d="M8.4 2.6v1.2M2.8 8.2H4M4.4 4.2l.9.9M12.4 4.2l-.9.9M3.5 12.3l.9-.9" />
      <path d="M12.6 20h4.9a3.3 3.3 0 0 0 .6-6.6 4.5 4.5 0 0 0-8.8 1.2A2.8 2.8 0 0 0 9.9 20h2.7Z" />
    </>
  ),
  // A weighing scale, familiar from every mandi.
  market: (
    <>
      <path d="M12 4v3M6 7h12" />
      <path d="M6 7l-2.6 5.4a3 3 0 0 0 5.2 0L6 7ZM18 7l-2.6 5.4a3 3 0 0 0 5.2 0L18 7Z" />
      <path d="M12 7v13M8.4 20h7.2" />
    </>
  ),
  // A government building: pediment and columns.
  scheme: (
    <>
      <path d="m12 3-8.5 4.6h17L12 3Z" />
      <path d="M4.6 10.4h14.8" />
      <path d="M6.8 10.4v6.4M12 10.4v6.4M17.2 10.4v6.4" />
      <path d="M4.6 16.8h14.8M3.4 20.2h17.2" />
    </>
  ),
  // A tractor: big rear wheel, small front wheel, cab.
  tools: (
    <>
      <circle cx="7.2" cy="16.4" r="3.6" />
      <circle cx="7.2" cy="16.4" r="0.4" />
      <circle cx="18" cy="17.6" r="2.4" />
      <path d="M10.8 16.4h4.8" />
      <path d="M4 12.8V8.4h6.4l1.6 4.6" />
      <path d="M10.4 8.4V5.6h3.2l2.4 7h3.6v3.2" />
    </>
  ),
  // An open book.
  book: (
    <>
      <path d="M12 6.2C10.2 4.8 7.4 4.3 3.8 4.8v13.7c3.6-.5 6.4 0 8.2 1.4 1.8-1.4 4.6-1.9 8.2-1.4V4.8c-3.6-.5-6.4 0-8.2 1.4Z" />
      <path d="M12 6.2v13.7" />
    </>
  ),
  // A newspaper front page.
  news: (
    <>
      <rect x="3.6" y="4.6" width="16.8" height="14.8" rx="1.8" />
      <path d="M7 8.4h10" />
      <path d="M7 12h4v4H7Z" />
      <path d="M14 12h3M14 16h3" />
    </>
  ),
  // A bar chart on an axis.
  chart: (
    <>
      <path d="M4 4v16h16" />
      <path d="M8.6 16.4v-4.2M13 16.4V7.6M17.4 16.4v-6.6" />
    </>
  ),
  // A person: head and shoulders.
  farmer: (
    <>
      <circle cx="12" cy="8" r="3.6" />
      <path d="M5 20.2a7 7 0 0 1 14 0" />
    </>
  ),
  // A magnifying glass.
  search: (
    <>
      <circle cx="11" cy="11" r="5.8" />
      <path d="m15.4 15.4 4.8 4.8" />
    </>
  ),
  // A globe with meridians.
  language: (
    <>
      <circle cx="12" cy="12" r="8.4" />
      <path d="M3.6 12h16.8" />
      <path d="M12 3.6c2.4 2.2 3.6 5 3.6 8.4s-1.2 6.2-3.6 8.4c-2.4-2.2-3.6-5-3.6-8.4s1.2-6.2 3.6-8.4Z" />
    </>
  ),
  // A warning triangle.
  alert: (
    <>
      <path d="M12 4 2.8 19.4h18.4L12 4Z" />
      <path d="M12 10.2v4" />
      <path d="M12 17h.01" />
    </>
  ),
  // A check mark.
  check: <path d="m4.8 12.6 4.8 4.8L19.2 6.8" />,
  // A circled letter i.
  info: (
    <>
      <circle cx="12" cy="12" r="8.4" />
      <path d="M12 11.2v5" />
      <path d="M12 7.8h.01" />
    </>
  ),
  // An arrow pointing right.
  "arrow-right": (
    <>
      <path d="M4 12h15.2" />
      <path d="m13.4 6.2 5.8 5.8-5.8 5.8" />
    </>
  ),
  // A telephone handset.
  phone: (
    <>
      <path d="M8.2 3.8H5.3c-.8 0-1.5.7-1.5 1.5A15.4 15.4 0 0 0 18.7 20.2c.8 0 1.5-.7 1.5-1.5v-2.9l-3.8-1.5-1.7 2.1a12.3 12.3 0 0 1-5.1-5.1l2.1-1.7-1.5-3.8Z" />
    </>
  ),
  // A map pin.
  location: (
    <>
      <path d="M12 21c-4.3-4.2-6.4-7.6-6.4-10.6a6.4 6.4 0 0 1 12.8 0c0 3-2.1 6.4-6.4 10.6Z" />
      <circle cx="12" cy="10.2" r="2.3" />
    </>
  ),
  // A wall calendar.
  calendar: (
    <>
      <rect x="4" y="5.4" width="16" height="14.6" rx="1.8" />
      <path d="M4 10h16" />
      <path d="M8.4 3.4v3.6M15.6 3.4v3.6" />
    </>
  ),
  // The rupee sign.
  rupee: (
    <>
      <path d="M6.8 4h10.4M6.8 8.6h10.4" />
      <path d="M9.4 4c5.4 0 5.4 8.4 0 8.4H6.8L14.6 20" />
    </>
  ),
  // An arrow going up into a tray.
  upload: (
    <>
      <path d="M4 15.8v3a1.6 1.6 0 0 0 1.6 1.6h12.8A1.6 1.6 0 0 0 20 18.8v-3" />
      <path d="M12 15.4V4.2" />
      <path d="M7.4 8.4 12 3.8l4.6 4.6" />
    </>
  ),
  // A clock turning back.
  history: (
    <>
      <path d="M4.4 11.4a7.8 7.8 0 1 1 1.6 5.4" />
      <path d="M4.2 12.6 3.6 8.8l3.8.6" />
      <path d="M12 8.2v4.4l3 1.8" />
    </>
  ),
  // A single leaf with a stem vein.
  leaf: (
    <>
      <path d="M19.8 4.2c-9.4-.4-15 4.4-15.4 11 0 1.8.4 3.4 1.2 4.6C7 13 11 8.8 16.6 6.9c-4.8 2.8-8.2 7-9.4 12.3 1 .4 2.2.6 3.4.6 6.6-.4 9.6-7.2 9.2-15.6Z" />
    </>
  ),
};

export function Icon({ name, size = 24 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {ICON_PATHS[name]}
    </svg>
  );
}

export const ICON_NAMES = Object.keys(ICON_PATHS) as IconName[];
