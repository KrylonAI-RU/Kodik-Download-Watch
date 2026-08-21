from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from anime_parsers_ru import KodikParser

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

kodik = KodikParser(token=None)
SHIKI_API = "https://shikimori.one/api"
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

# 1. Каталог с нормальными постерами
@app.route('/api/anime/catalog', methods=['GET'])
def get_catalog():
    page = request.args.get('page', 1)
    limit = request.args.get('limit', 40)
    order = request.args.get('order', 'popularity')
    kind = request.args.get('kind', '')
    search = request.args.get('search', '')

    url = f"{SHIKI_API}/animes?page={page}&limit={limit}&order={order}"
    if kind: url += f"&kind={kind}"
    if search: url += f"&search={search}"

    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        data = res.json()
        # Добавляем прямые надежные ссылки на постеры
        for item in data:
            shiki_img = item.get('image', {}).get('original') or item.get('image', {}).get('preview')
            if shiki_img:
                item['poster_url'] = f"https://shikimori.one{shiki_img}"
                item['backup_poster'] = f"https://desu.shikimori.one{shiki_img}"
            else:
                item['poster_url'] = ""
                item['backup_poster'] = ""
        return jsonify({'status': 'ok', 'data': data})
    return jsonify({'status': 'error', 'message': 'Ошибка API'}), res.status_code

# 2. Детальная инфа
@app.route('/api/anime/details', methods=['GET'])
def get_details():
    shiki_id = request.args.get('shiki_id')
    if not shiki_id:
        return jsonify({'status': 'error', 'message': 'shiki_id обязателен'}), 400
        
    res = requests.get(f"{SHIKI_API}/animes/{shiki_id}", headers=HEADERS)
    if res.status_code == 200:
        data = res.json()
        shiki_img = data.get('image', {}).get('original')
        data['poster_url'] = f"https://shikimori.one{shiki_img}" if shiki_img else ""
        return jsonify({'status': 'ok', 'data': data})
    return jsonify({'status': 'error', 'message': 'Не найдено'}), res.status_code

# 3. Точный стрим нужной серии
@app.route('/api/stream', methods=['GET'])
def get_stream():
    shiki_id = request.args.get('shiki_id')
    episode = int(request.args.get('episode', 1))
    
    if not shiki_id:
        return jsonify({'status': 'error', 'message': 'shiki_id обязателен'}), 400

    try:
        # Получаем базовую embed ссылку на плеер с точной серией
        embed_url = kodik.get_embed_link(str(shiki_id), "shikimori")
        if embed_url:
            separator = "&" if "?" in embed_url else "?"
            embed_url = f"{embed_url}{separator}episode={episode}&only_episode=true"

        # Ищем доступные озвучки для точного HLS стрима
        try:
            info = kodik.get_info(str(shiki_id), "shikimori")
            trans_id = "0"
            if info and 'translations' in info and len(info['translations']) > 0:
                # Берем первую доступную озвучку, где есть наша серия
                for tr in info['translations']:
                    r = tr.get('series_range', [1, 9999])
                    if r[0] <= episode <= r[1]:
                        trans_id = str(tr['id'])
                        break

            m3u8_url = kodik.get_m3u8_playlist_link(str(shiki_id), "shikimori", episode, trans_id, 720)
            return jsonify({
                'status': 'ok',
                'stream_url': m3u8_url,
                'embed_url': embed_url,
                'type': 'hls',
                'episode': episode
            })
        except Exception:
            return jsonify({
                'status': 'ok',
                'stream_url': embed_url,
                'embed_url': embed_url,
                'type': 'iframe',
                'episode': episode
            })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
