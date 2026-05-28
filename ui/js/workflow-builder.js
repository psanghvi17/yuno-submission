(function () {
    const config = window.WORKFLOW_BUILDER_CONFIG;
    if (!config) {
        return;
    }

    const agents = config.agents || [];

    function parseGraphJson(value) {
        if (!value) {
            return { nodes: [], edges: [] };
        }
        if (typeof value === "object") {
            return value;
        }
        if (typeof value === "string") {
            return JSON.parse(value);
        }
        return { nodes: [], edges: [] };
    }

    let initialGraph = { nodes: [], edges: [] };
    try {
        initialGraph = parseGraphJson(config.graphJson);
    } catch (e) {
        console.warn("Invalid initial graph JSON", e);
    }

    const container = document.getElementById("drawflow");
    const statusEl = document.getElementById("builder-status");
    const editor = new Drawflow(container);
    editor.reroute = true;
    editor.start();

    function setStatus(message, type) {
        if (!statusEl) {
            return;
        }
        statusEl.textContent = message;
        statusEl.className = `alert alert-${type} py-3 px-4`;
        statusEl.classList.remove("d-none");
    }

    function loadGraph() {
        try {
            const drawflowData = WorkflowGraph.prepareGraphForEditor(initialGraph, agents);
            editor.clear();
            editor.import(drawflowData);
        } catch (err) {
            console.error("Failed to load workflow graph", err);
            setStatus(`Could not load graph: ${err.message}`, "danger");
        }
    }

    function addNode(type) {
        const nodeId = WorkflowGraph.newNodeId();
        const data = { node_id: nodeId, label: "" };
        let inputs = 1;
        let outputs = 1;
        if (type === "condition") {
            data.label = "Condition";
            outputs = 2;
        } else if (type === "end") {
            data.label = "END";
            inputs = 1;
            outputs = 0;
        } else if (type === "channel") {
            data.label = "Channel step";
            data.channel = "telegram";
        } else {
            data.label = "Agent";
            type = "agent";
        }

        const existing = Object.keys(WorkflowGraph.getDrawflowHomeData(editor.export())).length;
        const col = existing % 3;
        const row = Math.floor(existing / 3);
        const pos_x = 80 + col * 220;
        const pos_y = 80 + row * 120;

        editor.addNode(
            type,
            inputs,
            outputs,
            pos_x,
            pos_y,
            type,
            data,
            WorkflowGraph.buildNodeHtml(type, data, agents)
        );
    }

    async function saveGraph() {
        const exportData = WorkflowGraph.collectNodeDataFromDom(editor);
        const simple = WorkflowGraph.drawflowToSimple(exportData);

        setStatus("Saving…", "info");

        try {
            const response = await fetch(`/api/v1/workflows/${config.workflowId}/graph`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({ graph_json: simple }),
            });

            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                const detail = err.detail;
                const message =
                    typeof detail === "object"
                        ? Object.values(detail).join("; ")
                        : detail || response.statusText;
                setStatus(`Save failed: ${message}`, "danger");
                return;
            }

            const saved = await response.json();
            initialGraph = saved.graph_json;
            setStatus(`Saved (v${saved.version}, ${saved.agent_links.length} agent links)`, "success");
        } catch (err) {
            setStatus(`Save failed: ${err.message}`, "danger");
        }
    }

    document.getElementById("btn-add-agent")?.addEventListener("click", () => addNode("agent"));
    document.getElementById("btn-add-condition")?.addEventListener("click", () => addNode("condition"));
    document.getElementById("btn-add-end")?.addEventListener("click", () => addNode("end"));
    document.getElementById("btn-add-channel")?.addEventListener("click", () => addNode("channel"));
    document.getElementById("btn-save-graph")?.addEventListener("click", saveGraph);
    document.getElementById("btn-reload-graph")?.addEventListener("click", () => {
        loadGraph();
        setStatus("Graph reloaded from memory", "secondary");
    });

    loadGraph();
})();
