import asyncio
import sqlite3
import time
import json
import logging
import feedparser
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("news_server")

app = FastAPI(title="News Aggregator RSS")

# Zezwalamy na dostep z dowolnego frontendu (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RSS_FEEDS = {
    "RPP": "https://www.google.com/alerts/feeds/10817393600312151665/6430730879577189074",
    "Paliwa": "https://www.google.com/alerts/feeds/10817393600312151665/2686049431790703442"
}

DB_FILE = "news.db"
new_articles_queue = asyncio.Queue()

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY,
            source TEXT,
            title TEXT,
            summary TEXT,
            link TEXT,
            published TEXT,
            published_parsed REAL
        )
    ''')
    conn.commit()
    conn.close()

async def fetch_feed(url, source_name):
    logger.info(f"Pobieranie feedu: {source_name}")
    parsed = await asyncio.to_thread(feedparser.parse, url)
    new_entries = []
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    for entry in parsed.entries:
        guid = getattr(entry, 'id', getattr(entry, 'link', ''))
        if not guid:
            continue
            
        c.execute('SELECT 1 FROM articles WHERE id = ?', (guid,))
        if not c.fetchone():
            title = getattr(entry, 'title', 'Brak tytułu')
            # Czasem google news przechowuje treść w innych polach, ale głownie content/summary
            summary = getattr(entry, 'summary', getattr(entry, 'description', ''))
            
            # Extract main link from google news url wrapper if needed
            link = getattr(entry, 'link', '')
            published = getattr(entry, 'published', '')
            
            parsed_time = getattr(entry, 'published_parsed', None)
            ts = time.mktime(parsed_time) if parsed_time else time.time()
            
            c.execute('''
                INSERT INTO articles (id, source, title, summary, link, published, published_parsed)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (guid, source_name, title, summary, link, published, ts))
            
            article_dict = {
                "id": guid,
                "source": source_name,
                "title": title,
                "summary": summary,
                "link": link,
                "published": published,
                "timestamp": ts
            }
            new_entries.append(article_dict)
            
    conn.commit()
    conn.close()
    
    if new_entries:
        logger.info(f"[{source_name}] Dodano nowe articles: {len(new_entries)}")
        for article in sorted(new_entries, key=lambda x: x['timestamp']):
            await new_articles_queue.put(article)

async def check_feeds_loop():
    while True:
        try:
            for source_name, url in RSS_FEEDS.items():
                await fetch_feed(url, source_name)
        except Exception as e:
            logger.error(f"Error fetching feeds: {e}")
            
        # Sprawdzania co 60 sekund
        await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    init_db()
    asyncio.create_task(check_feeds_loop())

@app.get("/api/news/history")
def get_history(limit: int = 50):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # Sort malejaco, czyli nowe na gorze
    c.execute('SELECT * FROM articles ORDER BY published_parsed DESC LIMIT ?', (limit,))
    rows = c.fetchall()
    
    articles = []
    for row in rows:
        articles.append({
            "id": row["id"],
            "source": row["source"],
            "title": row["title"],
            "summary": row["summary"],
            "link": row["link"],
            "published": row["published"],
            "timestamp": row["published_parsed"]
        })
    conn.close()
    return articles

@app.get("/api/news/stream")
async def news_stream(request: Request):
    """
    Strumien SSE. Trzyma polaczenie od frontendu z alive, i jak tylko sse wybudzi background task - yield.
    """
    async def event_generator():
        while True:
            if await request.is_disconnected():
                logger.info("SSE Client disconnected")
                break
                
            try:
                article = await asyncio.wait_for(new_articles_queue.get(), timeout=15.0)
                # Send data JSON
                yield {
                    "event": "new_article",
                    "data": json.dumps(article)
                }
            except asyncio.TimeoutError:
                # Keep alive
                yield {
                    "event": "ping",
                    "data": "ok"
                }
                
    return EventSourceResponse(event_generator())

if __name__ == "__main__":
    import uvicorn
    # Testowy start jezeli python news_server.py zostalo odpalone z reki
    uvicorn.run("news_server:app", host="127.0.0.1", port=8000, reload=True)
