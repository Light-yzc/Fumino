from PySide6.QtWidgets import ( QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton,QLabel, QGraphicsOpacityEffect, QFrame, QProgressBar, QRadioButton, QButtonGroup, QComboBox
)
import requests
import json
from google import genai
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QRect, QParallelAnimationGroup, Property, QThread # 导入 QEvent
from PySide6.QtGui import QPainter, QColor, QPen, QBrush # 导入 QMouseEvent
class affinity_bar(QFrame):
    """半透明覆盖层"""
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 关键设置：确保覆盖层在父窗口之上
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # 设置透明度效果
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        
        # 主布局
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # 设置面板（居中显示）
        self.settings_panel = QFrame(self)
        self.settings_panel.setFixedSize(400, 230)
        
        self.affinity = 48
        # 设置面板样式 - 增加一些半透明效果
        self.settings_panel.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 30, 170); /* 深灰色，带一点透明度 */
                border-radius: 15px; /* 更大的圆角 */
                padding: 20px; /* 内部填充 */
            }

            /* 好感度状态栏样式 */
            QProgressBar {
                border: 2px solid #555; /* 边框 */
                border-radius: 5px; /* 圆角 */
                text-align: center; /* 文本居中 */
                color: white; /* 文本颜色 */
                background-color: rgba(50, 50, 50, 100); /* 进度条背景 */
            }
            QProgressBar::chunk {
                background-color: #EFC3CA; /* 进度条颜色：红色 */
                border-radius: 6px; /* 内部块的圆角 */
            }
        """)
        
        self.settings_layout = QVBoxLayout(self.settings_panel)
        self.settings_layout.setAlignment(Qt.AlignCenter)
        self.settings_layout.setSpacing(20)
        affinity_layout = QHBoxLayout()
        affinity_layout.setAlignment(Qt.AlignCenter)
        
        affinity_label = QLabel("好感度:")
        affinity_label.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white; font-size: 16px;")
        self.affinity_bar = QProgressBar()
        self.affinity_bar.setFixedSize(250, 20)
        self.affinity_bar.setRange(0, 100) # 设定范围 0-100
        self.affinity_bar.setValue(self.affinity)
        
        affinity_layout.addWidget(affinity_label)
        affinity_layout.addWidget(self.affinity_bar)
        
        self.settings_layout.addLayout(affinity_layout)

        close_button = QPushButton("关闭设置")
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50; /* 绿色 */
                color: white;
                border-radius: 10px; /* 圆角 */
                padding: 10px 20px; /* 内边距 */
                font-size: 16px;
                border: none;
            }
            QPushButton:hover {
                background-color: #45a049; /* 悬停颜色 */
            }
            QPushButton:pressed {
                background-color: #367c39; /* 按下颜色 */
            }
        """)
        close_button.setFixedSize(150, 40)
        close_button.clicked.connect(self.hide_with_animation)
        self.settings_layout.addWidget(close_button, 0, Qt.AlignCenter)
        
        self.layout.addStretch()
        self.layout.addWidget(self.settings_panel, 0, Qt.AlignCenter)
        self.layout.addStretch()
        
        self.setup_animations()
        self.hide()
    
    def set_affinity(self, affinity):
        self.affinity = affinity
        self.affinity_bar.setValue(self.affinity)
    def setup_animations(self):
        """设置动画"""
        self.opacity_animation = QPropertyAnimation(self.effect, b"opacity")
        self.opacity_animation.setDuration(300)
        self.animation_group = QParallelAnimationGroup()
        self.animation_group.addAnimation(self.opacity_animation)
        self.animation_group.finished.connect(self.on_animation_finished)
    
    def show_with_animation(self):
        """显示覆盖层并播放动画"""
        self.show()
        self.raise_()
        self.resizeEvent(None) # 触发一次 resizeEvent 来更新 settings_panel 的位置

        full_rect = self.settings_panel.geometry()
        center = full_rect.center()

        start_rect = QRect(center.x() - 1, center.y() - 1, 2, 2) 
        
        self.opacity_animation.setStartValue(0.0)
        self.opacity_animation.setEndValue(1.0)

        self.animation_group.setDirection(QPropertyAnimation.Forward)
        
        self.animation_group.start()
        
    def hide_with_animation(self):
        """隐藏覆盖层并播放淡出动画"""
        
        self.animation_group.setDirection(QPropertyAnimation.Backward)
        
        self.animation_group.start()
    
    def on_animation_finished(self):
        """动画完成时的处理"""
        if self.animation_group.direction() == QPropertyAnimation.Backward:
            self.hide()

            
    def resizeEvent(self, event):
        """调整大小时确保覆盖层与父窗口一致"""
        super().resizeEvent(event)
        if self.parent():
            self.setGeometry(self.parent().rect())
            panel_width = self.settings_panel.width()
            panel_height = self.settings_panel.height()
            x = (self.width() - panel_width) // 2
            y = (self.height() - panel_height) // 2
            self.settings_panel.move(x, y)

class OverlayWidget(QFrame):
    """半透明覆盖层"""
    API_KEY_ect = Signal(str, str, str, bool)
    # use_rag = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.radio_btn_select = 'Gemini'
        self.model = None
        self.model_fetcher = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # 增大面板高度以容纳新控件
        self.settings_panel = QFrame(self)
        self.settings_panel.setFixedSize(500, 830) 
        with open('./config.json', 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.settings_panel.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 30, 170);
                border-radius: 15px;
                padding: 20px;
            }
            QLabel {
                color: white;
                font-size: 20px;
            }
            QTextEdit {
                background-color: rgba(50, 50, 50, 0);
                border: none;
                padding: 16px;
                color: #e0e0e0;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
                font-size: 20pt;
                font-weight: bold;
            }
            QTextEdit::placeholder {
                color: #808080; /* 占位符文本颜色（通常比主文本浅） */
                font-size: 16pt; /* 与主文本相同的字体大小 */
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
                font-weight: bold;
            }
            QTextEdit QScrollBar:vertical {
                width: 0px; 
            }
            QRadioButton {
                color: white;
                font-size: 16px;
                background-color: rgba(0, 0, 0, 0);
            }
            QRadioButton::indicator {
                width: 15px;
                height: 15px;
            }
            QPushButton {
                background-color: #015195;
                color: white;
                border-radius: 10px;
                padding: 10px 20px;
                font-size: 16px;
                border: none;
            }
            QPushButton:hover {
                background-color: #043662;
            }
            QPushButton:pressed {
                background-color: #00203C;
            }
        """)
        
        self.settings_layout = QVBoxLayout(self.settings_panel)
        self.settings_layout.setAlignment(Qt.AlignCenter)
        self.settings_layout.setSpacing(20)
        
        # 添加开关按钮和标签
        switch_layout = QHBoxLayout()
        switch_layout.setAlignment(Qt.AlignCenter)
        switch_label = QLabel("开启/关闭Rag检索:")
        switch_label.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white; font-size: 16px;")
        self.my_switch_button = SwitchButton(self)
        self.my_switch_button.setChecked(self.config['rag'])
        if not self.config['rag']:
            self.my_switch_button._x_offset = 0
        # self.my_switch_button.toggled.connect(self.handle_rag)
        switch_layout.addWidget(switch_label)
        switch_layout.addWidget(self.my_switch_button)
        self.settings_layout.addLayout(switch_layout)

        # --- 新增圆点式选择按钮部分 ---
        options_label = QLabel("选择模型:")
        options_label.setAlignment(Qt.AlignCenter)
        options_label.setStyleSheet("color: white; font-size: 18px;")
        self.settings_layout.addWidget(options_label)
        
        options_layout = QHBoxLayout()
        options_layout.setAlignment(Qt.AlignCenter)
        options_layout.setSpacing(30)
        
        self.model_button_group = QButtonGroup(self)
        self.model_button_group.setExclusive(True)

        self.option1_btn = QRadioButton("Gemini")
        self.option2_btn = QRadioButton("质谱")
        # self.option3_btn = QRadioButton("Option 3")
        
        self.option1_btn.setChecked(True)
        
        self.model_button_group.addButton(self.option1_btn, 1)
        self.model_button_group.addButton(self.option2_btn, 2)
        # self.model_button_group.addButton(self.option3_btn, 3)

        options_layout.addWidget(self.option1_btn)
        options_layout.addWidget(self.option2_btn)
        # options_layout.addWidget(self.option3_btn)
        
        self.settings_layout.addLayout(options_layout)
        
        self.model_button_group.buttonClicked.connect(self.handle_option_selection)

        model_list_label = QLabel("选择模型列表:")
        model_list_label.setAlignment(Qt.AlignCenter)
        model_list_label.setStyleSheet("color: white; font-size: 18px;")
        self.settings_layout.addWidget(model_list_label)

        self.model_list_combo = QComboBox(self)
        # self.model_list_combo.setFixedHeight(40)
        self.model_list_combo.setStyleSheet("""
            height: 40px; 
            font-size: 16pt;""")
        self.settings_layout.addWidget(self.model_list_combo)

        title_label = QLabel("设置APIkey")
        title_label.setAlignment(Qt.AlignCenter)
        self.settings_layout.addWidget(title_label)
        
        self.set_api = QTextEdit()
        self.set_api.setPlaceholderText('请输入你的APIkey')
        self.settings_layout.addWidget(self.set_api)
        check_button = QPushButton("检查模型列表")
        check_button.setFixedSize(170, 40)
        check_button.clicked.connect(lambda: self.handel_model_list(self.radio_btn_select, self.set_api.toPlainText().strip()))
        self.settings_layout.addWidget(check_button, 0, Qt.AlignCenter)
        ok_button = QPushButton("确定")
        ok_button.setFixedSize(170, 40)
        ok_button.clicked.connect(lambda: self.handle_api_input_from_textedit(self.set_api.toPlainText().strip()))
        self.settings_layout.addWidget(ok_button, 0, Qt.AlignCenter)
        close_button = QPushButton("关闭设置")
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border-radius: 10px;
                padding: 10px 20px;
                font-size: 16px;
                border: none;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #367c39;
            }
        """)
        close_button.setFixedSize(170, 40)
        close_button.clicked.connect(self.hide_with_animation)
        self.settings_layout.addWidget(close_button, 0, Qt.AlignCenter)
        self.layout.addStretch()
        self.layout.addWidget(self.settings_panel, 0, Qt.AlignCenter)
        self.layout.addStretch()
        self.setup_animations()
        self.hide()

    def add_models(self,models):
        self.model_list_combo.clear()
        self.model_list_combo.addItems(models)

    def handle_option_selection(self, button):
        """处理圆点选择事件"""
        selected_text = button.text()
        print(f"选择了: {selected_text}")
        self.radio_btn_select = selected_text
        
    def handle_model_list_and_rag(self, llm, model, key):
        api_key = key.strip()
        if api_key:
            self.API_KEY_ect.emit(llm, None, api_key, None)
            print('检查信息已经发送')
        else:
            print("API Key 不能为空！")
            self.set_api.setPlaceholderText("API Key 不能为空！请重新输入。")
            
    def handle_api_input_from_textedit(self, api_key_text):
        """
        将 API Key 发送给主窗口，并隐藏 OverlayWidget。
        """
        api_key = api_key_text.strip()
        llm = self.radio_btn_select
        model = self.model_list_combo.currentText()
        if api_key:
            self.API_KEY_ect.emit(llm, model, api_key, self.my_switch_button.isChecked())
            print(f"OverlayWidget 收到并发送 API Key: {api_key, model, llm}")
            self.set_api.setPlaceholderText("API输入成功！")
            self.set_api.clear()
        else:
            print("API Key 不能为空！")
            self.API_KEY_ect.emit(None, None, None, self.my_switch_button.isChecked())
            self.set_api.setPlaceholderText("API Key 不能为空！请重新输入。")

        
    def handel_model_list(self, llm, api_key):
        """启动模型获取线程"""
        # 如果已有线程在运行，先终止
        if self.model_fetcher and self.model_fetcher.isRunning():
            self.model_fetcher.terminate()
            self.model_fetcher.wait()
        
        # 创建新线程
        self.model_fetcher = ModelFetcher(llm, api_key)
        
        # 连接信号
        self.model_fetcher.finished.connect(self.add_models)
        self.model_fetcher.error.connect(self.show_error)
        
        # 启动线程
        self.model_fetcher.start()


    def show_error(self, msg):
        self.set_api.setPlaceholderText(f"API Key错误或者服务器未响应：{msg}")
        self.set_api.clear()
    def setup_animations(self):
        """设置动画"""
        self.opacity_animation = QPropertyAnimation(self.effect, b"opacity")
        self.opacity_animation.setDuration(300)
        
        self.animation_group = QParallelAnimationGroup()
        self.animation_group.addAnimation(self.opacity_animation)
        
        self.animation_group.finished.connect(self.on_animation_finished)
    
    def show_with_animation(self):
        """显示覆盖层并播放动画"""
        self.show()
        self.raise_()
        
        self.resizeEvent(None)
        
        full_rect = self.settings_panel.geometry()
        center = full_rect.center()
        start_rect = QRect(center.x() - 1, center.y() - 1, 2, 2)
        
        self.opacity_animation.setStartValue(0.0)
        self.opacity_animation.setEndValue(1.0)

        self.animation_group.setDirection(QPropertyAnimation.Forward)
        self.animation_group.start()
        
    def hide_with_animation(self):
        """隐藏覆盖层并播放淡出动画"""
        self.animation_group.setDirection(QPropertyAnimation.Backward)
        self.animation_group.start()
    
    def on_animation_finished(self):
        """动画完成时的处理"""
        if self.animation_group.direction() == QPropertyAnimation.Backward:
            self.hide()
            
    def resizeEvent(self, event):
        """调整大小时确保覆盖层与父窗口一致"""
        super().resizeEvent(event)
        if self.parent():
            self.setGeometry(self.parent().rect())
            panel_width = self.settings_panel.width()
            panel_height = self.settings_panel.height()
            x = (self.width() - panel_width) // 2
            y = (self.height() - panel_height) // 2
            self.settings_panel.move(x, y)


class SwitchButton(QPushButton):
    """一个带有平滑滑动动画的自定义开关按钮"""
    toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 25)
        self.setCheckable(True)
        self.setChecked(True)
        # 修复点：确保 _x_offset 在 __init__ 中被正确初始化
        self._x_offset = 25.0

        # 定义一个动画，它将改变 _x_offset 这个属性
        self._animation = QPropertyAnimation(self, b"x_offset", self)
        self._animation.setDuration(250)
        self._animation.setEasingCurve(QEasingCurve.OutQuart)

        self.clicked.connect(self.start_animation)

    def start_animation(self, checked):
        if checked:
            self._animation.setStartValue(0.0)
            self._animation.setEndValue(25.0) # 按钮向右移动 25px
        else:
            self._animation.setStartValue(25.0)
            self._animation.setEndValue(0.0) # 按钮向左移动 0px
        self._animation.start()
        self.toggled.emit(checked)
    
    # 使用 PySide6 的 Property
    @Property(float)
    def x_offset(self):
        return self._x_offset

    @x_offset.setter
    def x_offset(self, value):
        self._x_offset = value
        # 每次动画更新时，重绘按钮
        self.update()

    def paintEvent(self, event):
        """重写 paintEvent 方法，自定义绘制按钮"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. 绘制按钮的背景
        if self.isChecked():
            # 开启状态：绿色背景
            background_color = QColor("#4CAF50") 
        else:
            # 关闭状态：灰色背景
            background_color = QColor("#BDBDBD")
        
        painter.setPen(QPen(background_color, 2))
        painter.setBrush(QBrush(background_color))
        painter.drawRoundedRect(self.rect(), 12, 12) # 绘制圆角矩形背景

        # 2. 绘制滑块（白色的圆圈）
        knob_color = QColor(255, 255, 255) # 白色
        knob_rect = QRect(
            int(self._x_offset) + 2, 2, # x_offset 控制 x 坐标，留 2px 边距
            self.height() - 4,          # 滑块高度 = 按钮高度 - 边距
            self.height() - 4           # 滑块宽度 = 按钮宽度 - 边距
        )
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(knob_color))
        painter.drawEllipse(knob_rect) # 绘制圆形的滑块

        painter.end()


class ModelFetcher(QThread):
    finished = Signal(list)  # 定义信号，用于传递结果
    error = Signal(str)      # 定义信号，用于传递错误信息

    def __init__(self, llm, api_key):
        super().__init__()
        self.llm = llm
        self.api_key = api_key

    def run(self):
        """线程执行的主要逻辑"""
        try:
            print('开始获取模型列表')
            if self.llm == '质谱':
                res = requests.get(
                    'https://open.bigmodel.cn/api/paas/v4/models',
                    headers={'Authorization': f"Bearer {self.api_key}"},
                    timeout=5
                )
                data = res.json()
                model_list = [item['id'] for item in data['data']]
            else:
                client = genai.Client(api_key=self.api_key)
                model_list = [m.name for m in client.models.list()]
            
            self.finished.emit(model_list)  # 发送成功信号
        except Exception as e:
            error_msg = f"获取模型列表失败: {str(e)}"
            print(error_msg)
            self.error.emit(error_msg)  # 发送错误信号


class Dialog(QFrame):
    """半透明覆盖层"""
    instruct = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.settings_panel = QFrame(self)
        self.settings_panel.setFixedSize(320, 460)
        
        self.settings_panel.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 30, 170); /* 深灰色，带一点透明度 */
                border-radius: 15px; /* 更大的圆角 */
                padding: 20px; /* 内部填充 */
            }

        """)
        
        self.settings_layout = QVBoxLayout(self.settings_panel)
        self.settings_layout.setAlignment(Qt.AlignCenter)
        self.settings_layout.setSpacing(35)

        dialog_label = QLabel("聊天记录设置")
        dialog_label.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: white; font-size: 16px;")
        dialog_label.setFixedHeight(70)
        self.settings_layout.addWidget(dialog_label, 0, Qt.AlignCenter)


        btn_sytle = """
        QPushButton {
                    background-color: #007bff;
                    color: white;
                    border: none;
                    border-radius: 10px;
                    padding: 8px 15px;
                    font-size: 10pt;
                    font-weight: bold;
                }
        QPushButton:hover {
                    background-color: #0056b3;
                }
        QPushButton:pressed {
                    background-color: #004085;
        """
        save_btn = QPushButton("保存聊天记录")
        save_btn.setStyleSheet(btn_sytle)
        save_btn.setFixedSize(180, 50)
        save_btn.clicked.connect(self.save_dialog)
        self.settings_layout.addWidget(save_btn, 0, Qt.AlignCenter)

        load_btn = QPushButton("加载聊天记录")
        load_btn.setStyleSheet(btn_sytle)
        load_btn.setFixedSize(180, 50)
        load_btn.clicked.connect(self.load_dialog)
        self.settings_layout.addWidget(load_btn, 0, Qt.AlignCenter)

        clear_btn = QPushButton("清空当前聊天记录")
        clear_btn.setStyleSheet(btn_sytle)
        clear_btn.setFixedSize(180, 50)
        clear_btn.clicked.connect(self.clear_dialog)
        self.settings_layout.addWidget(clear_btn, 0, Qt.AlignCenter)

        self.info_label = QLabel("")
        self.info_label.setStyleSheet("background-color: rgba(0, 0, 0, 0); color: #b6c9b8; font-size: 20px;")
        self.info_label.setFixedHeight(70)
        self.settings_layout.addWidget(self.info_label, 0, Qt.AlignCenter)

        close_button = QPushButton("关闭设置")
        close_button.setStyleSheet("""
            QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 10px;
                    padding: 8px 15px;
                    font-size: 10pt;
                    font-weight: bold;
                }
            QPushButton:hover {
                background-color: #45a049; /* 悬停颜色 */
            }
            QPushButton:pressed {
                background-color: #367c39; /* 按下颜色 */
            }
        """)
        close_button.setFixedSize(180, 50)
        close_button.clicked.connect(self.hide_with_animation)
        self.settings_layout.addWidget(close_button, 0, Qt.AlignCenter)
        
        self.layout.addStretch()
        self.layout.addWidget(self.settings_panel, 0, Qt.AlignCenter)
        self.layout.addStretch()
        
        self.setup_animations()
        self.hide()
    
    def clear_dialog(self):
        self.instruct.emit('CLEAR')

    def load_dialog(self):
        self.instruct.emit('LOAD') 

    def save_dialog(self):
        self.instruct.emit('SAVE')

    def setup_animations(self):
        """设置动画"""
        self.opacity_animation = QPropertyAnimation(self.effect, b"opacity")
        self.opacity_animation.setDuration(300)
        self.animation_group = QParallelAnimationGroup()
        self.animation_group.addAnimation(self.opacity_animation)
        self.animation_group.finished.connect(self.on_animation_finished)
    
    def handle_info(self, info):
        self.info_label.setText(info)

    def show_with_animation(self):
        """显示覆盖层并播放动画"""
        self.show()
        self.raise_()
        self.resizeEvent(None) # 触发一次 resizeEvent 来更新 settings_panel 的位置

        full_rect = self.settings_panel.geometry()
        center = full_rect.center()

        start_rect = QRect(center.x() - 1, center.y() - 1, 2, 2) 
        
        self.opacity_animation.setStartValue(0.0)
        self.opacity_animation.setEndValue(1.0)

        self.animation_group.setDirection(QPropertyAnimation.Forward)
        
        self.animation_group.start()
        
    def hide_with_animation(self):
        """隐藏覆盖层并播放淡出动画"""
        
        self.animation_group.setDirection(QPropertyAnimation.Backward)
        
        self.animation_group.start()
        
        self.info_label.clear()
    
    def on_animation_finished(self):
        """动画完成时的处理"""
        if self.animation_group.direction() == QPropertyAnimation.Backward:
            self.hide()

            
    def resizeEvent(self, event):
        """调整大小时确保覆盖层与父窗口一致"""
        super().resizeEvent(event)
        if self.parent():
            self.setGeometry(self.parent().rect())
            panel_width = self.settings_panel.width()
            panel_height = self.settings_panel.height()
            x = (self.width() - panel_width) // 2
            y = (self.height() - panel_height) // 2
            self.settings_panel.move(x, y)


