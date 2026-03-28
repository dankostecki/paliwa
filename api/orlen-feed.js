const ORLEN_RSS_URL = "https://rss.app/feeds/pe3hhZeRcVPoDAuU.xml";

export default async function handler(req, res) {
  try {
    const r = await fetch(ORLEN_RSS_URL, {
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
