from flask import Flask, request, jsonify
from flask_cors import CORS
from anime_parsers_ru import KodikParser, AnimegoParser, JutsuParser

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

kodik = KodikParser(token=None)
animego = AnimegoParser()
jutsu = JutsuParser()

@app.route('/api/stream', methods=['GET'])
def get_stream():
    source = request.args.get('source', 'kodik').lower()
    kp_id = request.args.get('kp_id')
    episode = int(request.args.get('episode', 1))
    translation_id = request.args.get('translation_id', '0')
    
    if not kp_id:
        return jsonify({'status': 'error', 'message': 'Параметр kp_id обязателен'}), 400

    try:
        # 1. Попытка через Kodik m3u8
        if 'kodik' in source or 'dub' in source:
            try:
                m3u8_url = kodik.get_m3u8_playlist_link(
                    str(kp_id), 
                    "kinopoisk", 
                    int(episode), 
                    str(translation_id), 
                    720
                )
                embed_url = kodik.get_embed_link(str(kp_id), "kinopoisk")
                return jsonify({
                    'status': 'ok', 
                    'stream_url': m3u8_url, 
                    'embed_url': embed_url,
                    'type': 'hls'
                })
            except Exception:
                embed_url = kodik.get_embed_link(str(kp_id), "kinopoisk")
                return jsonify({'status': 'ok', 'stream_url': embed_url, 'type': 'iframe'})
            
        # 2. Попытка через Animego
        elif 'animego' in source:
            try:
                voices = animego.get_voices(str(kp_id), episode)
                if voices and 'voices' in voices and len(voices['voices']) > 0:
                    first_voice = voices['voices'][0]
                    stream = animego.aniboom_get_stream_for_voice(
                        str(first_voice['translation_id']), 
                        episode, 
                        str(kp_id)
                    )
                    return jsonify({'status': 'ok', 'stream_url': stream['url'], 'type': stream.get('kind', 'HLS')})
            except Exception:
                pass

        # Fallback для всех остальных случаев (чтобы сервер никогда не возвращал None)
        embed_url = kodik.get_embed_link(str(kp_id), "kinopoisk")
        return jsonify({'status': 'ok', 'stream_url': embed_url, 'type': 'iframe'})
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
