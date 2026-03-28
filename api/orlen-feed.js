const NITTER_INSTANCES = [
  "https://nitter.privacydev.net",
  "https://nitter.poast.org",
  "https://nitter.1d4.us",
  "https://nitter.fdn.fr",
];

export default async function handler(req, res) {
  for (const instance of NITTER_INSTANCES) {
    try {
      const url = `${instance}/b_prasoweORLEN/with_replies/rss`;
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
  }
  res.status(503).json({ error: "All nitter instances unavailable" });
}
