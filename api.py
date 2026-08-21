from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from anime_parsers_ru import KodikParser
from functools import lru_cache
import time

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Инициализируем парсер Kodik
kodik = KodikParser(token=None)

# Настройка постоянной HTTP-сессии
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Encoding': 'gzip, deflate'
})

SHIKI_API = "https://shikimori.one/api"

# Простой in-memory кэш с TTL (временем жизни)
MEMORY_CACHE = {}

def get_cached(key, ttl=300):
    if key in MEMORY_CACHE:
        val, expire = MEMORY_CACHE[key]
        if time.time() < expire:
            return val
        del MEMORY_CACHE[key]
    return None

def set_cache(key, value, ttl=300):
    MEMORY_CACHE[key] = (value, time.time() + ttl)

# 1. Каталог (кэш на 5 минут)
@app.route('/api/anime/catalog', methods=['GET'])
def get_catalog():
    page = request.args.get('page', '1')
    limit = request.args.get('limit', '40')
    order = request.args.get('order', 'popularity')
    kind = request.args.get('kind', '')
    search = request.args.get('search', '')

    cache_key = f"cat_{page}_{limit}_{order}_{kind}_{search}"
    cached_data = get_cached(cache_key, ttl=300)
    if cached_data:
        return jsonify(cached_data)

    url = f"{SHIKI_API}/animes?page={page}&limit={limit}&order={order}"
    if kind: url += f"&kind={kind}"
    if search: url += f"&search={search}"

    try:
        res = session.get(url, timeout=4)
        if res.status_code == 200:
            data = res.json()
            for item in data:
                shiki_img = item.get('image', {}).get('original') or item.get('image', {}).get('preview')
                item['poster_url'] = f"https://shikimori.one{shiki_img}" if shiki_img else ""
                item['backup_poster'] = f"https://desu.shikimori.one{shiki_img}" if shiki_img else ""
            
            result = {'status': 'ok', 'data': data}
            set_cache(cache_key, result, ttl=300)
            return jsonify(result)
        return jsonify({'status': 'error', 'message': 'Ошибка источника'}), res.status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 2. Детальная инфа (кэш на 1 час)
@app.route('/api/anime/details', methods=['GET'])
def get_details():
    shiki_id = request.args.get('shiki_id')
    if not shiki_id:
        return jsonify({'status': 'error', 'message': 'shiki_id обязателен'}), 400
        
    cache_key = f"details_{shiki_id}"
    cached_data = get_cached(cache_key, ttl=3600)
    if cached_data:
        return jsonify(cached_data)

    try:
        res = session.get(f"{SHIKI_API}/animes/{shiki_id}", timeout=4)
        if res.status_code == 200:
            data = res.json()
            shiki_img = data.get('image', {}).get('original')
            data['poster_url'] = f"https://shikimori.one{shiki_img}" if shiki_img else ""
            result = {'status': 'ok', 'data': data}
            set_cache(cache_key, result, ttl=3600)
            return jsonify(result)
        return jsonify({'status': 'error', 'message': 'Не найдено'}), res.status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 3. Быстрая отдача стрима (кэш на 10 минут)
@app.route('/api/stream', methods=['GET'])
def get_stream():
    shiki_id = request.args.get('shiki_id')
    episode = int(request.args.get('episode', 1))
    
    if not shiki_id:
        return jsonify({'status': 'error', 'message': 'shiki_id обязателен'}), 400

    cache_key = f"stream_{shiki_id}_{episode}"
    cached_stream = get_cached(cache_key, ttl=600)
    if cached_stream:
        return jsonify(cached_stream)

    try:
        embed_url = kodik.get_embed_link(str(shiki_id), "shikimori")
        if embed_url:
            separator = "&" if "?" in embed_url else "?"
            embed_url = f"{embed_url}{separator}episode={episode}&only_episode=true"

        try:
            info = kodik.get_info(str(shiki_id), "shikimori")
            trans_id = "0"
            if info and 'translations' in info:
                for tr in info['translations']:
                    r = tr.get('series_range', [1, 9999])
                    if r[0] <= episode <= r[1]:
                        trans_id = str(tr['id'])
                        break

            m3u8_url = kodik.get_m3u8_playlist_link(str(shiki_id), "shikimori", episode, trans_id, 720)
            result = {
                'status': 'ok',
                'stream_url': m3u8_url,
                'embed_url': embed_url,
                'type': 'hls',
                'episode': episode
            }
        except Exception:
            result = {
                'status': 'ok',
                'stream_url': embed_url,
                'embed_url': embed_url,
                'type': 'iframe',
                'episode': episode
            }

        set_cache(cache_key, result, ttl=600)
        return jsonify(result)

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
