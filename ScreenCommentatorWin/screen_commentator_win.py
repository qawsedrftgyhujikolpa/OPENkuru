"""
Screen Commentator Win V2
ニコニコ風画面コメントオーバーレイ（絶対動くシンプル版）
"""

import base64
import io
import json
import os
import random
import re
import queue
import time
import threading
from dataclasses import dataclass
from typing import Any
import tkinter as tk

import mss
from PIL import Image
try:
    from dotenv import load_dotenv, set_key
    load_dotenv()
except ImportError:
    load_dotenv = None
    set_key = None

# ==========================================
# 1. シンプルな設定
# ==========================================
# ==========================================
# 1. シンプルな設定
# ==========================================
CFG = {
    # 役割別設定
    # ── 画像解析 (Vision) ──
    "vision_nvidia_model": "google/gemma-3-4b-it",   # 4b 級で爆速ｗ
    "use_vision_nvidia": True,                        # NVIDIAクラウド解析を使うかどうか
    "vision_local_model": "qwen2.5-vl:3b",            # ローカル解析用モデル
    "use_vision_local": False,                         # ローカル解析：デフォルト OFF
    
    # ── 実況生成 (Talker) ──
    "talker_nvidia_model": "google/gemma-3-4b-it",   # 4b 級で爆速ｗ
    "use_talker_nvidia": True,                        # NVIDIA実況を使うか
    "talker_local_model": "qwen2.5:0.5b",             # ローカル実況用（超軽量！ｗ）
    "use_talker_local": False,                         # ローカル実況：デフォルト OFF
    
    # ── 記憶要約 (Memory) ──
    "memory_nvidia_model": "google/gemma-3-4b-it",   # 4b 級で爆速ｗ
    "use_memory_nvidia": True,                        # NVIDIA記憶を使うか
    "memory_local_model": "qwen2.5:1.5b",             # ローカル記憶用
    "use_memory_local": False,                         # ローカル記憶：デフォルト OFF

    # ── 接続先 ──
    "host": "https://integrate.api.nvidia.com/v1/chat/completions",  # NVIDIA NIM エンドポイント
    "ollama_host": "http://127.0.0.1:11434/api/chat",                # Ollama ローカルサーバー
    "api_key": os.getenv("NVIDIA_API_KEY") or "",          # 環境変数から優先読み込みｗ
    "interval_sec": 1.5,    # 実況の間隔（秒）
    "nvidia_count": 5,      # NVIDIA 実況者の人数（1〜10）
    "ollama_count": 3,      # Ollama 実況者の人数（0〜5）
    
    # ── 画質設定 ──
    "vision_max_width": 448,   # 解析時の最大横幅（px）
    "vision_jpeg_quality": 65, # JPEG 圧縮率 (1-95)
    
    # ── カスタムプロンプト ──
    "talker_instruction": "今の状況に対して、あなたの属性らしく短いニコニコ風のツッコミを1〜2個考えて。",
    
    # ── 表示設定 ──
    "font_family": "Meiryo UI",
    "font_size": 24,
    "lanes": 15,         # 弾幕レーン数
    "lane_gap": 45,      # レーン間隔（ピクセル）
    "top_margin": 80,    # 上端余白
    "fps": 40,           # アニメーションFPS
    "transparent_color": "#000100"  # 透過色（この色が透明になる）
}

# ==========================================
# 2. NVIDIA & Ollama AI 連携 (Hybrid System)
# ==========================================
def ask_nvidia_nim(messages: list[dict], model: str) -> str:
    """NVIDIA NIM にリクエストを投げる汎用関数よ！ｗ"""
    import urllib.request
    if not CFG["api_key"]: return ""
    
    # リクエストデータを JSON で組み立てるわ！ｗ
    data = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.7,    # 創造性パラメータ（高いほど多彩なレスポンス）
        "max_tokens": 300      # 応答の最大トークン数
    }).encode("utf-8")
    
    req = urllib.request.Request(
        CFG["host"],
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {CFG['api_key']}"
        }
    )
    
    try:
        # タイムアウトを120秒に延長！ｗ 不安定なNVIDIAを救うわ！ｗ
        with urllib.request.urlopen(req, timeout=120) as res:
            resp_data = json.loads(res.read().decode("utf-8"))
            return resp_data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[NVIDIAエラー] {model}: {e}")
        return ""

def ask_ollama(messages: list[dict], model: str) -> str:
    """ローカル Ollama にリクエストを投げるわよ！戻ってきたわねｗ"""
    import urllib.request
    data = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False       # ストリーミングOFF（一括応答）
    }).encode("utf-8")
    
    req = urllib.request.Request(
        CFG["ollama_host"],
        data=data,
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            resp_data = json.loads(res.read().decode("utf-8"))
            return resp_data["message"]["content"]
    except Exception as e:
        msg = str(e)
        # 404 エラーの場合はモデル未インストールの可能性が高いわよ！ｗ
        if "404" in msg:
            print(f"[Ollamaエラー] 404 Not Found! モデル '{model}' を pull したか確認してね！ｗ")
        else:
            print(f"[Ollamaエラー] {model}: {e}")
        return ""

def vision_analyze(img_b64: str) -> str:
    """映像解析エージェント：今の状況を言語化！ｗ"""
    msgs = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "今の画面で何が起きているか、スコアや動きを110文字以内で客観的に。"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
        ]
    }]
    # 有効なモデルを使うわよ！両方ONならLocal優先ｗ
    if CFG["use_vision_local"]:
        return ask_ollama(msgs, CFG["vision_local_model"])
    if CFG["use_vision_nvidia"]:
        return ask_nvidia_nim(msgs, CFG["vision_nvidia_model"])
    return "解析がすべてOFFよ！ｗ"

def talker_shout(situation: str, history_summary: str, personality: str, provider: str = "nvidia") -> list[str]:
    """実況者エージェント：属性に合わせたツッコミ生成！ｗ"""
    # システムプロンプト：実況者のキャラ設定
    system_prompt = (
        f"あなたはニコニコ実況者『{personality}』です。属性を守り、絶対にタメ口・ネットスラングのみで実況して。"
        "返信は、純粋な JSON 配列のみを出力してください。"
    )
    # ユーザープロンプト：状況と指示を渡す
    user_prompt = (
        f"【状況】: {situation}\n【過去の流れ】: {history_summary}\n"
        f"【指示】: {CFG['talker_instruction']}"
    )
    msgs = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
    
    # プロバイダーに応じて NVIDIA or Ollama に投げる
    if provider == "nvidia":
        text = ask_nvidia_nim(msgs, CFG["talker_nvidia_model"])
    else:
        text = ask_ollama(msgs, CFG["talker_local_model"])
    
    # JSON 配列を抽出する処理ｗ
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1:
        try:
            parsed = json.loads(text[start:end+1])
            if isinstance(parsed, list): return [str(s) for s in parsed]
        except: pass
    # JSON パース失敗時はダブルクォート内のテキストを抽出ｗ
    matches = re.findall(r'"([^"]+)"', text)
    return [m for m in matches if len(m) < 50]

def update_memory(new_situation: str, new_comments: list[str], old_history: str) -> str:
    """記憶エージェント：10ターンの文脈を整理！ｗ"""
    prompt = (
        "実況の流れを統合し、次の実況に役立つ『あらすじ』を150文字以内で更新して。"
        f"【旧】: {old_history}\n【今】: {new_situation}\n【出たコメント】: {', '.join(new_comments)}"
    )
    msgs = [{"role": "user", "content": prompt}]
    
    # Local 優先、なければ NVIDIA、両方 OFF なら旧履歴を返すｗ
    if CFG["use_memory_local"]:
        return ask_ollama(msgs, CFG["memory_local_model"])
    if CFG["use_memory_nvidia"]:
        return ask_nvidia_nim(msgs, CFG["memory_nvidia_model"])
    return old_history

# 弾幕の色リスト（白多め＋たまにカラフルｗ）
COLORS = ["#ffffff", "#ffffff", "#ffffff", "#ffffaa", "#aaffff", "#aaffaa", "#ffaaff", "#ffaaaa"]

@dataclass
class CommentItem:
    """弾幕1個分のデータ"""
    text_id: int           # テキストの Canvas ID
    shadow_id: int | None  # 影の Canvas ID
    speed: float           # 移動速度
    color: str             # 文字色
    is_rainbow: bool       # 虹色アニメーションするかどうか

# ==========================================
# 3. メインアプリ（Tkinter）
# ==========================================
import concurrent.futures

# 15人の実況者の豪華属性ｗ
PERSONALITIES = [
    "熱血実況者", "冷静な分析家", "煽り全開のネット民", "癒やし系ボイス", 
    "古参ニコ厨", "絶叫ゲーマー", "ポエム系女子", "毒舌な批評家",
    "メタ発言の神", "伝説の予言者", "ガチ勢の解説", "迷い込んだ初心者",
    "AI信者", "AI否定派", "ただの暇人"
]

class SimpleCommentator:
    """メインの弾幕オーバーレイアプリケーション"""
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Screen Commentator V2 (Ensemble Cloud)")
        self.root.overrideredirect(True)       # ウィンドウ枠を消す
        self.root.attributes("-topmost", True)  # 最前面に表示
        
        bg_color = CFG["transparent_color"]
        self.root.configure(bg=bg_color)
        self.root.attributes("-transparentcolor", bg_color)  # この色を透明にする
        
        # Windows の拡張スタイル：クリック透過＋レイヤー化
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00000020 | 0x00080000)
        except: pass
            
        # 透明キャンバス（ここに弾幕を描画する）
        self.canvas = tk.Canvas(self.root, bg=bg_color, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 画面サイズを取得ｗ
        with mss.mss() as sct:
            mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            self.width = mon["width"]
            self.height = mon["height"]
            left = mon["left"]
            top = mon["top"]
            
        self.root.geometry(f"{self.width}x{self.height}+{left}+{top}")
        self.comments: list[CommentItem] = []  # 画面上の弾幕リスト
        self.msg_queue = queue.Queue()          # AI から来たメッセージのキュー
        self.lane_idx = 0                       # 次に使うレーン番号
        self.is_fetching = False                # AI 問い合わせ中フラグ
        self.history_summary = "実況開始。まだ何も起きていないわ。ｗ"  # 10ターンの記憶ｗ
        
        print(f"[V2] アンサンブルシステム起動！ (画面: {self.width}x{self.height})")
        
        # 各種ループを起動！ｗ
        self.root.after(100, self.fetch_loop)                  # AI に聞くループ
        self.root.after(200, self.drain_queue)                 # キューから弾幕を生成するループ
        self.root.after(int(1000/CFG["fps"]), self.animate)    # アニメーションループ
        self.root.after(1000, self.keep_on_top)                # 最前面維持ループ

    def keep_on_top(self):
        """ウィンドウを最前面に維持するわよ！ｗ"""
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(2000, self.keep_on_top)

    def fetch_loop(self):
        """AI に画面を見せてコメントを取得するループ"""
        if not self.is_fetching:
            self.is_fetching = True
            threading.Thread(target=self._worker, daemon=True).start()
        else:
            self.root.after(1000, self.fetch_loop)

    def _worker(self):
        """バックグラウンドワーカー：画面撮影 → 解析 → 実況 → 記憶 の全工程を実行！ｗ"""
        try:
            # ── 1. 画面をキャプチャして縮小 ──
            with mss.mss() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                sct_img = sct.grab(mon)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            max_w = int(CFG.get("vision_max_width", 448))
            ratio = max_w / float(img.size[0])
            img = img.resize((max_w, int(img.size[1]*ratio)), Image.Resampling.LANCZOS)
            buf = io.BytesIO(); img.save(buf, format="JPEG", quality=int(CFG.get("vision_jpeg_quality", 65)))
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            
            # ── 2. 映像解析（Vision Master）──
            print("[AI] 映像解析中 (NVIDIA)...")
            situation = vision_analyze(b64)
            if not situation: situation = "画面が暗転しているか、解析に失敗したわ。ｗ"
            print(f"[状況] {situation}")

            # ── 3. ハイブリッド実況者を並列召喚！ ──
            nv_active = bool(CFG["use_talker_nvidia"])
            ol_active = bool(CFG["use_talker_local"])
            nv_count = int(CFG["nvidia_count"]) if nv_active else 0
            ol_count = int(CFG["ollama_count"]) if ol_active else 0
            total_count = nv_count + ol_count
            
            print(f"[AI] 合計{total_count}人の実況チーム出撃！ (NVIDIA:{nv_count}人, Local:{ol_count}人)")
            if total_count == 0:
                print("[警告] 実況者が一人もいないわよ！有効化チェックボックスを確認して！ｗ")
                return

            start_t = time.time()
            all_comments = []
            
            # ランダムに属性を割り当てるｗ
            active_personalities = random.sample(PERSONALITIES, min(total_count, len(PERSONALITIES)))
            nv_team = active_personalities[:nv_count]
            ol_team = active_personalities[nv_count:nv_count + ol_count]

            # 並列処理で全員同時に実況させる！！ｗｗｗ
            with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, total_count)) as executor:
                futures = []
                for p in nv_team:
                    futures.append(executor.submit(talker_shout, situation, self.history_summary, p, "nvidia"))
                for p in ol_team:
                    futures.append(executor.submit(talker_shout, situation, self.history_summary, p, "ollama"))

                for future in concurrent.futures.as_completed(futures):
                    try:
                        res = future.result()
                        if res: all_comments.extend(res)
                    except Exception as e:
                        print(f"[実行エラー] {e}")

            if all_comments:
                print(f"[AI] 合計{len(all_comments)}件の弾幕獲得！ ({time.time()-start_t:.1f}s)")
                random.shuffle(all_comments)
                for r in all_comments: self.msg_queue.put(r)
                
                # ── 4. 記憶の更新（The Chronicler）──
                print("[AI] 記憶整理中...")
                self.history_summary = update_memory(situation, all_comments, self.history_summary)
            else:
                print("[AI] 誰も喋らないわね...みんな寝てるのかしら？ｗ")
                
        finally:
            self.is_fetching = False
            self.root.after(int(CFG["interval_sec"] * 1000), self.fetch_loop)

    def drain_queue(self):
        """キューからメッセージを取り出して弾幕を生成するｗ"""
        try:
            msg = self.msg_queue.get_nowait()
            self.spawn_text(msg)
        except queue.Empty: pass
        # キューが多ければ速く、少なければゆっくり消化ｗ
        delay = 300 if self.msg_queue.qsize() < 5 else 100
        self.root.after(delay, self.drain_queue)

    def spawn_text(self, text: str):
        """弾幕テキストを画面に出現させるわよ！ｗ"""
        lane = self.lane_idx % CFG["lanes"]; self.lane_idx += 1
        y = CFG["top_margin"] + (lane * CFG["lane_gap"])
        fs = CFG["font_size"] + random.randint(-4, 8)  # フォントサイズにバラつきｗ
        font = (CFG["font_family"], fs, "bold")
        is_rainbow = random.random() < 0.05  # 5%の確率で虹色弾幕！ｗ
        color = random.choice(COLORS) if not is_rainbow else "#ff0000"
        x = self.width + 100  # 画面右端の外から登場
        # 影（黒いテキスト）を先に描くことで立体感を出すｗ
        shadow_id = self.canvas.create_text(x + 2, y + 2, text=text, fill="#111111", font=font, anchor=tk.NW)
        text_id = self.canvas.create_text(x, y, text=text, fill=color, font=font, anchor=tk.NW)
        speed = 3.5 + (len(text) * 0.1) + (fs / 15.0) + random.uniform(-0.5, 0.5)
        self.comments.append(CommentItem(text_id, shadow_id, speed, color, is_rainbow))

    def animate(self):
        """全弾幕を左に動かすアニメーションループ"""
        remains = []
        for c in self.comments:
            self.canvas.move(c.text_id, -c.speed, 0)
            if c.shadow_id: self.canvas.move(c.shadow_id, -c.speed, 0)
            coords = self.canvas.coords(c.text_id)
            if not coords or coords[0] < -1000:
                # 画面外に出たら削除するわ！ｗ
                self.canvas.delete(c.text_id)
                if c.shadow_id: self.canvas.delete(c.shadow_id)
                continue
            # 虹色アニメーション（HSV 色相を時間で回転させる）
            if c.is_rainbow:
                hue = (time.time() * 2.0) % 1.0
                from colorsys import hsv_to_rgb
                r, g, b = hsv_to_rgb(hue, 1.0, 1.0)
                hx = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
                self.canvas.itemconfig(c.text_id, fill=hx)
            remains.append(c)
        self.comments = remains
        self.root.after(int(1000/CFG["fps"]), self.animate)

class StartupDialog:
    """起動時の設定ダイアログ：全てをここで決めるのよ！ｗｗｗ"""
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("NVIDIA & Ollama 究極ハイブリッド V2 + モデルガイド")
        self.root.geometry("950x750")  # ガイドパネル分を横に広げたわ！ｗ
        self.root.eval('tk::PlaceWindow . center')
        
        # 保存済み API キーを読み込むわよ！ｗ
        saved_key = self.load_key()
        if saved_key: CFG["api_key"] = saved_key

        # 左右のメインフレームｗ
        main_frame = tk.Frame(self.root); main_frame.pack(fill="both", expand=True)
        left_f = tk.Frame(main_frame, padx=20, pady=10); left_f.pack(side="left", fill="both", expand=True)
        right_f = tk.Frame(main_frame, padx=20, pady=10, bg="#f0f0f0", relief="sunken", borderwidth=1); right_f.pack(side="right", fill="both")

        def row_label(parent, text, fg="black"):
            """設定項目のラベルを作るヘルパー関数ｗ"""
            l = tk.Label(parent, text=text, font=(CFG["font_family"], 9, "bold"), fg=fg)
            l.pack(pady=(10, 0), anchor="w")
            return l

        # =====================================
        # --- 左側：設定入力 ---
        # =====================================
        
        # 1. NVIDIA API Key
        row_label(left_f, "1. NVIDIA API Key:", "#76b900")
        self.key_entry = tk.Entry(left_f, width=60, show="*"); self.key_entry.insert(0, CFG["api_key"]); self.key_entry.pack()

        # 1.5 Ollama Host URL（復活！ｗ）
        row_label(left_f, "1.5 Ollama Host URL:", "#ff9900")
        self.ol_host_entry = tk.Entry(left_f, width=60); self.ol_host_entry.insert(0, CFG["ollama_host"]); self.ol_host_entry.pack()

        # 2. 画像解析 NVIDIA
        row_label(left_f, "2. 画像解析 (NVIDIA):", "#76b900")
        f2 = tk.Frame(left_f); f2.pack(anchor="w")
        self.v_nv_check = tk.BooleanVar(value=CFG["use_vision_nvidia"])
        tk.Checkbutton(f2, text="有効化", variable=self.v_nv_check).pack(side="left")
        self.v_nv_entry = tk.Entry(f2, width=35); self.v_nv_entry.insert(0, CFG["vision_nvidia_model"]); self.v_nv_entry.pack(side="left", padx=5)

        # 3. 画像解析 Local
        row_label(left_f, "3. 画像解析 (Local):", "#ff9900")
        f3 = tk.Frame(left_f); f3.pack(anchor="w")
        self.v_l_check = tk.BooleanVar(value=CFG["use_vision_local"])
        tk.Checkbutton(f3, text="有効化", variable=self.v_l_check).pack(side="left")
        self.v_l_entry = tk.Entry(f3, width=35); self.v_l_entry.insert(0, CFG["vision_local_model"]); self.v_l_entry.pack(side="left", padx=5)

        # 4. 実況 NVIDIA（人数設定付き！ｗ）
        row_label(left_f, "4. 実況生成 (NVIDIA):", "#76b900")
        f4 = tk.Frame(left_f); f4.pack(anchor="w")
        self.t_nv_check = tk.BooleanVar(value=CFG["use_talker_nvidia"])
        tk.Checkbutton(f4, text="有効", variable=self.t_nv_check).pack(side="left")
        self.t_nv_entry = tk.Entry(f4, width=30); self.t_nv_entry.insert(0, CFG["talker_nvidia_model"]); self.t_nv_entry.pack(side="left", padx=5)
        self.t_nv_count = tk.Entry(f4, width=3); self.t_nv_count.insert(0, str(CFG["nvidia_count"])); self.t_nv_count.pack(side="left"); tk.Label(f4, text="人").pack(side="left")

        # 5. 実況 Local（人数設定付き！ｗ）
        row_label(left_f, "5. 実況生成 (Local):", "#ff9900")
        f5 = tk.Frame(left_f); f5.pack(anchor="w")
        self.t_l_check = tk.BooleanVar(value=CFG["use_talker_local"])
        tk.Checkbutton(f5, text="有効", variable=self.t_l_check).pack(side="left")
        self.t_l_entry = tk.Entry(f5, width=30); self.t_l_entry.insert(0, CFG["talker_local_model"]); self.t_l_entry.pack(side="left", padx=5)
        self.t_l_count = tk.Entry(f5, width=3); self.t_l_count.insert(0, str(CFG["ollama_count"])); self.t_l_count.pack(side="left"); tk.Label(f5, text="人").pack(side="left")

        # 6. 記憶 NVIDIA
        row_label(left_f, "6. 記憶要約 (NVIDIA):", "#76b900")
        f6 = tk.Frame(left_f); f6.pack(anchor="w")
        self.m_nv_check = tk.BooleanVar(value=CFG["use_memory_nvidia"])
        tk.Checkbutton(f6, text="有効化", variable=self.m_nv_check).pack(side="left")
        self.m_nv_entry = tk.Entry(f6, width=35); self.m_nv_entry.insert(0, CFG["memory_nvidia_model"]); self.m_nv_entry.pack(side="left", padx=5)

        # 7. 記憶 Local
        row_label(left_f, "7. 記憶要約 (Local):", "#ff9900")
        f7 = tk.Frame(left_f); f7.pack(anchor="w")
        self.m_l_check = tk.BooleanVar(value=CFG["use_memory_local"])
        tk.Checkbutton(f7, text="有効化", variable=self.m_l_check).pack(side="left")
        self.m_l_entry = tk.Entry(f7, width=35); self.m_l_entry.insert(0, CFG["memory_local_model"]); self.m_l_entry.pack(side="left", padx=5)
        
        # --- 実況プロンプト指示（カスタマイズ可能！ｗ）---
        row_label(left_f, "実況への追加指示（もっと詳しく、等）:", "#0066ff")
        self.inst_entry = tk.Entry(left_f, width=60)
        self.inst_entry.insert(0, str(CFG["talker_instruction"]))
        self.inst_entry.pack(pady=2)

        # --- 画質設定（軽量化用ｗ） ---
        f_img = tk.Frame(left_f); f_img.pack(fill="x", pady=5)
        tk.Label(f_img, text="解析画質(横px):", font=(CFG["font_family"], 9, "bold")).pack(side="left")
        self.v_w_entry = tk.Entry(f_img, width=6); self.v_w_entry.insert(0, str(CFG["vision_max_width"])); self.v_w_entry.pack(side="left", padx=5)
        tk.Label(f_img, text="JPEG品質(1-95):", font=(CFG["font_family"], 9, "bold")).pack(side="left", padx=(10,0))
        self.v_q_entry = tk.Entry(f_img, width=6); self.v_q_entry.insert(0, str(CFG["vision_jpeg_quality"])); self.v_q_entry.pack(side="left", padx=5)

        # --- 間隔設定 ---
        row_label(left_f, "実況間隔 (秒):")
        self.interval_entry = tk.Entry(left_f, width=10); self.interval_entry.insert(0, str(CFG["interval_sec"])); self.interval_entry.pack(anchor="w", padx=20)

        # --- 始動ボタン！！ｗ ---
        tk.Button(left_f, text="究極実況 始動！！", font=(CFG["font_family"], 12, "bold"), 
                  bg="#ff4400", fg="white", command=self.start, width=30).pack(pady=20)

        # =====================================
        # --- 右側：モデル推奨ガイドｗ ---
        # =====================================
        tk.Label(right_f, text="【推奨: 4b以下の爆速モデル】", font=(CFG["font_family"], 11, "bold"), bg="#f0f0f0").pack(pady=5)
        
        guide_txt = tk.Text(right_f, width=45, height=35, font=("Consolas", 9), bg="#ffffff", relief="flat")
        guide_txt.insert("end", "--- NVIDIA NIM (Cloud) ---\n")
        guide_txt.insert("end", "[Vision/Talker/Memory]\n- google/gemma-3-4b-it (爆速!)\n- google/gemma-3-1b-it (最速!)\n- qwen/qwen2.5-7b-instruct (精鋭)\n")
        guide_txt.insert("end", "※ Qwenは現在2.5が最新よ！ｗ\n\n")
        guide_txt.insert("end", "--- Ollama (Local) ---\n")
        guide_txt.insert("end", "[Vision]\n- qwen2.5-vl:3b\n\n")
        guide_txt.insert("end", "[Talker - 超軽量!]\n- qwen2.5:0.5b\n- qwen2.5:1.5b\n- gemma2:2b\n\n")
        guide_txt.insert("end", "※タイムアウト(Timeout)が出る場合は、\n  4b以下の最軽量モデルを試してね！ｗ")
        guide_txt.config(state="disabled")
        guide_txt.pack()

        self.started = False

    def load_key(self):
        """保存済み NVIDIA キーを読み込む"""
        try:
            if os.path.exists(".nvidia_key"):
                with open(".nvidia_key", "r") as f: return f.read().strip()
        except: pass
        return ""

    def save_key(self, key):
        """NVIDIA キーをファイルに保存"""
        try:
            with open(".nvidia_key", "w") as f: f.write(key)
        except: pass
        
    def save_key(self, key: str):
        if not key: return
        # .env ファイルに保存するわ！これぞプロの流儀！ｗ
        env_path = os.path.join(os.getcwd(), ".env")
        if set_key:
            try:
                set_key(env_path, "NVIDIA_API_KEY", key)
                print(f"[保存完了] キーが .env に刻まれたわよ！ｗ ({env_path})")
            except Exception as e:
                print(f"[保存失敗] .env への保存に失敗しちゃったｗ: {e}")
        else:
            # 代替手段として従来の .nvidia_key も残しておくわねｗ
            with open(".nvidia_key", "w") as f: f.write(key)
            print("[警告] python-dotenv が無かったから .nvidia_key に保存したわｗ")

    def load_key(self) -> str:
        # .env (環境変数) から優先的に読み込むわよ！ｗ
        k = os.getenv("NVIDIA_API_KEY")
        if k: return k
        if os.path.exists(".nvidia_key"):
            with open(".nvidia_key", "r") as f: return f.read().strip()
        return ""

    def start(self):
        """始動ボタンが押されたら全設定を CFG に反映して起動！ｗ"""
        CFG["api_key"] = self.key_entry.get().strip()
        CFG["ollama_host"] = self.ol_host_entry.get().strip()
        
        CFG["vision_nvidia_model"] = self.v_nv_entry.get().strip()
        CFG["use_vision_nvidia"] = self.v_nv_check.get()
        CFG["vision_local_model"] = self.v_l_entry.get().strip()
        CFG["use_vision_local"] = self.v_l_check.get()
        
        CFG["talker_nvidia_model"] = self.t_nv_entry.get().strip()
        CFG["use_talker_nvidia"] = self.t_nv_check.get()
        CFG["talker_local_model"] = self.t_l_entry.get().strip()
        CFG["use_talker_local"] = self.t_l_check.get()
        
        CFG["memory_nvidia_model"] = self.m_nv_entry.get().strip()
        CFG["use_memory_nvidia"] = self.m_nv_check.get()
        CFG["memory_local_model"] = self.m_l_entry.get().strip()
        CFG["use_memory_local"] = self.m_l_check.get()

        try:
            nv_c = self.t_nv_count.get().strip()
            ol_c = self.t_l_count.get().strip()
            iv_s = self.interval_entry.get().strip()
            v_w = self.v_w_entry.get().strip()
            v_q = self.v_q_entry.get().strip()
            
            if nv_c: CFG["nvidia_count"] = max(1, min(10, int(nv_c)))
            if ol_c: CFG["ollama_count"] = max(0, min(5, int(ol_c)))
            if iv_s: CFG["interval_sec"] = max(0.1, float(iv_s))
            if v_w: CFG["vision_max_width"] = max(128, min(1024, int(v_w))) # 下限128px
            if v_q: CFG["vision_jpeg_quality"] = max(1, min(95, int(v_q)))
            
            CFG["talker_instruction"] = self.inst_entry.get().strip()
        except Exception as e:
            print(f"[設定エラー] 入力値が不正よ！デフォルト値を使うわねｗ: {e}")

        print(f"[設定完了] NVIDIA:{CFG['nvidia_count']}人({CFG['use_talker_nvidia']}), Local:{CFG['ollama_count']}人({CFG['use_talker_local']}), 画質:{CFG['vision_max_width']}px/Q{CFG['vision_jpeg_quality']}")

        # せめて解析の1つは ON にしないとダメよ！ｗ
        if not any([CFG["use_vision_nvidia"], CFG["use_vision_local"]]):
            from tkinter import messagebox
            messagebox.showwarning("警告", "せめて解析のどれかはONにして！ｗｗｗ")
            return
        
        self.save_key(CFG["api_key"])
        self.started = True
        self.root.destroy()

if __name__ == "__main__":
    dialog = StartupDialog()
    dialog.root.mainloop()
    if dialog.started:
        app = SimpleCommentator()
        app.root.mainloop()

# =============================================================================
# 初心者向け：このプログラムの仕組み
# =============================================================================
# 1. 【画面を撮る】：448pxに縮小してAIの負荷を極限まで減らしています。ｗ
# 2. 【AI に聞く】：NVIDIA NIM（クラウド）と Ollama（ローカル）のハイブリッドｗ
# 3. 【画面に流す】：Tkinterの透明キャンバスでニコニコ風にコメントを流します。ｗ
# 4. 【記憶する】：10ターン分の文脈を AI が要約して次の実況に活かしますｗ
# 5. 【設定画面】：全 7 項目の ON/OFF と人数を自由にカスタマイズ可能ｗ
