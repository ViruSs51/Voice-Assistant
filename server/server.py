from pathlib import Path
import json
import logging
import sys
import os
from faster_whisper import WhisperModel
from gtts import gTTS
import ollama
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s : %(message)s',
    handlers=[
        logging.FileHandler('server.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)                   
    ]
)

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "settings" / "config.json"
DATA_PATH = BASE / 'data'
AUDIO_PATH = DATA_PATH / 'received_audio.pcm'

config = None
whisper_model = None

app = FastAPI()


def load_config():
    logging.info('Load config')
    global config

    with open(CONFIG_PATH, 'r', encoding='UTF-8') as conf:
        config = json.loads(conf.read())

def save_config():
    logging.info('Update config')
    with open(CONFIG_PATH, 'w', encoding='UTF-8') as conf:
        conf.write(json.dumps(config, indent=4))

def CLI_interface():
    global config

    print('\nWelcome to the Voice Assistant!\n\nType "help" for more details.\n\n')

    run = True
    while run:
        cmd = input('>>> ').split()

        if not cmd: continue
        if cmd[0] == 'help':
            print('''More details:
    run - Running server.
    conf - Show config of server.
    update [param] - Set a new value for config.
    quit - Quit server
''')
        elif cmd[0] == 'run': run = False
        elif cmd[0] == 'conf': print(json.dumps(config, indent=4, ensure_ascii=False))
        elif cmd[0] == 'update':
            if len(cmd) != 2:
                print('Error: Incorect syntax for "update" command!\n')
                continue
                
            if not config.get(cmd[1]):
                print(f'Error: The parameter "{cmd[1]}" does not exist or is not updatable!\n')
                continue
            
            print(f'Select new value for "{cmd[1]}":')
            if cmd[1] == 'whisper_device_type': print('- cpu\n- cuda\n')
            
            value = input('> ')

            if cmd[1] == 'whisper_device_type' and not value in ['cpu', 'cuda']: 
                print('Error: Incorect value for parameter!')
                continue

            config.update({cmd[1]: value})
            save_config()

        elif cmd[0] == 'quit':
            quit()
        else:
            print(f'Error: "{cmd[0]}" is not a command!\n')

def init_models():
    global whisper_model
    logging.info('Initialise models')

    whisper_model = WhisperModel(
        'base', 
        device=config['whisper_device_type'], 
        compute_type='int8')
    


def speech_to_text_ro(path: Path) -> str:
    logging.info('Convert speech to text')

    segments, info = whisper_model.transcribe(
        path, 
        beam_size=11,
        language='ro', 
        vad_filter=True)

    texts = []
    for segment in segments:
        texts.append(segment.text)

    return '. '.join(texts)


def text_to_speech_ro(text_to_speak, output_file="response.wav"):
    logging.info("Convert text to speech")
    tts = gTTS(text=text_to_speak, lang='ro')

    tts.save(DATA_PATH / output_file)
    logging.info(f'Saved audio file to data/{output_file}')

def call_llm(prompt: str):
    logging.info(f'Call {config['llm_model']} LLM Model')
    response = ollama.chat(
    model=config['llm_model'], 
    messages=[
            {
                'role': 'system', 
                'content': config['llm_system_prompt']
            },
            {
                'role': 'user', 
                'content': prompt
            }
        ]
    )

    return response['message']['content']

@app.websocket('/ws/audio')
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logging.info('ESP32 Connected!')

    audio_file = open(AUDIO_PATH, 'wb')

    try:
        while True:
            data = await websocket.receive()

            if 'bytes' in data:
                audio_file.write(data['bytes'])

            elif 'text' in data:
                pass
            
    except WebSocketDisconnect:
        logging.warning('ESP32 Disconnected')
    finally:
        if not audio_file.closed:
            audio_file.close()
            

def main(): 
    logging.info('Start Voice Assistant')
    load_config()
    init_models()
    CLI_interface()

    uvicorn.run(app, host='0.0.0.0', port=8000)


if __name__ == '__main__':
    main()