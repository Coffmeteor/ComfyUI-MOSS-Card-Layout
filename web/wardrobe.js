import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

let catalogPromise;
function catalog() {
    return catalogPromise ??= api.fetchApi("/moss-card/wardrobe").then(async response => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Wardrobe catalog unavailable");
        return data.entries;
    }).catch(error => { catalogPromise = null; throw error; });
}
const thumbnail = id => api.apiURL(`/moss-card/wardrobe/${encodeURIComponent(id)}/thumbnail`);
function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text) el.textContent = text;
    return el;
}

function browse(entries, current, choose) {
    const dialog = element("dialog", "moss-wardrobe-dialog");
    dialog.setAttribute("aria-label", "Choose wardrobe");
    const header = element("header");
    header.append(element("h2", "", "Choose your outfit"));
    const close = element("button", "", "Close");
    close.onclick = () => dialog.close();
    header.append(close);
    const controls = element("div", "moss-wardrobe-controls");
    const search = element("input");
    search.placeholder = "Search dresses, lace, mint, floral…";
    search.setAttribute("aria-label", "Search wardrobe");
    const category = element("select");
    category.setAttribute("aria-label", "Wardrobe category");
    for (const name of ["All categories", ...new Set(entries.map(e => e.category))]) {
        const option = element("option", "", name);
        option.value = name === "All categories" ? "" : name;
        category.append(option);
    }
    controls.append(search, category);
    const filters = element("div", "moss-wardrobe-filters");
    const selected = new Set();
    for (const family of ["Garment", "Color", "Material", "Detail"]) {
        const row = element("div", "moss-wardrobe-filter-row");
        row.append(element("strong", "", family));
        const tags = [...new Set(entries.flatMap(e => e.facets[family]))].sort();
        for (const tag of tags) {
            const chip = element("button", "moss-wardrobe-chip", tag);
            chip.setAttribute("aria-pressed", "false");
            chip.onclick = () => {
                selected.has(tag) ? selected.delete(tag) : selected.add(tag);
                chip.setAttribute("aria-pressed", String(selected.has(tag)));
                page = 0; render();
            };
            row.append(chip);
        }
        filters.append(row);
    }
    const clear = element("button", "", "Clear filters");
    clear.onclick = () => { selected.clear(); search.value = ""; category.value = "";
        filters.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", "false")); page = 0; render(); };
    controls.append(clear);
    const status = element("p", "moss-wardrobe-status");
    status.setAttribute("role", "status");
    const grid = element("div", "moss-wardrobe-grid");
    const footer = element("footer");
    const previous = element("button", "", "Previous page");
    const next = element("button", "", "Next page");
    footer.append(previous, next);
    let page = 0;
    function render() {
        const words = search.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
        const filtered = entries.filter(entry => (!category.value || entry.category === category.value)
            && [...selected].every(tag => entry.tags.includes(tag))
            && words.every(word => `${entry.label} ${entry.tags} ${entry.category} ${entry.keywords} ${entry.description}`.toLowerCase().includes(word)));
        const pages = Math.max(1, Math.ceil(filtered.length / 60));
        page = Math.min(page, pages - 1);
        status.textContent = `${filtered.length} outfits · Page ${page + 1} of ${pages} · Click a picture to use it`;
        grid.replaceChildren();
        for (const entry of filtered.slice(page * 60, (page + 1) * 60)) {
            const button = element("button", "moss-wardrobe-outfit");
            button.setAttribute("aria-label", `Wear ${entry.label}`);
            button.setAttribute("aria-pressed", String(entry.id === current));
            button.title = entry.description;
            const image = element("img");
            image.loading = "lazy";
            image.src = thumbnail(entry.id);
            image.alt = entry.label;
            button.append(image, element("strong", "", entry.label));
            const chips = element("div", "moss-wardrobe-card-tags");
            for (const tag of [...entry.facets.Garment.slice(0, 1), ...entry.facets.Color.slice(0, 2), ...entry.facets.Material.slice(0, 1), ...entry.facets.Detail.slice(0, 2)]) chips.append(element("span", "", tag));
            button.append(chips);
            button.onclick = () => { choose(entry.id); dialog.close(); };
            grid.append(button);
        }
        previous.disabled = page === 0;
        next.disabled = page + 1 >= pages;
        grid.scrollTop = 0;
    }
    search.oninput = category.onchange = () => { page = 0; render(); };
    previous.onclick = () => { page--; render(); };
    next.onclick = () => { page++; render(); };
    dialog.append(header, controls, filters, status, grid, footer);
    dialog.addEventListener("close", () => dialog.remove(), { once: true });
    document.body.append(dialog);
    render();
    dialog.showModal();
    search.focus();
}

function install(node) {
    const selection = node.widgets.find(widget => widget.name === "outfit_id");
    if (!selection || node.mossWardrobeRefresh) return;
    selection.type = "converted-widget";
    selection.hidden = true;
    selection.draw = () => {};
    selection.computeSize = () => [0, -4];
    const root = element("div", "moss-wardrobe-preview");
    const imageButton = element("button", "moss-wardrobe-current");
    imageButton.setAttribute("aria-label", "Browse wardrobe from preview");
    const image = element("img");
    imageButton.append(image);
    const label = element("strong");
    const description = element("p");
    const button = element("button", "", "Browse Wardrobe");
    const actions = element("div", "moss-wardrobe-actions");
    const previous = element("button", "", "← Previous");
    const next = element("button", "", "Next →");
    actions.append(previous, button, next);
    root.append(imageButton, label, description, actions);
    root.addEventListener("pointerdown", event => event.stopPropagation());
    root.addEventListener("wheel", event => event.stopPropagation());
    let sequence = 0;
    async function refresh() {
        const ticket = ++sequence;
        const id = String(selection.value || "").trim().toUpperCase();
        label.textContent = "Loading outfit…";
        image.hidden = true;
        try {
            const entries = await catalog();
            if (ticket !== sequence) return;
            const entry = entries.find(e => e.id === id);
            if (!entry) throw new Error("Select an outfit from the wardrobe");
            label.textContent = entry.label;
            image.alt = entry.label;
            image.src = thumbnail(id);
            image.hidden = false;
            description.textContent = entry.description;
        } catch (error) { if (ticket === sequence) description.textContent = error.message; }
    }
    image.onerror = () => { image.hidden = true; description.textContent = "Preview image unavailable. Check the downloaded gallery files."; };
    function choose(id) {
        selection.value = id;
        selection.callback?.(id);
        node.graph?.change();
        node.setDirtyCanvas(true, true);
    }
    async function open() {
        try { browse(await catalog(), String(selection.value).toUpperCase(), choose); }
        catch (error) { description.textContent = error.message; }
    }
    async function step(delta) {
        try {
            const entries = await catalog();
            const index = entries.findIndex(e => e.id === String(selection.value).trim().toUpperCase());
            choose(entries[(index + delta + entries.length) % entries.length].id);
        } catch (error) { description.textContent = error.message; }
    }
    imageButton.onclick = button.onclick = open;
    previous.onclick = () => step(-1);
    next.onclick = () => step(1);
    const originalCallback = selection.callback;
    selection.callback = function (...args) { originalCallback?.apply(this, args); refresh(); };
    const widget = node.addDOMWidget("wardrobe_preview", "custom", root, {
        serialize: false, hideOnZoom: false, getHeight: () => 390,
    });
    widget.computeSize = width => [width, 390];
    node.mossWardrobeRefresh = refresh;
    const originalConfigure = node.onConfigure;
    node.onConfigure = function (...args) { originalConfigure?.apply(this, args); refresh(); };
    node.setSize([Math.max(520, node.size[0]), Math.max(630, node.size[1])]);
    refresh();
}

app.registerExtension({
    name: "Mio.MOSS.WardrobePreview",
    setup() {
        const stylesheet = element("link");
        stylesheet.rel = "stylesheet";
        stylesheet.href = new URL("./wardrobe.css", import.meta.url).href;
        document.head.append(stylesheet);
    },
    nodeCreated(node) { if (node.comfyClass === "MOSSFourViewWardrobeCard") install(node); },
    loadedGraphNode(node) { node.mossWardrobeRefresh?.(); },
});
