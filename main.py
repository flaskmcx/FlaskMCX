import os
import sys
import logging
import json
import subprocess as s
import pyperclip as clip
import threading as thr

import flask
import minecraft_launcher_lib as mc
import mcauth3
from flask_cors import CORS


# ================= 核心路径处理 =================
def get_resource_path(relative_path):
    """ 获取打包后内部资源的绝对路径 """
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        # 用 sys.argv[0] 获取当前运行的 main.py 的绝对路径
        base_path = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(base_path, relative_path)


def get_executable_dir():
    """ 获取 exe 所在的真实目录 (用于写数据) """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.abspath(".")


# 获取真实数据目录，所有的存档、token都在 exe 旁边
DATA_DIR = get_executable_dir()
MC_LOCAL_DIR = os.path.join(DATA_DIR, "mc")

app = flask.Flask(__name__)
# 注意：原版启动器的 .minecraft 目录依然放在系统默认位置
mc_dir = mc.utils.get_minecraft_directory()
CORS(app)

logging.getLogger("werkzeug").setLevel(logging.ERROR)

status_ = "无操作"
jvmArg = []

# --- 目录与文件初始化 ---
if not os.path.exists(MC_LOCAL_DIR):
    os.makedirs(MC_LOCAL_DIR)

NAME_FILE = os.path.join(MC_LOCAL_DIR, "name.txt")
TOKEN_FILE = os.path.join(MC_LOCAL_DIR, "token.json")

if not os.path.isfile(NAME_FILE):
    with open(NAME_FILE, "w", encoding="utf-8") as f:
        f.write("Player")

if not os.path.isfile(TOKEN_FILE):
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)

# --- 进度条回调 ---
progress: int = 0
mx: int = 0
st: str = ""


def Progress(p):
    global progress, status_
    progress = p
    status_ = str(progress - 1) + " / " + str(mx) + " : " + st + f" ({(progress - 1) / max(mx, 1) * 100:.1f}%)"


def Mx(v):
    global mx
    mx = v


def St(v):
    global st, status_
    st = v
    status_ = str(progress - 1) + " / " + str(mx) + " : " + st + f" ({(progress - 1) / max(mx, 1) * 100:.1f}%)"


# --- 启动线程 (核心逻辑) ---
def launch_task(v, n):
    print("当前 JVM 参数:", jvmArg, type(jvmArg))

    uuid = "00000000-0000-0000-0000-000000000000"
    access_token = "00000000-0000-0000-0000-000000000000"
    user_type = "legacy"  # 默认离线模式

    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            token_data = json.load(f)

        if token_data.get("refresh_token"):
            print("检测到正版缓存，正在静默刷新 Token...")
            auth = mcauth3.MCMSA()
            res = auth.refresh_auth(token_data["refresh_token"])

            token_data = {
                "access_token": res['tokens']['minecraft_access_token'],
                "refresh_token": res['tokens']['microsoft_refresh_token'],
                "uuid": res['profile']['id'],
                "name": res['profile']['name']
            }
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump(token_data, f)

            n = token_data["name"]
            uuid = token_data["uuid"]
            access_token = token_data["access_token"]
            user_type = "msa"
            print("Token 刷新成功，当前玩家:", n)

    except Exception as e:
        print("刷新 Token 失败或未登录，将以离线模式启动:", e)

    options = {
        "username": n,
        "uuid": uuid,
        "accessToken": access_token,
        "userType": user_type,
    }

    if jvmArg:
        try:
            options["jvmArguments"] = json.loads(jvmArg) if isinstance(jvmArg, str) else jvmArg
        except Exception as e:
            print("JVM 参数解析失败，使用默认参数:", e)

    try:
        c = mc.command.get_minecraft_command(v, mc_dir, options)
        print("即将执行命令:", c)

        p = s.Popen(c, cwd=mc_dir, stdout=s.PIPE, stderr=s.STDOUT, text=True, bufsize=1)

        def read_logs(proc):
            for line in iter(proc.stdout.readline, ''):
                if line:
                    print("[Java Log]", line.strip())

        thr.Thread(target=read_logs, args=(p,), daemon=True).start()

    except Exception as e:
        global status_
        status_ = "启动失败: " + str(e)
        print("启动失败:", e)


# --- Flask 路由 ---
@app.route('/')
def index():
    # 修复：使用 get_resource_path 定位前端文件
    web_path = get_resource_path(os.path.join("data", "web", "index.html"))
    if not os.path.exists(web_path):
        return f"致命错误：找不到网页文件。当前尝试路径: {web_path}", 404
    return flask.send_file(web_path)

@app.route('/mcapi/launch', methods=['POST'])
def launch():
    global status_
    v = flask.request.get_json().get('version')
    n = ''
    try:
        with open(NAME_FILE, "r", encoding="utf-8") as f:
            n = f.read().strip()
    except:
        return flask.jsonify("error: name not found")

    status_ = "正在启动，Java日志已输出到Python控制台"
    thr.Thread(target=launch_task, args=(v, n), daemon=True).start()
    return flask.jsonify("success launching " + v)


@app.route('/mcapi/install', methods=['POST'])
def install():
    global status_
    v = flask.request.get_json().get('version')

    def install_task(version):
        global status_
        try:
            status_ = "开始安装 " + version
            mc.install.install_minecraft_version(version, mc_dir, callback={
                "setProgress": Progress,
                "setMax": Mx,
                "setStatus": St
            })
            status_ = "安装成功: " + version
        except Exception as e:
            status_ = "安装失败: " + str(e)

    thr.Thread(target=install_task, args=(v,), daemon=True).start()
    return flask.jsonify("installing " + v)


@app.route('/mcapi/nickname', methods=['POST'])
def nickname():
    n = flask.request.get_json().get('name')
    with open(NAME_FILE, "w", encoding="utf-8") as f:
        f.write(n)
    return flask.jsonify("success name:" + n)


@app.route('/mcapi/status', methods=['GET'])
def status():
    return flask.jsonify(status_)


@app.route('/mcapi/jvmarg_set', methods=["POST"])
def jvmARGSet():
    global status_, jvmArg
    jvmArg = flask.request.get_json()
    status_ = "已保存 JVM 数据！"
    return flask.jsonify("success")


# --- 正版验证路由 ---
auth = mcauth3.MCMSA()
dinfo = None


@app.route('/mcauth/start', methods=["POST"])
def mcauth():
    global status_, dinfo
    status_ = "正版验证中，请前往浏览器"
    try:
        dinfo = auth.start_auth()
        return flask.jsonify({"url": dinfo["verification_uri"], "code": dinfo["user_code"]})
    except Exception as e:
        return flask.jsonify({"error": str(e)}), 500


@app.route('/mcauth/succ', methods=["POST"])
def mcauthSucc():
    global status_, dinfo
    try:
        res = auth.finish_auth(dinfo)

        with open(NAME_FILE, "w", encoding="utf-8") as f:
            f.write(res['profile']['name'])

        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "access_token": res['tokens']['minecraft_access_token'],
                "refresh_token": res['tokens']['microsoft_refresh_token'],
                "uuid": res['profile']['id'],
                "name": res['profile']['name']
            }, f)

        status_ = "正版验证成功！"
        return flask.jsonify({"status": "success", "name": res['profile']['name']})
    except Exception as e:
        status_ = "验证失败: " + str(e)
        return flask.jsonify({"status": "error", "msg": str(e)}), 500

@app.route('/mcauth/get', methods=["GET"])
def getData():
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        try:
            d = json.load(f)
            # 如果字典里有 refresh_token 和 name，说明登录过
            if d.get("refresh_token") and d.get("name"):
                return flask.jsonify({"logged_in": True, "name": d["name"]})
            else:
                return flask.jsonify({"logged_in": False})
        except json.JSONDecodeError:
            return flask.jsonify({"logged_in": False})


if __name__ == '__main__':
    # 1. 启动 Flask 服务（放在后台）
    thr.Thread(target=lambda: app.run(host='127.0.0.1', port=5000, debug=False)).start()

    # 2. 复制链接
    clip.copy("http://127.0.0.1:5000")
    print("请自行打开浏览器，网页已自动复制链接")

    # 3. 为了防止服务刚启动浏览器打不开，这里可以加个延时打开，或者你可以用 pywebview
    import webbrowser
    import time

    time.sleep(1)
    webbrowser.open("http://127.0.0.1:5000")