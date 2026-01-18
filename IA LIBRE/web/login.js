// handles register/login and token storage
const AUTH = {
  token: localStorage.getItem("ia_liber_token") || null,
  setToken(t) { this.token = t; localStorage.setItem("ia_liber_token", t); },
  clear() { this.token = null; localStorage.removeItem("ia_liber_token"); }
};

document.addEventListener("DOMContentLoaded", () => {
  const authPanel = document.getElementById("authPanel");
  const chatPanel = document.getElementById("chatPanel");
  const regBtn = document.getElementById("regBtn");
  const loginBtn = document.getElementById("loginBtn");
  const logoutBtn = document.getElementById("logoutBtn");
  const newConvBtn = document.getElementById("newConvBtn");
  const convList = document.getElementById("convList");

  function showChat() {
    authPanel.style.display = "none";
    chatPanel.style.display = "flex";
    loadConversations();
  }
  function showAuth() {
    authPanel.style.display = "block";
    chatPanel.style.display = "none";
  }

  regBtn.onclick = async () => {
    const user = document.getElementById("reg_user").value;
    const pass = document.getElementById("reg_pass").value;
    const res = await fetch("/api/register", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({username:user,password:pass})});
    const j = await res.json();
    alert(j.msg || JSON.stringify(j));
  };

  loginBtn.onclick = async () => {
    const user = document.getElementById("login_user").value;
    const pass = document.getElementById("login_pass").value;
    const res = await fetch("/api/login", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({username:user,password:pass})});
    if (!res.ok) {
      const t = await res.json().catch(()=>({detail:res.statusText}));
      alert("Error: " + (t.detail || "login failed"));
      return;
    }
    const j = await res.json();
    AUTH.setToken(j.access_token);
    showChat();
  };

  logoutBtn.onclick = () => { AUTH.clear(); showAuth(); };

  async function loadConversations() {
    convList.innerHTML = "";
    const res = await fetch("/api/conversations", { headers: { "Authorization": "Bearer " + AUTH.token }});
    if (!res.ok) { console.error("failed to load convs"); return; }
    const j = await res.json();
    j.conversations.forEach(c => {
      const li = document.createElement("li");
      li.textContent = `${c.title} (${c.id})`;
      li.dataset.id = c.id;
      li.onclick = () => selectConversation(c.id);
      convList.appendChild(li);
    });
  }

  newConvBtn.onclick = async () => {
    const res = await fetch("/api/conversations", { method: "POST", headers: { "Authorization": "Bearer " + AUTH.token, "Content-Type": "application/json"}, body: JSON.stringify({title: "New conv"})});
    // fallback: reload list
    loadConversations();
  };

  function selectConversation(id) {
    window.currentConv = id;
    document.getElementById("chat").innerHTML = "";
    // fetch messages
    fetch(`/api/conversations/${id}/messages`, { headers: { "Authorization": "Bearer " + AUTH.token }})
      .then(r => r.json())
      .then(j => {
        const chat = document.getElementById("chat");
        j.messages.forEach(m => {
          const b = document.createElement("div");
          b.className = "msg " + m.role;
          b.textContent = m.content;
          chat.appendChild(b);
        });
      });
  }

  // If token present, go to chat
  if (AUTH.token) showChat(); else showAuth();
});