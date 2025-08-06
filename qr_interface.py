import tkinter as tk
from tkinter import ttk, messagebox, font
from abc import ABC, abstractmethod
import cv2
from PIL import Image, ImageTk
import time
import numpy as np
from utils import DatabaseSingleton, QRCodeProcessor
from datetime import datetime


class InterfaceState(ABC):
    @abstractmethod
    def update_interface(self, interface):
        pass


class IdleState(InterfaceState):
    def update_interface(self, interface):
        interface.status_label.config(text="Pronto para iniciar a leitura", style='Info.TLabel')
        interface.action_btn.config(text="INICIAR LEITURA", style='Primary.TButton')
        interface.video_frame.config(image='')
        interface.tranca_status.pack_forget()  # Esconde o status da tranca


class ScanningState(InterfaceState):
    def update_interface(self, interface):
        interface.status_label.config(text="Posicione o QR Code na câmera", style='Info.TLabel')
        interface.action_btn.config(text="PARAR LEITURA", style='Secondary.TButton')
        interface.tranca_status.pack(fill=tk.X, pady=20)  # Mostra o status da tranca


class SuccessState(InterfaceState):
    def __init__(self, message):
        self.message = message

    def update_interface(self, interface):
        interface.status_label.config(text=self.message, style='Success.TLabel')
        interface.root.after(2000, interface.reset_to_idle)  # Volta ao estado inicial após 2 segundos


class ErrorState(InterfaceState):
    def __init__(self, message):
        self.message = message

    def update_interface(self, interface):
        interface.status_label.config(text=self.message, style='Error.TLabel')
        interface.root.after(2000, interface.continue_scanning)  # Continua a leitura após 2 segundos


class TrancaStatus(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, style='Status.TFrame')
        self.status_var = tk.StringVar(value="🔒 PORTA TRANCADA")
        self.timer_var = tk.StringVar()

        self.status_label = ttk.Label(
            self,
            textvariable=self.status_var,
            font=('Helvetica', 14, 'bold'),
            style='StatusLabel.TLabel'
        )
        self.status_label.pack(pady=5)

        self.timer_label = ttk.Label(
            self,
            textvariable=self.timer_var,
            font=('Helvetica', 10)
        )
        self.timer_label.pack()

        self.after_id = None

    def abrir_porta(self):
        self.status_var.set("🔓 PORTA ABERTA")
        self.timer_var.set("Fechando em 5 segundos...")
        self.configure(style='StatusAberto.TFrame')
        self.status_label.configure(style='StatusLabelAberto.TLabel')

        if self.after_id:
            self.after_cancel(self.after_id)
        self.after_id = self.after(5000, self.fechar_porta)

    def fechar_porta(self):
        self.status_var.set("🔒 PORTA TRANCADA")
        self.timer_var.set("")
        self.configure(style='Status.TFrame')
        self.status_label.configure(style='StatusLabel.TLabel')
        self.after_id = None


class QRReaderInterface:
    def __init__(self, root):
        self.root = root
        self.state = IdleState()
        self.camera = None
        self.reading = False
        self.current_image = None
        self.video_source = 0
        self.setup_ui()

        self.debug = False
        self.detector = cv2.QRCodeDetector()
        self.qr_processor = QRCodeProcessor()
        self.last_valid_code = None
        self.cooldown_until = 0

    def setup_ui(self):
        self.root.title("Leitor QR - Biblioteca Comunitária")
        self.root.geometry("800x600")
        self.root.configure(bg='#f5f5f5')

        # Frame principal com gradiente moderno
        main_frame = ttk.Frame(self.root, padding="20", style='Main.TFrame')
        main_frame.pack(expand=True, fill=tk.BOTH)

        # Título moderno
        title_frame = ttk.Frame(main_frame, style='Title.TFrame')
        title_frame.pack(fill=tk.X, pady=(0, 20))

        ttk.Label(title_frame, text="Leitor de QR Code",
                  font=('Helvetica', 20, 'bold'), style='Title.TLabel').pack(pady=10)

        ttk.Label(title_frame, text="Biblioteca Comunitária",
                  font=('Helvetica', 12), style='Subtitle.TLabel').pack()

        # Container da câmera com borda arredondada
        camera_frame = ttk.Frame(main_frame, style='Camera.TFrame')
        camera_frame.pack(pady=20, expand=True)

        self.video_frame = ttk.Label(camera_frame)
        self.video_frame.pack()

        # Botão centralizado moderno
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=20)

        self.action_btn = ttk.Button(
            btn_frame,
            text="INICIAR LEITURA",
            command=self.toggle_reader,
            style='Primary.TButton'
        )
        self.action_btn.pack(ipadx=30, ipady=12)

        # Status com ícone
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(pady=10)

        self.status_icon = ttk.Label(status_frame, text="⏺", font=('Helvetica', 14), style='Info.TLabel')
        self.status_icon.pack(side=tk.LEFT, padx=5)

        self.status_label = ttk.Label(
            status_frame,
            text="Pronto para iniciar a leitura",
            font=('Helvetica', 12),
            style='Info.TLabel'
        )
        self.status_label.pack(side=tk.LEFT)

        # Status da tranca
        self.tranca_status = TrancaStatus(main_frame)
        self._configure_styles()

    def _configure_styles(self):
        self.style = ttk.Style()

        # Configuração do tema
        self.style.theme_use('clam')

        # Cores
        self.style.configure('Main.TFrame', background='linear-gradient(#ffffff, #f0f8ff)')
        self.style.configure('Title.TFrame', background='#ffffff')
        self.style.configure('Title.TLabel', foreground='#2c3e50', background='#ffffff')
        self.style.configure('Subtitle.TLabel', foreground='#7f8c8d', background='#ffffff')
        self.style.configure('Camera.TFrame', background='#ecf0f1', relief='solid', borderwidth=1)

        # Botões
        self.style.configure('Primary.TButton',
                             foreground='white',
                             background='#3498db',
                             font=('Helvetica', 12, 'bold'),
                             padding=10,
                             borderwidth=0,
                             focusthickness=0,
                             focuscolor='none',
                             relief='flat',
                             width=20)
        self.style.map('Primary.TButton',
                       background=[('active', '#2980b9'), ('pressed', '#1f618d')])

        self.style.configure('Secondary.TButton',
                             foreground='white',
                             background='#e74c3c',
                             font=('Helvetica', 12, 'bold'),
                             padding=10)

        # Status com ícones
        self.style.configure('Info.TLabel', foreground='#3498db', font=('Helvetica', 12))
        self.style.configure('Success.TLabel', foreground='#27ae60', font=('Helvetica', 12, 'bold'))
        self.style.configure('Error.TLabel', foreground='#e74c3c', font=('Helvetica', 12, 'bold'))

        # Status da tranca
        self.style.configure('Status.TFrame', background='#f8f9fa', borderwidth=2, relief='solid')
        self.style.configure('StatusAberto.TFrame', background='#e8f5e9', borderwidth=2, relief='solid')
        self.style.configure('StatusLabel.TLabel', foreground='#e74c3c', font=('Helvetica', 14, 'bold'))
        self.style.configure('StatusLabelAberto.TLabel', foreground='#27ae60', font=('Helvetica', 14, 'bold'))

    def toggle_reader(self):
        if isinstance(self.state, IdleState):
            self.iniciar_leitura()
        else:
            self.parar_leitura()

    def iniciar_leitura(self):
        self.video_source = 0
        self.camera = cv2.VideoCapture(self.video_source)

        if self.camera.isOpened():
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.state = ScanningState()
            self.state.update_interface(self)
            self.update_frame()
        else:
            messagebox.showerror("Erro", "Não foi possível acessar a câmera")

    def parar_leitura(self):
        if self.camera and self.camera.isOpened():
            self.camera.release()
        self.state = IdleState()
        self.state.update_interface(self)

    def reset_to_idle(self):
        """Reseta a interface para o estado inicial"""
        self.parar_leitura()

    def continue_scanning(self):
        """Continua a leitura após um erro"""
        if isinstance(self.state, ErrorState):
            self.state = ScanningState()
            self.state.update_interface(self)
            self.update_frame()

    def update_frame(self):
        if not isinstance(self.state, ScanningState):
            return

        ret, frame = self.camera.read()
        if not ret:
            self.root.after(1000, self.reiniciar_camera)
            return

        frame = cv2.resize(frame, (640, 480))
        result = self.processar_frame(frame)

        img = Image.fromarray(cv2.cvtColor(result['frame'], cv2.COLOR_BGR2RGB))
        self.current_image = ImageTk.PhotoImage(image=img)
        self.video_frame.config(image=self.current_image)

        if result['success']:
            self.state = SuccessState(result['message'])
            self.status_icon.config(text="✓", foreground='#27ae60')
        elif result['error']:
            self.state = ErrorState(result['message'])
            self.status_icon.config(text="✗", foreground='#e74c3c')
        else:
            self.status_icon.config(text="⏺", foreground='#3498db')

        self.state.update_interface(self)

        if isinstance(self.state, ScanningState):
            self.root.after(30, self.update_frame)

    def processar_frame(self, frame):
        result = {
            'frame': frame,
            'success': False,
            'error': False,
            'message': "Posicione o QR Code"
        }

        try:
            current_time = time.time()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(gray, (5, 5), 0)
            _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            retval, decoded_info, points, _ = self.detector.detectAndDecodeMulti(thresh)

            if retval:
                processed_result = self._process_qr_codes(decoded_info, current_time, frame)
                if processed_result:
                    return processed_result

            if current_time < self.cooldown_until and self.last_valid_code:
                result['message'] = "Aprovado - Aguardando ação"
                return result

            return result

        except Exception as e:
            result['error'] = True
            result['message'] = f"Erro no processamento: {str(e)}"
            return result

    def _process_qr_codes(self, decoded_info, current_time, frame):
        if not decoded_info:
            return None

        qr_data_str = decoded_info[0] if isinstance(decoded_info, (tuple, list)) else str(decoded_info)
        qr_data_str = qr_data_str.strip("('").strip("',)")

        success, message = self.qr_processor.process(qr_data_str)
        if success:
            self.tranca_status.abrir_porta()
            self.last_valid_code = qr_data_str
            self.cooldown_until = current_time + 5

            return {
                'frame': self._draw_debug_info(frame, qr_data_str, "VALIDO"),
                'success': True,
                'message': message,
                'error': False
            }
        else:
            return {
                'frame': self._draw_debug_info(frame, qr_data_str, "INVALIDO"),
                'success': False,
                'message': message,
                'error': True
            }

    def _draw_debug_info(self, frame, qr_data, status):
        if self.debug:
            frame = cv2.putText(frame, f"STATUS: {status}", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            frame = cv2.putText(frame, f"DATA: {qr_data[:30]}...", (10, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        return frame

    def reiniciar_camera(self):
        self.parar_leitura()
        self.iniciar_leitura()


if __name__ == "__main__":
    root = tk.Tk()
    app = QRReaderInterface(root)
    root.mainloop()