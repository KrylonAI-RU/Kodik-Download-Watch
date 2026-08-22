from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from anime_parsers_ru import KodikParser
import time

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

kodik = KodikParser(token=None)

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Encoding': 'gzip, deflate'
})

SHIKI_API = "https://shikimori.one/api"
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

def format_image_urls(raw_path):
    if not raw_path:
        return "", ""
    img_url = raw_path if raw_path.startswith('http') else f"https://shikimori.one{raw_path}"
    proxy_url = f"https://images.weserv.nl/?url={img_url.replace('https://', '')}&w=500&output=webp"
    return proxy_url, f"https://desu.shikimori.one{raw_path}"

@app.after_request
def add_cache_headers(response):
    if response.status_code == 200:
        response.headers['Cache-Control'] = 'public, max-age=3600, s-maxage=3600'
        response.headers['CDN-Cache-Control'] = 'max-age=3600'
    return response

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
        res = session.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            for item in data:
                shiki_id = item.get('id')
                shiki_img = item.get('image', {}).get('original') or item.get('image', {}).get('preview')
                poster, backup = format_image_urls(shiki_img)
                item['poster_url'] = poster
                item['backup_poster'] = backup
                item['backdrop_url'] = f"https://images.weserv.nl/?url=shikimori.one/system/animes/original/{shiki_id}.jpg&w=1280&output=webp"
            
            result = {'status': 'ok', 'data': data}
            set_cache(cache_key, result, ttl=300)
            return jsonify(result)
        return jsonify({'status': 'error', 'message': 'Ошибка источника'}), res.status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

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
        res = session.get(f"{SHIKI_API}/animes/{shiki_id}", timeout=5)
        if res.status_code == 200:
            data = res.json()
            shiki_img = data.get('image', {}).get('original')
            poster, backup = format_image_urls(shiki_img)
            data['poster_url'] = poster
            data['backup_poster'] = backup
            
            screens_res = session.get(f"{SHIKI_API}/animes/{shiki_id}/screenshots", timeout=4)
            data['screenshots'] = []
            if screens_res.status_code == 200:
                screens_data = screens_res.json()
                data['screenshots'] = [
                    f"https://images.weserv.nl/?url=shikimori.one{s['original']}&w=1280&output=webp"
                    for s in screens_data if 'original' in s
                ]
                
            data['backdrop_url'] = data['screenshots'][0] if data['screenshots'] else poster
            
            result = {'status': 'ok', 'data': data}
            set_cache(cache_key, result, ttl=3600)
            return jsonify(result)
        return jsonify({'status': 'error', 'message': 'Не найдено'}), res.status_code
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/stream', methods=['GET'])
def get_stream():
    shiki_id = request.args.get('shiki_id')
    episode = int(request.args.get('episode', 1))
    translation_id = request.args.get('translation_id', '')
    
    if not shiki_id:
        return jsonify({'status': 'error', 'message': 'shiki_id обязателен'}), 400

    cache_key = f"stream_{shiki_id}_{episode}_{translation_id}"
    cached_stream = get_cached(cache_key, ttl=600)
    if cached_stream:
        return jsonify(cached_stream)

    try:
        info = kodik.get_info(str(shiki_id), "shikimori")
        translations = []
        target_trans_id = translation_id

        if info and 'translations' in info:
            for tr in info['translations']:
                t_id = str(tr.get('id', ''))
                t_title = tr.get('title') or tr.get('name') or 'Озвучка'
                translations.append({'id': t_id, 'title': t_title})
            
            if not target_trans_id and translations:
                target_trans_id = translations[0]['id']

        raw_embed = kodik.get_embed_link(str(shiki_id), "shikimori")
        embed_url = ""
        if raw_embed:
            if raw_embed.startswith('//'):
                raw_embed = 'https:' + raw_embed
            separator = "&" if "?" in raw_embed else "?"
            base_query = f"{separator}episode={episode}&only_episode=true"
            if target_trans_id:
                base_query += f"&translation_id={target_trans_id}"
            embed_url = raw_embed + base_query
            # Принудительно заменяем домены на kodik.info
            for blocked in ['aniqit.com', 'kodik.cc', 'anivod.com']:
                embed_url = embed_url.replace(blocked, 'kodik.info')

        # Пробуем достать прямой HLS поток
        m3u8_url = None
        try:
            m3u8_url = kodik.get_m3u8_playlist_link(str(shiki_id), "shikimori", episode, str(target_trans_id or 0), 720)
        except Exception:
            m3u8_url = None

        result = {
            'status': 'ok',
            'stream_url': m3u8_url if m3u8_url else "",
            'embed_url': embed_url,
            'translations': translations,
            'active_translation_id': target_trans_id,
            'type': 'hls' if m3u8_url else 'iframe',
            'episode': episode
        }

        set_cache(cache_key, result, ttl=600)
        return jsonify(result)

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
