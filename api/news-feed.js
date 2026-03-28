const Q_PALIWA = '("ceny paliw" OR "benzyna" OR "Iran" OR "diesel" OR "ON" OR "LPG" OR "ropa Brent" OR "ropa WTI") AND ("Polska" OR "Orlen" OR "stacje paliw") AND ("prognoza" OR "prognozy" OR "e-petrol" OR "Reflex" OR "podwyżki" OR "obniżki")';
const Q_RPP = '("stopy procentowe" OR "stopami procentowymi" OR "stóp procentowych" OR "inflacja" OR "polityka pieniężna" OR "RPP" OR "Iran") AND ("Glapiński" OR "Ireneusz Dąbrowski" OR "Iwona Duda" OR "Janczyk" OR "Kotecki" OR "Litwiniuk" OR "Masłowska" OR "Tyrowicz" OR "Wronowski" OR "Zarzecki")';

const FEEDS = {
  RPP: `https://news.google.com/rss/search?q=${encodeURIComponent(Q_RPP)}&hl=pl&gl=PL&ceid=PL:pl`,
  Paliwa: `https://news.google.com/rss/search?q=${encodeURIComponent(Q_PALIWA)}&hl=pl&gl=PL&ceid=PL:pl`,
};

export default async function handler(req, res) {
  const source = req.query.source;
  const url = FEEDS[source];
  if (!url) return res.status(400).json({ error: "Unknown source" });

  try {
    const r = await fetch(url, {
      signal: AbortSignal.timeout(8000),
      headers: { "User-Agent": "Mozilla/5.0 (compatible; RSS reader)" },
    });
    if (r.ok) {
      const text = await r.text();
      res.setHeader("Content-Type", "application/rss+xml; charset=utf-8");
      res.setHeader("Cache-Control", "s-maxage=300, stale-while-revalidate=60");
      res.setHeader("Access-Control-Allow-Origin", "*");
      return res.status(200).send(text);
    }
  } catch {}
  res.status(503).json({ error: "Feed unavailable" });
}
