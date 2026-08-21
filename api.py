from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from anime_parsers_ru import KodikParser, AnimegoParser

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

kodik = KodikParser(token=None)
animego = AnimegoParser()

SHIKI_API = "https://shikimori.one/api"
HEADERS = {'User-Agent': 'AnimeStreamApp/1.0'}

# 1. Поиск и списки аниме с Шикимори
@app.route('/api/anime/catalog', methods=['GET'])
def get_catalog():
    page = request.args.get('page', 1)
    limit = request.args.get('limit', 24)
    order = request.args.get('order', 'popularity') # popularity, ranked, aired_on
    kind = request.args.get('kind', 'tv') # tv, movie, ova
    search = request.args.get('search', '')

    url = f"{SHIKI_API}/animes?page={page}&limit={limit}&order={order}&kind={kind}&search={search}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        return jsonify({'status': 'ok', 'data': res.json()})
    return jsonify({'status': 'error', 'message': 'Ошибка Shikimori API'}), res.status_code

# 2. Детальная информация об аниме
@app.route('/api/anime/details', methods=['GET'])
def get_details():
    shiki_id = request.args.get('shiki_id')
    if not shiki_id:
        return jsonify({'status': 'error', 'message': 'shiki_id обязателен'}), 400
        
    res = requests.get(f"{SHIKI_API}/animes/{shiki_id}", headers=HEADERS)
    if res.status_code == 200:
        return jsonify({'status': 'ok', 'data': res.json()})
    return jsonify({'status': 'error', 'message': 'Тайтл не найден'}), res.status_code

# 3. Получение видеопотока / плеера
@app.route('/api/stream', methods=['GET'])
def get_stream():
    shiki_id = request.args.get('shiki_id')
    episode = int(request.args.get('episode', 1))
    
    if not shiki_id:
        return jsonify({'status': 'error', 'message': 'shiki_id обязателен'}), 400

    try:
        # Пробуем m3u8 поток из Kodik по ID шикимори
        try:
            m3u8_url = kodik.get_m3u8_playlist_link(str(shiki_id), "shikimori", episode, "0", 720)
            embed_url = kodik.get_embed_link(str(shiki_id), "shikimori")
            return jsonify({'status': 'ok', 'stream_url': m3u8_url, 'embed_url': embed_url, 'type': 'hls'})
        except Exception:
            embed_url = kodik.get_embed_link(str(shiki_id), "shikimori")
            return jsonify({'status': 'ok', 'stream_url': embed_url, 'type': 'iframe'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
