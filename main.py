import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QSystemTrayIcon,
    QMenu, QLabel, QGraphicsOpacityEffect, QStackedLayout
)
from PySide6.QtCore import Qt, QPoint, QThread, Signal, QPropertyAnimation, QEasingCurve, QTimer, QCoreApplication, QEvent, QObject, QRect, QParallelAnimationGroup, Property # 导入 QEvent
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QMouseEvent# 导入 QMouseEvent
from collections import deque
from openai import OpenAI
import re
import os
from pathlib import Path
import json
from config import L_Config
from Rag import init_db, start_retrieval
import queue
from PySide6.QtCore import QThread, Signal
import time
from Get_TTS import Audio_Worker, AudioState
from assets import affinity_bar, OverlayWidget, Dialog

class LLMWorker(QObject):
    response_ready = Signal(str)
    error_occurred = Signal(str)
    send_tmp_msg = Signal(bool)
    trigger_audio_worker = Signal(str, str)
    info_audio_worker = Signal(bool)
    info_text = Signal(str)
    info_dialog = Signal(str)
    char_and_bg = Signal(int, int, str)
    def __init__(self, parent=None):
        self.api_key = ''
        self.BASE_DIR = Path(__file__).resolve().parent 
        self.dialogue_DIR = self.BASE_DIR / 'saves' / 'dialogue.json'
        with open(self.BASE_DIR / 'config.json', 'r', encoding='utf-8') as file:
            self.config = json.load(file)
        self.api_key = self.config['api_key']
        self.rag_url = self.config['embed_url']
        self.rag_key = self.config['embed_key']
        super().__init__(parent)
        self.audio_worker = None
        self.text_queue = None
        self.is_start = None
        self.voice_handle = None
        self.llm = None
        self.rag_db = None
        self.model = None
        self.use_rag = self.config['rag']
        if self.use_rag:
            self.set_rag()
        self.change_llm_and_models()
        print(f"当前模型：{self.llm} {self.model}")
        # 初始发送的提示
        self.prompt = L_Config.prompt
        self.prefix = L_Config.prefix + '---\n以下是用户输入:\n'
        self.system_prompt = L_Config.system_prompt

        self.conversation = [
        {"role": "system", "content": self.system_prompt},
        {"role": "assistant", "content": self.prompt}
        ]
        

        # 使用队列来接收主线程发送的消息
        self.message_queue = queue.Queue()
        self._is_running = True # 控制线程循环的标志

    def process_message(self, msg):
        """主线程调用此方法将消息放入队列。"""
        self.message_queue.put(self.prefix + msg)

    def set_queue(self, queue):
        self.text_queue = queue

    def run(self): # 这个 run 方法将在 QThread 中被调用
        """
        线程的实际执行逻辑。此方法现在是一个循环，持续处理消息。
        """
        print("LLMWorker 线程启动，等待消息...")
        while True:
            message_to_process = self.message_queue.get() 
            if message_to_process is None:
                break
            try:
                llm_response_object = self.call_llm(message_to_process)
                # print('ddondddddd')
                self.response_ready.emit(llm_response_object)
            except Exception as e:
                self.error_occurred.emit(f"LLM调用发生错误: {e}")
            finally:
                # 标记此任务已完成
                self.message_queue.task_done()

        print("LLMWorker 线程停止。")

    def stop(self):
        """安全停止线程的方法。"""
        self._is_running = False

    def set_rag(self):
        if not self.rag_db:
            self.info_text.emit('正在加载rag')
            print('正在加载rag')
            self.rag_db = init_db(self.rag_url, self.rag_key)
            if self.rag_db == '<<ERROR>>':
                self.info_text.emit('Rag加载出错') 
                print('Rag加载出错')
            else:
                self.info_text.emit('加载完成')
                print('加载完成')

    def load_dialog(self):
        try:
            with open(self.dialogue_DIR, 'r', encoding='utf-8') as f:
                dia_file = json.load(f)
                self.conversation = dia_file['dialog']
                bg = dia_file['bg']
                dress = dia_file['dress']
                emo = dia_file['emo']
                self.char_and_bg.emit(int(dress), int(bg), emo)
            self.info_dialog.emit('加载完成')
        except Exception as e:
            print(f"对话记录加载错误{e}")
            self.info_dialog.emit(f"对话记录加载错误：{e}")
            
    def save_dialog(self, current_char_index, current_bg_index, emo):
        try:
            with open(self.dialogue_DIR, 'w', encoding='utf-8') as f:
                json.dump({"dialog":self.conversation, "dress":current_char_index, "bg":current_bg_index, 'emo':emo}, f, ensure_ascii=False)
            self.info_dialog.emit('保存完成')
        except Exception as e:
            print(e)
            self.info_dialog.emit(f"保存错误：{e}")

    def clear_dialog(self):
        self.conversation = [
        {"role": "system", "content": self.system_prompt},
        {"role": "assistant", "content": self.prompt}
        ]
        self.info_dialog.emit('清空完成')


    def change_llm_and_models(self, llm = None, model = None, api_key =None):
        if llm == model == api_key == None:
            self.llm = self.config['llm']
            self.model = self.config['model']
            self.api_key = self.config['api_key']
        else:
            self.llm = llm
            self.model = model
            self.api_key = api_key
        if self.llm == '质谱':
            self.client = OpenAI(api_key=self.api_key,
                                base_url="https://open.bigmodel.cn/api/paas/v4/")
        elif self.llm == 'Gemini':
            self.client = OpenAI(api_key=self.api_key,
                                base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
        elif self.llm.startswith('https'):
            self.client = OpenAI(api_key=self.api_key,
                                base_url=self.llm)
        # return
        # if api_key != None:
        #     self.api_key = api_key
        #     self.model = model
        # if llm == '质谱':
        #     self.llm = llm
        #     self.client = OpenAI(
        #             api_key=self.api_key,
        #             base_url="https://open.bigmodel.cn/api/paas/v4/")
        # elif llm == 'Gemini':
        #     self.llm = llm
        #     self.client = OpenAI(api_key=self.api_key,
        #                             base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    def call_llm(self, msg):
        """实际调用LLM服务的方法。"""
        full_response, no_change_res = '', ''
        self.is_start = True
        self.voice_handle = None
        self.text_queue.clear()
        # try:
        if self.use_rag:
            if not self.rag_db:
                self.set_rag()
            res = start_retrieval(self.rag_db, msg)
            msg = f'''你的任务是：
                        1. **学习并模仿**检索文本中的说话方式、语气和用词特色；
                        2. **提取有效信息**（例如：用户需求、关键细节、上下文线索）；
                        3. **生成连贯且符合角色设定**的回复，同时根据“user输入”完成具体互动。

                        检索到的对话文本：
                        ---
                        {res}
                        ---

                        用户新输入：
                        ---
                        {msg}
                        ---

                        '''
        else:
            self.rag_db = None

        print(f'/////是否用rag:{self.use_rag}')
        self.conversation.append({"role": "user", "content": msg})
        response = self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation,
                temperature=1.0,
                max_tokens=96000, 
                stream=True
            )
        print('开始流式')
        print(response)
        for chunk in response:
            if chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end='')
                full_response += chunk.choices[0].delta.content
                no_change_res += chunk.choices[0].delta.content
            pattern = r'<<[^>]+>>.*?<<[^>]+>>'
            match = re.search(pattern, full_response)
            if match:
                full_match_str = match.group(0).strip()
                full_response = full_response.replace(full_match_str, '', 1)
                self.match_condition(full_match_str)
        while len(full_response) != 0:
            match = re.search(pattern, full_response)
            if match:
                full_match_str = match.group(0).strip()
                full_response = full_response.replace(full_match_str, '', 1)
                if self.match_condition(full_match_str):
                    break
            else:
                break
        self.conversation.append({"role": "assistant", "content": no_change_res})
        # print(f'完整文本：{no_change_res}')
        self.is_start = None
        return no_change_res

        # except Exception as e:
        #     print(f"发生错误: {e}")
        #     return e
        
    def match_condition(self, full_match_str):
        if self.text_queue != None and full_match_str.startswith('<<文乃说>>'):
            ja = self.extract_ja(full_match_str)
            if ja!='':
                if self.is_start == True:
                    print('已经发送语音初始化')
                    self.info_audio_worker.emit(True)
                    self.is_start = False
                print(f'\n开始获取到语音：{ja}\n')
                ja = re.sub('mube', 'むべ', ja, re.DOTALL)
                t = time.strftime("%Y%m%d_%H%M%S")
                file_plus_reply = f'<<FILE>>{t}<<FILE>>' + full_match_str
                self.text_queue.append(file_plus_reply)
                # print(self.text_queue)
                self.trigger_audio_worker.emit(ja, t)
                ja = ''
                return False
        elif self.text_queue != None and full_match_str != '':
            self.text_queue.append(full_match_str)
            # print(self.text_queue)
            if self.is_start == True:
                self.send_tmp_msg.emit(True)
                print('非语音初始文本已经发送')
                self.is_start = False
            return False
        return True
    
    def extract_ja(self, text):
        pattern = r'\[ja\](.*?)\[\/ja\]'
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()  # 去除首尾空白
        return ''

# --- 主应用程序 ---
class LLMChatApp(QWidget):

    set_affinity = Signal(int)
    play_autdio = Signal(str)
    handel_model_list = Signal(str, str)

    def __init__(self):
        super().__init__()
        self._height = 1600
        self._width = 900
        self.BASE_DIR = Path(__file__).resolve().parent 
        BG_IMG_DIR = self.BASE_DIR / "img" / "bg"
        CHAR_DIR = self.BASE_DIR / "img" / "fumino_02l_resize" / "char"
        EMO_DIR = self.BASE_DIR / "img" / "fumino_02l_resize" / "emotion"
        self.bg_image_files = self.load_images_from_folder(BG_IMG_DIR)
        self.char_image_files = self.load_images_from_folder(CHAR_DIR)
        self.emotion_image_files = self.load_images_from_folder(EMO_DIR)
        self.setWindowTitle("Fumino")
        Icon_DIR = self.BASE_DIR / "img" / "icon.png"
        self.setWindowIcon(QIcon(str(Icon_DIR)))
        # self.setWindowIcon(QIcon('./img/icon.png' ))
        self.setGeometry(100, 100, self._height, self._width) # 增大窗口以适应图片
        self.setFixedSize(self.width(), self.height())
        self.is_llm_working = False # 跟踪 LLM 是否正在处理当前请求
        self.animation = None
        self.emotion_opacity_effect = None
        self.text_fade_animation = None # 文本淡入动画
        self.floating_button_container = None
        self.floating_button_opacity_animation = None
        self.current_bg_index = 2
        self.current_char_index = 1
        self.current_emotion_index = 0
        self.overlay = OverlayWidget(self)
        self.affinity = affinity_bar(self)
        self.Dialog = Dialog(self)
        self.Dialog.instruct.connect(self.handle_dialog)
        self.overlay.API_KEY_ect.connect(self.handle_api_key_from_overlay)
        # self.overlay.use_rag.connect(self.handle_rag)
        self.resizeEvent = self.on_resize
        self.set_affinity.connect(self.affinity.set_affinity)
        self.cn = ''
        self.emo = 'peace'
        self.text_queue = deque()
        # 用于保存按钮的原始QSS
        self.send_button_default_qss = """
            QPushButton {
                background-color: #007bff; /* 蓝色基调 */
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #004085;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #cccccc;
            }
        """
        self.next_button_default_qss = """
            QPushButton {
                background-color: #489E26; 
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
                font-size: 10pt;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #317417;
            }
            QPushButton:pressed {
                background-color: #204610;
            }
            QPushButton:disabled {
                background-color: #4A4C49;
                color: #cccccc;
            }
        """

        self.init_ui()
        self.setup_tray_icon()
        # self.hide() # 初始时隐藏窗口到托盘

        self.llm_thread = QThread(self)
        # 2. 创建 LLMWorker 对象（它现在是 QObject 子类）
        self.llm_worker = LLMWorker()
        # 3. 将 worker 移到新线程
        self.llm_worker.moveToThread(self.llm_thread)
        # 4. 连接信号和槽
        # 当线程启动时，调用 worker 的 run 方法
        self.llm_thread.started.connect(self.llm_worker.run)
        # worker 发出响应信号时，更新 UI
        self.llm_worker.response_ready.connect(self.handel_end)
        # worker 发出错误信号时，显示错误
        self.llm_worker.error_occurred.connect(self.handel_end)
        # 当线程结束时，进行清理（可选，但推荐）
        self.llm_thread.finished.connect(self.llm_thread.deleteLater) # 释放线程对象内存
        self.llm_thread.finished.connect(self.llm_worker.deleteLater) # 释放 worker 对象内存
        # 5. 启动线程
        self.audio_thread = QThread(self)
        self.audio_worker = Audio_Worker()
        self.audio_worker.moveToThread(self.audio_thread)

        self.play_audio_thread = QThread(self)
        self.play_audio_worker = AudioState()
        self.play_audio_worker.moveToThread(self.play_audio_thread)
        self.llm_worker.set_queue(self.text_queue)

        # connect
        # self.llm_worker.send_model_list.connect(self.overlay.add_models)
        self.llm_worker.info_dialog.connect(self.Dialog.handle_info)
        self.llm_worker.info_text.connect(self.show_dialog_text)
        self.llm_worker.trigger_audio_worker.connect(self.audio_worker.gengerate_voice)
        self.handel_model_list.connect(self.overlay.handel_model_list)
        self.llm_worker.send_tmp_msg.connect(self.show_next_text)
        self.llm_worker.info_audio_worker.connect(self.audio_worker.set_res_emit)
        self.llm_worker.char_and_bg.connect(self.handle_dress_and_bg)
        self.play_autdio.connect(self.play_audio_worker.audio_play_thread)
        self.audio_worker.response_ready.connect(self.put_audio_queue)
        self.audio_queue = deque()
        if self.llm_worker.voice_handle == 'HANDLE_VOICE':
            print('初始信号已经发送')
            self.llm_worker.voice_handle = None
        # self.audio_worker.response_ready.connect(self.handel_end)
        # self.audio_worker.error_occurred.connect(self.handel_end)
        self.audio_thread.finished.connect(self.audio_worker.deleteLater) # 释放 worker 对象内存

        self.llm_thread.start()
        self.audio_thread.start()
        self.play_audio_thread.start()
        self.closeEvent = self.on_close_event

        try:
            self.handle_dialog('LOAD')
            print('已经加载上传对话...')
        except Exception as e:
            print('加载上一次保存对话失败' + e)
            
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0) # 移除边距，让图片填充
        main_layout.setSpacing(0) # 移除间距
        
        # --- 顶部图片显示区域 - 使用 QStackedLayout 实现图层 ---

        self.image_stack_widget = QWidget() # 创建一个容器QWidget来承载堆叠布局
        self.image_stack_widget.setFixedSize(self._height, self._width) # 调整高度以适应新的窗口大小
        self.image_stack_widget.setMouseTracking(True)
        # 在 image_stack_widget 上安装事件过滤器以检测双击
        self.image_stack_widget.installEventFilter(self) 
        self.floating_button = None
        image_stack_layout = QStackedLayout()
        # image_stack_layout = QStackedLayout(self.image_stack_widget)
        self.image_stack_widget.setLayout(image_stack_layout)
        image_stack_layout.setContentsMargins(0, 0, 0, 0) # 移除布局边距
        image_stack_layout.setStackingMode(QStackedLayout.StackAll) # 关键：允许所有层堆叠显示
        self.background_label = QLabel(self.image_stack_widget)
        self.background_label.setScaledContents(True)

        # 角色
        self.char_label = QLabel(self.image_stack_widget)
        self.char_label.setStyleSheet("background: transparent;")

        # 表情
        self.emotion_label = QLabel(self.image_stack_widget)
        self.emotion_label.setStyleSheet("background: transparent;")
        self.emotion_opacity_effect = QGraphicsOpacityEffect(self.emotion_label)
        self.emotion_label.setGraphicsEffect(self.emotion_opacity_effect)
        # 把容器加到主布局
        main_layout.addWidget(self.image_stack_widget)

        image_stack_layout.setAlignment(
            self.emotion_label,
            Qt.AlignHCenter | Qt.AlignBottom
        )
        main_layout.addWidget(self.image_stack_widget) # 将包含堆叠布局的容器添加到主布局

        # 初始加载图片
        QTimer.singleShot(0, lambda: self.load_layered_images(self.bg_image_files[self.current_bg_index], self.char_image_files[self.current_char_index], f"./img/fumino_02l_resize/emotion/{self.emo}.png"))

        # --- 对话显示区域（半透明覆盖在图片底部） ---
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setLineWrapMode(QTextEdit.WidgetWidth) # 确保单词换行
        
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: rgba(50, 50, 50, 0); /* 聊天框背景：完全透明 */
                border: none; /* 移除边框，防止边框是纯黑的 */
                padding: 20px; /* 增加内边距 */
                color: #e0e0e0; /* 文本颜色 */
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
                font-size: 14pt; /* 增大字体 */
                font-weight: bold; /* 字体加粗 */

            }
            /* 滚动条隐藏，因为每次只显示一句，理论上不需要滚动条 */
            QTextEdit QScrollBar:vertical {
                width: 0px; 
            }
        """)
        self.chat_display.setFixedHeight(96) # 固定对话框高度
        main_layout.addWidget(self.chat_display)

        input_layout = QHBoxLayout()
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("在这里输入你的消息...")
        self.user_input.returnPressed.connect(self.send_message)
        self.user_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(50, 50, 50, 0); /* 深灰色 */
                border: 1px solid white;
                border-radius: 8px;
                height: 26px; 
                padding: 10px;
                color: #ffffff;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
                font-size: 16pt;
            }
            QLineEdit:focus {
                border: 1px solid #007bff; /* 聚焦时的亮蓝色 */
                background-color: rgba(50, 50, 50, 0);
            }
        """)
        self.send_button = QPushButton("发送")
        # 直接在这里应用保存的默认QSS
        self.send_button.setStyleSheet(self.send_button_default_qss + """
            QPushButton {
                border: none;
                color: white;
                height: 26px; 
                width: 38px;
                margin: 2px;
            }
        """)
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.user_input)
        input_layout.addWidget(self.send_button)

        self.next_btn = QPushButton("下一条")
        self.next_btn.setStyleSheet(self.next_button_default_qss + """
            QPushButton {
                border: none;
                color: white;
                height: 26px; 
                margin: 2px;
                                    
            }
        """)
        self.next_btn.clicked.connect(self.show_next_text)
        input_layout.addWidget(self.next_btn)

        main_layout.addLayout(input_layout)


        # 设置窗口整体背景
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(50, 50, 50, 0); /* 更深的背景色 */
                font-family: 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
                color: #ffffff; /* 默认文本颜色为白色 */
            }
            /* 统一滚动条样式，隐藏所有 */
            QScrollBar {
                width: 0px; 
                height: 0px;
            }
        """)


            
    # 修改 load_or_create_image 函数为 load_layered_images，并更新其逻辑
    def load_layered_images(self, background_path, char_path, emotion_path):
        w = self.image_stack_widget.width()
        h = self.image_stack_widget.height()

        # 2. 背景全铺
        bg = QPixmap(background_path)
        if not bg.isNull():
            self.background_label.setPixmap(
                bg.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            )
        self.background_label.setGeometry(0, 0, w, h)

        # 3. 前景保持原图大小，手动计算「底部居中」坐标
        char = QPixmap(char_path)
        if not char.isNull():
            self.char_label.setPixmap(char)
            ew, eh = char.width(), char.height()
            # 如果想限制它不超出容器宽度，可以：
            if ew > w:
                ew = w
                eh = int(w * char.height() / char.width())
                self.char_label.setPixmap(char.scaled(ew, eh, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            # 计算居中底部坐标
            cur_x = (w - ew) // 2
            parent_height = self.char_label.parent().height()
            # cur_y = parent_height-eh+80
            cur_y = parent_height-eh+380
            self.char_label.setGeometry(cur_x, cur_y, ew, eh)

        emo = QPixmap(emotion_path)
        if not emo.isNull():
            self.emotion_label.setPixmap(emo)
            ew, eh = emo.width(), emo.height()
            # 如果想限制它不超出容器宽度，可以：
            if ew > w:
                ew = w
                eh = int(w * emo.height() / emo.width())
                self.emotion_label.setPixmap(emo.scaled(ew, eh, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            # 计算居中底部坐标
            self.emotion_label.setGeometry(cur_x, cur_y, ew, eh)


    def create_placeholder_image(self, label, size, text="Placeholder"):
        pixmap = QPixmap(size.width(), size.height())
        pixmap.fill(QColor("#0a0a0a")) # 深色占位背景
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#007bff"))
        painter.drawEllipse(pixmap.width() // 4, pixmap.height() // 4, pixmap.width() // 2, pixmap.height() // 2)
        painter.setPen(QColor("#e0e0e0"))
        painter.setFont(QApplication.font())
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
        painter.end()
        label.setPixmap(pixmap)
        label.setScaledContents(True)

    def show_dialog_text(self, text):
        # 清空当前显示
        self.chat_display.clear()
        
        # 应用淡入动画
        if self.text_fade_animation:
            self.text_fade_animation.stop()
        
        # 创建透明度效果
        opacity_effect = QGraphicsOpacityEffect(self.chat_display)
        self.chat_display.setGraphicsEffect(opacity_effect)

        self.text_fade_animation = QPropertyAnimation(opacity_effect, b"opacity")
        self.text_fade_animation.setDuration(500)
        self.text_fade_animation.setStartValue(0.0)
        self.text_fade_animation.setEndValue(1.0)
        self.text_fade_animation.setEasingCurve(QEasingCurve.InQuad)

        html = f"""
        <div style='text-align: center; margin-top: 10px;'>
            <span style='color: white; 
                        font-size: 26pt; 
                        padding: 5px 10px; /* 给背景增加一点内边距，让文字不拥挤 */
                        background-color: rgba(0, 0, 0, 0.4); 
                        '>
                {text}
            </span>
        </div>
        """

        self.chat_display.insertHtml(html)
        
        QTimer.singleShot(0, self.adjust_chat_display_height)
        
        self.text_fade_animation.start()

    def adjust_chat_display_height(self):
        doc_height = self.chat_display.document().size().height()
        
        total_height = int(doc_height) + 40
        
        min_height = 96
        total_height = max(total_height, min_height)
        
        max_height = 300  
        total_height = min(total_height, max_height)
        
        self.chat_display.setFixedHeight(total_height)

    def send_message(self):
        user_text = self.user_input.text().strip()
        if not user_text:
            return

        self.user_input.clear()
        self.send_button.setEnabled(False)
        
        # 直接替换为“正在思考...”
        self.show_dialog_text("正在思考...") # 助手显示“思考中”

        self.llm_worker.process_message(user_text)

    def handel_end(self):
        self.send_button.setEnabled(True)
        self.user_input.setFocus()
        opacity_animation = QPropertyAnimation(self.emotion_opacity_effect, b"opacity")
        opacity_animation.setDuration(400) # 0.4秒
        opacity_animation.setKeyValueAt(0, 1.0)
        opacity_animation.setKeyValueAt(0.5, 0.3) # 闪烁到30%透明度
        opacity_animation.setKeyValueAt(1, 1.0) # 再恢复完全不透明
        opacity_animation.setLoopCount(1)
        opacity_animation.start(QPropertyAnimation.DeleteWhenStopped) # 动画结束后自动删除

    def create_tray_icon_pixmap(self):
        pixmap = QPixmap('./img/icon.png')
        return pixmap

    def setup_tray_icon(self):
        pixmap = self.create_tray_icon_pixmap()
        self.tray_icon = QSystemTrayIcon(QIcon(pixmap), self)
        self.tray_icon.setToolTip("Fumino")

        tray_menu = QMenu()
        tray_menu.setStyleSheet("""
            QMenu {
                background-color: #3e3e3e;
                border: 1px solid #5a5a5a;
                border-radius: 5px;
                color: #e0e0e0;
            }
            QMenu::item {
                padding: 5px 20px;
                background-color: transparent;
            }
            QMenu::item:selected {
                background-color: #007bff;
                color: white;
                border-radius: 3px;
            }
        """)

        show_action = QAction("显示窗口", self)
        show_action.triggered.connect(self.show_window)
        tray_menu.addAction(show_action)

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_window()

    def show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()
        self.user_input.setFocus()

    def on_close_event(self, event):
        self.hide()
        event.ignore()

    def quit_app(self):
        if self.animation and self.animation.state() == QPropertyAnimation.Running:
            self.animation.stop()
        if self.text_fade_animation and self.text_fade_animation.state() == QPropertyAnimation.Running:
            self.text_fade_animation.stop()
        # 确保退出时按钮样式恢复
        if hasattr(self, 'send_button') and hasattr(self, 'send_button_default_qss'):
            self.send_button.setStyleSheet(self.send_button_default_qss)
        self.tray_icon.hide()
        QCoreApplication.quit() 

    def eventFilter(self, obj, event):
        if obj is self.image_stack_widget and event.type() == QEvent.Type.MouseButtonDblClick:
            if isinstance(event, QMouseEvent): # 确保是 QMouseEvent 类型
                self.show_floating_button_row(event.globalPosition().toPoint()) # 调用新的函数
                return True # 阻止事件继续传播
        return super().eventFilter(obj, event)

    def show_floating_button_row(self, global_pos: QPoint):
        if self.floating_button_container is None:
            self.floating_button_container = QWidget(self)
            self.floating_button_container.setObjectName('floating_button_container')
            self.floating_button_container.setStyleSheet("""
                QWidget {
                    background-color: rgba(30, 30, 30, 200); /* 深灰半透明 */
                    border: 1px solid rgba(70, 70, 70, 200);
                    border-radius: 8px;
                    padding: 5px;
                }
                QPushButton {
                    background-color: #007bff;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 15px;
                    font-size: 10pt;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #0056b3;
                }
                QPushButton:pressed {
                    background-color: #004085;
                }
            """)
            
            button_layout = QHBoxLayout(self.floating_button_container)
            button_layout.setContentsMargins(5, 5, 5, 5)
            button_layout.setSpacing(10)

            # 定义按钮文本
            button_texts = ["设置", "状态栏", "聊天记录", "更换服装", "更换背景", "关闭"]
            for text in button_texts:
                btn = QPushButton(text)
                btn.clicked.connect(lambda checked, t=text: self.on_floating_option_clicked(t))
                button_layout.addWidget(btn)
            self.floating_button_opacity_effect = QGraphicsOpacityEffect(self.floating_button_container)
            self.floating_button_container.setGraphicsEffect(self.floating_button_opacity_effect)

        # 将全局坐标转换为父窗口（QWidget）的局部坐标
        local_pos = self.mapFromGlobal(global_pos)

        # 调整位置，让按钮容器出现在双击位置的右下方
        # 考虑到容器的尺寸，稍微偏移一下
        # 自动调整大小以适应内容
        self.floating_button_container.adjustSize() 
        self.floating_button_container.move(local_pos.x() + 10, local_pos.y() + 10)
        self.floating_button_container.show()
        self.floating_button_container.raise_() # 确保按钮在最上层

        # 启动浮动按钮容器的淡入动画
        self.floating_button_opacity_animation = QPropertyAnimation(self.floating_button_opacity_effect, b"opacity")
        self.floating_button_opacity_animation.setDuration(300)
        self.floating_button_opacity_animation.setStartValue(0.0)
        self.floating_button_opacity_animation.setEndValue(1.0)
        self.floating_button_opacity_animation.start(QPropertyAnimation.DeleteWhenStopped)

    # 新的槽函数，处理浮动选项按钮的点击
    def on_floating_option_clicked(self, option_text: str):
        if option_text == "关闭":
            self.hide_floating_button_row()
        elif option_text == '状态栏':
            self.affinity.show_with_animation()
        elif option_text == "设置":
            self.show_settings()
        elif option_text == "聊天记录":
            self.Dialog.show_with_animation()
        elif option_text == "更换背景":
            self.current_bg_index = (self.current_bg_index + 1) % len(self.bg_image_files)
            emo_dir = self.BASE_DIR / 'img' / 'fumino_02l_resize' / 'emotion' / f'{self.emo}.png'
            self.load_layered_images(self.bg_image_files[self.current_bg_index], self.char_image_files[self.current_char_index], emo_dir)
        elif option_text == "更换服装":
            self.current_char_index = (self.current_char_index + 1) % len(self.char_image_files)
            emo_dir = self.BASE_DIR / 'img' / 'fumino_02l_resize' / 'emotion' / f'{self.emo}.png'
            self.load_layered_images(self.bg_image_files[self.current_bg_index], self.char_image_files[self.current_char_index], emo_dir)

    # 新的函数，用于隐藏浮动按钮容器
    def hide_floating_button_row(self):
        if self.floating_button_container and self.floating_button_container.isVisible():
            self.floating_button_opacity_animation = QPropertyAnimation(self.floating_button_opacity_effect, b"opacity")
            self.floating_button_opacity_animation.setDuration(300)
            self.floating_button_opacity_animation.setStartValue(1.0)
            self.floating_button_opacity_animation.setEndValue(0.0)
            # 动画结束后隐藏容器
            self.floating_button_opacity_animation.finished.connect(self.floating_button_container.hide) 
            self.floating_button_opacity_animation.start(QPropertyAnimation.DeleteWhenStopped)

    # 重写 mousePressEvent 来隐藏浮动按钮（点击空白处隐藏）
    def mousePressEvent(self, event):
        if self.floating_button_container and self.floating_button_container.isVisible():
            # 如果点击的位置不在浮动按钮容器上，则隐藏浮动按钮容器
            if not self.floating_button_container.geometry().contains(event.pos()):
                self.hide_floating_button_row()
        super().mousePressEvent(event)

    def show_settings(self):
        """显示设置覆盖层"""
        self.overlay.show_with_animation()

    def on_resize(self, event):
        """窗口大小改变时调整覆盖层大小"""
        self.overlay.resize(self.size())
        super().resizeEvent(event)

    def load_images_from_folder(self, folder_path):
        """
        从指定文件夹加载所有支持的图片文件。
        """
        supported_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp')
        image_files = []

        if not os.path.isdir(folder_path):
            print("错误", f"'{folder_path}' 不是一个有效的文件夹。")
            return

        for filename in os.listdir(folder_path):
            if filename.lower().endswith(supported_extensions):
                image_files.append(os.path.join(folder_path, filename))
        
        if not image_files:
            print("提示", "该文件夹中没有找到支持的图片文件。")
            return

        image_files.sort() # 对图片文件路径进行排序，以便按序显示
        return image_files
    
    def handle_api_key_from_overlay(self, llm, model, api_key, rag):
        """
        当 OverlayWidget 发出 apiKeyEntered 信号时，此槽函数会被调用，
        并接收到 API Key 作为参数。
        """
        print(f"主窗口收到来自 OverlayWidget 的 API Key: {llm, model, api_key, rag}")
        if rag != None:
            print('设置rag')
            self.llm_worker.use_rag = rag
            # if rag == True:
            #     self.llm_worker.set_rag()
            if not api_key:
                return
        self.llm_worker.api_key = api_key
        self.llm_worker.change_llm_and_models(llm, model, api_key)

        if model == None or model == '':
            print('获取模型列表信息已发送')
            print(llm, api_key)
            self.handel_model_list.emit(llm, api_key)
            return
        try:
            with open(self.BASE_DIR / "config.json", 'r', encoding='utf-8') as file:
                config = json.load(file)
            config['api_key'] = api_key 
            config['llm'] = llm
            config['model'] = model
            config['rag'] = self.llm_worker.use_rag
            with open(self.BASE_DIR / "config.json", 'w', encoding='utf-8') as file:
                json.dump(config, file, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"写入 './config.json' 时发生错误: {e}")
        except json.JSONDecodeError:
            print(f"警告: ./config.json' 内容损坏或为空，将创建新的配置。")
        except Exception as e:
            # 捕获其他可能的读取错误
            print(f"读取 ./config.json' 时发生错误: {e}")

    def extract_parts(self, text):
        # 使用正则表达式提取各部分
        ja, emo, cn, sta_num = '', '', '', ''
        try:
            ja_match = re.search(r'\[ja\](.*?)\[\/ja\]', text, re.DOTALL)
            emo_match = re.search(r'\[emo\](.*?)\[\/emo\]', text, re.DOTALL)
            cn_match = re.search(r'\[cn\](.*?)\[\/cn\]', text, re.DOTALL)
            sta_match = re.search(r'<<StatusBlock>>(.*?)<<StatusBlock>>', text, re.DOTALL)
            ja = ja_match.group(1).strip() if cn_match else ""
            cn = cn_match.group(1).strip() if cn_match else ""
            emo = emo_match.group(1).strip() if emo_match else ""
            sta = sta_match.group(1).strip() if sta_match else ""
            sta_num = int(re.findall(r'\d+', sta)[0])
        except Exception as e:
            print(e)

        finally:
            return ja, emo, cn, sta_num
    
    def loc_re(self, text):
        loc_match = re.search(r'⁇(.*?)⁇', text, re.DOTALL)
        return loc_match.group(1).strip() if loc_match else ""
    
    def show_next_text(self):
        print(self.text_queue)
        print('//////////////////////////\n ', self.audio_queue)
        if self.text_queue:
            self.next_btn.setEnabled(True)
            # 从队列左侧弹出一个元素
            text_to_show = self.text_queue.popleft()
            print(f'开始显示文本：{text_to_show}')
            try:
                loc = self.loc_re(text_to_show)
                if loc:    
                    # index = self.bg_image_files.index(loc)
                    indices = [index for index, value in enumerate(self.bg_image_files) if loc in value]
                    if indices:
                        print(f'已经将背景切换为{loc}')
                        text_to_show = text_to_show.replace(f'⁇{loc}⁇', '', 1)
                        self.current_bg_index = indices[0]
                        self.load_layered_images(self.bg_image_files[self.current_bg_index], self.char_image_files[self.current_char_index], f"./img/fumino_02l_resize/emotion/{self.emo}.png")
                file_match = file_match = re.search(r'<<FILE>>(.*?)<<FILE>>', text_to_show)
                if file_match:
                        file_name = file_match.group(1)
                        try:
                            item = self.audio_queue.popleft()
                            if file_name != item:
                                self.next_btn.setEnabled(False)
                                self.text_queue.appendleft(text_to_show)
                                return
                            else:
                                ja, emo, cn, _ = self.extract_parts(text_to_show)
                                self.emo = emo
                                self.load_layered_images(self.bg_image_files[self.current_bg_index], self.char_image_files[self.current_char_index], f"./img/fumino_02l_resize/emotion/{self.emo}.png")
                                print(f'开始播放语音:{ja} 从文件：{file_name}')
                                self.play_audio_worker.stop()
                                file_name = f'./voices/{file_name}.wav' 
                                self.play_autdio.emit(file_name)
                                text_to_show = cn
                        except IndexError:
                            self.next_btn.setEnabled(False)
                            self.text_queue.appendleft(text_to_show)
                elif '<<StatusBlock>>' in text_to_show:
                    _, _, _, sta_num = self.extract_parts(text_to_show)
                    self.set_affinity.emit(sta_num)
                    text_to_show = f'「完」\n当前好感度: {sta_num}'
                    self.next_btn.setEnabled(False)
                else:
                    text_to_show = re.sub(r'<<[^>]+>>', '', text_to_show, re.DOTALL)
                self.show_dialog_text(text_to_show)
            except Exception as e:
                    print(f'文本显示出错：{e}')
            
        else:
            # 队列为空，所有文本都已显示
            self.audio_queue.clear()

            # self.show_dialog_text("故事到此结束。")
            return
        
    def handle_dialog(self, instruct):
        print(f"已经接到指令{instruct}")
        if instruct == 'CLEAR':
            self.llm_worker.clear_dialog()
        elif instruct == 'LOAD':
            self.llm_worker.load_dialog()
        elif instruct == 'SAVE':
            self.llm_worker.save_dialog(self.current_char_index, self.current_bg_index, self.emo)
        else:
            print('未知指令')

    def handle_dress_and_bg(self, dress = None, bg = None, emo =None):
        self.current_bg_index = bg
        self.current_char_index = dress
        self.current_emotion_index = emo
        emo_dir = self.BASE_DIR / 'img' / 'fumino_02l_resize' / 'emotion' / f'{emo}.png'
        self.load_layered_images(self.bg_image_files[bg], self.char_image_files[dress], emo_dir)
    
    def put_audio_queue(self, name):
        print('++++++++++已经将' + name +'入队列++++++++++++++++')
        self.audio_queue.append(name)
        self.next_btn.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QWidget {
            background-color: #111111; /* 更深的背景色 */
            font-family: 'Segoe UI', 'Microsoft YaHei', Arial, sans-serif;
            color: #ffffff; /* 默认文本颜色为白色 */
        }
        /* 统一滚动条样式，隐藏所有 */
        QScrollBar {
            width: 0px; 
            height: 0px;
        }
    """)
    chat_app = LLMChatApp()
    chat_app.show()
    sys.exit(app.exec())