// 1. 初始化 JVM 参数输入框
const savedJvm = localStorage.getItem('jvmdata') || '[]';
document.getElementById('jvmset').value = savedJvm;

// 2. 基础 API 请求封装
const API_BASE = 'http://localhost:5000';


async function status() {
    try {
        const res = await fetch(`${API_BASE}/mcapi/status`);
        return await res.json();
    } catch (e) {
        return "后端连接失败";
    }
}

async function jvmset(dt) {
    await fetch(`${API_BASE}/mcapi/jvmarg_set`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(dt)
    });
}

// 3. 事件监听 (JVM 输入框失焦保存)
document.getElementById('jvmset').onblur = async (e) => {
    const val = e.target.value;
    localStorage.setItem('jvmdata', val);
    try {
        const parsed = JSON.parse(val);
        if (!Array.isArray(parsed)) throw new Error();
        await jvmset(parsed);
    } catch (err) {
        alert("参数必须是合法的 JSON 数组，例如: [\"-Xmx4G\"]");
    }
}

// 4. 状态轮询 (只查状态，别再发 JVM 参数了！)
setInterval(async () => {
    document.getElementById("status").innerText = await status();
}, 1000); // 改成 1000 毫秒，别把后端干碎了

