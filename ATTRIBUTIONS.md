# Attributions and licences

Every locally created visual and audio element of the F1Grid frontend is original
work in this repository or an openly licensed dependency. The 2026 driver portraits
are remotely loaded from Formula 1's media CDN and remain Formula 1 property.
F1Grid is an independent fan project and is not affiliated with Formula 1 or the FIA.

## Fonts (Google Fonts, loaded in web/index.html)

| Font | Use | Licence |
| --- | --- | --- |
| Bebas Neue | Display headings | SIL Open Font License 1.1 |
| Inter | Body text | SIL Open Font License 1.1 |
| JetBrains Mono | Numbers and telemetry labels | SIL Open Font License 1.1 |

All three are served by Google Fonts under the SIL Open Font License 1.1, which
permits use, embedding, and redistribution. They are general-purpose typefaces,
not any team's brand font.

## Software dependencies (web/package.json)

| Package | Use | Licence |
| --- | --- | --- |
| react, react-dom | UI framework | MIT |
| framer-motion | The TimingTower spring and layout animation | MIT |
| vite, @vitejs/plugin-react | Build tooling | MIT |
| playwright (dev only) | Headless rendering check, not shipped | Apache-2.0 |

## Original assets (created for this repo, owned by the author)

- The Ferrari-red and white open-wheel car in the hero is an original SVG drawn
  in code (`web/src/components/Hero.jsx`), styled after the 2026 SF-26 livery.
  It uses no official Ferrari logo or sponsor marks. Ferrari's red-and-white
  2026 livery was confirmed in the [SF-26 reveal](https://www.formula1.com/en/latest/article/first-look-ferrari-reveal-new-sf-26-car-for-2026-f1-season.19b0ad82cdsyXgvA675Ey4.19b0ad82cdsyXgvA675Ey4).
- The circuit outline in the track map (`web/src/components/TrackMap.jsx`) is a
  deliberately generic, invented loop. It is not traced from any real circuit and
  is labelled as such in the UI.
- All motion (animated background grid and scan, speed lines, light sweep, boot
  telemetry lines, timing-tower streaks and pulses, count-up numbers) is built
  from original CSS and SVG plus the MIT-licensed framer-motion library. No
  stock footage or image files are bundled locally; remote portraits are listed
  below.
- Team colorways are plain color values used to identify each team's prediction
  cards. They are not team logos or sponsor marks.

## Formula 1 data and portraits

- Current driver names, teams, portrait URLs, and profile details are based on the
  [official 2026 driver directory](https://www.formula1.com/en/drivers). Race
  numbers are based on the [official 2026 driver-number list](https://www.formula1.com/en/latest/article/all-the-2026-f1-driver-numbers-confirmed-in-full.5rh7o9mPntG7NerzVk9onc.5rh7o9mPntG7NerzVk9onc).
- Driver profiles are presented inside F1Grid. Portraits are served directly by
  `media.formula1.com`; the repository does not contain copies of the image files.
  Portraits and Formula 1 marks remain the property of Formula One World
  Championship Limited and their respective owners.
- Team color values correspond to the 2026 color key in the unofficial
  [F1 2026 Assets index](https://turn1visuals.com/f1-2026-assets/). No team logo,
  badge, or official car photograph is bundled.

## Icons

No icon library is used. The podium medals are standard Unicode emoji
(U+1F947 / U+1F948 / U+1F949) rendered by the viewer's own system font; no image
files are bundled.

If any future asset cannot have its licence confirmed, it must not be used.
