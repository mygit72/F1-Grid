const F1_MEDIA = "https://media.formula1.com/image/upload";

export const TEAM_STYLES = {
  alpine: { name: "Alpine", accent: "#00a1e8", deep: "#004e70", assetColor: "00a1e8" },
  aston: { name: "Aston Martin", accent: "#229971", deep: "#0f4331", assetColor: "229971" },
  audi: { name: "Audi", accent: "#ff2d00", deep: "#751500", assetColor: "ff2d00" },
  cadillac: { name: "Cadillac", accent: "#aaaaad", deep: "#58585b", assetColor: "aaaaad" },
  ferrari: { name: "Ferrari", accent: "#e8002d", deep: "#5c0012", assetColor: "e8002d" },
  haas: { name: "Haas", accent: "#aeb6bb", deep: "#667175", assetColor: "dee1e2" },
  mclaren: { name: "McLaren", accent: "#ff8000", deep: "#804000", assetColor: "ff8000" },
  mercedes: { name: "Mercedes", accent: "#27f4d2", deep: "#067e6a", assetColor: "27f4d2" },
  racingBulls: { name: "Racing Bulls", accent: "#6692ff", deep: "#0038c2", assetColor: "6692ff" },
  redBull: { name: "Red Bull Racing", accent: "#3671c6", deep: "#142948", assetColor: "3671c6" },
  williams: { name: "Williams", accent: "#1868db", deep: "#082145", assetColor: "1868db" },
  sauber: { name: "Sauber", accent: "#52e252", deep: "#1b571b", assetColor: "52e252" },
};

const TEAM_ALIASES = {
  alpine: "alpine", "alpine f1 team": "alpine",
  "aston martin": "aston", "aston martin aramco": "aston",
  audi: "audi", "audi f1 team": "audi",
  cadillac: "cadillac", "cadillac f1 team": "cadillac",
  ferrari: "ferrari", "scuderia ferrari": "ferrari",
  haas: "haas", "haas f1 team": "haas", "tgr haas f1 team": "haas",
  mclaren: "mclaren", "mclaren formula 1 team": "mclaren",
  mercedes: "mercedes", "mercedes-amg petronas": "mercedes",
  "rb f1 team": "racingBulls", "racing bulls": "racingBulls", rb: "racingBulls", vcarb: "racingBulls",
  "red bull": "redBull", "red bull racing": "redBull", "oracle red bull racing": "redBull", rbr: "redBull",
  williams: "williams", "williams racing": "williams",
  sauber: "sauber", "kick sauber": "sauber", "alfa romeo": "sauber",
};

// Image paths resolve to F1's 2026 portrait assets. The assets remain hosted
// by Formula 1 and are loaded only when a driver card enters the page.
const driver = (name, surname, number, nationality, teamKey, profileSlug, assetPath) => ({
  name,
  surname,
  number,
  nationality,
  teamKey,
  profileUrl: `https://www.formula1.com/en/drivers/${profileSlug}`,
  portraitUrl: `${F1_MEDIA}/ar_1%3A1%2Cc_crop%2Cg_north%2Cw_420/b_rgb%3A${TEAM_STYLES[teamKey].assetColor}/common/f1/2026/${assetPath}`,
});

export const DRIVER_PROFILES = {
  COL: driver("Franco Colapinto", "Colapinto", 43, "Argentina", "alpine", "franco-colapinto", "alpine/fracol01/2026alpinefracol01front.png"),
  GAS: driver("Pierre Gasly", "Gasly", 10, "France", "alpine", "pierre-gasly", "alpine/piegas01/2026alpinepiegas01front.png"),
  ALO: driver("Fernando Alonso", "Alonso", 14, "Spain", "aston", "fernando-alonso", "astonmartin/feralo01/2026astonmartinferalo01front.png"),
  STR: driver("Lance Stroll", "Stroll", 18, "Canada", "aston", "lance-stroll", "astonmartin/lanstr01/2026astonmartinlanstr01front.png"),
  BOR: driver("Gabriel Bortoleto", "Bortoleto", 5, "Brazil", "audi", "gabriel-bortoleto", "audi/gabbor01/2026audigabbor01front.png"),
  HUL: driver("Nico Hulkenberg", "Hulkenberg", 27, "Germany", "audi", "nico-hulkenberg", "audi/nichul01/2026audinichul01front.png"),
  PER: driver("Sergio Perez", "Perez", 11, "Mexico", "cadillac", "sergio-perez", "cadillac/serper01/2026cadillacserper01front.png"),
  BOT: driver("Valtteri Bottas", "Bottas", 77, "Finland", "cadillac", "valtteri-bottas", "cadillac/valbot01/2026cadillacvalbot01front.png"),
  LEC: driver("Charles Leclerc", "Leclerc", 16, "Monaco", "ferrari", "charles-leclerc", "ferrari/chalec01/2026ferrarichalec01front.png"),
  HAM: driver("Lewis Hamilton", "Hamilton", 44, "United Kingdom", "ferrari", "lewis-hamilton", "ferrari/lewham01/2026ferrarilewham01front.png"),
  OCO: driver("Esteban Ocon", "Ocon", 31, "France", "haas", "esteban-ocon", "haasf1team/estoco01/2026haasf1teamestoco01front.png"),
  BEA: driver("Oliver Bearman", "Bearman", 87, "United Kingdom", "haas", "oliver-bearman", "haasf1team/olibea01/2026haasf1teamolibea01front.png"),
  NOR: driver("Lando Norris", "Norris", 1, "United Kingdom", "mclaren", "lando-norris", "mclaren/lannor01/2026mclarenlannor01front.png"),
  PIA: driver("Oscar Piastri", "Piastri", 81, "Australia", "mclaren", "oscar-piastri", "mclaren/oscpia01/2026mclarenoscpia01front.png"),
  RUS: driver("George Russell", "Russell", 63, "United Kingdom", "mercedes", "george-russell", "mercedes/georus01/2026mercedesgeorus01front.png"),
  ANT: driver("Kimi Antonelli", "Antonelli", 12, "Italy", "mercedes", "kimi-antonelli", "mercedes/andant01/2026mercedesandant01front.png"),
  LIN: driver("Arvid Lindblad", "Lindblad", 41, "United Kingdom", "racingBulls", "arvid-lindblad", "racingbulls/arvlin01/2026racingbullsarvlin01front.png"),
  LAW: driver("Liam Lawson", "Lawson", 30, "New Zealand", "racingBulls", "liam-lawson", "racingbulls/lialaw01/2026racingbullslialaw01front.png"),
  HAD: driver("Isack Hadjar", "Hadjar", 6, "France", "redBull", "isack-hadjar", "redbullracing/isahad01/2026redbullracingisahad01front.png"),
  VER: driver("Max Verstappen", "Verstappen", 3, "Netherlands", "redBull", "max-verstappen", "redbullracing/maxver01/2026redbullracingmaxver01front.png"),
  ALB: driver("Alexander Albon", "Albon", 23, "Thailand", "williams", "alexander-albon", "williams/alealb01/2026williamsalealb01front.png"),
  SAI: driver("Carlos Sainz", "Sainz", 55, "Spain", "williams", "carlos-sainz", "williams/carsai01/2026williamscarsai01front.png"),
};

export function getDriverProfile(code) {
  const key = String(code ?? "").toUpperCase();
  return DRIVER_PROFILES[key] ?? {
    name: key || "Unknown driver",
    surname: key || "Unknown",
    number: null,
    nationality: null,
    profileUrl: null,
    portraitUrl: null,
    teamKey: null,
  };
}

export function getTeamStyle(team, code) {
  const profile = DRIVER_PROFILES[String(code ?? "").toUpperCase()];
  const teamKey = TEAM_ALIASES[String(team ?? "").trim().toLowerCase()] ?? profile?.teamKey;
  return TEAM_STYLES[teamKey] ?? { name: team || "F1 driver", accent: "#77818a", deep: "#3d454d", assetColor: "77818a" };
}

export function getTeamName(team, code) {
  return DRIVER_PROFILES[String(code ?? "").toUpperCase()]?.teamKey
    ? TEAM_STYLES[DRIVER_PROFILES[String(code ?? "").toUpperCase()].teamKey].name
    : team || "Independent";
}
