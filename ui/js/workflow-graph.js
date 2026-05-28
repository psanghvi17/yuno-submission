/**
 * Convert between persisted simple {nodes, edges} and Drawflow editor export.
 */
(function (global) {
    const NODE_LAYOUT_X = 80;
    const NODE_LAYOUT_Y = 70;

    function defaultPos(index) {
        const col = index % 4;
        const row = Math.floor(index / 4);
        return {
            pos_x: 60 + col * NODE_LAYOUT_X * 2.2,
            pos_y: 60 + row * NODE_LAYOUT_Y * 2,
        };
    }

    function inputsForType(type) {
        if (type === "end") {
            return {};
        }
        return { input_1: { connections: [] } };
    }

    function outputsForType(type) {
        if (type === "end") {
            return {};
        }
        if (type === "condition") {
            return {
                output_1: { connections: [] },
                output_2: { connections: [] },
            };
        }
        return { output_1: { connections: [] } };
    }

    function outputKeyForWhen(when) {
        if (when === "low") {
            return "output_2";
        }
        return "output_1";
    }

    function whenFromOutputKey(outputKey, sourceType) {
        if (sourceType !== "condition") {
            return undefined;
        }
        if (outputKey === "output_2") {
            return "low";
        }
        if (outputKey === "output_1") {
            return "ok";
        }
        return undefined;
    }

    function resolveAgentId(node, agentsByName) {
        if (node.agent_id != null && node.agent_id !== "") {
            return Number(node.agent_id);
        }
        const name = node.agent_name;
        if (name && agentsByName[name]) {
            return agentsByName[name].id;
        }
        return null;
    }

    function buildNodeHtml(type, data, agents) {
        const label = data.label || "";
        const nodeId = data.node_id || "";
        if (type === "agent") {
            const options = (agents || [])
                .map(
                    (a) =>
                        `<option value="${a.id}"${
                            String(data.agent_id) === String(a.id) ? " selected" : ""
                        }>${escapeHtml(a.name)}</option>`
                )
                .join("");
            return (
                `<div class="wf-node-body" data-wf-type="agent">` +
                `<div class="wf-node-title">Agent</div>` +
                `<input type="hidden" class="wf-node-id" value="${escapeHtml(nodeId)}" />` +
                `<label class="form-label">Label</label>` +
                `<input type="text" class="form-control wf-node-label" value="${escapeHtml(label)}" />` +
                `<label class="form-label mt-2">Agent</label>` +
                `<select class="form-select wf-node-agent"><option value="">— Select —</option>${options}</select>` +
                `</div>`
            );
        }
        if (type === "condition") {
            return (
                `<div class="wf-node-body" data-wf-type="condition">` +
                `<div class="wf-node-title">Condition</div>` +
                `<input type="hidden" class="wf-node-id" value="${escapeHtml(nodeId)}" />` +
                `<label class="form-label">Label</label>` +
                `<input type="text" class="form-control wf-node-label" value="${escapeHtml(label)}" />` +
                `<label class="form-label mt-2">Field</label>` +
                `<input type="text" class="form-control wf-node-field" value="${escapeHtml(data.field || "")}" />` +
                `<label class="form-label mt-2">Threshold</label>` +
                `<input type="number" step="0.01" class="form-control wf-node-threshold" value="${escapeHtml(String(data.threshold ?? ""))}" />` +
                `<p class="text-muted fs-8 mt-2 mb-0">Top out = OK · Bottom out = Low</p>` +
                `</div>`
            );
        }
        if (type === "channel") {
            return (
                `<div class="wf-node-body" data-wf-type="channel">` +
                `<div class="wf-node-title">Channel</div>` +
                `<input type="hidden" class="wf-node-id" value="${escapeHtml(nodeId)}" />` +
                `<label class="form-label">Label</label>` +
                `<input type="text" class="form-control wf-node-label" value="${escapeHtml(label)}" />` +
                `<label class="form-label mt-2">Channel</label>` +
                `<input type="text" class="form-control wf-node-channel" value="${escapeHtml(data.channel || "telegram")}" />` +
                `</div>`
            );
        }
        return (
            `<div class="wf-node-body" data-wf-type="end">` +
            `<div class="wf-node-title">End</div>` +
            `<input type="hidden" class="wf-node-id" value="${escapeHtml(nodeId)}" />` +
            `<label class="form-label">Label</label>` +
            `<input type="text" class="form-control wf-node-label" value="${escapeHtml(label || "END")}" />` +
            `</div>`
        );
    }

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function readNodeDataFromElement(nodeEl) {
        const body = nodeEl.querySelector(".wf-node-body");
        if (!body) {
            return {};
        }
        const type = body.getAttribute("data-wf-type") || "agent";
        const data = {
            node_id: body.querySelector(".wf-node-id")?.value?.trim() || "",
            label: body.querySelector(".wf-node-label")?.value?.trim() || "",
        };
        if (type === "agent") {
            const agentVal = body.querySelector(".wf-node-agent")?.value;
            if (agentVal) {
                data.agent_id = Number(agentVal);
            }
        } else if (type === "condition") {
            data.field = body.querySelector(".wf-node-field")?.value?.trim() || "";
            const th = body.querySelector(".wf-node-threshold")?.value;
            if (th !== "" && th != null) {
                data.threshold = Number(th);
            }
        } else if (type === "channel") {
            data.channel = body.querySelector(".wf-node-channel")?.value?.trim() || "telegram";
        }
        return { type, data };
    }

    function normalizeDrawflowExport(exportData) {
        const cloned = JSON.parse(JSON.stringify(exportData));
        const modules = cloned.drawflow;
        if (!modules || typeof modules !== "object") {
            return cloned;
        }
        Object.keys(modules).forEach((moduleName) => {
            const data = modules[moduleName]?.data;
            if (!data) {
                return;
            }
            Object.keys(data).forEach((key) => {
                const node = data[key];
                if (node && typeof node.html === "string") {
                    node.typenode = false;
                }
            });
        });
        return cloned;
    }

    function prepareGraphForEditor(graph, agents) {
        if (graph?.drawflow) {
            return normalizeDrawflowExport(graph);
        }
        return simpleToDrawflow(graph, agents);
    }

    function simpleToDrawflow(graph, agents) {
        const nodes = Array.isArray(graph?.nodes) ? graph.nodes : [];
        const edges = Array.isArray(graph?.edges) ? graph.edges : [];
        const agentsByName = {};
        (agents || []).forEach((a) => {
            agentsByName[a.name] = a;
        });

        const data = {};
        const idMap = {};

        nodes.forEach((node, index) => {
            const simpleId = String(node.id || `node_${index + 1}`);
            const dfId = index + 1;
            idMap[simpleId] = dfId;
            const type = node.type || "agent";
            const pos = defaultPos(index);
            const nodeData = {
                node_id: simpleId,
                label: node.label || "",
                field: node.field || "",
                threshold: node.threshold,
                channel: node.channel || "telegram",
            };
            const agentId = resolveAgentId(node, agentsByName);
            if (agentId != null) {
                nodeData.agent_id = agentId;
            }
            data[dfId] = {
                id: dfId,
                name: type,
                data: nodeData,
                class: type,
                html: buildNodeHtml(type, nodeData, agents),
                typenode: false,
                inputs: inputsForType(type),
                outputs: outputsForType(type),
                pos_x: node.pos_x ?? pos.pos_x,
                pos_y: node.pos_y ?? pos.pos_y,
            };
        });

        edges.forEach((edge) => {
            const fromId = idMap[edge.from];
            const toId = idMap[edge.to];
            if (!fromId || !toId) {
                return;
            }
            const source = data[fromId];
            if (!source) {
                return;
            }
            const outputKey = outputKeyForWhen(edge.when);
            if (!source.outputs[outputKey]) {
                return;
            }
            source.outputs[outputKey].connections.push({
                node: String(toId),
                output: "input_1",
            });
            const target = data[toId];
            if (target?.inputs?.input_1) {
                target.inputs.input_1.connections.push({
                    node: String(fromId),
                    input: outputKey,
                });
            }
        });

        return { drawflow: { Home: { data } } };
    }

    function getDrawflowHomeData(exportData) {
        if (!exportData || typeof exportData !== "object") {
            return {};
        }
        if (exportData.drawflow?.Home?.data) {
            return exportData.drawflow.Home.data;
        }
        if (exportData.Home?.data) {
            return exportData.Home.data;
        }
        return {};
    }

    function drawflowToSimple(exportData) {
        const home = getDrawflowHomeData(exportData);
        const nodes = [];
        const edges = [];
        const dfIdToSimple = {};

        Object.keys(home).forEach((key) => {
            const dfNode = home[key];
            const dfId = String(dfNode.id ?? key);
            const type = dfNode.name || dfNode.class || "agent";
            const stored = dfNode.data || {};
            const simpleId = stored.node_id || `node_${dfId}`;
            dfIdToSimple[dfId] = simpleId;

            const simpleNode = {
                id: simpleId,
                type,
                label: stored.label || "",
                pos_x: dfNode.pos_x,
                pos_y: dfNode.pos_y,
            };
            if (type === "agent" && stored.agent_id != null && stored.agent_id !== "") {
                simpleNode.agent_id = Number(stored.agent_id);
            }
            if (type === "condition") {
                if (stored.field) {
                    simpleNode.field = stored.field;
                }
                if (stored.threshold != null && stored.threshold !== "") {
                    simpleNode.threshold = Number(stored.threshold);
                }
            }
            if (type === "channel" && stored.channel) {
                simpleNode.channel = stored.channel;
            }
            nodes.push(simpleNode);
        });

        Object.keys(home).forEach((key) => {
            const dfNode = home[key];
            const fromSimple = dfIdToSimple[String(dfNode.id ?? key)];
            const sourceType = dfNode.name || dfNode.class;
            const outputs = dfNode.outputs || {};
            Object.keys(outputs).forEach((outputKey) => {
                const conns = outputs[outputKey].connections || [];
                conns.forEach((conn) => {
                    const toSimple = dfIdToSimple[String(conn.node)];
                    if (!fromSimple || !toSimple) {
                        return;
                    }
                    const edge = { from: fromSimple, to: toSimple };
                    const when = whenFromOutputKey(outputKey, sourceType);
                    if (when) {
                        edge.when = when;
                    }
                    if (conn.max_loops != null) {
                        edge.max_loops = conn.max_loops;
                    }
                    edges.push(edge);
                });
            });
        });

        return { nodes, edges };
    }

    function collectNodeDataFromDom(editor) {
        const exportData = editor.export();
        const home = getDrawflowHomeData(exportData);
        const root =
            editor?.container ||
            editor?.precanvas ||
            document.getElementById("drawflow") ||
            document;
        Object.keys(home).forEach((key) => {
            const dfNode = home[key];
            const nodeId = dfNode.id ?? key;
            const el =
                root.querySelector?.(`#node-${nodeId}`) ||
                document.getElementById(`node-${nodeId}`);
            if (!el) {
                return;
            }
            const { type, data } = readNodeDataFromElement(el);
            dfNode.name = type;
            dfNode.class = type;
            dfNode.data = { ...(dfNode.data || {}), ...data };
        });
        return exportData;
    }

    function newNodeId() {
        return `node_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
    }

    global.WorkflowGraph = {
        simpleToDrawflow,
        drawflowToSimple,
        getDrawflowHomeData,
        normalizeDrawflowExport,
        prepareGraphForEditor,
        buildNodeHtml,
        collectNodeDataFromDom,
        newNodeId,
        readNodeDataFromElement,
    };
})(window);
