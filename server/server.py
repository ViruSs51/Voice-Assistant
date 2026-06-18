from pathlib import Path
import json
import logging
import sys
import os
import asyncio
import struct
import math
import subprocess
import wave
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
WAV_OUTPUT_PATH = DATA_PATH / 'command.wav'
AUDIO_RESPONSE_PATH = DATA_PATH / 'response.mp3'
WAV_AUDIO_RESPONSE_PATH = DATA_PATH / 'response.wav'

DATA_PATH.mkdir(parents=True, exist_ok=True)

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
        'small', 
        device=config['whisper_device_type'], 
        compute_type='int8')
    
def pcm_to_wav(pcm_data: bytes, output_path: Path):
    with wave.open(str(output_path), 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  
        wav_file.setframerate(16000)  
        wav_file.writeframes(pcm_data)

def speech_to_text_ro(path: Path) -> str:
    logging.info('Convert speech to text')
    segments, info = whisper_model.transcribe(path, beam_size=7, language='ro', vad_filter=True)
    return '. '.join([segment.text for segment in segments])

def text_to_speech_ro(text_to_speak, output_file):
    logging.info("Convert text to speech")
    tts = gTTS(text=text_to_speak, lang='ro')
    tts.save(str(output_file))

def call_llm(prompt: str):
    logging.info(f"Call {config['llm_model']} LLM Model")
    response = ollama.chat(
        model=config['llm_model'], 
        messages=[
            {'role': 'system', 'content': config['llm_system_prompt']},
            {'role': 'user', 'content': prompt}
        ]
    )
    return response['message']['content']

def prepare_response():
    subprocess.run([
        "ffmpeg", "-y", "-i", str(AUDIO_RESPONSE_PATH), 
        "-f", "wav", "-ac", "2", "-ar", "16000", "-acodec", "pcm_s16le",
        str(WAV_AUDIO_RESPONSE_PATH)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    logging.info("Audio response converted to WAV (Stereo)")

async def process_and_respond(websocket: WebSocket, command_audio: bytes):
    try:
        await asyncio.to_thread(pcm_to_wav, command_audio, WAV_OUTPUT_PATH)
        user_prompt = await asyncio.to_thread(speech_to_text_ro, WAV_OUTPUT_PATH)
        
        if user_prompt and len(user_prompt.strip()) > 2:
            logging.info(f'[User Command]: {user_prompt}')
            
            llm_response = await asyncio.to_thread(call_llm, user_prompt)
            logging.info(f'[LLM Response]: {llm_response}')
            
            await asyncio.to_thread(text_to_speech_ro, llm_response, AUDIO_RESPONSE_PATH)
            await asyncio.to_thread(prepare_response)

            if not WAV_AUDIO_RESPONSE_PATH.exists():
                logging.error("WAV file do not generated!")
                await websocket.send_text('CANCEL')
                return

            with wave.open(str(WAV_AUDIO_RESPONSE_PATH), "rb") as wav_file:
                n_frames = wav_file.getnframes()
                pcm_data = wav_file.readframes(n_frames)

            await websocket.send_text("START_SPEAKING")
            await asyncio.sleep(0.2) 

            chunk_size = 2048  
            logging.info(f"Start sending audio: {len(pcm_data)} bytes")
            
            for i in range(0, len(pcm_data), chunk_size):
                chunk = pcm_data[i:i+chunk_size]
                await websocket.send_bytes(chunk)
                
                await asyncio.sleep(0.029) 

            await asyncio.sleep(0.5) 
            await websocket.send_text("END_SPEAKING")
            logging.info("[Server]: Sent END_SPEAKING to ESP32")
        else:
            logging.warning('A pause was detected, but no text was recognized. Resetting.')
            await websocket.send_text('CANCEL')
            
    except Exception as e:
        logging.error(f"Processing error: {e}")
        try:
            await websocket.send_text('CANCEL')
        except:
            pass

@app.websocket('/ws/audio')
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logging.info('ESP32 Connected!')

    pcm_buffer = bytearray()
    is_recording_command = False
    silence_packet_counter = 0
    
    SILENCE_THRESHOLD = 800
    SILENCE_DURATION_LIMIT = 1.5
    max_silence_packets = int(SILENCE_DURATION_LIMIT / 0.032)
    
    processing_task = None

    try:
        while True:
            data = await websocket.receive()

            if data.get("type") == "websocket.disconnect":
                logging.warning("ESP32 Deconnected")
                break

            if 'bytes' in data:
                chunk = data['bytes']
                
                if processing_task and not processing_task.done():
                    continue

                pcm_buffer.extend(chunk)

                if not is_recording_command and len(pcm_buffer) >= 80000:
                    temp_pcm = bytes(pcm_buffer)
                    pcm_to_wav(temp_pcm, WAV_OUTPUT_PATH)

                    detected_text = await asyncio.to_thread(speech_to_text_ro, WAV_OUTPUT_PATH)
                    logging.info(f'[Scanning] Whisper detected: "{detected_text}"')
                    normalized_text = detected_text.lower().replace(',', '').replace('.', '')

                    if any(word in normalized_text for word in ['salut', 'marius', 'iulian']):
                        logging.info('WAKE WORD DETECTED "Okay Bro" !!!')
                        await websocket.send_text("WOKE_UP")
                        is_recording_command = True
                        pcm_buffer = bytearray()
                        silence_packet_counter = 0
                    else:
                        pcm_buffer = pcm_buffer[-16000:]

                elif is_recording_command:
                    count = len(chunk) // 2
                    if count > 0:
                        shorts = struct.unpack(f'{count}h', chunk)
                        sum_squares = sum(s ** 2 for s in shorts)
                        rms = math.sqrt(sum_squares / count)

                        if rms < SILENCE_THRESHOLD:
                            silence_packet_counter += 1
                        else:
                            silence_packet_counter = 0
                    
                    if silence_packet_counter >= max_silence_packets:
                        logging.info(f'Detected pause {SILENCE_DURATION_LIMIT}s. Starting Background Processing!')
                        
                        bytes_to_cut = max_silence_packets * 1024
                        command_audio = bytes(pcm_buffer[:-bytes_to_cut]) if len(pcm_buffer) > bytes_to_cut else bytes(pcm_buffer)
                        
                        processing_task = asyncio.create_task(process_and_respond(websocket, command_audio))
                    
                        pcm_buffer = bytearray()
                        is_recording_command = False
                        silence_packet_counter = 0

            elif 'text' in data:
                logging.info(f'Message from ESP32: {data["text"]}')
            
    except WebSocketDisconnect:
        logging.warning('ESP32 Disconnected via Exception')
    finally:
        if processing_task and not processing_task.done():
            processing_task.cancel()

def main(): 
    logging.info('Start Voice Assistant')
    load_config()
    init_models()
    CLI_interface()
    uvicorn.run(app, host='0.0.0.0', port=8000)

if __name__ == '__main__':
    main()