import yt_dlp
import subprocess
import pyaudio
import sys

def PlayBilibili(URL):
    # 1. ========== 设置 (Settings) ==========
    BILI_URL = URL  # 使用您的链接

    PYAUDIO_FORMAT = pyaudio.paInt16
    CHANNELS = 2
    RATE = 48000
    CHUNK_SIZE = 4096

    # 2. ========== 使用 yt-dlp 获取音频流直链和Headers ==========
    print(f"正在从 {BILI_URL} 获取音频信息...")

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(BILI_URL, download=False)
            audio_url = info['url']
            video_title = info.get('title', '未知标题')

            # ========== [关键修改 1] ==========
            # 获取 yt-dlp 提供的 HTTP Headers
            http_headers = info.get('http_headers')
            print(f"成功获取到音频流: {video_title}")

    except Exception as e:
        print(f"错误：无法获取音频流。请检查链接是否有效或网络连接。")
        print(f"详细错误: {e}")
        sys.exit(1)

    # 3. ========== 设置并启动 FFmpeg 进程 ==========
    print("正在启动 FFmpeg 进行实时转码...")

    # ========== [关键修改 2] ==========
    # 构建 FFmpeg 命令，并添加 Headers 参数
    ffmpeg_command = [
        'ffmpeg',
        # 如果有headers，则添加headers参数
        *(['-headers', '\r\n'.join(f'{key}: {value}' for key, value in http_headers.items())] if http_headers else []),
        '-i', audio_url,
        '-f', 's16le',
        '-ar', str(RATE),
        '-ac', str(CHANNELS),
        '-loglevel', 'error',
        'pipe:1'
    ]

    # 打印最终的ffmpeg命令（用于调试）
    # print("FFmpeg command:", " ".join(ffmpeg_command))

    # 将 FFmpeg 的 stderr 也连接到管道，以便捕获错误信息
    ffmpeg_process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # 4. ========== 初始化 PyAudio 并打开音频流 ==========
    # ... (这部分代码和原来一样，无需修改)
    print("正在初始化本地音频播放器 (PyAudio)...")
    p = pyaudio.PyAudio()

    try:
        stream = p.open(
            format=PYAUDIO_FORMAT,
            channels=CHANNELS,
            rate=RATE,
            output=True,
            frames_per_buffer=CHUNK_SIZE
        )
    except Exception as e:
        print("错误：无法打开PyAudio音频流。请检查你的音频设备是否正常。")
        print(f"详细错误: {e}")
        ffmpeg_process.kill()
        p.terminate()
        sys.exit(1)

    # 5. ========== 读取FFmpeg输出并写入PyAudio进行播放 ==========
    print(f"\n▶️  正在播放: {video_title}")
    print("按 Ctrl+C 停止播放。")

    try:
        while True:
            raw_audio = ffmpeg_process.stdout.read(CHUNK_SIZE)
            if not raw_audio:
                break
            stream.write(raw_audio)

    except KeyboardInterrupt:
        print("\n用户中断播放。")
    finally:
        # 6. ========== 清理资源 ==========
        print("正在停止播放并清理资源...")

        # 检查FFmpeg是否有错误输出
        ffmpeg_errors = ffmpeg_process.stderr.read().decode('utf-8', errors='ignore')
        if ffmpeg_errors:
            print("\n--- FFmpeg 错误信息 ---")
            print(ffmpeg_errors)
            print("------------------------\n")

        stream.stop_stream()
        stream.close()
        p.terminate()

        ffmpeg_process.terminate()
        try:
            ffmpeg_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            ffmpeg_process.kill()
            print("FFmpeg 进程被强制终止。")

        print("播放结束。")
