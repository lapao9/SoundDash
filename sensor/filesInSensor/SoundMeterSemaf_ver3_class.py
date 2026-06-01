
import sounddevice as sd
import numpy as np
import threading
from threading import Thread

import queue
from multiprocessing import Process, Event
from multiprocessing.queues import Empty
from multiprocessing import Queue as MPQueue
from multiprocessing import Value
from multiprocessing import Lock

from ctypes import c_double

from scipy.io.wavfile import write as write_wav
from scipy.signal import sosfilt, lfilter
from scipy.signal import stft, istft
from scipy.fft import rfft, irfft


#from pydub import AudioSegment
#from pydub.utils import which
import lameenc

import FilterCoefs_48000
import time
from datetime import datetime
from time import sleep

import os

import csv

import matplotlib.pyplot as plt

import ctypes

#Inicio codigo
#pip install paho-mqtt
import paho.mqtt.client as mqtt

import json
from types import SimpleNamespace

#import numpy as np
import tensorflow as tf
import pandas as pd

#import multiprocessing as mp
#mp.set_start_method('spawn', force=True)

from yamnet_worker import yamnet_worker

#print("Using ffmpeg:", which("ffmpeg"))

##from gpiozero import LED
#import RPi.GPIO as GPIO
#import tm1637

#imports para atualizar o senso através da pagina de acesso técnico na app
from station_config_receiver import StationConfigReceiver


# ================================================================
# ===== CONFIG =====
# ================================================================

with open("SoundMeterSemaf_config.json") as f:
    data = json.load(f)

config = json.loads(json.dumps(data), object_hook=lambda d: SimpleNamespace(**d))

print(config.audio.sample_rate)
print(config.config_flags.save_audiofile_ok)

#Para receber novas configurações da app:
sensor_id = config.station.sensor_ID
config_receiver = StationConfigReceiver(
    sensor_id=sensor_id,
    config_file_path='SoundMeterSemaf_config.json',
    mqtt_broker='10.64.137.6',
    mqtt_port=1884
)

config_thread = threading.Thread(target=config_receiver.start, daemon=True)
config_thread.start()
print(f"[Main] Config receiver iniciado para sensor {sensor_id}")
    

#"station"
SENSOR_ID = config.station.sensor_ID
LOCAL_INFO = config.station.local_Info
LOCAL_LAT = config.station.local_Lat
LOCAL_LONG = config.station.local_Long
LOCAL_ALT = config.station.local_Alt

#"audio"
SAMPLE_RATE = config.audio.sample_rate
CHANNELS = config.audio.channels
DTYPE = config.audio.dtype
CHUNK_SIZE = config.audio.chunk_size
NBITS = config.audio.nbits
difOutIndB = config.audio.dif_out_in_db
TARGET_DEVICE_NAME = config.audio.target_device_name

#"timing"
FILE_DURATION = config.timing.file_duration                     # Duração de cada ficheiro
SESSION_DURATION = config.timing.session_duration               # Duração total da sessão de gravação
SEGMENT_DURATION = config.timing.segment_duration               # Periodicidade de medição de cada nível sonoro (seg)
PERCENTIL_DURATION_LAxx = config.timing.percentil_duration_laxx # Tempo para cálculo do percentil LA90 ou outro - ruído de fundo
TIME_CSV_STORE = config.timing.time_csv_store                   # Periodicidade de escrita no CSV (multiplos de SEGMENT_DURATION)
FILE_DURATION_CSV = config.timing.file_duration_csv             # Duração de cada ficheiro CSV
LINES_PER_CSV = FILE_DURATION_CSV * (1/SEGMENT_DURATION)        # Num Linhas por cada CSV

#"audio_save"
FILE_PREFIX = config.audio_save.file_prefix
BITRATE = config.audio_save.bitrate                             # kbps Para gravação .mp3 c/ LAME
#BITRATE = "128k"                                               # Para gravação .mp3 c/ ffmpeg

#"levels"
CAL94 = config.levels.cal94
Pref = config.levels.pref
N_13OCTAVE_BANDS = config.levels.n_13octave_bands

#"noise_reduction"
REDUCTION_FACTOR = config.noise_reduction.reduction_factor
initial_noise_frames = config.noise_reduction.initial_noise_frames

#"percentil_noise"
PERCENTIL_VALUE = config.percentil_noise.percentil_value                # define the value of percentil LA70
THRESHOLD_EVENT_OFFSET = config.percentil_noise.threshold_event_offset  # Level for sound event detection
Percentil_LAxx = config.percentil_noise.percentil_LAxx                  # Nível inicial do LAxx

#"output"
output_path = config.output.path
outputDIR_CSV = config.output.dir_csv
outputDIR_Waves = config.output.dir_waves

os.makedirs("outputDIR_CSV", exist_ok=True)
os.makedirs("outputDIR_Waves", exist_ok=True)

#"leds_display"
LEVEL_LED_GREEN = config.leds_display.level_led_green
LEVEL_LED_GREEN_YELLOW = config.leds_display.level_led_green_yellow
LEVEL_LED_YELLOW = config.leds_display.level_led_yellow
LEVEL_LED_YELLOW_RED = config.leds_display.level_led_yellow_red

LED_GR = config.leds_display.gpio_green
LED_YE = config.leds_display.gpio_yellow
LED_RD = config.leds_display.gpio_red

#"mqtt"
MQTT_BROKER = config.mqtt.broker
MQTT_BROKER2 = config.mqtt.broker2

MQTT_PORT = config.mqtt.port
MQTT_TOPIC = config.mqtt.topic
print('MQTT_BROKER: ', MQTT_BROKER)
print('MQTT_PORT: ', MQTT_PORT)
print('MQTT_TOPIC: ', MQTT_TOPIC)


#"config_flags"
plots_OK = config.config_flags.plots_ok
SaveAudiofile_OK = config.config_flags.save_audiofile_ok
Noise_TimeLine_OK = config.config_flags.noise_timeline_ok
EchoShort_OK = config.config_flags.echo_short_ok
EchoComplete_OK = config.config_flags.echo_complete_ok
ShowLEDsDisplay_OK = config.config_flags.show_leds_display_ok
NoiseReduction_OK = config.config_flags.noise_reduction_ok
Publica_MQTT_OK = config.config_flags.publica_mqtt_ok
PlatMAC = config.config_flags.plat_mac
SoundEvent_OK = config.config_flags.sound_classification_ok

#"sound_event_detect"
MODEL_PATH = config.sound_event_detect.model_path
LABELS_CSV = config.sound_event_detect.classes
FAMILIA_CSV = config.sound_event_detect.family_map
PESOS_CSV = config.sound_event_detect.weight_map
BLACKLIST = config.sound_event_detect.blacklist
FactMUSIC = config.sound_event_detect.reduce_Eventmusic

sizeEvent = config.sound_event_detect.size_event

label_df = pd.read_csv(LABELS_CSV)
name_to_index = dict(zip(label_df["display_name"], label_df["index"]))


#SAMPLE_RATE = 48000
#CHANNELS = 1
#DTYPE = 'int16'
#FILE_DURATION = 1*30*60                                     # Duração de cada ficheiro
#SESSION_DURATION = 10+16*60*60                              # Duração total da sessão de gravação
#SEGMENT_DURATION = 1/16                                     # Periodicidade de medição de cada nível sonoro (seg)
#PERCENTIL_DURATION_LAxx = 15*60                             # Tempo para cálculo do percentil LA90 ou outro - ruído de fundo
#TIME_CSV_STORE = 10*(1/SEGMENT_DURATION)                    # Periodicidade de escrita no CSV (multiplos de SEGMENT_DURATION)
#FILE_DURATION_CSV = 1*30*60                                 # Duração de cada ficheiro CSV
#LINES_PER_CSV = FILE_DURATION_CSV * (1/SEGMENT_DURATION)    # Num Linhas por cada CSV

#FILE_PREFIX = 'chunk'
##BITRATE = "128k"                                           # Para gravação .mp3 c/ ffmpeg
#BITRATE = 128                                               # kbps Para gravação .mp3 c/ LAME
#CHUNK_SIZE = int(2*512)                                     # Bloco de aquisição do interface de áudio
#NBITS = 16
#CAL94 = 94

#Pref = 20e-6

#N_13OCTAVE_BANDS = 30

SEGMENT_SIZE = int(SEGMENT_DURATION * SAMPLE_RATE)

SAMPLES_PER_BLOCK_FILE = 10 * SEGMENT_SIZE
SAMPLES_PER_BLOCK_EVENT = int(sizeEvent * SAMPLE_RATE)
SAMPLES_PER_FILE = int(FILE_DURATION * SAMPLE_RATE)

SEGMENTS_PERCENTIL_LAxx = PERCENTIL_DURATION_LAxx * (1/SEGMENT_DURATION) # 

cntSegmBegin = 0 # Used to average on Leq sound levels (nº of segment from the beginning of the session)

countBlock = 0
counter_CSV = 0
counter_File_CSV = 0

counter_JSON = 0

counterPercentil_LAxx = 0

#BUFFER_SIZE = (SEGMENT_SIZE + CHUNK_SIZE) #10000 # FIFO of ringbuffer
BUFFER_SIZE = (SEGMENT_SIZE) #10000 # FIFO of ringbuffer
# (its bigger than SEGMENT_SIZE because SEGMENT_SIZE could not be an integer multiple of CHUNK_SIZE)
#BUFFER_SIZE_OCT = (SEGMENT_SIZE + CHUNK_SIZE) * N_OCTAVE_BANDS #1000   # frames
#BUFFER_SIZE_13OCT = (SEGMENT_SIZE + CHUNK_SIZE) * N_13OCTAVE_BANDS #1000   # frames

#PERCENTIL_VALUE = 30 # define the value of percentil LA70
#THRESHOLD_EVENT_OFFSET = 10 # Level for sound event detection
#Percentil_LAxx = 40
#Percentil = []


# Search for the desired input device by name substring
# "Built-in Microphon"  - microfone do PC
# "CM477-30757"         - USB + mic Primo/Senheiser lapela
# "USB PnP"              - mic 'USB PnP Sound Device'

#TARGET_DEVICE_NAME = "Built-in Microphon" 

#REDUCTION_FACTOR = 1.0

#plots_OK = False
#SaveAudiofile_OK = True
#Noise_TimeLine_OK = False
#EchoShort_OK = True
#EchoComplete_OK = False

#ShowLEDsDisplay_OK =False

#NoiseReduction_OK = True

#Publica_MQTT_OK = False

#PlatMAC = True


if ShowLEDsDisplay_OK:
    print('ShowLEDsDisplay_OK: ====1')

    #from gpiozero import LED
    import RPi.GPIO as GPIO
    import tm1637

'''
if Publica_MQTT_OK:
    print('MQTT_BROKER', MQTT_BROKER)
    print('MQTT_PORT', MQTT_PORT)

    #client = mqtt.Client(callback_api_version=2)
    client = mqtt.Client()
    client2 = mqtt.Client()

    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client2.connect(MQTT_BROKER2, MQTT_PORT, 60)
'''

    #converter linha csv para json
    #json que resulta publica 
    #client.publish(mqtt_topic, json_string)
'''    
def publish_rows(rows):
    payload = json.dumps(rows)
    client.publish(MQTT_TOPIC, payload)
'''

Echo_RefreshTimes = 1  # De quantas em quantas vezes dados são ecoados para o ecran relativo ao cálculo dos NoiseLevels (segmentos)

#samples_written = 0 # FIFO of ringbuffer
#samples_read = 0 # FIFO of ringbuffer

write_index = 0 # FIFO of ringbuffer
read_index = 0 # FIFO of ringbuffer
available_samples = 0 # FIFO of ringbuffer

#===== Noise Reduction

#initial_noise_frames = 60  # nº de blocos para extração da amostra de ruído de fundo - Noise Reduction
# Set a threshold factor (e.g., 1.5 times the mean noise per freq)
threshold_factor = 1.0          #- Noise Reduction

hop_size = int(CHUNK_SIZE/2)    #- Noise Reduction

threshold = []

# Variables for noise estimation
noise_estimate = None
noise_magnitudes = []
noise_frames_collected = 0

# Store raw and processed chunks
original_chunks = []
processed_chunks = []

#======



# Shared data container
#SPLReal = None
lock = threading.Lock()

SPLReal_shared = Value(c_double, 0.0)
spl_lock = Lock()

#RECORD_SECONDS =8*60*60 # Tempo de gravação ou Tempo de análise de ficheiro (seg)

#output_path = '/Users/joelpaulo/Documents/ISEL/Projects2024_2025/ProjetosEscolhidos/StereoMic/'


#outputDIR_CSV = 'outputDIR_CSV'
#os.makedirs("outputDIR_CSV", exist_ok=True)
#outputDIR_Waves = 'outputDIR_Waves'
#os.makedirs("outputDIR_Waves", exist_ok=True)


#=================================================
#=======================ATENÇÃO - INICIALIZAÇÃO ==========================
#=================================================
cntSegmBeginOffSetIni = 0 #320         # Usado para inicializar o contador de buffers processados até ao momento
                                    # Usado para inicializar os valores dos níveis processados até ao momento
LZeq_dB_Ini = 0                  # Colocar 0 se for o 1º ficheiro
LCeq_dB_Ini = 0                  # Colocar 0 se for o 1º ficheiro
LAeq_dB_Ini = 0                  # Colocar 0 se for o 1º ficheiro

LCpeakT_dB_Last = 0              # Colocar 0 se for o 1º ficheiro

                                    # permite analizar as gravações por ficheiros mais pequenos
                                    # para o 1º ficheiro, este valor é 0. Este valor é retirado do ficheiro csv
#=================================================

#=================================================

#=== para simular o valor prms do calibrador

f = 1000
n = np.arange(0, 1, 1/SAMPLE_RATE)
Amp = 0.1
#xCAL = 0.165*np.sin(2*np.pi*f*n)      # 0.126 é equivalente ao que está no ficheiro WAVE 'TestNoise.wav'
                                        # 0.112 é equivalente ao mic 'USB PnP Sound Device'
                                        # 0.0112 é equivalente ao mic 'QUAD-CAPTURE' (botão sensibilidade a meio - canal 1)
                                        # 0.16 é equivalente ao mic 'PC'
                                        # 0.165 é equivalente ao que está no ficheiro WAVE HospEMoniz
                                        # 0.425 é equivalente ao que está no ficheiro WAVE HospEMoniz_Captacoes_20a28_12_2024

xCAL = Amp*np.sin(2*np.pi*f*n)

PcalrmsRef = np.sqrt(np.mean(xCAL**2))  # Valor de pressão sonora do calibrador calculada na DAW

print( "PcalrmsRef",PcalrmsRef)
print( "PcalrmsRef_dB", 20*np.log10(PcalrmsRef/Pref))


# difOutIndB = -2.0 é equivalente ao mic 'USB PnP Sound Device' LogiLink
# difOutIndB = -5 é equivalente ao mic 'CM477-30757' USB + mic Primo lapela 
# difOutIndB = 1.5 é equivalente ao mic 'CM477-30757' USB + mic Sennheiser lapela 


# difOutIndB = 10 é equivalente ao mic 'PC'

#difOutIndB = 10

Pcalrms = PcalrmsRef * 10**(difOutIndB/20) # difOutIndB = 20*np.log10(Pcalrms/PcalrmsRef)) -> Pcalrms/PcalrmsRef = 10^(difOutIndB/20) -> 

#=== para simular o valor prms do calibrador


# === Load the C libraries ===
if PlatMAC:
      # .dylib for MacOS
    lib = ctypes.CDLL('./libringbuffer_fifo.dylib')
    lib_13Oct = ctypes.CDLL('./libringbuffer_fifo_13Oct.dylib')
    lib_filters = ctypes.CDLL('./libtob_filterbank.dylib')
    lib_NoiseLevels = ctypes.CDLL('./libnoiseprocess13Oct_ver3_float.dylib')
    lib_filterbankSquared = ctypes.CDLL('./libtob_filterbankSquared.dylib')
    lib_TimeWeightFilter = ctypes.CDLL('./libtime_weight.dylib')
    
else:
    # .so for Linux/Raspberry Pi    
    lib = ctypes.CDLL('./libringbuffer_fifo.so')
    lib_13Oct = ctypes.CDLL('./libringbuffer_fifo_13Oct.so')
    lib_filters = ctypes.CDLL('./libtob_filterbank.so')
    lib_NoiseLevels = ctypes.CDLL('./libnoiseprocess13Oct_ver3_float.so')
    lib_filterbankSquared = ctypes.CDLL('./libtob_filterbankSquared.so')
    lib_TimeWeightFilter = ctypes.CDLL('./libtime_weight.so')
'''
# === Load the C library ===
lib = ctypes.CDLL('./libringbuffer_fifo.dylib')
#lib = ctypes.CDLL('./libringbuffer_fifo.so')
'''
class RingBufferFIFO(ctypes.Structure):
    pass

lib.ringbuffer_fifo_create.argtypes = [ctypes.c_size_t]
lib.ringbuffer_fifo_create.restype = ctypes.POINTER(RingBufferFIFO)

lib.ringbuffer_fifo_free.argtypes = [ctypes.POINTER(RingBufferFIFO)]

lib.ringbuffer_fifo_write.argtypes = [ctypes.POINTER(RingBufferFIFO),
    ctypes.POINTER(ctypes.c_float), ctypes.c_size_t]
lib.ringbuffer_fifo_write.restype = ctypes.c_size_t

lib.ringbuffer_fifo_peek.argtypes = [ctypes.POINTER(RingBufferFIFO),
    ctypes.POINTER(ctypes.c_float), ctypes.c_size_t, ctypes.c_size_t]
lib.ringbuffer_fifo_peek.restype = ctypes.c_size_t


# Load the shared library
'''
libname = './libringbuffer_fifo_13Oct.dylib'  # or .so for Linux/Raspberry Pi
#libname = './libringbuffer_fifo_13Oct.so'  # or .so for Linux/Raspberry Pi

lib_13Oct = ctypes.CDLL(libname)
'''
# C Struct 13Oct Bank Filters
class RingBufferFIFO_13Oct(ctypes.Structure):
    _fields_ = [("buffer", ctypes.POINTER(ctypes.c_float)),
                ("size", ctypes.c_size_t),
                ("write_index", ctypes.c_size_t),
                ("read_index", ctypes.c_size_t)]

# Function signatures
lib_13Oct.ringbuffer_fifo_create.argtypes = [ctypes.c_size_t]
lib_13Oct.ringbuffer_fifo_create.restype = ctypes.POINTER(RingBufferFIFO_13Oct)

lib_13Oct.ringbuffer_fifo_free.argtypes = [ctypes.POINTER(RingBufferFIFO_13Oct)]

lib_13Oct.ringbuffer_fifo_write.argtypes = [ctypes.POINTER(RingBufferFIFO_13Oct),
    ctypes.POINTER(ctypes.c_float), ctypes.c_size_t]
lib_13Oct.ringbuffer_fifo_write.restype = ctypes.c_size_t

lib_13Oct.ringbuffer_fifo_read.argtypes = [ctypes.POINTER(RingBufferFIFO_13Oct),
    ctypes.POINTER(ctypes.c_float), ctypes.c_size_t]
lib_13Oct.ringbuffer_fifo_read.restype = ctypes.c_size_t


# Load the shared lib_NoiseLevels - Biblioteca para a função process_block_Levels()
'''
libname = './libnoiseprocess13Oct_ver2.dylib'  # or .so for Linux/Raspberry Pi
#libname = './libnoiseprocess13Oct.so'  # or .so for Linux/Raspberry Pi
lib_NoiseLevels = ctypes.CDLL(libname)
'''
# Define argument types
lib_NoiseLevels.process_block_Levels.argtypes = [
    ctypes.c_float,       # Pcal_rms
    ctypes.c_int32,        # cntSegmBg
    ctypes.c_int32,        # cntSegmBeginOffSet
    ctypes.c_float,       # LZpeakTLast
    ctypes.c_float,       # LCpeakTLast
    ctypes.c_float,       # LApeakTLast
    ctypes.c_float,       # LAFmaxTLast
    ctypes.c_float,       # LAFminTLast
    ctypes.c_float,       # LZpLast
    ctypes.c_float,       # LCpLast
    ctypes.c_float,       # LApLast
    ctypes.POINTER(ctypes.c_float), # bufZW
    ctypes.POINTER(ctypes.c_float), # bufCW
    ctypes.POINTER(ctypes.c_float), # bufAW
    ctypes.POINTER(ctypes.c_float), # bufZWTW
    ctypes.POINTER(ctypes.c_float), # bufCWTW
    ctypes.POINTER(ctypes.c_float), # bufAWTW
    ctypes.POINTER(ctypes.c_float), # bufZWTW_13Oct
    ctypes.POINTER(ctypes.c_float), # bufAWTW_SLOW  # Alarms
    ctypes.c_int32,        # SEGMENT_SIZE
    ctypes.c_int32,        # N_13OCTAVE_BANDS
    ctypes.c_float,       # CAL94
    ctypes.POINTER(ctypes.c_float), # NoiLevls_dB
    ctypes.POINTER(ctypes.c_float), # Noi_Lin
]

# Load the shared lib_filters - Biblioteca para a função process_block()
'''
lib_filters = ctypes.CDLL('./libtob_filterbank.dylib')
#lib_filters = ctypes.CDLL('./libtob_filterbank.so')
'''
lib_filters.init_filters.restype = None
lib_filters.process_block.restype = None

# Define argument types
lib_filters.process_block.argtypes = [
    np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags='C_CONTIGUOUS'),  # input array
    np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags='C_CONTIGUOUS'),  # output array
    ctypes.c_size_t
]

# Load your library - Biblioteca para a função 13OctSquared()
'''
lib_filterbankSquared = ctypes.CDLL('./libtob_filterbankSquared.dylib')  # or './libyourlib.so' on Linux
#lib_filterbankSquared = ctypes.CDLL('./libtob_filterbankSquared.so')  # or './libyourlib.so' on Linux
'''
# Set argument types
lib_filterbankSquared.process_block_square_columns.argtypes = [
    np.ctypeslib.ndpointer(dtype=np.float32, ndim=2, flags='C_CONTIGUOUS'),
    ctypes.c_int,
    ctypes.c_int
]


# Load the shared lib_filters - Biblioteca para a função process_time_weight_block()
'''
lib_TimeWeightFilter = ctypes.CDLL('./libtime_weight.dylib')  # or .so
#lib_TimeWeightFilter = ctypes.CDLL('./libtime_weight.so')  # or .so
'''
# Set argument types
lib_TimeWeightFilter.init_time_weight_filters.argtypes = [
    ctypes.c_int,
    np.ctypeslib.ndpointer(dtype=np.float32, ndim=1, flags='C_CONTIGUOUS'),
    np.ctypeslib.ndpointer(dtype=np.float32, ndim=1, flags='C_CONTIGUOUS')
]
lib_TimeWeightFilter.process_time_weight_block.argtypes = [
    np.ctypeslib.ndpointer(dtype=np.float32, ndim=2, flags='C_CONTIGUOUS'),
    ctypes.c_int,
    ctypes.c_int
]


nColumns = 1 + 16 + N_13OCTAVE_BANDS + 2 + 10 + 6 # Added 6 for the top 3 Sound Event Classifications (Name + Score)

Noise_Lin = np.zeros(nColumns, dtype='float32')
NoiseLevels_dB = np.zeros(nColumns, dtype='float32')

Noise_dBTimeLine = np.zeros(nColumns, dtype=np.float32)  # or whatever the length is
Noise_dBTimeLine_buffer = []

Noise_LinTimeLine = np.zeros(nColumns, dtype=np.float32)  # or whatever the length is
Noise_LinTimeLine_buffer = []

# Initialization of levels to consider analysis of separated recorded audio files
#NoiLevls_dB[16] = 20*np.log10(Noi_Lin[16]/Pcal_rms) + Pcal_dB

LZeq_Lin_Ini = Pcalrms * 10 ** ((LZeq_dB_Ini - CAL94)/20)
Noise_LinTimeLine[14] = LZeq_Lin_Ini
Noise_dBTimeLine[14] = LZeq_dB_Ini

LCeq_Lin_Ini = Pcalrms * 10**((LCeq_dB_Ini - CAL94)/20)
Noise_LinTimeLine[15] = LCeq_Lin_Ini
Noise_dBTimeLine[15] = LCeq_dB_Ini

LAeq_Lin_Ini = Pcalrms * 10**((LAeq_dB_Ini - CAL94)/20)
Noise_LinTimeLine[16] = LAeq_Lin_Ini
Noise_dBTimeLine[16] = LAeq_dB_Ini

LZpeakTprmsLast = 0
LApeakTprmsLast = 0
LCpeakTprmsLast = Pcalrms * 10 ** ((LCpeakT_dB_Last - CAL94)/20)
LAFmaxTprmsLast = 0
LAFminTprmsLast = 100
LZprmsLast = 0
LCprmsLast = 0
LAprmsLast = 0


CountringBuff = 0
buffer_CSV = []

current_file = []
current_writer = []

elapsed_timeTimeLine = []


#===== A-Weighting Filter ========
A_WEIGHTED_taps = FilterCoefs_48000.A_WEIGHTED_taps
print('A_WEIGHTED_taps :', A_WEIGHTED_taps)

#===== C-Weighting Filter ========
C_WEIGHTED_taps = FilterCoefs_48000.C_WEIGHTED_taps
print('C_WEIGHTED_taps :', C_WEIGHTED_taps)


#===== 1/3 Octave Filter Bank ========
#global OCTAVE_BAND_1_taps
OCTAVE_BAND13_1_taps = FilterCoefs_48000.OCTAVE_BAND13_1_taps
print('OCTAVE_BAND13_1_taps :', OCTAVE_BAND13_1_taps)
OCTAVE_BAND13_2_taps = FilterCoefs_48000.OCTAVE_BAND13_2_taps
print('OCTAVE_BAND13_2_taps :', OCTAVE_BAND13_2_taps)
OCTAVE_BAND13_3_taps = FilterCoefs_48000.OCTAVE_BAND13_3_taps
print('OCTAVE_BAND13_3_taps :', OCTAVE_BAND13_3_taps)
OCTAVE_BAND13_4_taps = FilterCoefs_48000.OCTAVE_BAND13_4_taps
print('OCTAVE_BAND13_4_taps :', OCTAVE_BAND13_4_taps)
OCTAVE_BAND13_5_taps = FilterCoefs_48000.OCTAVE_BAND13_5_taps
print('OCTAVE_BAND13_5_taps :', OCTAVE_BAND13_5_taps)
OCTAVE_BAND13_6_taps = FilterCoefs_48000.OCTAVE_BAND13_6_taps
print('OCTAVE_BAND13_6_taps :', OCTAVE_BAND13_6_taps)
OCTAVE_BAND13_7_taps = FilterCoefs_48000.OCTAVE_BAND13_7_taps
print('OCTAVE_BAND13_7_taps :', OCTAVE_BAND13_7_taps)
OCTAVE_BAND13_8_taps = FilterCoefs_48000.OCTAVE_BAND13_8_taps
print('OCTAVE_BAND13_8_taps :', OCTAVE_BAND13_8_taps)
OCTAVE_BAND13_9_taps = FilterCoefs_48000.OCTAVE_BAND13_9_taps
print('OCTAVE_BAND13_9_taps :', OCTAVE_BAND13_9_taps)
OCTAVE_BAND13_10_taps = FilterCoefs_48000.OCTAVE_BAND13_10_taps
print('OCTAVE_BAND13_10_taps :', OCTAVE_BAND13_10_taps)
OCTAVE_BAND13_11_taps = FilterCoefs_48000.OCTAVE_BAND13_11_taps
print('OCTAVE_BAND13_11_taps :', OCTAVE_BAND13_11_taps)
OCTAVE_BAND13_12_taps = FilterCoefs_48000.OCTAVE_BAND13_12_taps
print('OCTAVE_BAND13_12_taps :', OCTAVE_BAND13_12_taps)
OCTAVE_BAND13_13_taps = FilterCoefs_48000.OCTAVE_BAND13_13_taps
print('OCTAVE_BAND13_13_taps :', OCTAVE_BAND13_13_taps)
OCTAVE_BAND13_14_taps = FilterCoefs_48000.OCTAVE_BAND13_14_taps
print('OCTAVE_BAND13_14_taps :', OCTAVE_BAND13_14_taps)
OCTAVE_BAND13_15_taps = FilterCoefs_48000.OCTAVE_BAND13_15_taps
print('OCTAVE_BAND13_15_taps :', OCTAVE_BAND13_15_taps)
OCTAVE_BAND13_16_taps = FilterCoefs_48000.OCTAVE_BAND13_16_taps
print('OCTAVE_BAND13_16_taps :', OCTAVE_BAND13_16_taps)
OCTAVE_BAND13_17_taps = FilterCoefs_48000.OCTAVE_BAND13_17_taps
print('OCTAVE_BAND13_17_taps :', OCTAVE_BAND13_17_taps)
OCTAVE_BAND13_18_taps = FilterCoefs_48000.OCTAVE_BAND13_18_taps
print('OCTAVE_BAND13_18_taps :', OCTAVE_BAND13_18_taps)
OCTAVE_BAND13_19_taps = FilterCoefs_48000.OCTAVE_BAND13_19_taps
print('OCTAVE_BAND13_19_taps :', OCTAVE_BAND13_19_taps)
OCTAVE_BAND13_20_taps = FilterCoefs_48000.OCTAVE_BAND13_20_taps
print('OCTAVE_BAND13_20_taps :', OCTAVE_BAND13_20_taps)
OCTAVE_BAND13_21_taps = FilterCoefs_48000.OCTAVE_BAND13_21_taps
print('OCTAVE_BAND13_21_taps :', OCTAVE_BAND13_21_taps)
OCTAVE_BAND13_22_taps = FilterCoefs_48000.OCTAVE_BAND13_22_taps
print('OCTAVE_BAND13_22_taps :', OCTAVE_BAND13_22_taps)
OCTAVE_BAND13_23_taps = FilterCoefs_48000.OCTAVE_BAND13_23_taps
print('OCTAVE_BAND13_23_taps :', OCTAVE_BAND13_23_taps)
OCTAVE_BAND13_24_taps = FilterCoefs_48000.OCTAVE_BAND13_24_taps
print('OCTAVE_BAND13_24_taps :', OCTAVE_BAND13_24_taps)
OCTAVE_BAND13_25_taps = FilterCoefs_48000.OCTAVE_BAND13_25_taps
print('OCTAVE_BAND13_25_taps :', OCTAVE_BAND13_25_taps)
OCTAVE_BAND13_26_taps = FilterCoefs_48000.OCTAVE_BAND13_26_taps
print('OCTAVE_BAND13_26_taps :', OCTAVE_BAND13_26_taps)
OCTAVE_BAND13_27_taps = FilterCoefs_48000.OCTAVE_BAND13_27_taps
print('OCTAVE_BAND13_27_taps :', OCTAVE_BAND13_27_taps)
OCTAVE_BAND13_28_taps = FilterCoefs_48000.OCTAVE_BAND13_28_taps
print('OCTAVE_BAND13_28_taps :', OCTAVE_BAND13_28_taps)
OCTAVE_BAND13_29_taps = FilterCoefs_48000.OCTAVE_BAND13_29_taps
print('OCTAVE_BAND13_29_taps :', OCTAVE_BAND13_29_taps)
OCTAVE_BAND13_30_taps = FilterCoefs_48000.OCTAVE_BAND13_30_taps
print('OCTAVE_BAND13_30_taps :', OCTAVE_BAND13_30_taps)



#====== Filtro Time Weighting =======
#% y[n] = αx[n]+(1-α)y[n−1]
#% Y(z) = αX(z)+(1−α)Y(z)Z(-1)
#% (1-(1−α)Z(-1))Y(z) = αX(z)
#% Y(z)/X(z)= α/(1-(1−α)Z(-1))
#% b = α
#% a = [1, -(1−α)]

alphaF = FilterCoefs_48000.alphaF  # Fast
alphaS = FilterCoefs_48000.alphaS  # Slow
alphaI = FilterCoefs_48000.alphaI  # Impulse

print('alphaF :', alphaF)  # Estamos a utilizar Fast

#alfa = 0.000167 # =(1.813894426370144 * pow(10, -4)) Fast constant
#b = [1/(tau*fs)]  # Numerator
#a = [1, -np.exp(-1/(tau*fs))]  # Denominator

bTW = np.array([alphaF], dtype='float32')
aTW = np.array([1, -(1-alphaF)], dtype='float32')

bTW_C = np.full(N_13OCTAVE_BANDS, alphaF, dtype=np.float32)
aTW_C = np.full(N_13OCTAVE_BANDS, (1 - alphaF), dtype=np.float32)



print('bTW: ', bTW)
print('aTW: ', aTW)
print('bTW_C: ', bTW_C)
print('aTW_C: ', aTW_C)

bTW_SLOW = np.array([alphaS], dtype='float32')
aTW_SLOW = np.array([1, -(1-alphaS)], dtype='float32')

#aTW = np.array([1, -alphaF])
#bTW = np.array([1-alphaF, 0])

histZW = np.zeros([3, 2], dtype='float32')
histAW = np.zeros([3, 2], dtype='float32')
histCW = np.zeros([2, 2], dtype='float32')
#histAW_SLOW = np.zeros([3, 2], dtype='float32')

#    print("histAW ", histAW)
#    print("histCW ", histCW)
#histOctZW = np.zeros([3, 2, 10], dtype='float32')
#histOctZWTW = np.zeros([1, 10], dtype='float32')
#hist13OctZWTW = np.zeros([1, 30], dtype='float32')



#histOctZW = np.zeros([3, 2, 10], dtype='float32')
hist13OctZW = np.zeros([4, 2, N_13OCTAVE_BANDS], dtype='float32')

histZWTW = [0.0]
histCWTW = [0.0]
histAWTW = [0.0]
histAWTW_SLOW = [0.0]

#histOctZWTW = np.zeros([1, 10], dtype='float32')
hist13OctZWTW = np.zeros([1, N_13OCTAVE_BANDS], dtype='float32')


# Initialize filters once
lib_filters.init_filters()

# Initialize
lib_TimeWeightFilter.init_time_weight_filters(N_13OCTAVE_BANDS, bTW_C, aTW_C)


#================
#Open_session_Streaming()
tstamp = np.array([])
LAEZ = np.array([])
LAEC = np.array([])
LAEA = np.array([])
LZpeak = np.array([])

LZpeakT = np.array([])
LCpeak = np.array([])
LCpeakT = np.array([])
LApeak = np.array([])
LApeakT = np.array([])
LAFmax = np.array([])
LAFmaxT = np.array([])
LAFmin = np.array([])
LAFminT = np.array([])
LZeq = np.array([])
LCeq = np.array([])
LAeq = np.array([])

BT25 = np.array([])
BT31_5 = np.array([])
BT40 = np.array([])
BT50 = np.array([])
BT63 = np.array([])
BT80 = np.array([])

BT100 = np.array([])
BT125 = np.array([])
BT160 = np.array([])
BT200 = np.array([])
BT250 = np.array([])
BT315 = np.array([])
BT400 = np.array([])
BT500 = np.array([])
BT630 = np.array([])
BT800 = np.array([])
BT1000 = np.array([])
BT1250 = np.array([])
BT1600 = np.array([])
BT2000 = np.array([])
BT2500 = np.array([])
BT3150 = np.array([])
BT4000 = np.array([])
BT5000 = np.array([])
BT6300 = np.array([])
BT8000 = np.array([])
BT10000 = np.array([])
BT12500 = np.array([])
BT16000 = np.array([])
BT20000 = np.array([])

LAEA_SLOW_Event = np.array([])
EventDetect = np.array([])
EventType1 = np.array([])
EventType2 = np.array([])
EventType3 = np.array([])
EventType4 = np.array([])
EventType5 = np.array([])
EventType6 = np.array([])
EventType7 = np.array([])
EventType8 = np.array([])
EventType9 = np.array([])
EventType10 = np.array([])
    
sensor_ID = np.array([])

def create_new_csv_file():

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"Levels_{timestamp}.csv"
    filepath_CSV = os.path.join(outputDIR_CSV, filename)
    #os.makedirs("output_CSV", exist_ok=True)

    f = open(filepath_CSV, "a", newline='')
    writer = csv.writer(f)

    writer.writerow([
        "TimeStamp", "SensorID", "LAEZ", "LAEC", "LAEA", "LZpeak", "LZpeakT", "LCpeak", "LCpeakT", "LApeak", "LApeakT",
        "LAFmax", "LAFmaxT", "LAFmin", "LAFminT", "LZeq", "LCeq", "LAeq",
        "BT25", "BT31_5", "BT40", "BT50", "BT63", "BT80", "BT100", "BT125", "BT160", "BT200", "BT250", "BT315", "BT400", "BT500",
        "BT630", "BT800", "BT1000", "BT1250", "BT1600", "BT2000", "BT2500", "BT3150", "BT4000", "BT5000", "BT6300", "BT8000",
        "BT10000", "BT12500", "BT16000", "BT20000", "LAEA_SLOW_Event", "EventDetect",
        "EventType1", "EventType2", "EventType3", "EventType4", "EventType5", "EventType6", "EventType7", "EventType8", "EventType9", "EventType10", 
        "Class1ID", "Class1Score", "Class2ID", "Class2Score", "Class3ID", "Class3Score"
    ])

    print(f"[CSV] Opened new file with header: {filename}")

    return f, writer

current_file, current_writer = create_new_csv_file()


ringBuffZW = lib.ringbuffer_fifo_create(BUFFER_SIZE)
ringBuffCW = lib.ringbuffer_fifo_create(BUFFER_SIZE)
ringBuffAW = lib.ringbuffer_fifo_create(BUFFER_SIZE)
ringBuffZWTW = lib.ringbuffer_fifo_create(BUFFER_SIZE)
ringBuffCWTW = lib.ringbuffer_fifo_create(BUFFER_SIZE)
ringBuffAWTW = lib.ringbuffer_fifo_create(BUFFER_SIZE)
ringBuffZWTW_13Oct = lib_13Oct.ringbuffer_fifo_create(BUFFER_SIZE)

#ringBuffAW_SLOW = lib.ringbuffer_fifo_create(BUFFER_SIZE) # Alarms
ringBuffAWTW_SLOW = lib.ringbuffer_fifo_create(BUFFER_SIZE)


# Memory allocation
NoiLevls_size = 1 + 1 + 16 + N_13OCTAVE_BANDS + 2 + 10 + 6         # 1 (timeStamp) + 16 (sound levels) + N_13OCTAVE_BANDS + 2 (Alarms) + 10 (TypeEvents) + 6 (Top 3 Specific Events + Respective Scores)

NoiLevls_dB = (ctypes.c_float * NoiLevls_size)()
Noi_Lin = (ctypes.c_float * NoiLevls_size)()

ringBuffZW_ = np.zeros(SEGMENT_SIZE, dtype=np.float32)
ringBuffCW_ = np.zeros(SEGMENT_SIZE, dtype=np.float32)
ringBuffAW_ = np.zeros(SEGMENT_SIZE, dtype=np.float32)
ringBuffZWTW_ = np.zeros(SEGMENT_SIZE, dtype=np.float32)
ringBuffCWTW_ = np.zeros(SEGMENT_SIZE, dtype=np.float32)
ringBuffAWTW_ = np.zeros(SEGMENT_SIZE, dtype=np.float32)
ringBuffAWTW_SLOW_ = np.zeros(SEGMENT_SIZE, dtype=np.float32)
#ringBuffZWTW_13Oct_ = np.zeros((SEGMENT_SIZE, N_13OCTAVE_BANDS), dtype=np.float32)

if ShowLEDsDisplay_OK:
    #def Initialise_LEDsDisplay():
    #print('Initialise_LEDsDisplay: ====1')


    #====== LEDS and 7segment display

    ## LED levels
    #LEVEL_LED_GREEN = 50
    ##LEVEL_LED_GREEN_YELLOW = 63
    #LEVEL_LED_YELLOW = 60
    ##LEVEL_LED_YELLOW_RED = 83


    #LED_GR = 23
    #LED_YE = 24
    #LED_RD = 25

    # Setup GPIO\
    GPIO.setmode(GPIO.BCM)  # Use BCM pin numbering (GPIO numbers)\
    GPIO.setup(LED_GR, GPIO.OUT)  # Set LED_PIN as an output\
    GPIO.setup(LED_YE, GPIO.OUT)  # Set LED_PIN as an output\
    GPIO.setup(LED_RD, GPIO.OUT)  # Set LED_PIN as an output\


    segment_map = {
        '0': 0b00111111,  # 0\
        '1': 0b00000110,  # 1\
        '2': 0b01011011,  # 2\
        '3': 0b01001111,  # 3\
        '4': 0b01100110,  # 4\
        '5': 0b01101101,  # 5\
        '6': 0b01111101,  # 6\
        '7': 0b00000111,  # 7\
        '8': 0b01111111,  # 8\
        '9': 0b01101111,  # 9\
        'A': 0b01110111,  # A\
        'b': 0b01111100,  # b\
        'C': 0b00111001,  # C\
        'd': 0b01011110,  # d\
        'E': 0b01111001,  # E\
        'F': 0b01110001,  # F\
    }

    d = int(0b01011110)
    b = int(0b01111100)

    dH = hex(d)
    bH = hex(b)

    print('d: ', d)
    print('b: ', b)
    print('dH: ', dH)
    print('bH: ', bH)


    char_map = {
        '0': 0x3F,  # 0\
        '1': 0x06,  # 1\
        '2': 0x5b,  # 2\
        '3': 0x4f,  # 3\
        '4': 0x66,  # 4\
        '5': 0x6d,  # 5\
        '6': 0x7d,  # 6\
        '7': 0x07,  # 7\
        '8': 0x7f,  # 8\
        '9': 0x6f,  # 9\
        'd': 0x5e,  # d\
        'b': 0x7c,  # b\
    }

    char_map2 = {
        0: 0x3F,  # 0\
        1: 0x06,  # 1\
        2: 0x5b,  # 2\
        3: 0x4f,  # 3\
        4: 0x66,  # 4\
        5: 0x6d,  # 5\
        6: 0x7d,  # 6\
        7: 0x07,  # 7\
        8: 0x7f,  # 8\
        9: 0x6f,  # 9\
        10: 0x5e,  # d\
        11: 0x7c,  # b\
    }

    tes1 = char_map2[7]
    print('tes1: ', tes1) 

    # Configura o Grove - 4-Digit Display
    # Configuração dos pinos CLK e DIO (substitua se necessário)
    CLK = 22  # Pino GPIO conectado ao CLK
    DIO = 27  # Pino GPIO conectado ao DIO

    # Inicializa o display
    display = tm1637.TM1637(clk=CLK, dio=DIO)

    # Define o brilho do display (0 a 7)
    display.brightness(7)
        
    



def process_LEDs(SPLReal):
    #print(str(np.round(SPLReal, 1)) + "dB ================================")
    if SPLReal < LEVEL_LED_GREEN:
        #print('GREEN')

        GPIO.output(LED_GR, GPIO.LOW)  # Turn LED on\
        GPIO.output(LED_YE, GPIO.HIGH)  # Turn LED off\
        GPIO.output(LED_RD, GPIO.HIGH)  # Turn LED off\

        '''        
        ledGr.ChangeDutyCycle(0)  # CHANGE: Set 50% brightness for GREEN LED
        ledYe.ChangeDutyCycle(100)
        ledRd.ChangeDutyCycle(100)
        '''
        #time.sleep(flash_interval)       # Wait for the flash_interval duration\

        
    # elif LEVEL_LED_GREEN <= SPLReal < LEVEL_LED_GREEN_YELLOW:
        # print('GREEN_YELLOW')

        # GPIO.output(LED_GR, GPIO.LOW)  # Turn LED on\
        # GPIO.output(LED_YE, GPIO.LOW)  # Turn LED on\
        # GPIO.output(LED_RD, GPIO.HIGH)  # Turn LED off\
        # '''        
        # ledGr.ChangeDutyCycle(100)
        # ledYe.ChangeDutyCycle(100)
        # ledRd.ChangeDutyCycle(0)  # CHANGE: Set 75% brightness for RED LED
        # '''       
        # #time.sleep(flash_interval)       # Wait for the flash_interval duration\
              
    #elif LEVEL_LED_GREEN_YELLOW <= SPLReal < LEVEL_LED_YELLOW:
    elif LEVEL_LED_GREEN <= SPLReal < LEVEL_LED_YELLOW:
        #print('YELLOW')

        GPIO.output(LED_GR, GPIO.HIGH)  # Turn LED off\
        GPIO.output(LED_YE, GPIO.LOW)  # Turn LED on\
        GPIO.output(LED_RD, GPIO.HIGH)  # Turn LED off\

        '''       
        ledGr.ChangeDutyCycle(100)
        ledYe.ChangeDutyCycle(100)
        ledRd.ChangeDutyCycle(0)  # CHANGE: Set 75% brightness for RED LED
        '''       
        #time.sleep(flash_interval)       # Wait for the flash_interval duration\
                      
    # elif LEVEL_LED_YELLOW <= SPLReal < LEVEL_LED_YELLOW_RED:
        # print('YELLOW_RED')

        # GPIO.output(LED_GR, GPIO.HIGH)  # Turn LED off\
        # GPIO.output(LED_YE, GPIO.LOW)  # Turn LED on\
        # GPIO.output(LED_RD, GPIO.LOW)  # Turn LED on\
        # '''        
        # ledGr.ChangeDutyCycle(100)
        # ledYe.ChangeDutyCycle(100)
        # ledRd.ChangeDutyCycle(0)  # CHANGE: Set 75% brightness for RED LED
        # '''       
        # #time.sleep(flash_interval)       # Wait for the flash_interval duration\
                      
    else:
        #print('RED')

        GPIO.output(LED_GR, GPIO.HIGH)  # Turn LED off\
        GPIO.output(LED_YE, GPIO.HIGH)  # Turn LED off\
        GPIO.output(LED_RD, GPIO.LOW)  # Turn LED on\

        '''
        ledGr.ChangeDutyCycle(100)
        ledYe.ChangeDutyCycle(100)
        ledRd.ChangeDutyCycle(0)  # CHANGE: Set 75% brightness for RED LED
        '''
                
        #time.sleep(flash_interval)       # Wait for the flash_interval duration\
                
# Função para exibir números no display
def display7seg_LED(SPLReal_shared, spl_lock):

    #print('display7seg_LED==================')

    while True:
        time.sleep(0.1)  # update every 100 ms
        
        #print('display7seg_LED   while True ==================')

# Read latest data safely
        with spl_lock:
            SPLx = SPLReal_shared.value
            #print('SPLReal_shared: ', SPLReal_shared)

        if SPLx is not None:
            #print('SPLx: ', SPLx)

            process_LEDs(SPLx)
            


            #print('display.numbers:')
            #parte_fracionaria, parte_inteira = math.modf(SPLx)
            #print('display.numbers:', parte_inteira, '-', parte_fracionaria)
            #print('parte_inteira: ', int(parte_inteira))
            #print('parte_fracionaria: ', 10*int(np.round(10*parte_fracionaria, 1)))
            #parte_inteira = int(parte_inteira)
            #print('parte_fracionaria: ', 10*int(np.round(10*parte_fracionaria, 1)))
            #display.numbers(int(parte_inteira), 10*int(np.round(10*parte_fracionaria, 1)))  # Exibe o número no formato XX:XX
            
            #display.numbers(parte_inteira, 0)
            #display.show("db")
        #    parte_inteira = int(SPLx)                                           #Opcão 1 (escreve apenas SPL (primeiros 2 digitos)) - 
        #    display.numbers(parte_inteira, 0)                                   #Opcão 1 (escreve apenas SPL (primeiros 2 digitos)) 
            
        #====== Escrever texto no display 
            #MSD1H = hex(int(parte_inteira/10))
            #MSD2H = hex(int(parte_inteira//10))

            
            #parte_inteira = int(SPLx)                                          # Opcão 2 (escreve 'db') - Não funcionou bem==============================
            parte_inteira = np.round(SPLx, 0)
           # print('parte_inteira: ', parte_inteira)
            MSD1H, MSD2H = divmod(parte_inteira, 10)                           # Opcão 2 (escreve 'db') - Não funcionou bem==============================
            
        #    print('dH: ', dH)
        #    print('bH: ', bH)
        #    print('MSD1H: ', f"{hex(MSD1H):02}")
        #    print('MSD2H: ', f"{hex(MSD2H)}")
            
        #    print('str(MSD1H):', str(MSD1H))
        #    print('str(MSD2H):', str(MSD2H))  
            
        #    print(char_map2[str(MSD1H)])
        #    print(char_map2[str(MSD2H)])

            #display.write([MSD1H, MSD2H, dH, bH])
            #display.write([f"{hex(MSD1H)}", f"{hex(MSD2H)}", 0x5c, 0x7c])
            
        #    MSD1H = char_map[str(MSD1H)]                                       # Opcão 2 (escreve 'db') - Não funcionou bem==============================
        #    MSD2H = char_map[str(MSD2H)]                                       # Opcão 2 (escreve 'db') - Não funcionou bem==============================
        #    print('MSD1H: ', str(MSD1H))
        #    print('MSD2H: ', str(MSD2H))  
            MSD1H = char_map2[MSD1H]                                       # Opcão 2 (escreve 'db') - Não funcionou bem==============================
            MSD2H = char_map2[MSD2H]                                       # Opcão 2 (escreve 'db') - Não funcionou bem==============================
        #    print('MSD1H: ', MSD1H)
        #    print('MSD2H: ', MSD2H)  
        #    d = char_map['d']                                                  # Opcão 2 (escreve 'db') - Não funcionou bem==============================
        #    b = char_map['b']                                                  # Opcão 2 (escreve 'db') - Não funcionou bem==============================
            d = char_map2[10]                                                  # Opcão 2 (escreve 'db') - Não funcionou bem==============================
            b = char_map2[11]                                                  # Opcão 2 (escreve 'db') - Não funcionou bem==============================
        #    d = 0x5e,  # d\
        #    b = 0x7c,  # b\
        #    print(d)
        #    print(b)  
            display.write([MSD1H, MSD2H, d, b])                                # Não funcionou bem==============================
            
    

def process_block_square(blk):
    blk = blk**2
    return blk

def block_sample_to_float(blk):
#    print('blk_int:', blk)
    blk = blk.astype('float32')/(2.0**(NBITS-1))
#    print('blk_float:', blk)
    return blk



#===== Spectral Noise Gate Denoising ==============
# Step 1: Noise profile estimation

noise_magnitudes = []
mean_noise_mag = []


def noise_callback(indata, frames, time, status):
    sample = indata[:, 0]
    #spectrum = rfft(sample * np.hanning(CHUNK_SIZE))
    spectrum = rfft(sample)

    mag = np.abs(spectrum)
    noise_magnitudes.append(mag)





# Select the AudioInterface =========
for i, dev in enumerate(sd.query_devices()):
    print(f"{i}: {dev['name']} - {dev['max_input_channels']} input / {dev['max_output_channels']} output")

'''
#input_id = int(input("Select input device index: "))
sd.default.device = (input_id, None)
'''

def get_device_id_by_name(name_substring, kind="input"):
    devices = sd.query_devices()
    for idx, device in enumerate(devices):
        if name_substring.lower() in device['name'].lower():
            if kind == "input" and device['max_input_channels'] > 0:
                return idx
            elif kind == "output" and device['max_output_channels'] > 0:
                return idx
    raise RuntimeError(f"No matching {kind} device found with name containing: {name_substring}")

# Get the input device index
input_device = get_device_id_by_name(TARGET_DEVICE_NAME, kind="input")

# Optionally set as default
sd.default.device = (input_device, None)  # (input, output)
print("Please stay silent/noise for 1 second to estimate noise profile...")

# Record noise frames (~1 sec)
with sd.InputStream(samplerate=SAMPLE_RATE,
                    blocksize=CHUNK_SIZE,
                    channels=1,
                    callback=noise_callback):
    #for _ in range(int(SAMPLE_RATE / CHUNK_SIZE)):
    for _ in range(initial_noise_frames):

        sd.sleep(int(1000 * CHUNK_SIZE / SAMPLE_RATE))

# Calculate per-frequency mean magnitude of noise
mean_noise_mag = np.mean(np.array(noise_magnitudes), axis=0)
#print('mean_noise_mag: ', mean_noise_mag)

threshold = mean_noise_mag * threshold_factor

#print('threshold: ', threshold)
#print('len(threshold): ', len(threshold))
#print('np.shape((threshold)): ', np.shape((threshold)))

print("Per-frequency noise threshold computed.")

# Step 2: Real-time denoising using per-frequency threshold
window = np.hanning(CHUNK_SIZE)

def process_block_NoiseGate(block):
    #windowed = block * window
    windowed = block

    spectrum = rfft(windowed)
    mag = np.abs(spectrum)
    # Use per-frequency threshold
    gain = np.where(mag < threshold, 0.2, 1.0)
    spectrum_denoised = spectrum * gain

    denoised = irfft(spectrum_denoised)
    return denoised



def spectral_subtract(mag, noise_mag, reduction_factor=REDUCTION_FACTOR):
    # Subtract the noise spectrum magnitude
    mag_sub = mag - reduction_factor * noise_mag
    mag_sub = np.maximum(mag_sub, 0)
    return mag_sub

def process_block_SpectSubtraction(block):
    """
    Denoise a single audio block without windowing.
    """
    spectrum = np.fft.rfft(block)
    mag = np.abs(spectrum)
    phase = np.angle(spectrum)
            
    #global noise_spectrum
    mag_denoised = spectral_subtract(mag, mean_noise_mag)
            
    # Reconstruct time domain
    spectrum_denoised = mag_denoised * np.exp(1j * phase)
    denoised = np.fft.irfft(spectrum_denoised)
    #print(denoised)
    return denoised.astype(np.float32)



#def mqtt_sender(mqtt_queue, stop_event, batch_size=10, timeout=2):
#def mqtt_sender(mqtt_queue, stop_event, client, client2, batch_size=10, timeout=2):
def mqtt_sender(mqtt_queue, stop_event, client, batch_size=10, timeout=2):
    
    buffer = []

    print("mqtt_sender started")

    while True:
        try:
            # Wait for an item from the queue
            item = mqtt_queue.get(timeout=timeout)

            # Sentinel received → stop
            if item is None:
                break

            # Convert NumPy array or numeric value to list
            buffer.append(np.round(item, 2).tolist())

            # Publish if batch is full
            if len(buffer) >= batch_size:
                payload = json.dumps(buffer)
                client.publish("sound/levels", payload)
                #client2.publish("sound/levels", payload)
                buffer.clear()

        except Empty:
            # Timeout occurred
            if stop_event.is_set():
                # Flush remaining data
                if buffer:
                    payload = json.dumps(buffer)
                    client.publish("sound/levels", payload)
                    #client2.publish("sound/levels", payload)
                    buffer.clear()
                break
            continue

    # Final flush in case queue had extra items
    if buffer:
        payload = json.dumps(buffer)
        client.publish("sound/levels", payload)
        #client2.publish("sound/levels", payload)

    print("✅ MQTT sender finished")


buffer_JSON = []

def write_Json_to_Cloud_Stream(NoiseLevels_OneLine, JSON_full):
    global tstamp, LAEZ, LAEC, LAEA, LZpeak
    global LZpeakT, LCpeak, LCpeakT, LApeak, LApeakT
    global LAFmax, LAFmaxT, LAFmin, LAFminT, LZeq, LCeq, LAeq
    #global B31_5, B63, B125, B250, B500, B1000, B2000, B4000, B8000, B16000
    global BT25, BT31_5, BT40, BT50, BT63, BT80, BT100, BT125, BT160, BT200, BT250, BT315, BT400, BT500
    global BT630, BT800, BT1000, BT1250, BT1600, BT2000, BT2500, BT3150, BT4000, BT5000, BT6300, BT8000
    global BT10000, BT12500, BT16000, BT20000
    global LAEA_SLOW_Event, EventDetect, EventType1, EventType2, EventType3, EventType4, EventType5, EventType6, EventType7, EventType8, EventType9, EventType10
    global sensor_ID

    print('NoiseLevels_OneLine: ', len(NoiseLevels_OneLine))

    global session_id, station_id, headers

    #tstamp = np.append(tstamp, NoiseLevels_OneLine[0])
#    print('tstamp: ', tstamp)
    LAEZ = np.append(LAEZ, NoiseLevels_OneLine[1])
#    print('LAEZ: ', LAEZ)
    LAEC = np.append(LAEC, NoiseLevels_OneLine[2])
    LAEA = np.append(LAEA, NoiseLevels_OneLine[3])
    LZpeak = np.append(LZpeak, NoiseLevels_OneLine[4])
    LZpeakT = np.append(LZpeakT, NoiseLevels_OneLine[5])
    LCpeak = np.append(LCpeak, NoiseLevels_OneLine[6])
    LCpeakT = np.append(LCpeakT, NoiseLevels_OneLine[7])
    LApeak = np.append(LApeak, NoiseLevels_OneLine[8])
    LApeakT = np.append(LApeakT, NoiseLevels_OneLine[9])
    LAFmax = np.append(LAFmax, NoiseLevels_OneLine[10])
    LAFmaxT = np.append(LAFmaxT, NoiseLevels_OneLine[11])
    LAFmin = np.append(LAFmin, NoiseLevels_OneLine[12])
    LAFminT = np.append(LAFminT, NoiseLevels_OneLine[13])
    LZeq = np.append(LZeq, NoiseLevels_OneLine[14])
    LCeq = np.append(LCeq, NoiseLevels_OneLine[15])
    LAeq = np.append(LAeq, NoiseLevels_OneLine[16])
    '''
    B31_5 = np.append(B31_5, NoiseLevels_OneLine[17])
    B63 = np.append(B63, NoiseLevels_OneLine[18])
    B125 = np.append(B125, NoiseLevels_OneLine[19])
    B250 = np.append(B250, NoiseLevels_OneLine[20])
    B500 = np.append(B500, NoiseLevels_OneLine[21])
    B1000 = np.append(B1000, NoiseLevels_OneLine[22])
    B2000 = np.append(B2000, NoiseLevels_OneLine[23])
    B4000 = np.append(B4000, NoiseLevels_OneLine[24])
    B8000 = np.append(B8000, NoiseLevels_OneLine[25])
    B16000 = np.append(B16000, NoiseLevels_OneLine[26])
    '''
    BT25 = np.append(BT25, NoiseLevels_OneLine[17])
    BT31_5 = np.append(BT31_5, NoiseLevels_OneLine[18])
    BT40 = np.append(BT40, NoiseLevels_OneLine[19])
    BT50 = np.append(BT50, NoiseLevels_OneLine[20])
    BT63 = np.append(BT63, NoiseLevels_OneLine[21])
    BT80 = np.append(BT80, NoiseLevels_OneLine[22])
    BT100 = np.append(BT100, NoiseLevels_OneLine[23])
    BT125 = np.append(BT125, NoiseLevels_OneLine[24])
    BT160 = np.append(BT160, NoiseLevels_OneLine[25])
    BT200 = np.append(BT200, NoiseLevels_OneLine[26])
    BT250 = np.append(BT250, NoiseLevels_OneLine[27])
    BT315 = np.append(BT315, NoiseLevels_OneLine[28])
    BT400 = np.append(BT400, NoiseLevels_OneLine[29])
    BT500 = np.append(BT500, NoiseLevels_OneLine[30])
    BT630 = np.append(BT630, NoiseLevels_OneLine[31])
    BT800 = np.append(BT800, NoiseLevels_OneLine[32])
    BT1000 = np.append(BT1000, NoiseLevels_OneLine[33])
    BT1250 = np.append(BT1250, NoiseLevels_OneLine[34])
    BT1600 = np.append(BT1600, NoiseLevels_OneLine[35])
    BT2000 = np.append(BT2000, NoiseLevels_OneLine[36])
    BT2500 = np.append(BT2500, NoiseLevels_OneLine[37])
    BT3150 = np.append(BT3150, NoiseLevels_OneLine[38])
    BT4000 = np.append(BT4000, NoiseLevels_OneLine[39])
    BT5000 = np.append(BT5000, NoiseLevels_OneLine[40])
    BT6300 = np.append(BT6300, NoiseLevels_OneLine[41])
    BT8000 = np.append(BT8000, NoiseLevels_OneLine[42])
    BT10000 = np.append(BT10000, NoiseLevels_OneLine[43])
    BT12500 = np.append(BT12500, NoiseLevels_OneLine[44])
    BT16000 = np.append(BT16000, NoiseLevels_OneLine[45])
    BT20000 = np.append(BT20000, NoiseLevels_OneLine[46])

    LAEA_SLOW_Event = np.append(LAEA_SLOW_Event, NoiseLevels_OneLine[47])
    EventDetect = np.append(EventDetect, NoiseLevels_OneLine[48])
    EventType1 = np.append(EventType1, 0.0)
    EventType2 = np.append(EventType2, 0.0)
    EventType3 = np.append(EventType3, 0.0)
    EventType4 = np.append(EventType4, 0.0)
    EventType5 = np.append(EventType5, 0.0)
    EventType6 = np.append(EventType6, 0.0)
    EventType7 = np.append(EventType7, 0.0)
    EventType8 = np.append(EventType8, 0.0)
    EventType9 = np.append(EventType9, 0.0)
    EventType10 = np.append(EventType10, 0.0)
    sensor_ID   = np.append(sensor_ID, 2)



    if JSON_full:  # Tempo de Escreve para ficheiro

        LAEZ = np.round(LAEZ, 2).tolist()
        LAEC = np.round(LAEC, 2).tolist()
        LAEA = np.round(LAEA, 2).tolist()
        LZpeak = np.round(LZpeak, 2).tolist()

        LZpeakT = np.round(LZpeakT, 2).tolist()
        LCpeak = np.round(LCpeak, 2).tolist()
        LCpeakT = np.round(LCpeakT, 2).tolist()
        LApeak = np.round(LApeak, 2).tolist()
        LApeakT = np.round(LApeakT, 2).tolist()

        LAFmax = np.round(LAFmax, 2).tolist()
        LAFmaxT = np.round(LAFmaxT, 2).tolist()
        LAFmin = np.round(LAFmin, 2).tolist()
        LAFminT = np.round(LAFminT, 2).tolist()
        LZeq = np.round(LZeq, 2).tolist()
        LCeq = np.round(LCeq, 2).tolist()
        LAeq = np.round(LAeq, 2).tolist()
        '''
        B31_5 = np.round(B31_5, 2).tolist()
        B63 = np.round(B63, 2).tolist()
        B125 = np.round(B125, 2).tolist()
        B250 = np.round(B250, 2).tolist()
        B500 = np.round(B500, 2).tolist()
        B1000 = np.round(B1000, 2).tolist()
        B2000 = np.round(B2000, 2).tolist()
        B4000 = np.round(B4000, 2).tolist()
        B8000 = np.round(B8000, 2).tolist()
        B16000 = np.round(B16000, 2).tolist()
        '''
        BT25 = np.round(BT25, 2).tolist()
        BT31_5 = np.round(BT31_5, 2).tolist()
        BT40 = np.round(BT40, 2).tolist()
        BT50 = np.round(BT50, 2).tolist()
        BT63 = np.round(BT63, 2).tolist()
        BT80 = np.round(BT80, 2).tolist()
        BT100 = np.round(BT100, 2).tolist()
        BT125 = np.round(BT125, 2).tolist()
        BT160 = np.round(BT160, 2).tolist()
        BT200 = np.round(BT200, 2).tolist()
        BT250 = np.round(BT250, 2).tolist()
        BT315 = np.round(BT315, 2).tolist()
        BT400 = np.round(BT400, 2).tolist()
        BT500 = np.round(BT500, 2).tolist()

        BT630 = np.round(BT630, 2).tolist()
        BT800 = np.round(BT800, 2).tolist()
        BT1000 = np.round(BT1000, 2).tolist()
        BT1250 = np.round(BT1250, 2).tolist()
        BT1600 = np.round(BT1600, 2).tolist()
        BT2000 = np.round(BT2000, 2).tolist()
        BT2500 = np.round(BT2500, 2).tolist()
        BT3150 = np.round(BT3150, 2).tolist()
        BT4000 = np.round(BT4000, 2).tolist()
        BT5000 = np.round(BT5000, 2).tolist()
        BT6300 = np.round(BT6300, 2).tolist()
        BT8000 = np.round(BT8000, 2).tolist()

        BT10000 = np.round(BT10000, 2).tolist()
        BT12500 = np.round(BT12500, 2).tolist()
        BT16000 = np.round(BT16000, 2).tolist()
        BT20000 = np.round(BT20000, 2).tolist()

        LAEA_SLOW_Event = np.round(LAEA_SLOW_Event, 2).tolist()
        EventDetect = np.round(EventDetect, 0).tolist()
        EventType1 = np.round(EventType1, 2).tolist()
        EventType2 = np.round(EventType2, 2).tolist()
        EventType3 = np.round(EventType3, 2).tolist()
        EventType4 = np.round(EventType4, 2).tolist()
        EventType5 = np.round(EventType5, 2).tolist()
        EventType6 = np.round(EventType6, 2).tolist()
        EventType7 = np.round(EventType7, 2).tolist()
        EventType8 = np.round(EventType8, 2).tolist()
        EventType9 = np.round(EventType9, 2).tolist()
        EventType10 = np.round(EventType10, 2).tolist()

        sensor_ID = np.round(sensor_ID, 0).tolist()  


        x = {"DataRecord":
             {"noise_levels": {"LAEZ": LAEZ, "LAEC": LAEC, "LAEA": LAEA, "LZpeak": LZpeak,
                "LZpeakT": LZpeakT, "LCpeak": LCpeak, "LCpeakT": LCpeakT, "LApeak": LApeak, "LApeakT": LApeakT,
                "LAFmax": LAFmax, "LAFmaxT": LAFmaxT, "LAFmin": LAFmin, "LAFminT": LAFminT, "LZeq": LZeq,
                "LCeq": LCeq, "LAeq": LAeq,
                #"B31_5": B31_5, "B63": B63, "B125": B125, "B250": B250, "B500": B500, "B1000": B1000, "B2000": B2000,
                #"B4000": B4000, "B8000": B8000, "B16000": B16000,
                "BT25": BT25, "BT31_5": BT31_5, "BT40": BT40, "BT50": BT50, "BT63": BT63, "BT63": BT63, "BT80": BT80,
                "BT100": BT100, "BT125": BT125, "BT160": BT160, "BT250": BT250, "BT315": BT315, "BT400": BT400,
                "BT500": BT500, "BT630": BT630, "BT800": BT800, "BT1000": BT1000, "BT1250": BT1250, "BT1600": BT1600,
                "BT2000": BT2000, "BT2500": BT2500, "BT3150": BT3150, "BT4000": BT4000, "BT5000": BT5000,
                "BT6300": BT6300, "BT8000": BT8000, "BT10000": BT10000, "BT12500": BT12500, "BT16000": BT16000,
                "BT20000": BT20000,
                "LAEA_SLOW_Event": LAEA_SLOW_Event, "EventDetect": EventDetect,
                "EventType1": EventType1, "EventType2": EventType2, "EventType3": EventType3, "EventType4": EventType4, "EventType5": EventType5,
                "EventType6": EventType6, "EventType7": EventType7, "EventType8": EventType8, "EventType9": EventType9, "EventType10": EventType10}}}

#        print('x: ', x)

        y = json.dumps(x)
        print(y)

# Limpa as variáveis
        LAEZ = []
        LAEC = []
        LAEC = []
        LAEA = []
        LZpeak = []
        LZpeakT = []
        LCpeak = []
        LCpeakT = []
        LApeak = []
        LApeakT = []
        LAFmax = []
        LAFmaxT = []
        LAFmin = []
        LAFminT = []
        LZeq = []
        LCeq = []
        LAeq = []

        BT25 = []
        BT31_5 = []
        BT40 = []
        BT50 = []
        BT63 = []
        BT80 = []
        BT100 = []
        BT125 = []
        BT160 = []
        BT200 = []
        BT250 = []
        BT315 = []
        BT400 = []
        BT500 = []
        BT630 = []
        BT800 = []
        BT1000 = []
        BT1250 = []
        BT1600 = []
        BT2000 = []
        BT2500 = []
        BT3150 = []
        BT4000 = []
        BT5000 = []
        BT6300 = []
        BT8000 = []
        BT10000 = []
        BT12500 = []
        BT16000 = []
        BT20000 = []

        LAEA_SLOW_Event = []
        EventDetect = []
        EventType1 = []
        EventType2 = []
        EventType3 = []
        EventType4 = []
        EventType5 = []
        EventType6 = []
        EventType7 = []
        EventType8 = []
        EventType9 = []
        EventType10 = []
        sensor_ID  = []

def publish_block():
    global buffer_JSON
    try:
        payload = json.dumps(buffer_JSON)
        #client.publish(MQTT_TOPIC, payload)
        print(f"Sent block of {len(buffer_CSV)} rows")
        print(f"payload", payload)

        buffer_JSON = []  # Clear buffer after sending
    except Exception as e:
        print("Error sending block:", e)



def add_row(noise_row):
    """Convert to list and append to buffer."""
    buffer_JSON.append(noise_row.tolist())

    # Send every 20 rows
    if len(buffer_JSON) >= 20:
        publish_block()


i=0

output_array = np.zeros(CHUNK_SIZE * 30, dtype=np.float64)  # Array banco de filtors 1/3oct

start_time_session = time.time()

events_info = np.zeros(16, dtype='float32')

def audio_processor(audio_queue, write_queue, stop_event, mqtt_queue, SPLReal_shared, spl_lock, audio_Class_queue, resultClass_queue):
    global histAW, histCW, histZWTW, histCWTW, histAWTW, hist13OctZW, hist13OctZWTW, histAWTW_SLOW
    global cntSegmBegin, cntSegmBeginOffSetIni, countBlock, CountringBuff, CountringBuffJson, counter_CSV, counter_File_CSV, counter_JSON, counterPercentil_LAxx
#    global Noise_dBTimeLine, Noise_LinTimeLine
    global Noise_dBTimeLine_buffer, Noise_LinTimeLine_buffer
    global elapsed_timeTimeLine
    global LZpeakTprmsLast, LApeakTprmsLast, LCpeakTprmsLast, LAFmaxTprmsLast, LAFminTprmsLast, LZprmsLast, LCprmsLast, LAprmsLast
    global Noise_Lin
    global i

    #global ringBuffZWTW_13Oct_

    global samples_written, samples_read
    global write_index, read_index, available_samples

    global buffer_CSV, current_file, current_writer

    global output_array

    global noise_estimate, noise_frames_collected, noise_magnitudes

    global start_time_session   

    global SPLReal

    global Percentil_LAxx

    Percentil = []

    #global threshold

    #yamnet_model, yamnet_class_names, class_to_family, BLACKLIST = yamnet_classifier_init()
    #print('yamnet_model loaded successfully')
    #print('class_to_family')
    
#    sample_accumulator_raw = np.zeros((0,), dtype=np.float32)
#    sample_accumulator_filtered = np.zeros((0,), dtype=np.float32)
    sample_accumulator_raw = []
    sample_accumulator_event = []
    #sample_accumulator_filtered = []


    buffered_samples = 0
    buffered_samples_event = 0
    chunk_counter = 0
    counterEchoRefresh =0
    
    
    
    
    Noise_Lin = np.zeros(nColumns + 1, dtype='float32') # 
    NoiseLevels_dB = np.zeros(nColumns + 1, dtype='float32')

    print('==========TESTE INICIAL============')
    print('stop_event.is_set(): ', stop_event.is_set())
    print('audio_queue.empty(): ', audio_queue.empty())


    # While (the recording is still going on  OR there are still audio samples left to process in the queue)
    while not stop_event.is_set() or not audio_queue.empty():
        try:
            block = audio_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        start_time = time.time()

        # =================
        # === PORTO A =====
        # ================
        #start = time.perf_counter()

        #print('block ', block)
        blockZW = block.astype(np.float32)/(2**(NBITS-1))
#        blockZW = block_sample_to_float(blockZW)  # Convert to float with normalization (-1 : 1)


        #print('blockZW ', blockZW)

# ================================
        # === Noise Reduction algorithm ==
        # ================================
        
        if NoiseReduction_OK:

            #blockZW = process_block_NoiseGate(blockZW)

            blockZW = process_block_SpectSubtraction(blockZW)


        
            '''
            # STFT
            f, t, Zxx = stft(blockZW, SAMPLE_RATE, nperseg=CHUNK_SIZE, noverlap=hop_size)

            # Collect noise profile during initial frames
            if noise_frames_collected < initial_noise_frames:
                noise_magnitudes.append(np.abs(Zxx))
                noise_frames_collected += 1
                # Pass input directly to output during noise collection
                #outdata[:] = block
                CollectingNoiseProfile = True
                print('CollectingNoiseProfile======')
            else:
                CollectingNoiseProfile = False

            if not CollectingNoiseProfile:
                # Estimate noise once enough frames are collected
                if noise_estimate is None:
                    noise_estimate = np.median(np.array(noise_magnitudes), axis=0)
                    print("Noise profile estimated.")

                # Threshold
                threshold = noise_estimate * threshold_factor

                # Create gain mask
                gain = np.ones_like(Zxx)
                gain[np.abs(Zxx) < threshold] *= 0.2

                # Apply gating
                Zxx_denoised = Zxx * gain

                # Inverse STFT
                _, denoised_signal = istft(Zxx_denoised, SAMPLE_RATE, nperseg=CHUNK_SIZE, noverlap=hop_size)

                # Match length
                if len(denoised_signal) > CHUNK_SIZE:
                    denoised_signal = denoised_signal[:CHUNK_SIZE]

                
                blockZW = denoised_signal
            
            '''        








        #end = time.perf_counter()
        #print("elapsed_PORTO A (ms):", np.round((end - start) * 1000, 5))


        # _________ Audio Processing _____________________
        # =================
        # === PORTO B =====
        # =================
        #start = time.perf_counter()

        blockCW, histCW = sosfilt(C_WEIGHTED_taps, blockZW, zi=histCW)
        blockAW, histAW = sosfilt(A_WEIGHTED_taps, blockZW, zi=histAW)

        '''
        block13Oct1, hist13OctZW[:, :, 0] = sosfilt(OCTAVE_BAND13_1_taps, blockZW, zi=hist13OctZW[:, :, 0])
        block13Oct2, hist13OctZW[:, :, 1] = sosfilt(OCTAVE_BAND13_2_taps, blockZW, zi=hist13OctZW[:, :, 1])
        block13Oct3, hist13OctZW[:, :, 2] = sosfilt(OCTAVE_BAND13_3_taps, blockZW, zi=hist13OctZW[:, :, 2])
        block13Oct4, hist13OctZW[:, :, 3] = sosfilt(OCTAVE_BAND13_4_taps, blockZW, zi=hist13OctZW[:, :, 3])
        block13Oct5, hist13OctZW[:, :, 4] = sosfilt(OCTAVE_BAND13_5_taps, blockZW, zi=hist13OctZW[:, :, 4])
        block13Oct6, hist13OctZW[:, :, 5] = sosfilt(OCTAVE_BAND13_6_taps, blockZW, zi=hist13OctZW[:, :, 5])
        block13Oct7, hist13OctZW[:, :, 6] = sosfilt(OCTAVE_BAND13_7_taps, blockZW, zi=hist13OctZW[:, :, 6])
        block13Oct8, hist13OctZW[:, :, 7] = sosfilt(OCTAVE_BAND13_8_taps, blockZW, zi=hist13OctZW[:, :, 7])
        block13Oct9, hist13OctZW[:, :, 8] = sosfilt(OCTAVE_BAND13_9_taps, blockZW, zi=hist13OctZW[:, :, 8])
        block13Oct10, hist13OctZW[:, :, 9] = sosfilt(OCTAVE_BAND13_10_taps, blockZW, zi=hist13OctZW[:, :, 9])
        block13Oct11, hist13OctZW[:, :, 10] = sosfilt(OCTAVE_BAND13_11_taps, blockZW, zi=hist13OctZW[:, :, 10])
        block13Oct12, hist13OctZW[:, :, 11] = sosfilt(OCTAVE_BAND13_12_taps, blockZW, zi=hist13OctZW[:, :, 11])
        block13Oct13, hist13OctZW[:, :, 12] = sosfilt(OCTAVE_BAND13_13_taps, blockZW, zi=hist13OctZW[:, :, 12])
        block13Oct14, hist13OctZW[:, :, 13] = sosfilt(OCTAVE_BAND13_14_taps, blockZW, zi=hist13OctZW[:, :, 13])
        block13Oct15, hist13OctZW[:, :, 14] = sosfilt(OCTAVE_BAND13_15_taps, blockZW, zi=hist13OctZW[:, :, 14])
        '''
        #block13Oct16, hist13OctZW[:, :, 15] = sosfilt(OCTAVE_BAND13_16_taps, blockZW, zi=hist13OctZW[:, :, 15])
        #print('block13Oct16', block13Oct16)

        '''
        block13Oct17, hist13OctZW[:, :, 16] = sosfilt(OCTAVE_BAND13_17_taps, blockZW, zi=hist13OctZW[:, :, 16])
        block13Oct18, hist13OctZW[:, :, 17] = sosfilt(OCTAVE_BAND13_18_taps, blockZW, zi=hist13OctZW[:, :, 17])
        block13Oct19, hist13OctZW[:, :, 18] = sosfilt(OCTAVE_BAND13_19_taps, blockZW, zi=hist13OctZW[:, :, 18])
        block13Oct20, hist13OctZW[:, :, 19] = sosfilt(OCTAVE_BAND13_20_taps, blockZW, zi=hist13OctZW[:, :, 19])
        block13Oct21, hist13OctZW[:, :, 20] = sosfilt(OCTAVE_BAND13_21_taps, blockZW, zi=hist13OctZW[:, :, 20])
        block13Oct22, hist13OctZW[:, :, 21] = sosfilt(OCTAVE_BAND13_22_taps, blockZW, zi=hist13OctZW[:, :, 21])
        block13Oct23, hist13OctZW[:, :, 22] = sosfilt(OCTAVE_BAND13_23_taps, blockZW, zi=hist13OctZW[:, :, 22])
        block13Oct24, hist13OctZW[:, :, 23] = sosfilt(OCTAVE_BAND13_24_taps, blockZW, zi=hist13OctZW[:, :, 23])
        block13Oct25, hist13OctZW[:, :, 24] = sosfilt(OCTAVE_BAND13_25_taps, blockZW, zi=hist13OctZW[:, :, 24])
        block13Oct26, hist13OctZW[:, :, 25] = sosfilt(OCTAVE_BAND13_26_taps, blockZW, zi=hist13OctZW[:, :, 25])
        block13Oct27, hist13OctZW[:, :, 26] = sosfilt(OCTAVE_BAND13_27_taps, blockZW, zi=hist13OctZW[:, :, 26])
        block13Oct28, hist13OctZW[:, :, 27] = sosfilt(OCTAVE_BAND13_28_taps, blockZW, zi=hist13OctZW[:, :, 27])
        block13Oct29, hist13OctZW[:, :, 28] = sosfilt(OCTAVE_BAND13_29_taps, blockZW, zi=hist13OctZW[:, :, 28])
        block13Oct30, hist13OctZW[:, :, 29] = sosfilt(OCTAVE_BAND13_30_taps, blockZW, zi=hist13OctZW[:, :, 29])
        '''

        blockZW = blockZW.astype(np.float64)
        #start = time.perf_counter()
       # Call processing
        lib_filters.process_block(blockZW, output_array, CHUNK_SIZE)
        #print('np.shape(output_array): ', np.shape(output_array))
        #end = time.perf_counter()
        #print("elapsed_Filters13Oct.process_block (ms):", np.round((end - start) * 1000, 5))
 
        # Now, reshape output_array if necessary:
        #block13Oct = output_array.reshape((CHUNK_SIZE, N_13OCTAVE_BANDS))
        block13Oct = output_array.reshape(-1)
        block13Oct = block13Oct.astype(np.float32)
       
        #print('np.shape(block13Oct): ', np.shape(block13Oct))
        #print('block13Oct[:, 15]: ', block13Oct[:, 15])

        #end = time.perf_counter()
        #print("elapsed_PORTO B (ms):", np.round((end - start) * 1000, 5))

        # =================
        # === PORTO C =====
        # =================
        #start = time.perf_counter()


        blockZWSquare = process_block_square(blockZW)
        #print('blockZWSquare: ', blockZWSquare)
        blockCWSquare = process_block_square(blockCW)
        blockAWSquare = process_block_square(blockAW)

        block13OctZWSquare = process_block_square(block13Oct)
        block13OctZWSquare = block13OctZWSquare.reshape((CHUNK_SIZE, N_13OCTAVE_BANDS))

        '''
        # Call the function
        block13OctZWSquare = block13Oct # para preservar block13Oct
        lib_filterbankSquared.process_block_square_columns(block13OctZWSquare, CHUNK_SIZE, N_13OCTAVE_BANDS)
        '''
        #print('np.shape(block13OctZWSquare): ', np.shape(block13OctZWSquare))

        '''
        # 1/3 Octave Bands
        block13Oct1ZWSquare = process_block_square(block13Oct[:, 0])
        block13Oct2ZWSquare = process_block_square(block13Oct[:, 1])
        block13Oct3ZWSquare = process_block_square(block13Oct[:, 2])
        block13Oct4ZWSquare = process_block_square(block13Oct[:, 3])
        block13Oct5ZWSquare = process_block_square(block13Oct[:, 4])
        block13Oct6ZWSquare = process_block_square(block13Oct[:, 5])
        block13Oct7ZWSquare = process_block_square(block13Oct[:, 6])
        block13Oct8ZWSquare = process_block_square(block13Oct[:, 7])
        block13Oct9ZWSquare = process_block_square(block13Oct[:, 8])
        block13Oct10ZWSquare = process_block_square(block13Oct[:, 9])
        block13Oct11ZWSquare = process_block_square(block13Oct[:, 10])
        block13Oct12ZWSquare = process_block_square(block13Oct[:, 11])
        block13Oct13ZWSquare = process_block_square(block13Oct[:, 12])
        block13Oct14ZWSquare = process_block_square(block13Oct[:, 13])
        block13Oct15ZWSquare = process_block_square(block13Oct[:, 14])
        block13Oct16ZWSquare = process_block_square(block13Oct[:, 15])
        #print('block13Oct16ZWSquare: ', block13Oct16ZWSquare)
        #print('np.shape(block13Oct16ZWSquare): ', np.shape(block13Oct16ZWSquare))

        block13Oct17ZWSquare = process_block_square(block13Oct[:, 16])
        block13Oct18ZWSquare = process_block_square(block13Oct[:, 17])
        block13Oct19ZWSquare = process_block_square(block13Oct[:, 18])
        block13Oct20ZWSquare = process_block_square(block13Oct[:, 19])
        block13Oct21ZWSquare = process_block_square(block13Oct[:, 20])
        block13Oct22ZWSquare = process_block_square(block13Oct[:, 21])
        block13Oct23ZWSquare = process_block_square(block13Oct[:, 22])
        block13Oct24ZWSquare = process_block_square(block13Oct[:, 23])
        block13Oct25ZWSquare = process_block_square(block13Oct[:, 24])
        block13Oct26ZWSquare = process_block_square(block13Oct[:, 25])
        block13Oct27ZWSquare = process_block_square(block13Oct[:, 26])
        block13Oct28ZWSquare = process_block_square(block13Oct[:, 27])
        block13Oct29ZWSquare = process_block_square(block13Oct[:, 28])
        block13Oct30ZWSquare = process_block_square(block13Oct[:, 29])
        '''
        '''
        # 1/3 Octave Bands
        block13Oct1ZWSquare = process_block_square(block13Oct1)
        block13Oct2ZWSquare = process_block_square(block13Oct2)
        block13Oct3ZWSquare = process_block_square(block13Oct3)
        block13Oct4ZWSquare = process_block_square(block13Oct4)
        block13Oct5ZWSquare = process_block_square(block13Oct5)
        block13Oct6ZWSquare = process_block_square(block13Oct6)
        block13Oct7ZWSquare = process_block_square(block13Oct7)
        block13Oct8ZWSquare = process_block_square(block13Oct8)
        block13Oct9ZWSquare = process_block_square(block13Oct9)
        block13Oct10ZWSquare = process_block_square(block13Oct10)
        block13Oct11ZWSquare = process_block_square(block13Oct11)
        block13Oct12ZWSquare = process_block_square(block13Oct12)
        block13Oct13ZWSquare = process_block_square(block13Oct13)
        block13Oct14ZWSquare = process_block_square(block13Oct14)
        block13Oct15ZWSquare = process_block_square(block13Oct15)
        block13Oct16ZWSquare2 = process_block_square(block13Oct16)

        print('block13Oct16ZWSquare2: ', block13Oct16ZWSquare2)
        print('np.shape(block13Oct16ZWSquare2): ', np.shape(block13Oct16ZWSquare2))

        block13Oct17ZWSquare = process_block_square(block13Oct17)
        block13Oct18ZWSquare = process_block_square(block13Oct18)
        block13Oct19ZWSquare = process_block_square(block13Oct19)
        block13Oct20ZWSquare = process_block_square(block13Oct20)
        block13Oct21ZWSquare = process_block_square(block13Oct21)
        block13Oct22ZWSquare = process_block_square(block13Oct22)
        block13Oct23ZWSquare = process_block_square(block13Oct23)
        block13Oct24ZWSquare = process_block_square(block13Oct24)
        block13Oct25ZWSquare = process_block_square(block13Oct25)
        block13Oct26ZWSquare = process_block_square(block13Oct26)
        block13Oct27ZWSquare = process_block_square(block13Oct27)
        block13Oct28ZWSquare = process_block_square(block13Oct28)
        block13Oct29ZWSquare = process_block_square(block13Oct29)
        block13Oct30ZWSquare = process_block_square(block13Oct30)
        '''

        #end = time.perf_counter()
        #print("elapsed_PORTO C (ms):", np.round((end - start) * 1000, 5))

        # =================
        # === PORTO D =====
        # =================
        #start = time.perf_counter()


        blockZWTW, histZWTW = lfilter(bTW, aTW, blockZWSquare, zi=histZWTW) # Uses long time constant to detect Sound Events
        blockCWTW, histCWTW = lfilter(bTW, aTW, blockCWSquare, zi=histCWTW)
        blockAWTW, histAWTW = lfilter(bTW, aTW, blockAWSquare, zi=histAWTW)
        blockAWTW_SLOW, histAWTW_SLOW = lfilter(bTW_SLOW, aTW_SLOW, blockAWSquare, zi=histAWTW_SLOW) # Uses long time constant to detect Sound Events



# Example data block
        #block13OctZWSquare = np.random.randn(CHUNK_SIZE, N_13OCTAVE_BANDS).astype(np.float32)

        '''
        # 1/3 Octave Bands
        block13Oct1ZWTW, hist13OctZWTW[:, 0] = lfilter(bTW, aTW, block13OctZWSquare[:, 0], zi=hist13OctZWTW[:, 0])
        block13Oct2ZWTW, hist13OctZWTW[:, 1] = lfilter(bTW, aTW, block13OctZWSquare[:, 1], zi=hist13OctZWTW[:, 1])
        block13Oct3ZWTW, hist13OctZWTW[:, 2] = lfilter(bTW, aTW, block13OctZWSquare[:, 2], zi=hist13OctZWTW[:, 2])
        block13Oct4ZWTW, hist13OctZWTW[:, 3] = lfilter(bTW, aTW, block13OctZWSquare[:, 3], zi=hist13OctZWTW[:, 3])
        block13Oct5ZWTW, hist13OctZWTW[:, 4] = lfilter(bTW, aTW, block13OctZWSquare[:, 4], zi=hist13OctZWTW[:, 4])
        block13Oct6ZWTW, hist13OctZWTW[:, 5] = lfilter(bTW, aTW, block13OctZWSquare[:, 5], zi=hist13OctZWTW[:, 5])
        block13Oct7ZWTW, hist13OctZWTW[:, 6] = lfilter(bTW, aTW, block13OctZWSquare[:, 6], zi=hist13OctZWTW[:, 6])
        block13Oct8ZWTW, hist13OctZWTW[:, 7] = lfilter(bTW, aTW, block13OctZWSquare[:, 7], zi=hist13OctZWTW[:, 7])
        block13Oct9ZWTW, hist13OctZWTW[:, 8] = lfilter(bTW, aTW, block13OctZWSquare[:, 8], zi=hist13OctZWTW[:, 8])
        block13Oct10ZWTW, hist13OctZWTW[:, 9] = lfilter(bTW, aTW, block13OctZWSquare[:, 9], zi=hist13OctZWTW[:, 9])
        block13Oct11ZWTW, hist13OctZWTW[:, 10] = lfilter(bTW, aTW, block13OctZWSquare[:, 10], zi=hist13OctZWTW[:, 10])
        block13Oct12ZWTW, hist13OctZWTW[:, 11] = lfilter(bTW, aTW, block13OctZWSquare[:, 11], zi=hist13OctZWTW[:, 11])
        block13Oct13ZWTW, hist13OctZWTW[:, 12] = lfilter(bTW, aTW, block13OctZWSquare[:, 12], zi=hist13OctZWTW[:, 12])
        block13Oct14ZWTW, hist13OctZWTW[:, 13] = lfilter(bTW, aTW, block13OctZWSquare[:, 13], zi=hist13OctZWTW[:, 13])
        block13Oct15ZWTW, hist13OctZWTW[:, 14] = lfilter(bTW, aTW, block13OctZWSquare[:, 14], zi=hist13OctZWTW[:, 14])
        print('block13Oct13ZWTW: ', block13Oct13ZWTW)
        #print('block13Oct14ZWTW: ', block13Oct14ZWTW)
        #print('block13Oct15ZWTW: ', block13Oct15ZWTW)
        print('np.shape(block13Oct15ZWTW): ', np.shape(block13Oct15ZWTW))

        block13Oct16ZWTW, hist13OctZWTW[:, 15] = lfilter(bTW, aTW, block13OctZWSquare[:, 15], zi=hist13OctZWTW[:, 15])
        block13Oct17ZWTW, hist13OctZWTW[:, 16] = lfilter(bTW, aTW, block13OctZWSquare[:, 16], zi=hist13OctZWTW[:, 16])
        block13Oct18ZWTW, hist13OctZWTW[:, 17] = lfilter(bTW, aTW, block13OctZWSquare[:, 17], zi=hist13OctZWTW[:, 17])
        block13Oct19ZWTW, hist13OctZWTW[:, 18] = lfilter(bTW, aTW, block13OctZWSquare[:, 18], zi=hist13OctZWTW[:, 18])
        block13Oct20ZWTW, hist13OctZWTW[:, 19] = lfilter(bTW, aTW, block13OctZWSquare[:, 19], zi=hist13OctZWTW[:, 19])
        block13Oct21ZWTW, hist13OctZWTW[:, 20] = lfilter(bTW, aTW, block13OctZWSquare[:, 20], zi=hist13OctZWTW[:, 20])
        block13Oct22ZWTW, hist13OctZWTW[:, 21] = lfilter(bTW, aTW, block13OctZWSquare[:, 21], zi=hist13OctZWTW[:, 21])
        block13Oct23ZWTW, hist13OctZWTW[:, 22] = lfilter(bTW, aTW, block13OctZWSquare[:, 22], zi=hist13OctZWTW[:, 22])
        block13Oct24ZWTW, hist13OctZWTW[:, 23] = lfilter(bTW, aTW, block13OctZWSquare[:, 23], zi=hist13OctZWTW[:, 23])
        block13Oct25ZWTW, hist13OctZWTW[:, 24] = lfilter(bTW, aTW, block13OctZWSquare[:, 24], zi=hist13OctZWTW[:, 24])
        block13Oct26ZWTW, hist13OctZWTW[:, 25] = lfilter(bTW, aTW, block13OctZWSquare[:, 25], zi=hist13OctZWTW[:, 25])
        block13Oct27ZWTW, hist13OctZWTW[:, 26] = lfilter(bTW, aTW, block13OctZWSquare[:, 26], zi=hist13OctZWTW[:, 26])
        block13Oct28ZWTW, hist13OctZWTW[:, 27] = lfilter(bTW, aTW, block13OctZWSquare[:, 27], zi=hist13OctZWTW[:, 27])
        block13Oct29ZWTW, hist13OctZWTW[:, 28] = lfilter(bTW, aTW, block13OctZWSquare[:, 28], zi=hist13OctZWTW[:, 28])
        block13Oct30ZWTW, hist13OctZWTW[:, 29] = lfilter(bTW, aTW, block13OctZWSquare[:, 29], zi=hist13OctZWTW[:, 29])
        '''

        #block13OctZWTW = block13OctZWSquare
        #block13OctZWTW = block13OctZWTW.astype(np.float64)


        # Process block
        lib_TimeWeightFilter.process_time_weight_block(block13OctZWSquare, CHUNK_SIZE, N_13OCTAVE_BANDS)

        block13OctZWTW = block13OctZWSquare

        
        #block13OctZWTW = block13OctZWTW.astype(np.float32)

        #print('block13OctZWTW[:, 14] - PORTO D: ', block13OctZWTW[:, 12])
        #print('np.shape(block13OctZWTW): ', np.shape(block13OctZWTW))


        '''
        block13OctZWTW = np.zeros([len(block13Oct1ZWTW), 30], dtype='float32')

        block13OctZWTW[:, 0] = block13Oct1ZWTW.T
        block13OctZWTW[:, 1] = block13Oct2ZWTW.T
        block13OctZWTW[:, 2] = block13Oct3ZWTW.T
        block13OctZWTW[:, 3] = block13Oct4ZWTW.T
        block13OctZWTW[:, 4] = block13Oct5ZWTW.T
        block13OctZWTW[:, 5] = block13Oct6ZWTW.T
        block13OctZWTW[:, 6] = block13Oct7ZWTW.T
        block13OctZWTW[:, 7] = block13Oct8ZWTW.T
        block13OctZWTW[:, 8] = block13Oct9ZWTW.T
        block13OctZWTW[:, 9] = block13Oct10ZWTW.T
        block13OctZWTW[:, 10] = block13Oct11ZWTW.T
        block13OctZWTW[:, 11] = block13Oct12ZWTW.T
        block13OctZWTW[:, 12] = block13Oct13ZWTW.T
        block13OctZWTW[:, 13] = block13Oct14ZWTW.T
        block13OctZWTW[:, 14] = block13Oct15ZWTW.T
        block13OctZWTW[:, 15] = block13Oct16ZWTW.T
        block13OctZWTW[:, 16] = block13Oct17ZWTW.T
        block13OctZWTW[:, 17] = block13Oct18ZWTW.T
        block13OctZWTW[:, 18] = block13Oct19ZWTW.T
        block13OctZWTW[:, 19] = block13Oct20ZWTW.T
        block13OctZWTW[:, 20] = block13Oct21ZWTW.T
        block13OctZWTW[:, 21] = block13Oct22ZWTW.T
        block13OctZWTW[:, 22] = block13Oct23ZWTW.T
        block13OctZWTW[:, 23] = block13Oct24ZWTW.T
        block13OctZWTW[:, 24] = block13Oct25ZWTW.T
        block13OctZWTW[:, 25] = block13Oct26ZWTW.T
        block13OctZWTW[:, 26] = block13Oct27ZWTW.T
        block13OctZWTW[:, 27] = block13Oct28ZWTW.T
        block13OctZWTW[:, 28] = block13Oct29ZWTW.T
        block13OctZWTW[:, 29] = block13Oct30ZWTW.T
        '''

        blockZW = blockZW.astype(np.float32)
        #print('np.any(np.isnan(blockZW)): ', np.any(np.isnan(blockZW)))
        blockCW = blockCW.astype(np.float32)
        #print('np.any(np.isnan(blockCW)): ', np.any(np.isnan(blockCW)))
        blockAW = blockAW.astype(np.float32)
        #print('np.any(np.isnan(blockAW)): ', np.any(np.isnan(blockAW)))
        blockZWTW = blockZWTW.astype(np.float32)
        #print('np.any(np.isnan(blockZWTW)): ', np.any(np.isnan(blockZWTW)))
        blockCWTW = blockCWTW.astype(np.float32)
        #print('np.any(np.isnan(blockCWTW)): ', np.any(np.isnan(blockCWTW)))
        blockAWTW = blockAWTW.astype(np.float32)
        #print('np.any(np.isnan(blockAWTW)): ', np.any(np.isnan(blockAWTW)))
        blockAWTW_SLOW = blockAWTW_SLOW.astype(np.float32)
        flat_block13OctZWTW = block13OctZWTW.reshape(-1)  # or .ravel()
        #end2 = time.perf_counter()
        #print("elapsed_flat_block13OctZWTW (ms):", np.round((end2 - start2) * 1000, 5))
        #print('np.any(np.isnan(blockAWTW)): ', np.any(np.isnan(blockAWTW)))
        
        #start2 = time.perf_counter()

        #flat_block13OctZWTW = block13OctZWTW.flatten().astype(np.float32)
        #print('block13OctZWTW.flags[C_CONTIGUOUS]_____: ', block13OctZWTW.flags['C_CONTIGUOUS'])
        #print('np.shape(block13OctZWTW)_____: ', np.shape(block13OctZWTW))
        #print('np.shape(flat_block13OctZWTW - PORTO D): ', np.shape(flat_block13OctZWTW))
        #print('(flat_block13OctZWTW) - PORTO D: ', (flat_block13OctZWTW))
        #        print('(blockAWTW before ring)): ', (blockAWTW))
        #print('np.any(np.isnan(flat_block13OctZWTW)): ', np.any(np.isnan(flat_block13OctZWTW)))


        written = lib.ringbuffer_fifo_write(ringBuffZW, blockZW.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), CHUNK_SIZE)
        #print('lib.ringbuffer_fifo_write(ringBuffZW')
        lib.ringbuffer_fifo_write(ringBuffCW, blockCW.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), CHUNK_SIZE)
        lib.ringbuffer_fifo_write(ringBuffAW, blockAW.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), CHUNK_SIZE)
        lib.ringbuffer_fifo_write(ringBuffZWTW, blockZWTW.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), CHUNK_SIZE)
        lib.ringbuffer_fifo_write(ringBuffCWTW, blockCWTW.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), CHUNK_SIZE)
        lib.ringbuffer_fifo_write(ringBuffAWTW, blockAWTW.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), CHUNK_SIZE)

        lib.ringbuffer_fifo_write(ringBuffAWTW_SLOW, blockAWTW_SLOW.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), CHUNK_SIZE)   # Alarms

        write_index = (write_index + written) % BUFFER_SIZE
        available_samples += written
        #samples_written += CHUNK_SIZE


        lib_13Oct.ringbuffer_fifo_write(ringBuffZWTW_13Oct, flat_block13OctZWTW.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), CHUNK_SIZE)

        #end = time.perf_counter()
        #print("elapsed_PORTO D (ms):", np.round((end - start) * 1000, 5))

        if SaveAudiofile_OK:

            # Add to the accumulator to prepare to write to file
    #        sample_accumulator_raw = np.concatenate((sample_accumulator_raw, blockZW * 2**(NBITS-1)))
    #        sample_accumulator_filtered = np.concatenate((sample_accumulator_filtered, blockAW * 2**(NBITS-1)))
            sample_accumulator_raw.append(blockZW * 2 ** (NBITS - 1))
            #sample_accumulator_filtered.append(blockAW * 2 ** (NBITS - 1))
            buffered_samples += len(blockZW)

            #print('buffered_samples: ', buffered_samples)
            #print('ringBuffAWTW.is_full(): ', ringBuffAWTW.is_full())

            #print('samples_written: ', samples_written)
            #print('samples_read: ', samples_read)
        
        if SoundEvent_OK:
            sample_accumulator_event.append(blockZW * 2 ** (NBITS - 1))
            buffered_samples_event += len(blockZW)

        # The RingBuffer fills out. NoiseLevels calculation from filtered ring buffer
        while available_samples >= SEGMENT_SIZE:
        #while samples_written - samples_read >= SEGMENT_SIZE:

  
            #print('======= NOISE LEVELS CALCULATING ====== ')
            #ringBuffZW_ = np.zeros(SEGMENT_SIZE, dtype=np.float32)
            lib.ringbuffer_fifo_peek(ringBuffZW, ringBuffZW_.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                                     read_index, SEGMENT_SIZE)
            #print('(ringBuffZW_): ', (ringBuffZW_))

            #ringBuffCW_ = np.zeros(SEGMENT_SIZE, dtype=np.float32)
            lib.ringbuffer_fifo_peek(ringBuffCW, ringBuffCW_.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                                     read_index, SEGMENT_SIZE)
            #print('(ringBuffCW_): ', (ringBuffCW_))

            #ringBuffAW_ = np.zeros(SEGMENT_SIZE, dtype=np.float32)
            lib.ringbuffer_fifo_peek(ringBuffAW, ringBuffAW_.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                                     read_index, SEGMENT_SIZE)
            #print('(ringBuffAW_): ', (ringBuffAW_))

            #ringBuffZWTW_ = np.zeros(SEGMENT_SIZE, dtype=np.float32)
            lib.ringbuffer_fifo_peek(ringBuffZWTW, ringBuffZWTW_.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                                     read_index, SEGMENT_SIZE)
            #print('(ringBuffZWTW_): ', (ringBuffZWTW_))

            #ringBuffCWTW_ = np.zeros(SEGMENT_SIZE, dtype=np.float32)
            lib.ringbuffer_fifo_peek(ringBuffCWTW, ringBuffCWTW_.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                                     read_index, SEGMENT_SIZE)

            #ringBuffAWTW_ = np.zeros(SEGMENT_SIZE, dtype=np.float32)
            lib.ringbuffer_fifo_peek(ringBuffAWTW, ringBuffAWTW_.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
                                     read_index, SEGMENT_SIZE)
            #print('(ringBuffAWTW_): ', (ringBuffAWTW_))
            #print(f"Block read at {samples_read}: {out[:5]} ...")


            #ringBuffAWTW_SLOW_ = np.zeros(SEGMENT_SIZE, dtype=np.float32)
            lib.ringbuffer_fifo_peek(ringBuffAWTW_SLOW, ringBuffAWTW_SLOW_.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),      #Alarms
                                     read_index, SEGMENT_SIZE)
            #print('(ringBuffAWTW_): ', (ringBuffAWTW_))
 

            ringBuffZWTW_13Oct_ = np.zeros((SEGMENT_SIZE, N_13OCTAVE_BANDS), dtype=np.float32)
            lib_13Oct.ringbuffer_fifo_read(ringBuffZWTW_13Oct, ringBuffZWTW_13Oct_.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), SEGMENT_SIZE)

            #samples_read += SEGMENT_SIZE
            read_index = (read_index + SEGMENT_SIZE) % BUFFER_SIZE
            available_samples -= SEGMENT_SIZE
#            print('ringBuffAWTW_[2*CHUNK_SIZE:]: after ring', ringBuffAWTW_[2*CHUNK_SIZE:])

            start = time.perf_counter()

            #ringBuffZWTW_13Oct_ = ringBuffZWTW_13Oct_.T
            ringBuffZWTW_13Oct_ = ringBuffZWTW_13Oct_.T.copy()
            #print('(ringBuffZWTW_13Oct_  - PORTO D - SEGMENT): ', (ringBuffZWTW_13Oct_))
            #print('ringBuffZWTW_13Oct_.flags[C_CONTIGUOUS]_____: ', ringBuffZWTW_13Oct_.flags['C_CONTIGUOUS'])
            #print('np.shape(ringBuffZWTW_13Oct______): ', np.shape(ringBuffZWTW_13Oct_))



            '''
            #print('(Noise_LinTimeLine): ', (Noise_LinTimeLine))
            print('np.shape(Noise_LinTimeLine): ', np.shape(Noise_LinTimeLine))
            print('(cntSegmBegin): ', (cntSegmBegin))
            print('(Noise_LinTimeLine[14][0]): ', (Noise_LinTimeLine[14][0]))
            print('(np.shape(Noise_LinTimeLine[14][0]): ', np.shape(Noise_LinTimeLine[14][0]))


        #print('np.shape(cntSegmBegin): ', (cntSegmBegin))
            LZprmsLast = Noise_LinTimeLine[14, cntSegmBegin]  # Utiliza o último valor Lprms para calcular o atual
            #        print('LZprmsLast: ', LZprmsLast)
            LCprmsLast = Noise_LinTimeLine[15, cntSegmBegin]  # Utiliza o último valor Lprms para calcular o atual
            #    print('LCprmsLast: ', LCprmsLast)
            LAprmsLast = Noise_LinTimeLine[16, cntSegmBegin]  # Utiliza o último valor Lprms para calcular o atual
            #         print('LZprmsLast: ', LZprmsLast)
            #print('LAprmsLast: ', LAprmsLast)
            '''


            #bufZW = (ctypes.c_float * SEGMENT_SIZE)(*ringBuffZW_)
            bufZW = ringBuffZW_.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            #print('bufZW: ', bufZW)
            #bufCW = (ctypes.c_float * SEGMENT_SIZE)(*ringBuffCW_)
            bufCW = ringBuffCW_.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            #bufAW = (ctypes.c_float * SEGMENT_SIZE)(*ringBuffAW_)
            bufAW = ringBuffAW_.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            #bufZWTW = (ctypes.c_float * SEGMENT_SIZE)(*ringBuffZWTW_)
            bufZWTW = ringBuffZWTW_.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            #bufCWTW = (ctypes.c_float * SEGMENT_SIZE)(*ringBuffCWTW_)
            bufCWTW = ringBuffCWTW_.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            #bufAWTW = (ctypes.c_float * SEGMENT_SIZE)(*ringBuffAWTW_)
            bufAWTW = ringBuffAWTW_.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            
            bufAWTW_SLOW = ringBuffAWTW_SLOW_.ctypes.data_as(ctypes.POINTER(ctypes.c_float))    #Alarms

 
            #print('ringBuffZWTW_13Oct_: ', ringBuffZWTW_13Oct_)
            #flat_data = ringBuffZWTW_13Oct_.astype(np.float32).flatten()
            #bufZWTW_13Oct = (ctypes.c_float * (SEGMENT_SIZE * N_13OCTAVE_BANDS))(*flat_data)
            #print('ringBuffZWTW_13Oct_.flags[C_CONTIGUOUS]: ', ringBuffZWTW_13Oct_.flags['C_CONTIGUOUS'])
            #print('np.shape(ringBuffZWTW_13Oct_): ', np.shape(ringBuffZWTW_13Oct_))


            ringBuffZWTW_13Oct_ = ringBuffZWTW_13Oct_.reshape(-1)  # or .ravel()
            #ringBuffZWTW_13Oct_ = np.ascontiguousarray(ringBuffZWTW_13Oct_, dtype=np.float32)
            #print('ringBuffZWTW_13Oct_.flags[C_CONTIGUOUS]: ', ringBuffZWTW_13Oct_.flags['C_CONTIGUOUS'])
            #print('np.shape(ringBuffZWTW_13Oct_): ', np.shape(ringBuffZWTW_13Oct_))

            bufZWTW_13Oct = ringBuffZWTW_13Oct_.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
            #end = time.perf_counter()
            #print("elapsed_time_ringBuffZWTW_13Oct______ (ms):", np.round((end - start) * 1000, 3))

            #print('np.shape(ringBuffZWTW_13Oct_): ', np.shape(ringBuffZWTW_13Oct_))
            #print('len(ringBuffZWTW_13Oct_): ', len(ringBuffZWTW_13Oct_))
            #print('np.size(ringBuffZWTW_13Oct_): ', np.size(ringBuffZWTW_13Oct_))

            #print('bufZWTW_13Oct   - PORTO D - antes CalcNoiseLevels: ', bufZWTW_13Oct)
            #print('np.shape(bufZWTW_13Oct): ', np.shape(bufZWTW_13Oct))
            #print('len(bufZWTW_13Oct): ', len(bufZWTW_13Oct))
            #print('np.size(bufZWTW_13Oct): ', np.size(bufZWTW_13Oct))

            '''
            print(f"B500: {ringBuffZWTW_13Oct_[SEGMENT_SIZE * 13]}")
            print(f"B1000: {ringBuffZWTW_13Oct_[SEGMENT_SIZE * 16]}")
            print(f"B2000: {ringBuffZWTW_13Oct_[SEGMENT_SIZE * 19]}")
            print(ringBuffZW_.dtype)  # Should be float32
            print(ringBuffZWTW_13Oct_.dtype)  # Should be float32
            assert ringBuffZWTW_13Oct_.dtype == np.float32
            assert ringBuffZWTW_13Oct_.ndim == 1
            assert ringBuffZWTW_13Oct_.size == SEGMENT_SIZE * N_13OCTAVE_BANDS
            print('ringBuffZWTW_13Oct_.flags[C_CONTIGUOUS]: ', ringBuffZWTW_13Oct_.flags['C_CONTIGUOUS'])

            '''

            #NoiLevls_dB = (ctypes.c_float * (1 + 16 + N_13OCTAVE_BANDS + 2 + 10))() # 1 (timeStamp) + 16 (sound levels) + N_13OCTAVE_BANDS + 2 (Alarms) + 10 (TypeEvents)
            #Noi_Lin = (ctypes.c_float * (1 + 16 + N_13OCTAVE_BANDS + 2 + 10))()

            lib_NoiseLevels.process_block_Levels(
                Pcalrms,  # Pcal_rms
                cntSegmBegin,  # cntSegmBg
                cntSegmBeginOffSetIni,  # cntSegmBeginOffSet
                LZpeakTprmsLast,  # LZpeakTLast
                LCpeakTprmsLast,  # LCpeakTLast
                LApeakTprmsLast,  # LApeakTLast
                LAFmaxTprmsLast,  # LAFmaxTLast
                LAFminTprmsLast,  # LAFminTLast
                LZprmsLast,  # LZpLast
                LCprmsLast,  # LCpLast
                LAprmsLast,  # LApLast
                bufZW,
                bufCW,
                bufAW,
                bufZWTW,
                bufCWTW,
                bufAWTW,
                bufZWTW_13Oct,
                bufAWTW_SLOW,
                SEGMENT_SIZE,
                N_13OCTAVE_BANDS,
                CAL94,
                NoiLevls_dB,
                Noi_Lin
            )
            
            #print("len(NoiseLevels_dB:", len(NoiseLevels_dB))
            #print("size(NoiseLevels_dB:", np.size(NoiseLevels_dB))


            # Convert to numpy arrays to see results
            NoiseLevels_dB = np.ctypeslib.as_array(NoiLevls_dB)
            Noise_Lin = np.ctypeslib.as_array(Noi_Lin)

            
            NoiseLevels_dB = NoiseLevels_dB.astype(np.float64)

            NoiseLevels_dB[0] = np.round(time.time(), 2)
            #print("NoiseLevels_dB[0]:", NoiseLevels_dB[0])
            #print("NoiseLevels_dB:", NoiseLevels_dB)
            #print("len(NoiseLevels_dB:", len(NoiseLevels_dB))
            #print("size(NoiseLevels_dB:", np.size(NoiseLevels_dB))


            NoiseLevels_dB[1] = SENSOR_ID # SensorID = 'sensor1'

            counterPercentil_LAxx += 1

            #import random

            Percentil.append(NoiseLevels_dB[4]) # Utiliza o LAF para extrair o LAxx
            #random.shuffle(Percentil)
            
            #print('counterPercentil_LAxx: ', counterPercentil_LAxx)
            #print('Percentil: ', Percentil)



            #print('Percentil_LAxx: ', Percentil_LAxx)
            #print('NoiseLevels_dB[47] ', NoiseLevels_dB[47])
            #print('NoiseLevels_dB[47]')
            
            #NoiseLevels_dB[4] = NoiseLevels_dB[47]

            if counterPercentil_LAxx >= SEGMENTS_PERCENTIL_LAxx: # Atualiza o Percentil_LAxx

                Percentil_LAxx = np.percentile(Percentil, PERCENTIL_VALUE)
                #print('Percentil_LAxx: ', Percentil_LAxx)
                Percentil = []
                counterPercentil_LAxx = 0


            if NoiseLevels_dB[48] >= Percentil_LAxx + THRESHOLD_EVENT_OFFSET:
                NoiseLevels_dB[49] = 10
                #print('Alarm: ', NoiseLevels_dB[47])

            #===== grava LAxx para teste =====
            #NoiseLevels_dB[50] = Percentil_LAxx
            #NoiseLevels_dB[51] = Percentil_LAxx + THRESHOLD_EVENT_OFFSET
            #===== grava LAxx para teste =====

            with spl_lock:
                SPLReal_shared.value = NoiseLevels_dB[48]  # LAEA


            #print(type(NoiseLevels_dB))


            #print("NoiseLevels_dB:", NoiseLevels_dB)
            #print('np.shape(NoiseLevels_dB): ', np.shape(NoiseLevels_dB))


            #print("Noi_Lin:", Noise_Lin)
            

            '''
            NoiseLevels_dB, Noise_Lin = process_block_Levels(Pcalrms, cntSegmBegin, cntSegmBeginOffSetIni,
                                                             LZpeakTprmsLast, LCpeakTprmsLast, LApeakTprmsLast,
                                                             LAFmaxTprmsLast, LAFminTprmsLast, LZprmsLast, LCprmsLast, LAprmsLast,
                                                             ringBuffZW_, ringBuffCW_, ringBuffAW_,
                                                             ringBuffZWTW_, ringBuffCWTW_, ringBuffAWTW_, ringBuffZWTW_Oct_, ringBuffZWTW_13Oct_)
            '''

            
            if Noise_TimeLine_OK:
    #            Noise_dBTimeLine = np.hstack((Noise_dBTimeLine, np.round(NoiseLevels_dB, 1)))  # Atualiza o TimeLine dos níveis em dB
    #            Noise_LinTimeLine = np.hstack((Noise_LinTimeLine, Noise_Lin))  # Atualiza o TimeLine dos níveis
    #            print('np.shape(Noise_dBTimeLine): ', np.shape(Noise_dBTimeLine))

            # Append a copy (so changes next cycle don’t affect stored data)
                Noise_dBTimeLine_buffer.append(NoiseLevels_dB.copy())
                #Noise_LinTimeLine_buffer.append(Noise_Lin.copy())
                #print('np.shape(Noise_dBTimeLine_buffer): ', np.shape(Noise_dBTimeLine_buffer))

            NoiseLevels_dB_OneLine = np.transpose(NoiseLevels_dB)
            #print('NoiseLevels_dB_OneLine(timestamp): ', NoiseLevels_dB_OneLine[0])

            #print('NoiseLevels_dB_OneLine: ', NoiseLevels_dB_OneLine)

            #Echo_OK = False
            if EchoShort_OK:
################################################################# Para teste
                end = time.perf_counter()
                print("elapsed_time_block_Levels C (ms):", np.round((end - start) * 1000, 3))

                elapsed_time = np.round((time.time() - start_time) * 1000, 3)
                print('elapsed_time Total cycle (ms): ', elapsed_time)

                elapsed_time_session = np.round((time.time() - start_time_session)/60, 1)
                print('elapsed_time_Session (min): ', elapsed_time_session)




                counterEchoRefresh +=1
                if counterEchoRefresh % Echo_RefreshTimes == 0:
                    counterEchoRefresh = 0
                #if time.time() - last_print_time > Echo_RefreshTime:
                    #print(f"Status update at {time.time()}")

                    print('======= NOISE LEVELS CALCULATING ====== ')
                    print("NoiseLevels_dB[0]:", NoiseLevels_dB[0])

                    print('Percentil_LAxx: ', Percentil_LAxx)
                    print('Alarm: ', NoiseLevels_dB[49])
                    
                    if EchoComplete_OK:
                        print(f"ts: {np.round(NoiseLevels_dB[0], 3)} s")
                        print(f"Alarm: {np.round(NoiseLevels_dB[49], 0)} ")
                    
                    print(f"LAF: {np.round(NoiseLevels_dB[4], 1):.1f} dBA")
                    print(' ' * int(NoiseLevels_dB[4] - 1 + 10) + '*')
                    print(f"LCpeak: {np.round(NoiseLevels_dB[7], 1):.1f} dBA")
                    
                    if EchoComplete_OK:
                        print(f"LAFmax: {np.round(NoiseLevels_dB[11], 1):.1f} dBA")
                        print(f"LAFmin: {np.round(NoiseLevels_dB[13], 1):.1f} dBA")
                        print(f"LAeq: {np.round(NoiseLevels_dB[17], 1):.1f} dBA")
                        print(f"B31_5: {np.round(NoiseLevels_dB[19], 1):.1f} dBA")
                        print(f"B63: {np.round(NoiseLevels_dB[22], 1):.1f} dBA")
                        print(f"B125: {np.round(NoiseLevels_dB[25], 1):.1f} dBA")
                        print(f"B250: {np.round(NoiseLevels_dB[28], 1):.1f} dBA")
                        print(f"B500: {np.round(NoiseLevels_dB[31], 1):.1f} dBA")
                        print(f"B1000: {np.round(NoiseLevels_dB[34], 1):.1f} dBA")
                        print(f"B2000: {np.round(NoiseLevels_dB[37], 1):.1f} dBA")
                        print(f"B4000: {np.round(NoiseLevels_dB[40], 1):.1f} dBA")
                        print(f"B8000: {np.round(NoiseLevels_dB[43], 1):.1f} dBA")


                    #last_print_time = time.time()
                #print(f"LAZ: {np.round(NoiseLevels_dB[1], 1)} dBA")

                    #print('elapsed_time CalcNoiseLevels (ms): ', np.round(elapsed_time*1000,2))
                
                    #print('cntSegmBegin: ', cntSegmBegin)

                    #print('buffered_samples: ', buffered_samples)

            if SoundEvent_OK:
                while buffered_samples_event >= SAMPLES_PER_BLOCK_EVENT:
                    print('Classifying...')
                    stacked = np.ravel(np.hstack(sample_accumulator_event))
                    chunk_raw = stacked[:SAMPLES_PER_BLOCK_EVENT]
                    blockSC = chunk_raw

                    # Keep leftover samples
                    leftover = stacked[SAMPLES_PER_BLOCK_EVENT:]
                    sample_accumulator_event = [leftover] if len(leftover) > 0 else []
                    '''
                        blockSC = block
                        stacked = np.ravel(np.hstack(sample_accumulator_filtered))
                        chunk_filtered = stacked[:SAMPLES_PER_BLOCK_FILE]

                        # Keep leftover samples
                        leftover = stacked[SAMPLES_PER_BLOCK_FILE:]
                        sample_accumulator_filtered = [leftover] if len(leftover) > 0 else []
                        '''
                    buffered_samples_event = len(leftover)

                        #chunk_raw_i16 = np.clip(chunk_raw, -32768, 32767).astype(np.int16)
                        #chunk_filtered_i16 = np.clip(chunk_filtered, -32768, 32767).astype(np.int16)
                        #write_queue.put((chunk_counter, chunk_raw_i16, chunk_filtered_i16))
                    
                    # send chunk for classification
                    audio_Class_queue.put(blockSC)


                    # Wait for classification result
                    # Optionally: non-blocking check for classification result
                    try:
                        top_classes, top_families = resultClass_queue.get(timeout=1)
                        # Process result
                    except queue.Empty:
                                        # Wait for classification result
                        print("⚠️ Timeout: No classification result received.")
                        top_classes = []
                        top_families = []

                    # Process result
                    indice = 0
                    for fam, values in top_families:
                        #print(fam)
                        for idx, val in enumerate(values):
                            #print('idx: ', idx)
                            #print('val: ', val)
                            if idx == 0:
                                index = indice
                                events_info[index] = val

                    #=== Tira a relevâcia à familia Music / Atmosfera
                                '''
                                #=============== modelo HOSPITAL =======
                                #====================================================================================================
                                # COMENTAR SE O MODELO FOR RUIDO AMBIENTE CIDADE
                                if index == 2: # Music

                                    if NoiseLevels_dB_OneLine[4] < 40: # LAF < 30 dBA
                                        #FactMUSIC = 0.2
                                        val = FactMUSIC * val
                                        events_info[index] = val
                                #=== Tira a relevâcia à familia Music
                                '''                                
                                #=============== modelo RUIDO AMBIENTE CIDADE =======
                                #====================================================================================================
                                # COMENTAR SE O MODELO FOR HOSPITAL
                                
                                if (index == 9 or index == 0): # Music ou Atmosfera

                                    if NoiseLevels_dB_OneLine[4] < 40: # LAF < 30 dBA
                                        val = FactMUSIC * val
                                        events_info[index] = val
                                #=== Tira a relevâcia à familia Music
      

                                indice += 1
                            num_spaces = int(val * 40)
                            spacing = ' ' * num_spaces
                            if val == 0:
                                #print(f"  #{idx+1:<2} {val:.4f}*")
                                print(f"  #{fam} {val:.4f}*")

                            else:
                                #print(f"  #{idx+1:<2} {val:.4f}{spacing}*")
                                print(f"  #{fam} {val:.4f}{spacing}*")

                    # Top 3 classes
                    classes = [name for name, _ in top_classes[:3]]

                    '''NoiseLevels_dB_OneLine[51] = top_families["alarm"] # Event 1 Score (Sirenes/alarmes)
                    NoiseLevels_dB_OneLine[52] = top_families["screams"] # Event 2 Score (Impulsivos/percussivos (coisas a cair, bater, explodir...))
                    NoiseLevels_dB_OneLine[53] = top_families["alarm"] # Event 3 Score (Música)
                    NoiseLevels_dB_OneLine[54] = top_families["telephone"] # Event 4 Score (Gritos/chorar...)
                    NoiseLevels_dB_OneLine[55] = top_families["music"] # Event 5 Score (Sons naturais (roncar, respirar alto...))
                    NoiseLevels_dB_OneLine[56] = top_families["whistle"] # Event 6 Score (Fala)
                    NoiseLevels_dB_OneLine[57] = top_families["wheels"] # Event 7 Score (Toque de telefone)
                    NoiseLevels_dB_OneLine[58] = top_families["snore"] # Event 8 Score (Líquidos (água a correr, pingar...))
                    NoiseLevels_dB_OneLine[59] = top_families["waterfall"] # Event 9 Score (Carrinhos/trolleys)
                    NoiseLevels_dB_OneLine[60] = top_families["impulsive"] # Event 10 Score (Assobio)'''
                        
                    '''NoiseLevels_dB_OneLine[51] = 1
                        
                        
                    NoiseLevels_dB_OneLine[60] = dict(top_classes)[classes[0]] # Specific Event 1 Score
                    NoiseLevels_dB_OneLine[61] = name_to_index[classes[0]] # Specific Event 1 ID
                        
                    NoiseLevels_dB_OneLine[62] = name_to_index[classes[1]] # Specific Event 2 ID
                    NoiseLevels_dB_OneLine[63] = dict(top_classes)[classes[1]] # Specific Event 2 Score
                        
                    NoiseLevels_dB_OneLine[64] = name_to_index[classes[2]] # Specific Event 3 ID
                    NoiseLevels_dB_OneLine[65] = dict(top_classes)[classes[2]] # Specific Event 3 Score'''


                    if len(classes) >= 3:
                        events_info[10] = dict(top_classes)[classes[0]]
                        events_info[11] = name_to_index[classes[0]]
                        events_info[12] = name_to_index[classes[1]]
                        events_info[13] = dict(top_classes)[classes[1]]
                        events_info[14] = name_to_index[classes[2]]
                        events_info[15] = dict(top_classes)[classes[2]]

                    # Append to your global NoiseLevels_dB_OneLine
                for i in range(len(events_info)):
                    NoiseLevels_dB_OneLine[50 + i] = events_info[i]
 


            LZpeakTprmsLast = Noise_Lin[6]
            LCpeakTprmsLast = Noise_Lin[8]
            LApeakTprmsLast = Noise_Lin[10]
            LAFmaxTprmsLast = Noise_Lin[12]
            LAFminTprmsLast = Noise_Lin[14]
            LZprmsLast      = Noise_Lin[15]
            LCprmsLast      = Noise_Lin[16]
            LAprmsLast      = Noise_Lin[17]

    #            LAFminTprmsLast = 100

            cntSegmBegin += 1  # Atualiza o contador de Segmentos (i.e. 1 seg)
            #print('cntSegmBegin: ', cntSegmBegin)

        # Grava para ficheiro CSV
            #write_to_CSV(NoiseLevels_dB_OneLine)

            NoiseLevels_dB_OneLine_ = NoiseLevels_dB_OneLine.reshape(-1)
#            print('NoiseLevels_dB_OneLine_(timestamp): ', NoiseLevels_dB_OneLine_[0])

            buffer_CSV.append(NoiseLevels_dB_OneLine_)  # current_data is your 100-value array
#            print('np.shape(NoiseLevels_dB_OneLine): ', np.shape(NoiseLevels_dB_OneLine))
#            print('len(buffer):', len(buffer_CSV))  # How many rows (samples) have been appended
#            print('np.shape(np.array(buffer)):', np.shape(np.array(buffer_CSV)))  # Actual array shape
#            print('(buffer): ', (buffer_CSV))

            counter_CSV += 1
            counter_File_CSV += 1
            
            start_elapsed_JSON = time.perf_counter()
            
            '''
            counter_JSON +=1
            TIME_JSON_STORE = 20
            JSON_full = False

            if counter_JSON >= TIME_JSON_STORE:
                JSON_full = True
                counter_JSON =0
            '''
            #print('json.dumps(NoiseLevels_dB_OneLine_.tolist()): ', json.dumps(NoiseLevels_dB_OneLine_.tolist()))

            #print('json.dumps(buffer_CSV): ', json.dumps(buffer_CSV))


            #add_row(NoiseLevels_dB_OneLine_)
            #print(type(NoiseLevels_dB_OneLine_))
            
            if mqtt_queue is not None:
                mqtt_queue.put(NoiseLevels_dB_OneLine_)  # 👈 Send to MQTT thread
            
            #write_Json_to_Cloud_Stream(NoiseLevels_dB_OneLine_, JSON_full)
            
            elapsed_time_JSON = np.round((time.perf_counter() - start_elapsed_JSON) * 1000, 3)
            #print('elapsed_time_JSON (ms)=======: ', elapsed_time_JSON)

            if counter_CSV >= TIME_CSV_STORE:

 #               with open("output.csv", "a", newline="") as f:
 #                   writer = csv.writer(f)
 #                   writer.writerows(buffer)
                print('Write to CSV ...')
#                print('np.shape(buffer): ', np.shape(buffer_CSV))
                #print('(buffer): ', (buffer_CSV))

                data_to_write = np.array(buffer_CSV)  # shape (N, 57)

                #write_to_CSV(data_to_write)

                current_writer.writerows(np.round(data_to_write, 2))
                #current_writer.writerows((data_to_write))

                current_file.flush()

                buffer_CSV= []  # clear buffer
                counter_CSV = 0  # Reset counter


                if counter_File_CSV >= LINES_PER_CSV:
                    print('====WRITE CSV FILE =======')

                    current_file.close()
                    current_file, current_writer = create_new_csv_file()
                    current_writer = csv.writer(current_file)

                    counter_File_CSV = 0


        if SaveAudiofile_OK:
            # Buffer atinge o tamanho dos segmentos de áudio para gravar
            # Grava para ficheiro
            while buffered_samples >= SAMPLES_PER_BLOCK_FILE:
                print('Write to file.........')
                stacked = np.ravel(np.hstack(sample_accumulator_raw))
                chunk_raw = stacked[:SAMPLES_PER_BLOCK_FILE]

                # Keep leftover samples
                leftover = stacked[SAMPLES_PER_BLOCK_FILE:]
                sample_accumulator_raw = [leftover] if len(leftover) > 0 else []
                '''
                stacked = np.ravel(np.hstack(sample_accumulator_filtered))
                chunk_filtered = stacked[:SAMPLES_PER_BLOCK_FILE]

                # Keep leftover samples
                leftover = stacked[SAMPLES_PER_BLOCK_FILE:]
                sample_accumulator_filtered = [leftover] if len(leftover) > 0 else []
                '''
                buffered_samples = len(leftover)

    #
    #             print('Write to file.........')
    #             print('np.shape(sample_accumulator_raw: ', np.shape(sample_accumulator_raw))
    #             #np.hstack(sample_accumulator_raw)
    #             sample_accumulator_raw = np.ravel(sample_accumulator_raw)
    #             print('np.shape(sample_accumulator_raw: ', np.shape(sample_accumulator_raw))
    #             chunk_raw = sample_accumulator_raw[:SAMPLES_PER_BLOCK_FILE]
    #             print('np.shape(chunk_raw: ', np.shape(chunk_raw))
    #
    #             chunk_filtered = sample_accumulator_filtered[:SAMPLES_PER_BLOCK_FILE]
    #
    # #            chunk_raw = chunk_raw * 2.0 ** (NBITS-1)
    # #            chunk_filtered = chunk_filtered * 2.0 ** (NBITS-1))
    #             #print('np.max(chunk_raw): ', np.max(chunk_raw))
    #
    #             sample_accumulator_raw = sample_accumulator_raw[SAMPLES_PER_BLOCK_FILE:]
    #             sample_accumulator_filtered = sample_accumulator_filtered[SAMPLES_PER_BLOCK_FILE:]
    #             buffered_samples -= SAMPLES_PER_BLOCK_FILE

                chunk_raw_i16 = np.clip(chunk_raw, -32768, 32767).astype(np.int16)
                #chunk_filtered_i16 = np.clip(chunk_filtered, -32768, 32767).astype(np.int16)
                #write_queue.put((chunk_counter, chunk_raw_i16, chunk_filtered_i16))
                write_queue.put((chunk_counter, chunk_raw_i16))

                chunk_counter += 1

            #elapsed_time = time.time() - start_time

        countBlock += 1

      #  elapsed_time = time.time() - start_time
#        elapsed_timeTimeLine = np.hstack((elapsed_timeTimeLine, elapsed_time))
      #  elapsed_timeTimeLine.append(elapsed_time)

        #print('elapsed_time Segmento (ms): ', elapsed_time*1000)
        #elapsed_time = np.round((time.time() - start_time) * 1000, 2)
        #print('elapsed_time Segmento (ms): ', elapsed_time)


def audio_writer(write_queue, stop_event):
    samples_written = 0
    file_index = 0
    mp3_file = None
    encoder = None

    def start_new_file():
        nonlocal encoder, mp3_file, samples_written
        filename = generate_timestamped_filename(FILE_PREFIX)
        encoder = lameenc.Encoder()
        encoder.set_bit_rate(BITRATE)
        encoder.set_in_sample_rate(SAMPLE_RATE)
        encoder.set_channels(CHANNELS)
        encoder.set_quality(2)
        mp3_file = open(filename, 'wb')
        samples_written = 0
        print(f"🆕 Started new MP3 file: {filename}")

    def generate_timestamped_filename(prefix):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(outputDIR_Waves, f"{prefix}_raw_{timestamp}.mp3")

    start_new_file()

    while not stop_event.is_set() or not write_queue.empty():
        try:
            #chunk_counter, raw_chunk, _ = write_queue.get(timeout=0.1)
            chunk_counter, raw_chunk = write_queue.get(timeout=0.1)

        except queue.Empty:
            continue

        if encoder is None or mp3_file is None:
            raise RuntimeError("Encoder not initialised")

        # Encode and write to file
        encoded_data = encoder.encode(raw_chunk.tobytes())
        if encoded_data:
            mp3_file.write(encoded_data)

        samples_written += len(raw_chunk)

        # Check for rotation
        if samples_written >= SAMPLES_PER_FILE:
            # Flush encoder
            final_data = encoder.flush()
            if final_data:
                mp3_file.write(final_data)
            mp3_file.close()
            print(f"💾 Closed MP3 file after writing {samples_written} samples")

            # Start new file
            file_index += 1
            start_new_file()

    # Final flush and cleanup on exit
    if encoder and mp3_file:
        final_data = encoder.flush()
        if final_data:
            mp3_file.write(final_data)
        mp3_file.close()
        print(f"✅ Final MP3 file closed after writing {samples_written} samples")


def audio_callback_factory(audio_queue):
    def callback(indata, frames, time_info, status):
        if status:
            print("Stream status:", status)
        samples = indata[:, 0].copy()
        audio_queue.put(samples)
        #print("audio_queue.empty()", audio_queue.empty())

    return callback

def main():
    print(f"🎙️ Starting recording for {SESSION_DURATION} seconds...")

    # -------------------------------
    # Shared queues and events
    # -------------------------------
    audio_queue = MPQueue()
    write_queue = MPQueue()
    mqtt_queue = MPQueue() if Publica_MQTT_OK else None

    audio_Class_queue = MPQueue()
    resultClass_queue = MPQueue()

    stop_event = Event()           # multiprocessing.Event
    model_ready_event = Event()

    # -------------------------------
    # Launch YAMNet worker process
    # -------------------------------
    if SoundEvent_OK:
        proc_classify = Process(
            target=yamnet_worker,
            args=(audio_Class_queue, resultClass_queue, stop_event, model_ready_event)
        )
        proc_classify.start()

    # -------------------------------
    # Launch audio processing process
    # -------------------------------
    proc_processor = Process(
        target=audio_processor,
        args=(audio_queue,
              write_queue,
              stop_event,
              mqtt_queue,
              SPLReal_shared,
              spl_lock,
              audio_Class_queue,
              resultClass_queue)
    )
    proc_processor.start()

    # -------------------------------
    # Launch audio writer process (optional)
    # -------------------------------
    if SaveAudiofile_OK:
        proc_writer = Process(
            target=audio_writer,
            args=(write_queue, stop_event)
        )
        proc_writer.start()

    # -------------------------------
    # Launch LED display thread (optional)
    # -------------------------------
    if ShowLEDsDisplay_OK:
        display_thread = threading.Thread(
            target=display7seg_LED,
            args=(SPLReal_shared, spl_lock),
            daemon=True
        )
        display_thread.start()

    # -------------------------------
    # Launch MQTT sender thread
    # -------------------------------
    if Publica_MQTT_OK:
        
        client = mqtt.Client()
        #client2 = mqtt.Client()
        
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        #client2.connect(MQTT_BROKER2, MQTT_PORT, 60)
        
        client.loop_start()
        #client2.loop_start()
    
        mqtt_thread = threading.Thread(
            target=mqtt_sender,
            args=(mqtt_queue, stop_event, client),
#            args=(mqtt_queue, stop_event, client, client2),
            kwargs={'batch_size': 10, 'timeout': 2},
            daemon=True
        )
        mqtt_thread.start()
        print('==== MQTT sender started ====')

    # -------------------------------
    # Wait for YAMNet model
    # -------------------------------
    print("⏳ Waiting for YAMNet model to load...")
    if not model_ready_event.wait(timeout=10):
        print("⚠️ Model did not signal readiness. Continuing anyway...")
    else:
        print("✅ YAMNet model ready.")

    start_time_Tot = time.time()

    # -------------------------------
    # Start audio capture
    # -------------------------------
    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE,
        callback=audio_callback_factory(audio_queue),
        blocksize=CHUNK_SIZE
    ):
        print('Recording started. Press Ctrl+C to stop manually.')
        try:
            if SESSION_DURATION is None:
                while True:
                    time.sleep(1)
            else:
                sd.sleep(int(SESSION_DURATION * 1000))
        except KeyboardInterrupt:
            print('Recording stopped by user')

    # -------------------------------
    # Shutdown
    # -------------------------------
    print("Stopping...")
    stop_event.set()

    # Join all processes
    proc_processor.join()
    if SaveAudiofile_OK:
        proc_writer.join()
        
    if Publica_MQTT_OK:
    # 1. Signal shutdown
        stop_event.set()
        mqtt_queue.put(None)   # sentinel to unblock the thread

    # 2. Wait for thread to finish
        mqtt_thread.join()

    # 3. Cleanly stop the MQTT client
        client.loop_stop()
        client.disconnect()
        
    if SoundEvent_OK:
        proc_classify.join()

    print("Done recording.")

    # -------------------------------
    # Cleanup ring buffers
    # -------------------------------
    lib.ringbuffer_fifo_free(ringBuffZW)
    lib.ringbuffer_fifo_free(ringBuffCW)
    lib.ringbuffer_fifo_free(ringBuffAW)
    lib.ringbuffer_fifo_free(ringBuffZWTW)
    lib.ringbuffer_fifo_free(ringBuffCWTW)
    lib.ringbuffer_fifo_free(ringBuffAWTW)
    lib_13Oct.ringbuffer_fifo_free(ringBuffZWTW_13Oct)



    #===============================================================================================
#========== Plots ==============================================================================
#===============================================================================================

    if plots_OK:
        print('np.shape(Noise_dBTimeLine_buffer): ', np.shape(Noise_dBTimeLine_buffer))

    #    Noise_dBTimeLine = np.array(Noise_dBTimeLine_buffer)
        Noise_dBTimeLine = np.array([arr.reshape(-1) for arr in Noise_dBTimeLine_buffer])
        Noise_dBTimeLine = Noise_dBTimeLine.T
        print('np.shape(Noise_dBTimeLine): ', np.shape(Noise_dBTimeLine))
        print('(Noise_dBTimeLine): ', (Noise_dBTimeLine))


        n = np.arange(0, len(Noise_dBTimeLine[0, :])*SEGMENT_DURATION, SEGMENT_DURATION)
        print('np.shape(Noise_dBTimeLine :', np.shape(Noise_dBTimeLine))

        plt.figure()
        plt.plot(n, Noise_dBTimeLine[0+1, :])           # Shift to avoid TimeStamp
        plt.plot(n, 20+(10*Noise_dBTimeLine[1+1, :]))
        plt.plot(n, Noise_dBTimeLine[2+1, :])
        plt.plot(n, Noise_dBTimeLine[3+1, :])
        plt.plot(n, Noise_dBTimeLine[4+1, :], '.-')
        plt.plot(n, Noise_dBTimeLine[5+1, :])
        plt.plot(n, Noise_dBTimeLine[6+1, :], '.-')
        plt.plot(n, Noise_dBTimeLine[7+1, :])
        plt.plot(n, Noise_dBTimeLine[8+1, :], '.-')
        plt.plot(n, Noise_dBTimeLine[9+1, :])
        plt.plot(n, Noise_dBTimeLine[10+1, :], '.-')
        plt.plot(n, Noise_dBTimeLine[11+1, :])
        plt.plot(n, Noise_dBTimeLine[12+1, :], '.-')
        plt.plot(n, Noise_dBTimeLine[13+1, :])
        plt.plot(n, Noise_dBTimeLine[14+1, :])
        plt.plot(n, Noise_dBTimeLine[15+1, :])

        #plt.plot(n, Noise_LinTimeLine)
        plt.grid()
        plt.legend(["LAEZ", "LAEC", "LAEA", "LZpeak", "LZpeakT", "LCpeak", "LCpeakT", "LApeak", "LApeakT",
                    "LAFmax", "LAFmaxT", "LAFmin", "LAFminT", "LZeq", "LCeq", "LAeq"])

        plt.xlabel('time (s)')
        plt.ylabel('Levels (dB)')
        #plt.show()

        '''
        plt.figure()
        plt.plot(n, Noise_LinTimeLine[0+1, :])
        plt.plot(n, Noise_LinTimeLine[1+1, :])
        plt.plot(n, Noise_LinTimeLine[2+1, :])
        plt.plot(n, Noise_LinTimeLine[3+1, :])
        plt.plot(n, Noise_LinTimeLine[4+1, :], '.-')
        plt.plot(n, Noise_LinTimeLine[5+1, :])
        plt.plot(n, Noise_LinTimeLine[6+1, :], '.-')
        plt.plot(n, Noise_LinTimeLine[7+1, :])
        plt.plot(n, Noise_LinTimeLine[8+1, :], '.-')
        plt.plot(n, Noise_LinTimeLine[9+1, :])
        plt.plot(n, Noise_LinTimeLine[10+1, :], '.-')
        plt.plot(n, Noise_LinTimeLine[11+1, :])
        plt.plot(n, Noise_LinTimeLine[12+1, :], '.-')
        plt.plot(n, Noise_LinTimeLine[13+1, :])
        plt.plot(n, Noise_LinTimeLine[14+1, :])
        plt.plot(n, Noise_LinTimeLine[15+1, :])
    
        #plt.plot(n, Noise_LinTimeLine)
        plt.grid()
        plt.legend(["LAEZ", "LAEC", "LAEA", "LZpeak", "LZpeakT", "LCpeak", "LCpeakT", "LApeak", "LApeakT",
                    "LAFmax", "LAFmaxT", "LAFmin", "LAFminT", "LZeq", "LCeq", "LAeq"])
        plt.xlabel('time (s)')
        plt.ylabel('Levels')
        plt.show()
        '''
        plt.figure()
    #    plt.plot(elapsed_timeTimeLine)
        plt.xlabel('Iteration (blocks)')
        plt.ylabel('time (s)')
        plt.title('Elapsed_time')

        plt.show()

        # Spectrogram Octave Bands
 

        plt.figure(figsize=(10, 5))
        plt.title('Spectrogram - 1/3 Octave Bands')

        # Define 1/3-octave band labels (typically 31 bands from ~25 Hz to 20 kHz)
        bands_13oct = ["25", "31.5", "40", "50", "63", "80", "100", "125", "160", "200",
                       "250", "315", "400", "500", "630", "800", "1k", "1.25k", "1.6k", "2k",
                       "2.5k", "3.15k", "4k", "5k", "6.3k", "8k", "10k", "12.5k", "16k", "20k"]

        #N_13OCTAVE_BANDS = len(bands_13oct)

        # Adjust your slice — this assumes your matrix is stacked and the 1/3 bands start here
        start_row = 17
        end_row = start_row + N_13OCTAVE_BANDS

        # Extract only the relevant 1/3-octave data slice
        data = Noise_dBTimeLine[start_row:end_row, :]

        # Display the image
        plt.imshow(data,
                   cmap='hot',
                   #interpolation='bilinear',
                   #interpolation='bicubic',
                   #interpolation='gaussian',
                   interpolation='nearest',
                   aspect='auto',
                   extent=[0, data.shape[1], 0, N_13OCTAVE_BANDS])
        # Apply labels
        plt.gca().invert_yaxis()

        plt.yticks(ticks=np.arange(N_13OCTAVE_BANDS) + 0.5, labels=bands_13oct[::-1])  # flip for top-down
        plt.ylabel('1/3 Octave Band Center Frequency (Hz)')
        plt.xlabel('Time Frame')
        plt.colorbar(label='dB')
        plt.tight_layout()
        plt.show()




if __name__ == "__main__":
    
    #from multiprocessing import set_start_method
    #set_start_method("spawn")
    
    start_time = time.time()
    

    main()
