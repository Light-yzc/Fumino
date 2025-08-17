import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import threading
import numpy as np
import librosa
import sounddevice as sd
import os
from PySide6.QtCore import  Signal, QObject # 导入 QEvent
from pathlib import Path
class Audio_Worker(QObject):
    response_ready = Signal(str)
    error_occurred = Signal(str)
    def __init__(self, /, parent = None):
        super().__init__(parent)
        self._running = True  # 控制线程运行的标志
        self.Base_path = Path(__file__).resolve().parent 
        self.ref_path = self.Base_path / 'ref' / 'fumino0030.ogg_0000000000_0000176000.wav'
        self.res_emit = False
    def bin_to_mp3(self, data, file_name):
        # self.file_path = f'./voices/{file_name}.wav' 
        self.file_path = self.Base_path / 'voices' / f'{file_name}.wav'
        if os.path.exists(self.file_path):
            os.remove(self.file_path)
            print(f"文件 {self.file_path} 已删除")
        else:
            print(f"文件 {self.file_path} 已生成")

        with open(self.file_path, 'wb') as f:
            f.write(data)

    # BY local TTS
    def gengerate_voice(self, ja, file_name):
        url = f"http://127.0.0.1:9880/tts?text={ja}&text_lang=ja&ref_audio_path={self.ref_path}&prompt_lang=ja&prompt_text=私は、戸籍が男性のものになっておりますので&text_split_method=cut5&batch_size=1&media_type=wav&streaming_mode=false&top_k=15&top_p=0.7&speed_factor=0.9&batch_size=3"
        # url = f"http://127.0.0.1:9880?refer_wav_path={self.ref_path}&prompt_text=私は、戸籍が男性のものになっておりますので&prompt_language=ja&text={ja}&text_language=ja&top_k=15&top_p=0.6&temperature=1&speed=0.75"
        try:
            print(f'开始获取语音：{file_name}')
            response = requests.get(url=url)
            response.raise_for_status()  # 检查HTTP状态码（4xx/5xx会抛异常）
            self.bin_to_mp3(response.content, file_name)
            # if self.res_emit:
            print('audio work已发送信息')
            self.response_ready.emit(file_name)
                # self.res_emit = False
        except Exception as e:
            self.error_occurred.emit('0')
            print(e)
            print("------tts的Api服务器不可用，跳过声音生成------")

    def set_res_emit(self, Bool):
        if Bool:
            self.res_emit = Bool
            print('//////////////')
            print(self.res_emit)

    def stop(self):
        self._running = False
# audio_handle

class AudioState(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_data = None
        self.sample_rate = 44100
        # self.frame_size = int(44100 / 10) # 原始是30fps, 10应该是笔误，改为30
        self.frame_size = int(44100 / 30) # 30fps
        self.position = 0
        self.amplitude = 0.0
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self._stream = None # 私有变量，用于存储预初始化的音频流
        self._running = True 
        # 懒加载或确保流已初始化
    
    def reset(self):
        with self.lock:
            self.position = 0
            self.amplitude = 0.0
            self.stop_event.clear()
            # 如果流正在运行，停止它以准备下一次播放
            if self._stream:
                self._stream.stop()

    def get_stream(self):
        # 懒加载或确保流已初始化
        if self._stream is None or not self._stream.closed: # 检查流是否已关闭
            try:
                self._stream = sd.OutputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype='float32',
                    blocksize=self.frame_size,
                    latency='low'
                )
            except Exception as e:
                print(f"初始化音频流失败: {e}")
                self._stream = None # 如果失败，将其设为None
        return self._stream


    def audio_play_thread(self, mp3_path):
        """
        独立音频播放线程，并在播放中实时将字符写入文件。
        """
        # 加载音频
        self.reset()
        try:
            audio, sr = librosa.load(mp3_path, sr=self.sample_rate, mono=True)
            audio = np.clip(audio, -1.0, 1.0) # 振幅调整
        except:
            print('音频播放失败')
        # 获取音频流实例
        stream = self.get_stream()
        if stream is None:
            print("错误：无法获取或初始化音频流，无法播放。")
            return

        # 在播放前确保流已停止并准备好
        if stream.closed: # 如果流在某个时刻被外部关闭了，重新获取
            stream = self.get_stream()
            if stream is None:
                print("错误：重新初始化音频流失败，无法播放。")
                return

        # 开始音频流
        try:
            stream.start()
        except sd.PortAudioError as e:
            print(f"启动音频流失败: {e}")
            return

        # 文件写入逻辑 (保持不变)

        try:
            self.audio_data = audio # 将音频数据设置到共享状态
            while not self.stop_event.is_set():
                with self.lock:
                    start_sample = self.position
                    current_play_time_sec = start_sample / self.sample_rate
                    end_sample = start_sample + self.frame_size

                    if start_sample >= len(self.audio_data):
                        break # 音频播放完毕

                    chunk = self.audio_data[start_sample:end_sample]
                    self.position = end_sample # 更新音频播放位置

                amp = np.sqrt(np.mean(chunk**2)) * 6
                with self.lock:
                    self.amplitude = np.clip(amp, 0, 1).astype(float)

                stream.write(chunk.astype('float32'))
        except Exception as e:
            print(f"播放过程中发生错误: {e}")
        finally:
            # 播放结束后停止流
            # stream.stop()
            print("音频播放完毕或停止事件触发。")

    def stop(self):
        self._running = False
