(function () {
  const NODE_WIDTH = 236;
  const NODE_HEIGHT = 120;
  const COLUMN_WIDTH = 264;
  const BASE_COLORS = ["#f0b75e", "#9a4e3f", "#6a8fb3", "#758b54", "#d78b52", "#476c8a"];
  const TIER_COLORS = {9: "#f6b04d", 6: "#8ea8c3", 3: "#7a8d4e"};
  const viewport = document.getElementById("viewport");
  const frozenPane = document.querySelector(".frozen-pane");
  const frozenContent = document.getElementById("frozenContent");
  const scrollPane = document.getElementById("scrollPane");
  const scrollContent = document.getElementById("scrollContent");
  const emptyState = document.getElementById("emptyState");
  const tooltip = document.getElementById("tooltip");
  const statusLabel = document.getElementById("statusLabel");
  const frozenSelection = d3.select(frozenContent);
  const scrollSelection = d3.select(scrollContent);
  let currentGraphData = { nodes: [], reserved_regions: [], grid_mode: false, document_title: "(╯°□°)╯︵ ┻━┻ Blue Bench" };
  let tooltipTimer = null;

  function logEvent(eventName, payload) {
    console.debug(eventName, payload);
  }

  function updateGraph(data) {
    currentGraphData = data || { nodes: [], reserved_regions: [], grid_mode: false, document_title: "(╯°□°)╯︵ ┻━┻ Blue Bench" };
    logEvent("layout_received", {
      node_count: Array.isArray(currentGraphData.nodes) ? currentGraphData.nodes.length : 0,
      grid_mode: Boolean(currentGraphData.grid_mode),
    });
    render();
  }

  function setLayout() {}
  function focusNode() {}

  function getNodeMap() {
    return new Map((currentGraphData.nodes || []).map((node) => [String(node.id), node]));
  }

  function getRootAncestor(node, nodeMap) {
    let current = node;
    let guard = 0;
    while (current && current.parent_id && nodeMap.has(String(current.parent_id)) && guard < 1000) {
      const parent = nodeMap.get(String(current.parent_id));
      if (!parent || parent.column === 0) {
        return parent || current;
      }
      current = parent;
      guard += 1;
    }
    return current || node;
  }

  function hashCode(text) {
    let hash = 0;
    for (let index = 0; index < text.length; index += 1) {
      hash = ((hash << 5) - hash) + text.charCodeAt(index);
      hash |= 0;
    }
    return hash;
  }

  function hexToRgb(hex) {
    const clean = hex.replace("#", "");
    const value = parseInt(clean, 16);
    return {
      r: (value >> 16) & 255,
      g: (value >> 8) & 255,
      b: value & 255,
    };
  }

  function lighten(hex, factor) {
    const rgb = hexToRgb(hex);
    const mix = (channel) => Math.round(channel + ((255 - channel) * factor));
    return `rgb(${mix(rgb.r)}, ${mix(rgb.g)}, ${mix(rgb.b)})`;
  }

  function getNodeColor(node, nodeMap) {
    const rootAncestor = getRootAncestor(node, nodeMap);
    const rootId = String(rootAncestor && rootAncestor.id ? rootAncestor.id : node.id);
    const base = BASE_COLORS[Math.abs(hashCode(rootId)) % BASE_COLORS.length];
    const relativeDepth = Math.max(0, Number(node.column || 0) - 1);
    return relativeDepth <= 0 ? base : lighten(base, Math.min(0.16 * relativeDepth, 0.45));
  }

  function escapeHtml(text) {
    return String(text)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  function scheduleTooltip(text) {
    clearTimeout(tooltipTimer);
    tooltipTimer = window.setTimeout(() => {
      tooltip.textContent = text;
      tooltip.style.display = "block";
    }, 220);
  }

  function moveTooltip(event) {
    tooltip.style.left = `${event.clientX + 14}px`;
    tooltip.style.top = `${event.clientY + 14}px`;
  }

  function hideTooltip() {
    clearTimeout(tooltipTimer);
    tooltip.style.display = "none";
  }

  function getVisibleRootNodes() {
    return (currentGraphData.nodes || [])
      .filter((node) => Number(node.column || 0) === 0)
      .slice()
      .sort((left, right) => {
        const yDiff = Number(left.y || 0) - Number(right.y || 0);
        if (yDiff !== 0) {
          return yDiff;
        }
        return String(left.name || left.id || "").localeCompare(String(right.name || right.id || ""));
      });
  }

  function handleKeyNavigation(event) {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) {
      return;
    }

    const key = event.key.toLowerCase();
    const scrollStep = 120;
    if (key === "w") {
      scrollPane.scrollTop -= scrollStep;
      event.preventDefault();
      return;
    }
    if (key === "s") {
      scrollPane.scrollTop += scrollStep;
      event.preventDefault();
      return;
    }
    if (key === "a") {
      scrollPane.scrollLeft -= scrollStep;
      event.preventDefault();
      return;
    }
    if (key === "d") {
      scrollPane.scrollLeft += scrollStep;
      event.preventDefault();
      return;
    }

    if (!/^[1-9]$/.test(event.key)) {
      return;
    }

    const roots = getVisibleRootNodes();
    const root = roots[Number(event.key) - 1];
    if (!root) {
      return;
    }

    if (window.graphBridge && typeof window.graphBridge.openRootExclusive === "function") {
      window.graphBridge.openRootExclusive(String(root.id));
      event.preventDefault();
    }
  }

  function createNodeElement(node) {
    const element = document.createElement("div");
    element.className = "node";
    element.dataset.nodeId = String(node.id);

    const header = document.createElement("div");
    header.className = "node-header";

    const strip = document.createElement("div");
    strip.className = "header-strip";
    header.appendChild(strip);

    const collapseButton = document.createElement("button");
    collapseButton.className = "node-button";
    collapseButton.textContent = "−";
    collapseButton.addEventListener("click", (event) => {
      event.stopPropagation();
      if (window.graphBridge && typeof window.graphBridge.collapseSubtree === "function") {
        window.graphBridge.collapseSubtree(String(element.dataset.nodeId));
      }
    });

    const title = document.createElement("div");
    title.className = "node-title";
    title.addEventListener("mouseenter", () => {
      scheduleTooltip(title.dataset.tooltip || title.textContent || "");
    });
    title.addEventListener("mouseleave", hideTooltip);
    title.addEventListener("mousemove", moveTooltip);

    const expandButton = document.createElement("button");
    expandButton.className = "node-button";
    expandButton.textContent = "+";
    expandButton.addEventListener("pointerdown", (event) => {
      event.stopPropagation();
      event.preventDefault();
      const payload = element._nodeData || {};
      if (payload.type === "file") {
        if (window.graphBridge && typeof window.graphBridge.openInspectorFromExplorer === "function") {
          window.graphBridge.openInspectorFromExplorer({
            file_path: String(payload.file_path || ""),
          });
        }
        return;
      }
      if (window.graphBridge && typeof window.graphBridge.expandNode === "function") {
        window.graphBridge.expandNode(String(element.dataset.nodeId));
      }
    });

    header.appendChild(collapseButton);
    header.appendChild(title);
    header.appendChild(expandButton);

    const body = document.createElement("div");
    body.className = "node-body";

    const indicatorRow = document.createElement("div");
    indicatorRow.className = "indicator-row";
    const tierBadge = document.createElement("div");
    tierBadge.className = "tier-badge";
    const tierDot = document.createElement("div");
    tierDot.className = "tier-dot";
    const tierLabel = document.createElement("span");
    tierBadge.appendChild(tierDot);
    tierBadge.appendChild(tierLabel);
    const tally = document.createElement("div");
    indicatorRow.appendChild(tierBadge);
    indicatorRow.appendChild(tally);

    const metadataPanel = document.createElement("div");
    metadataPanel.className = "metadata-panel";

    const loadMore = document.createElement("button");
    loadMore.className = "load-more";
    loadMore.textContent = "Load 25 More";
    loadMore.addEventListener("click", (event) => {
      event.stopPropagation();
      if (window.graphBridge && typeof window.graphBridge.loadMore === "function") {
        window.graphBridge.loadMore(String(element.dataset.nodeId));
      }
    });

    const metadataToggle = document.createElement("button");
    metadataToggle.className = "node-button";
    metadataToggle.textContent = "i";
    metadataToggle.style.alignSelf = "flex-end";
    metadataToggle.addEventListener("click", (event) => {
      event.stopPropagation();
      if (window.graphBridge && typeof window.graphBridge.toggleMetadata === "function") {
        window.graphBridge.toggleMetadata(String(element.dataset.nodeId));
      }
    });

    body.appendChild(indicatorRow);
    body.appendChild(metadataPanel);
    body.appendChild(loadMore);
    body.appendChild(metadataToggle);

    element.appendChild(header);
    element.appendChild(body);

    element._refs = {
      strip,
      collapseButton,
      title,
      expandButton,
      tierDot,
      tierLabel,
      tally,
      metadataPanel,
      loadMore,
    };
    return element;
  }

  function syncNodeElement(element, node, nodeMap) {
    const refs = element._refs;
    const tier = Number(node.compute_tier || 3);
    const hasChildren = Number(node.child_count || 0) > 0;
    const canExpand = node.type === "folder" && hasChildren;
    const hasMore = node.type === "folder" && Number(node.loaded_children || 0) < Number(node.child_count || 0);
    const left = Number(node.column || 0) === 0 ? 12 : (Number(node.x || 0) - COLUMN_WIDTH);

    element.dataset.nodeId = String(node.id);
    element._nodeData = {
      id: String(node.id),
      name: String(node.name || node.id || ""),
      type: String(node.type || ""),
      file_path: String(node.file_path || ""),
      line_number: node.line_number,
      parent_id: node.parent_id,
    };
    element.classList.toggle("is-header-only", !node.metadata_expanded);
    element.style.top = `${Number(node.y || 0)}px`;
    element.style.left = `${left}px`;
    element.style.width = `${Number(node.width || NODE_WIDTH)}px`;
    element.style.height = `${Number(node.height || NODE_HEIGHT)}px`;
    refs.strip.style.background = getNodeColor(node, nodeMap);
    refs.title.textContent = String(node.name || node.id);
    refs.title.dataset.tooltip = String(node.file_path || node.id || node.name || "");
    refs.title.classList.toggle("is-openable", node.type === "file");
    refs.collapseButton.disabled = !canExpand;
    refs.expandButton.disabled = node.type === "file" ? false : !canExpand;
    refs.expandButton.textContent = node.type === "file" ? ">" : "+";
    refs.tierDot.style.background = TIER_COLORS[tier] || TIER_COLORS[3];
    refs.tierLabel.textContent = `Tier ${tier}`;
    refs.tally.textContent = `Tally ${Number(node.compute_tally || 0)}`;
    if (!node.metadata_expanded) {
      refs.metadataPanel.scrollTop = 0;
    }
    const relationshipSummary = node.relationship_summary || {};
    const relationshipLines = [
      ["Calls", Number(relationshipSummary.calls || 0)],
      ["Imports", Number(relationshipSummary.imports || 0)],
      ["Called By", Number(relationshipSummary.called_by || 0)],
      ["Imported By", Number(relationshipSummary.imported_by || 0)],
    ]
      .filter(([, count]) => count > 0)
      .map(([label, count]) => `<div>${escapeHtml(label)}: ${count}</div>`)
      .join("");
    refs.metadataPanel.innerHTML = `
      <div>Type: ${escapeHtml(node.type || "")}</div>
      <div>Compute tier: ${tier}</div>
      <div>Compute tally: ${Number(node.compute_tally || 0)}</div>
      <div>Children: ${Number(node.child_count || 0)}</div>
      <div>Path: ${escapeHtml(node.file_path || node.id || "")}</div>
      ${relationshipLines}
    `;
    refs.loadMore.hidden = !hasMore;
  }

  function patchContainer(selection, nodes, nodeMap) {
    selection
      .selectAll(".node")
      .data(nodes, (node) => String(node.id))
      .join(
        (enter) => enter
          .append((node) => createNodeElement(node))
          .each(function (node) {
            syncNodeElement(this, node, nodeMap);
            logEvent("node_rendered", { id: node.id });
          }),
        (update) => update
          .each(function (node) {
            syncNodeElement(this, node, nodeMap);
            logEvent("node_updated", { id: node.id });
          }),
        (exit) => exit
          .each(function (node) {
            logEvent("node_removed", { id: node.id });
          })
          .remove()
      );
  }

  function syncFrozenPane() {
    frozenContent.style.transform = `translateY(${-scrollPane.scrollTop}px)`;
  }

  function render() {
    const nodes = Array.isArray(currentGraphData.nodes) ? currentGraphData.nodes : [];
    if (!nodes.length) {
      viewport.hidden = false;
      emptyState.hidden = true;
      statusLabel.hidden = true;
      frozenSelection.selectAll(".node").remove();
      scrollSelection.selectAll(".node").remove();
      frozenContent.style.height = `${scrollPane.clientHeight}px`;
      scrollContent.style.height = `${scrollPane.clientHeight}px`;
      scrollContent.style.width = `${scrollPane.clientWidth}px`;
      return;
    }

    viewport.hidden = false;
    emptyState.hidden = true;
    statusLabel.hidden = false;
    statusLabel.textContent = currentGraphData.grid_mode ? "Grid Fallback Active" : "Deterministic Layout";

    const nodeMap = getNodeMap();
    const frozenNodes = nodes.filter((node) => Number(node.column || 0) === 0);
    const scrollNodes = nodes.filter((node) => Number(node.column || 0) !== 0);
    patchContainer(frozenSelection, frozenNodes, nodeMap);
    patchContainer(scrollSelection, scrollNodes, nodeMap);

    const frozenHeight = Math.max(...frozenNodes.map((node) => Number(node.y || 0) + Number(node.height || NODE_HEIGHT)), 0) + 48;
    const scrollHeight = Math.max(...nodes.map((node) => Number(node.y || 0) + Number(node.height || NODE_HEIGHT)), 0) + 48;
    const scrollWidth = Math.max(...scrollNodes.map((node) => Number(node.x || 0) - COLUMN_WIDTH + Number(node.width || NODE_WIDTH)), 0) + 48;
    frozenContent.style.height = `${Math.max(frozenHeight, scrollPane.clientHeight)}px`;
    scrollContent.style.height = `${Math.max(scrollHeight, scrollPane.clientHeight)}px`;
    scrollContent.style.width = `${Math.max(scrollWidth, scrollPane.clientWidth)}px`;
    syncFrozenPane();
  }

  function exportCurrentView() {
    if (!window.graphBridge || typeof window.graphBridge.exportLayoutDocument !== "function") {
      return;
    }

    const documentHtml = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>${escapeHtml(currentGraphData.document_title || "(╯°□°)╯︵ ┻━┻ Blue Bench")}</title>
  <style>${document.querySelector("style").textContent}</style>
</head>
<body>${document.querySelector(".shell").outerHTML}</body>
</html>`;
    window.graphBridge.exportLayoutDocument(documentHtml);
  }

  function initializeBridge() {
    scrollPane.addEventListener("scroll", syncFrozenPane);
    if (frozenPane) {
      frozenPane.addEventListener("wheel", (event) => {
        scrollPane.scrollTop += event.deltaY;
        scrollPane.scrollLeft += event.deltaX;
        event.preventDefault();
      }, { passive: false });
    }
    window.addEventListener("resize", render);
    window.addEventListener("keydown", handleKeyNavigation);

    if (!window.qt || !window.qt.webChannelTransport) {
      render();
      return;
    }

    new QWebChannel(window.qt.webChannelTransport, (channel) => {
      window.graphBridge = channel.objects.graphBridge;
      window.graphBridge.sendGraph((data) => updateGraph(data));
    });
  }

  window.updateGraph = updateGraph;
  window.setLayout = setLayout;
  window.focusNode = focusNode;
  window.exportCurrentView = exportCurrentView;
  window.BlueBenchRenderer = {
    updateGraph,
    setLayout,
    focusNode,
    exportCurrentView,
  };

  initializeBridge();
})();
