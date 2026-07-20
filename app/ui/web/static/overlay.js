const container = document.getElementById("chat-container");
const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
const ws = new WebSocket(protocol + "//" + window.location.host + "/api/chat/ws");

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);

    // 1. Обновление ID сообщения
    if (data.action === "update_id") {
        const el = document.getElementById("msg-" + data.old_id);
        if (el) {
            el.id = "msg-" + data.new_id;
        }
        return;
    }

    // 2. Локальное удаление сообщения модератором
    if (data.action === "delete") {
        const el = document.getElementById("msg-" + data.msg_id);
        if (el) {
            el.style.opacity = "0.35";
            const textEl = el.querySelector(".text-content");
            if (textEl) {
                textEl.innerHTML = "<i>&lt;сообщение удалено модератором&gt;</i>";
            }
        }
        return;
    }

    // 3. Блокировка/таймаут пользователя
    if (data.action === "ban_user") {
        const authorClass = "author-" + data.username.toLowerCase();
        const elements = document.getElementsByClassName(authorClass);
        for (let el of elements) {
            el.style.opacity = "0.35";
            const textEl = el.querySelector(".text-content");
            if (textEl) {
                textEl.innerHTML = "<i>&lt;сообщение удалено модератором&gt;</i>";
            }
        }
        return;
    }

    // 4. Обычное сообщение
    const msg = data;

    if (document.getElementById("msg-" + msg.id)) {
        return;
    }

    const box = document.createElement("div");
    box.id = "msg-" + msg.id;

    const authorClass = msg.author ? "author-" + msg.author.name.toLowerCase() : "author-anon";
    box.className = "message-box platform-" + msg.platform + " " + authorClass;

    let badgesHtml = "";
    if (msg.author && msg.author.badges) {
        msg.author.badges.forEach(b => {
            badgesHtml += `<span class="badge badge-${b}">${b}</span>`;
        });
    }

    const platformLabel = `<span style="font-size:10px; opacity:0.6; text-transform:uppercase; margin-right:5px;">[${msg.platform}]</span>`;

    box.innerHTML = `
        <div>
            ${platformLabel}
            ${badgesHtml}
            <span class="author-name" style="color: ${msg.platform === 'twitch' ? '#cba6f7' : '#89b4fa'}">${msg.author ? msg.author.name : 'Аноним'}</span>:
            <span class="text-content">${escapeHTML(msg.text)}</span>
        </div>
    `;

    container.appendChild(box);

    if (container.children.length > 25) {
        container.removeChild(container.firstChild);
    }

    // Плавное скрытие сообщений через 30 секунд
    setTimeout(() => {
        if (box.parentNode) {
            box.style.transition = "opacity 0.5s ease";
            box.style.opacity = "0";
            setTimeout(() => { if (box.parentNode) box.remove(); }, 500);
        }
    }, 30000);
};

function escapeHTML(str) {
    return str.replace(/[&<>'"]/g,
        tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
}
