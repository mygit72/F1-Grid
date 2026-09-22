# Attributions and licences

Every visual and audio element of the F1Grid frontend is either original work in
this repository or an openly licensed dependency, with the licence recorded below.
There are no real Formula 1 team liveries, logos, badges, driver likenesses,
broadcast footage, team fonts, or circuit maps traced from official sources.

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

- The abstract open-wheel car silhouette in the hero is original SVG drawn in
  code (`web/src/components/Hero.jsx`). It is a generic racing-car shape with no
  team livery, no sponsor marks, no car number, and no driver likeness.
- The circuit outline in the track map (`web/src/components/TrackMap.jsx`) is a
  deliberately generic, invented loop. It is not traced from any real circuit and
  is labelled as such in the UI.
- All motion (animated background grid and scan, speed lines, light sweep, boot
  telemetry lines, timing-tower streaks and pulses, count-up numbers) is built
  from original CSS and SVG plus the MIT-licensed framer-motion library. No stock
  media, video, image files, or audio are used anywhere.
- Team accent colours in the timing tower and strategy chart are plain hex colour
  values used as generic category accents, not reproductions of any brand asset.

## Icons

No icon library is used. The podium medals are standard Unicode emoji
(U+1F947 / U+1F948 / U+1F949) rendered by the viewer's own system font; no image
files are bundled.

If any future asset cannot have its licence confirmed, it must not be used.
