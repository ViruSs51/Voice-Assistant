#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <driver/i2s.h>

#define AUDIO_PORT I2S_NUM_0

const char* ssid     = "WI-FI";
const char* password = "PASSWORD";
const char* server_ip   = "IP ADDRESS"; 
const int server_port   = 8000;

WebSocketsClient webSocket;

#define I2S_MIC_WS   15   
#define I2S_MIC_SCK  14   
#define I2S_MIC_SD   32   

#define BUFFER_SIZE 1024
uint8_t i2s_buffer[BUFFER_SIZE];

bool isSpeaking = false; 
size_t bytes_written_total = 0;

void stopI2SAudio() {
    i2s_driver_uninstall(AUDIO_PORT);
}

void startSpeakerMode() {
    isSpeaking = true;
    stopI2SAudio();

    i2s_config_t i2s_config = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX | I2S_MODE_DAC_BUILT_IN),
        .sample_rate = 16000,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 16,
        .dma_buf_len = 512,
        .use_apll = true, 
    };
    
    i2s_driver_install(AUDIO_PORT, &i2s_config, 0, NULL);
    i2s_set_pin(AUDIO_PORT, NULL);
    i2s_set_dac_mode(I2S_DAC_CHANNEL_RIGHT_EN);
}

void startMicrophoneMode() {
    stopI2SAudio(); 

    i2s_config_t i2s_config = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX), 
        .sample_rate = 16000,                                 
        .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,       
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,        
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,  
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,           
        .dma_buf_count = 4,                                 
        .dma_buf_len = 512,                                 
        .use_apll = false,
        .tx_desc_auto_clear = false,
        .fixed_mclk = 0
    };

    i2s_pin_config_t pin_config = {
        .bck_io_num = I2S_MIC_SCK,
        .ws_io_num = I2S_MIC_WS,
        .data_out_num = I2S_PIN_NO_CHANGE, 
        .data_in_num = I2S_MIC_SD
    };

    i2s_driver_install(AUDIO_PORT, &i2s_config, 0, NULL);
    i2s_set_pin(AUDIO_PORT, &pin_config);
    i2s_zero_dma_buffer(AUDIO_PORT);

    isSpeaking = false; 
}

void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
    switch(type) {
        case WStype_TEXT: {
            String msg = String((char*)payload);
            
            if (msg == "WOKE_UP") {
                Serial.println("[WS] Server woke up device. Starting microphone...");
                startMicrophoneMode();
            }
            else if (msg == "CANCEL" || msg == "RESET") {
                Serial.println("[WS] Resetting state. Switching to listening mode...");
                startMicrophoneMode();
            }
            else if (msg == "START_SPEAKING") { 
                Serial.println("[WS] Server audio streaming started. Switching to speaker...");
                startSpeakerMode();
            }
            else if (msg == "END_SPEAKING") {
                isSpeaking = false;
                Serial.println("[WS] Server audio streaming ended. Switching to microphone...");
                i2s_zero_dma_buffer((i2s_port_t)0);
                startMicrophoneMode();
            }
            break;
        }

        case WStype_BIN:
            if (isSpeaking) {
                int16_t* samples = (int16_t*)payload;
                size_t sample_count = length / 2;
              
                for (size_t i = 0; i < sample_count; i++) {
                    samples[i] ^= 0x8000;
                }

                size_t bytes_written;
                esp_err_t err = i2s_write(AUDIO_PORT, payload, length, &bytes_written, pdMS_TO_TICKS(100));
                
                static size_t total_written = 0;
                total_written += bytes_written;
                
                if (total_written % 20480 == 0) {  
                    Serial.printf("[I2S] Total bytes written: %d\n", total_written);
                }
                
                if (err != ESP_OK) {
                    Serial.printf("[ERROR] I2S write failed: %d\n", err);
                }
            }
            break;
            
        case WStype_DISCONNECTED:
            Serial.println("[WS] Disconnected from server!");
            isSpeaking = false;
            break;
            
        case WStype_CONNECTED:
            Serial.println("[WS] Connected to server successfully.");
            break;
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    
    Serial.printf("\n[WIFI] Connecting to SSID: %s ", ssid);
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) { 
        delay(500); 
        Serial.print("."); 
    }
    Serial.println("\n[WIFI] Connected successfully.");
    Serial.print("[WIFI] ESP32 IP Address: ");
    Serial.println(WiFi.localIP());

    Serial.println("[I2S] Initializing assistant in Microphone mode...");
    startMicrophoneMode();
    Serial.println("[I2S] Device is ready for commands.");

    webSocket.begin(server_ip, server_port, "/ws/audio");
    webSocket.onEvent(webSocketEvent);
    webSocket.setReconnectInterval(5000); 
}

void loop() {
    webSocket.loop();

    if (webSocket.isConnected() && !isSpeaking) {
        size_t bytes_read = 0;
        
        esp_err_t result = i2s_read(AUDIO_PORT, &i2s_buffer, BUFFER_SIZE, &bytes_read, 10 / portTICK_PERIOD_MS);
        
        if (result == ESP_OK && bytes_read > 0 && !isSpeaking) {
            webSocket.sendBIN(i2s_buffer, bytes_read);
        }
    } else if (!webSocket.isConnected()) {
        delay(10); 
    }

    unsigned long curent_ms = millis();
    static unsigned long trecut_ms = 0;
    if (curent_ms - trecut_ms > 5) {
        vTaskDelay(1);
        trecut_ms = curent_ms;
    }
}