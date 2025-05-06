import os
import socket
from app import create_app, db, socketio
from app.models.danmu import Danmu
from app.models.video import Video
from app.models.author import Author

app = create_app()

@app.shell_context_processor
def make_shell_context():
    return {
        'db': db,
        'Video': Video,
        'Danmu': Danmu,
        'Author': Author
    }

def find_free_port(start_port=5000, max_port=5999):
    """查找可用端口"""
    for port in range(start_port, max_port + 1):
        try:
            # 尝试绑定端口
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port))
                return port
        except OSError:
            continue
    raise OSError("找不到可用的端口")

if __name__ == '__main__':
    app.run(port=5000, debug=True)