from flask import Flask, request, jsonify
from flask_cors import CORS
from anime_parsers_ru import KodikParser, AnimegoParser, JutsuParser

app = Flask(__name__)
CORS(app)

kodik = KodikParser(token=None)
animego = AnimegoParser()
jutsu = JutsuParser()

@app.route('/api/stream', methods=['GET'])
def get_stream():
    source = request.args.get('source', 'kodik')
    kp_id = request.args.get('kp_id')
    episode = int(request.args.get('episode', 1))
    translation_id = request.args.get('translation_id', '0')
    
    if not kp_id:
        return jsonify({'status': 'error', 'message': 'Параметр kp_id обязателен'}), 400

    try:
        if source == 'kodik':
            try:
                # Передаем строго по позициям: id, id_type, seria_num, translation_id, quality
                m3u8_url = kodik.get_m3u8_playlist_link(
                    str(kp_id), 
                    "kinopoisk", 
                    int(episode), 
                    str(translation_id), 
                    720
                )
                return jsonify({'status': 'ok', 'stream_url': m3u8_url, 'type': 'hls'})
            except Exception:
                # Если парсинг m3u8 сбрасывается или блокируется IP-фильтром Kodik
                embed_url = kodik.get_embed_link(str(kp_id), "kinopoisk")
                return jsonify({'status': 'ok', 'stream_url': embed_url, 'type': 'iframe'})
            
        elif source == 'animego':
            voices = animego.get_voices(str(kp_id), episode)
            if voices and 'voices' in voices and len(voices['voices']) > 0:
                first_voice = voices['voices'][0]
                stream = animego.aniboom_get_stream_for_voice(
                    str(first_voice['translation_id']), 
                    episode, 
                    str(kp_id)
                )
                return jsonify({'status': 'ok', 'stream_url': stream['url'], 'type': stream.get('kind', 'HLS')})
            else:
                return jsonify({'status': 'error', 'message': 'Озвучки не найдены'}), 404
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
