// chat sending + streaming handling
document.addEventListener("DOMContentLoaded", () => {
  const sendBtn = document.getElementById("sendBtn");
  const messageInput = document.getElementById("message");
  const chatEl = document.getElementById("chat");
  const AUTH = { token: localStorage.getItem("ia_liber_token") };

  function addBubble(role, text) {
    const d = document.createElement("div");
    d.className = "msg " + role;
    d.textContent = text;
    chatEl.appendChild(d);
    chatEl.scrollTop = chatEl.scrollHeight;
    return d;
  }

  sendBtn.onclick = async () => {
    const text = messageInput.value.trim();
    if (!text) return;
    addBubble("user", text);
    messageInput.value = "";
    // send to /api/chat
    const conv_id = window.currentConv || null;
    try {
      const resp = await fetch("/api/chat", { method: "POST", headers: { "Authorization": "Bearer " + AUTH.token, "Content-Type": "application/json" }, body: JSON.stringify({ message: text, conversation_id: conv_id })});
      if (!resp.ok) {
        const err = await resp.json().catch(()=>({detail:resp.statusText}));
        addBubble("system", "Error: " + (err.detail || "server error"));
        return;
      }
      // streaming
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      const assistantBubble = addBubble("assistant", "");
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let parts = buf.split("\n\n");
        buf = parts.pop();
        for (const p of parts) {
          if (!p.startsWith("data:")) continue;
          const payload = p.replace(/^data:\s*/, "");
          try {
            const obj = JSON.parse(payload);
            if (obj.type === "token") {
              assistantBubble.textContent += obj.text;
            } else if (obj.type === "blocked") {
              assistantBubble.textContent = "Blocked: " + (obj.reasons||[]).join(",");
            }
          } catch (e) {
            console.warn("parse error", e);
          }
        }
      }
    } catch (e) {
      addBubble("system", "Connection error: " + String(e));
    }
  };
});