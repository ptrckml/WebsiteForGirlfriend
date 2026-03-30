const state = JSON.parse(document.getElementById("initial-state").textContent);
const session = { authenticated: false };
const elements = {
  pageContent: document.getElementById("pageContent"),
  toolbarSubtitle: document.getElementById("toolbarSubtitle"),
  ownerToggle: document.getElementById("ownerToggle"),
  newPostButton: document.getElementById("newPostButton"),
  logoutButton: document.getElementById("logoutButton"),
  editAboutButton: document.getElementById("editAboutButton"),
  authDialog: document.getElementById("authDialog"),
  authForm: document.getElementById("authForm"),
  authTitle: document.getElementById("authTitle"),
  authDescription: document.getElementById("authDescription"),
  authMessage: document.getElementById("authMessage"),
  authCancel: document.getElementById("authCancel"),
  editorDialog: document.getElementById("editorDialog"),
  editorForm: document.getElementById("editorForm"),
  editorTitle: document.getElementById("editorTitle"),
  editorMessage: document.getElementById("editorMessage"),
  editorCancel: document.getElementById("editorCancel"),
  aboutDialog: document.getElementById("aboutDialog"),
  aboutForm: document.getElementById("aboutForm"),
  aboutMessage: document.getElementById("aboutMessage"),
  aboutCancel: document.getElementById("aboutCancel"),
};

init();

async function init() {
  attachEvents();
  render();
  await refreshSession();
  render();
}

function attachEvents() {
  elements.ownerToggle.addEventListener("click", openAuthDialog);
  elements.authCancel.addEventListener("click", () => closeModal(elements.authDialog));
  elements.editorCancel.addEventListener("click", () => closeModal(elements.editorDialog));
  elements.aboutCancel.addEventListener("click", () => closeModal(elements.aboutDialog));
  elements.logoutButton.addEventListener("click", logout);
  elements.newPostButton.addEventListener("click", () => openEditor());
  elements.editAboutButton.addEventListener("click", openAboutEditor);

  elements.authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(elements.authForm);
    const endpoint = state.ownerConfigured ? "/api/login" : "/api/setup";
    elements.authMessage.textContent = "";
    const result = await api(endpoint, "POST", { password: form.get("password") });
    if (!result.ok) {
      elements.authMessage.textContent = result.error || "Could not sign in.";
      return;
    }
    state.ownerConfigured = true;
    elements.authForm.reset();
    closeModal(elements.authDialog);
    await refreshSession();
    render();
  });

  elements.editorForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(elements.editorForm);
    const postId = form.get("post_id");
    const payload = {
      category: form.get("category"),
      title: form.get("title"),
      content: form.get("content"),
    };
    elements.editorMessage.textContent = "";
    const result = await api(postId ? `/api/posts/${postId}` : "/api/posts", postId ? "PUT" : "POST", payload);
    if (!result.ok) {
      elements.editorMessage.textContent = result.error || "Could not save that post.";
      return;
    }
    upsertPost(result.post);
    elements.editorForm.reset();
    closeModal(elements.editorDialog);
    if (state.page !== "home" && state.page !== result.post.category) {
      window.location.href = `/page/${result.post.category}`;
      return;
    }
    render();
  });

  elements.aboutForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(elements.aboutForm);
    elements.aboutMessage.textContent = "";
    const result = await api("/api/about", "POST", { about_text: form.get("about_text") });
    if (!result.ok) {
      elements.aboutMessage.textContent = result.error || "Could not save your about page.";
      return;
    }
    state.aboutText = result.aboutText;
    elements.aboutForm.reset();
    closeModal(elements.aboutDialog);
    render();
  });
}

async function refreshSession() {
  try {
    const result = await api("/api/session", "GET");
    session.authenticated = Boolean(result.authenticated);
  } catch (error) {
    session.authenticated = false;
    elements.toolbarSubtitle.textContent = "The site loaded, but the server connection is having trouble.";
  }
}

function render() {
  elements.newPostButton.classList.toggle("hidden", !session.authenticated || state.page === "about");
  elements.logoutButton.classList.toggle("hidden", !session.authenticated);
  elements.editAboutButton.classList.toggle("hidden", !session.authenticated || state.page !== "about");
  elements.toolbarSubtitle.textContent = session.authenticated
    ? "You are logged in as the site owner."
    : " ";
  if (state.page === "about") return renderAboutPage();
  if (state.focusedPost) return renderPostDetail(state.focusedPost);
  renderPostList();
}

function renderAboutPage() {
  const copy = state.aboutText.trim() ? escapeHtml(state.aboutText) : "Write your own introduction here once you log in.";
  elements.pageContent.innerHTML = `<article class="about-sheet"><h3 class="about-title">About Me</h3><p class="about-body">${copy.replace(/\n/g, "<br>")}</p></article>`;
}

function renderPostList() {
  const posts = state.page === "home" ? [...state.posts] : state.posts.filter((post) => post.category === state.page);
  if (!posts.length) {
    elements.pageContent.innerHTML = `<section class="empty-state"><h3 class="about-title">Nothing here yet</h3><p>Start filling this page with your own notes when you're ready.</p></section>`;
    return;
  }
  const intro = state.page === "home"
    ? `<section class="about-sheet"><h3 class="about-title">Latest Posts</h3><p class="about-body">Your newest entries across every page appear here first.</p></section>`
    : "";
  const cards = posts.map((post) => `
    <a class="post-card" href="/post/${post.id}">
      <h3 class="post-title">${escapeHtml(post.title)}</h3>
      <p class="post-meta">${escapeHtml(categoryLabel(post.category))} · ${formatDate(post.updated_at)}</p>
      <p class="post-preview">${escapeHtml(snippet(post.content))}</p>
    </a>`).join("");
  elements.pageContent.innerHTML = `${intro}<section class="post-grid">${cards}</section>`;
}

function renderPostDetail(post) {
  elements.pageContent.innerHTML = `
    <article class="post-detail">
      <section class="about-sheet">
        <h3 class="post-title">${escapeHtml(post.title)}</h3>
        <p class="post-meta">${escapeHtml(categoryLabel(post.category))} · Updated ${formatDate(post.updated_at)}</p>
        <p class="post-body">${escapeHtml(post.content).replace(/\n/g, "<br>")}</p>
      </section>
      ${session.authenticated ? '<div class="post-actions"><button class="secondary danger" id="deleteCurrentPost" type="button">Delete Post</button><button class="primary" id="editCurrentPost" type="button">Edit Post</button></div>' : ""}
    </article>`;
  const editButton = document.getElementById("editCurrentPost");
  if (editButton) editButton.addEventListener("click", () => openEditor(post));
  const deleteButton = document.getElementById("deleteCurrentPost");
  if (deleteButton) deleteButton.addEventListener("click", () => removePost(post));
}

function openAuthDialog() {
  elements.authForm.reset();
  elements.authMessage.textContent = "";
  elements.authTitle.textContent = state.ownerConfigured ? "Owner Access" : "Create Owner Access";
  elements.authDescription.textContent = state.ownerConfigured
    ? "Log in to create or edit posts."
    : "Create your owner password. Only you will use this to edit the site.";
  openModal(elements.authDialog);
}

window.__softPagesOwnerAccess = openAuthDialog;

function openEditor(post) {
  elements.editorForm.reset();
  elements.editorMessage.textContent = "";
  elements.editorTitle.textContent = post ? "Edit Post" : "New Post";
  elements.editorForm.elements.post_id.value = post ? String(post.id) : "";
  elements.editorForm.elements.category.value = post ? post.category : (state.page !== "home" && state.page !== "about" ? state.page : "movies-tv-shows");
  elements.editorForm.elements.title.value = post ? post.title : "";
  elements.editorForm.elements.content.value = post ? post.content : "";
  openModal(elements.editorDialog);
}

function openAboutEditor() {
  elements.aboutForm.reset();
  elements.aboutMessage.textContent = "";
  elements.aboutForm.elements.about_text.value = state.aboutText || "";
  openModal(elements.aboutDialog);
}

async function logout() {
  await api("/api/logout", "POST");
  session.authenticated = false;
  render();
}

async function removePost(post) {
  const confirmed = window.confirm(`Delete "${post.title}"? This cannot be undone.`);
  if (!confirmed) return;
  const result = await api(`/api/posts/${post.id}`, "DELETE");
  if (!result.ok) {
    window.alert(result.error || "Could not delete that post.");
    return;
  }
  state.posts = state.posts.filter((item) => item.id !== post.id);
  state.focusedPost = null;
  window.location.href = post.category === state.page ? `/page/${post.category}` : "/";
}

function upsertPost(post) {
  const index = state.posts.findIndex((item) => item.id === post.id);
  if (index >= 0) state.posts[index] = post;
  else state.posts.unshift(post);
  state.focusedPost = post;
}

function categoryLabel(slug) {
  const item = state.categories.find((category) => category.slug === slug);
  return item ? item.label : slug;
}

function snippet(text) {
  const trimmed = text.trim();
  return trimmed.length > 160 ? `${trimmed.slice(0, 157)}...` : trimmed;
}

function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function escapeHtml(value) {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

function openModal(dialog) {
  if (typeof dialog.showModal === "function") {
    try {
      dialog.showModal();
      return;
    } catch (error) {
      if (dialog.open) return;
    }
  }
  dialog.setAttribute("open", "");
}

function closeModal(dialog) {
  if (typeof dialog.close === "function") {
    try {
      dialog.close();
      return;
    } catch (error) {
      if (!dialog.open) return;
    }
  }
  dialog.removeAttribute("open");
}

async function api(url, method, body) {
  const options = { method, headers: {} };
  if (body) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch (error) {
    data = { error: "The server returned an unexpected response." };
  }
  return { ok: response.ok, ...data };
}
