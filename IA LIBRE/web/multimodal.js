// web/multimodal.js
// Example routines to upload files + message to /api/multimodal and handle SSE streaming

async function sendMultimodal(message, files, authToken) {
  const form = new FormData();
  form.append("message", message);
  files.forEach(f => {
    // f: File object; pick field name by type
    if (f.type.startsWith("image/")) form.append("images", f, f.name);
    else if (f.type.startsWith("audio/")) form.append("audios", f, f.name);
    else form.append("images", f, f.name); // fallback
  });

  const resp = await fetch("/api/multimodal", {
    method: "POST",
    headers: {
      "Authorization": "Bearer " + authToken
    },
    body: form
  });
  if (!resp.ok) {
    const err = await resp.json().catch(()=>({detail: resp.statusText}));
    console.error("Error", err);
    return;
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while(true) {
    const {done, value} = await reader.read();
    if (done) break;
    buf += decoder.decode(value, {stream: true});
    let parts = buf.split("\n\n");
    buf = parts.pop();
    for (const p of parts) {
      if (!p.startsWith("data:")) continue;
      const payload = p.replace(/^data:\s*/, "");
      try {
        const obj = JSON.parse(payload);
        if (obj.type === "token") {
          // append token to assistant bubble in UI
          appendAssistantText(obj.text);
        } else if (obj.type === "blocked") {
          alert("Blocked: " + obj.reasons.join(", "));
        } else if (obj.type === "error") {
          console.error("Error from server:", obj.message);
        }
      } catch (e) {
        console.warn("parse error", e);
      }
    }
  }
}